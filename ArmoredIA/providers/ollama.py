from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from .base import AIProviderError
from .context import context_text as _context_text
from .transport import bounded_number, close_response, retryable_failure
from ..caption.grounded import caption_prompt_context


class OllamaProvider:
    """Local Ollama adapter implementing the same caption-candidate contract as Gemini."""

    def __init__(self, requester=None):
        self.requester = requester or requests.post
        self.last_attempts: list[dict[str, Any]] = []
        self.last_request_count = 0
        self.last_candidate_count = 0
        self.last_raw_candidates: list[str] = []

    @staticmethod
    def configuration() -> dict[str, str]:
        return {"provider": "ollama", "model": (os.getenv("ARMORED_IA_OLLAMA_MODEL") or "qwen2.5:3b").strip()}

    @staticmethod
    def _extract_raw_candidates(data: dict[str, Any], limit: int) -> list[str]:
        try:
            raw_text = data["response"]
            payload = json.loads(str(raw_text))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError("Ollama não retornou JSON estruturado") from exc

        raw = payload.get("captions") if isinstance(payload, dict) else None
        if not isinstance(raw, list):
            raise AIProviderError("Ollama não retornou a lista de candidatas")

        # Preserve the complete requested batch for auditing. Selection uses
        # distinct candidates below, but duplicates remain visible in evidence.
        candidates: list[str] = []
        cap = max(1, min(limit, 10))
        for entry in raw:
            value = entry.get("text") if isinstance(entry, dict) else entry
            caption = str(value or "").strip()
            if isinstance(entry, dict) and "hashtags" in entry:
                tags = entry["hashtags"]
                if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                    raise AIProviderError("Ollama retornou hashtags sem estrutura válida")
                caption += "\n" + " ".join(tags)
            if caption:
                candidates.append(caption)
            if len(candidates) >= cap:
                break
        if not candidates:
            raise AIProviderError("Ollama retornou zero candidatas não vazias")
        return candidates

    @staticmethod
    def _extract_candidates(data: dict[str, Any], limit: int) -> list[str]:
        raw_candidates = OllamaProvider._extract_raw_candidates(data, limit)
        # The shared CaptionGenerator policy is the sole authority for content
        # validation; exact duplicates do not need repeated evaluation.
        candidates: list[str] = []
        seen: set[str] = set()
        for caption in raw_candidates:
            if caption in seen:
                continue
            seen.add(caption)
            candidates.append(caption)
        return candidates

    def generate_candidates(self, task: str, context: dict[str, Any], limit: int) -> list[str]:
        if task != "caption":
            raise AIProviderError(f"Ollama task não suportada: {task}")

        base_url = (os.getenv("ARMORED_IA_OLLAMA_URL") or "http://localhost:11434").strip().rstrip("/")
        model = self.configuration()["model"]
        if not model:
            raise AIProviderError("ARMORED_IA_OLLAMA_MODEL está vazio")

        prompt_context = caption_prompt_context(context)
        facts = tuple(
            str(value).strip()
            for value in prompt_context.get("__vision_confirmed_facts", ())
            if str(value).strip()
        )
        candidate_count = min(max(1, limit), 10)
        caption_pattern = (
            r"^[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*"
            r"(?: [A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*){1,4}[.]?$"
        )

        # The Vision title is the primary source when the affiliate endpoint
        # returns no long description or structured attributes. Keep it explicit
        # in the single request; the shared Policy filters listing fragments,
        # sales noise, technical details and unsupported claims afterward.
        semantic_record = {
            "titulo_do_produto_vision": str(prompt_context.get("productName") or "").strip(),
            "categoria": str(prompt_context.get("__vision_category") or "").strip(),
            "fatos_confirmados": list(facts),
        }
        prompt_parts = [
            "Crie legendas curtas em português brasileiro que soem como comentários naturais, espontâneos e simples.",
            "Use o título da Vision como principal fonte para entender o produto e seus detalhes. Os fatos confirmados ajudam a conferir a leitura; não exija que exista um benefício explícito.",
            "Pode mencionar o nome comum do produto se isso soar natural, mas não copie o título, não repita uma sequência de palavras do anúncio e não use marca, loja ou modelo.",
            "Escolha um aspecto concreto que esteja no título ou nos fatos da Vision e transforme-o em uma frase curta. Não faça lista de palavras nem descrição de catálogo.",
            "Não invente benefício, material, cor, ocasião, desempenho ou qualidade. Ignore superlativos, promessas, termos de venda, códigos, medidas e números do título.",
            "Preserve a relação entre os detalhes: não transfira uma qualidade de um atributo para outro e não una informações sem relação clara.",
            "Sem anúncio, elogio de venda, promessa ou chamada para compra. Varie as construções; não force uma abertura nem repita o mesmo começo.",
            "Cada frase principal deve ter de 2 a 5 palavras e parecer completa; não inclua coração, hashtag, rótulo ou explicação.",
            f"Retorne exatamente {candidate_count} opções distintas, ordenadas da mais natural e específica para a menos forte. Se o título só sustentar poucas ideias, use variações naturais sem acrescentar fatos.",
            "Contexto e fatos da Vision em JSON: " + json.dumps(semantic_record, ensure_ascii=False, separators=(",", ":")),
            f"Responda somente com um objeto JSON com a chave 'captions' e exatamente {candidate_count} frases.",
        ]
        policy_feedback = context.get("__policy_retry_feedback")
        if isinstance(policy_feedback, list) and policy_feedback:
            prompt_parts.append(
                "A Policy recusou a tentativa anterior por: "
                + "; ".join(str(value) for value in policy_feedback[:3])
                + ". Corrija sem acrescentar fatos."
            )
        previous_candidates = context.get("__policy_retry_previous_candidates")
        if isinstance(previous_candidates, list) and previous_candidates:
            rejected = []
            for value in previous_candidates[-10:]:
                text = re.sub(r"#[\wÀ-ÿ]+", "", str(value), flags=re.UNICODE)
                text = text.replace("🧡", " ").strip(" \t\r\n.,;:!?")
                if text and text not in rejected:
                    rejected.append(text[:100])
            if rejected:
                prompt_parts.append(
                    "Não repita estas formulações recusadas nem apenas troque uma palavra: "
                    + " | ".join(rejected)
                    + ". Crie outra construção natural usando somente o detalhe confirmado."
                )
        previous_caption = str(context.get("__previous_caption_to_avoid") or "").strip()
        if previous_caption:
            prompt_parts.append(
                "Legenda anterior, fornecida apenas para evitar repetição e nunca como evidência do produto: "
                + json.dumps(previous_caption, ensure_ascii=False)
                + ". Evite copiar a frase inteira, mas pode expressar naturalmente o mesmo fato confirmado "
                "se ele continuar sendo o detalhe mais forte. Não invente outra característica só para variar "
                "e não use texto vago, negação ou preenchimento."
            )
        prompt = " ".join(prompt_parts)
        output_format = {
            "type": "object",
            "properties": {
                "captions": {
                    "type": "array",
                    "minItems": candidate_count,
                    "maxItems": candidate_count,
                    "items": {
                        "type": "string",
                        "minLength": 8,
                        "maxLength": 100,
                        # Enforce the Policy's 2–5-word surface in Ollama's
                        # constrained decoder; small CPU models often ignore
                        # word-count instructions in prose.
                        "pattern": caption_pattern,
                    },
                }
            },
            "required": ["captions"],
            "additionalProperties": False,
        }
        # Local CPU inference can be slow. Keep the transport retry budget to
        # one request by default; the durable caption-recovery ledger may
        # authorize one later retry without making a single run hang for
        # several provider timeouts. The shared setting remains a compatible
        # explicit override for existing installations.
        try:
            attempts_default = float(os.getenv("ARMORED_IA_MAX_ATTEMPTS", "1"))
        except ValueError as exc:
            raise AIProviderError("Configuração IA inválida: ARMORED_IA_MAX_ATTEMPTS") from exc
        attempts_value = bounded_number(
            "ARMORED_IA_OLLAMA_MAX_ATTEMPTS",
            attempts_default,
            1,
            10,
        )
        if not attempts_value.is_integer():
            raise AIProviderError("Configuração IA inválida: ARMORED_IA_MAX_ATTEMPTS")
        attempts = int(attempts_value)
        retry_delay = bounded_number("ARMORED_IA_RETRY_DELAY", 2, 0, 60)
        timeout = bounded_number("ARMORED_IA_OLLAMA_TIMEOUT", 90, 1, 600)
        max_tokens = bounded_number("ARMORED_IA_OLLAMA_MAX_TOKENS", 512, 64, 4096)
        temperature = bounded_number("ARMORED_IA_OLLAMA_TEMPERATURE", 0.1, 0, 2)
        repeat_penalty = bounded_number(
            "ARMORED_IA_OLLAMA_REPEAT_PENALTY", 1.15, 1, 2,
        )
        if not max_tokens.is_integer():
            raise AIProviderError("ARMORED_IA_OLLAMA_MAX_TOKENS deve ser inteiro")
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": output_format,
            "options": {
                "temperature": temperature,
                "repeat_penalty": repeat_penalty,
                "num_predict": int(max_tokens),
            },
        }
        think = os.getenv("ARMORED_IA_OLLAMA_THINK")
        if think is not None:
            if think.strip().casefold() not in {"0", "1", "true", "false"}:
                raise AIProviderError("ARMORED_IA_OLLAMA_THINK deve ser 0, 1, true ou false")
            # Opt-in only. Configure values supported by the selected model's
            # /api/show response; preserve its default when this is unset.
            payload["think"] = think.strip().casefold() in {"1", "true"}

        self.last_attempts = []
        self.last_request_count = 0
        self.last_candidate_count = 0
        self.last_raw_candidates = []
        format_retries = bounded_number("ARMORED_IA_OLLAMA_FORMAT_RETRIES", 1, 0, 2)
        if not format_retries.is_integer():
            raise AIProviderError("ARMORED_IA_OLLAMA_FORMAT_RETRIES deve ser inteiro")
        format_retry_count = 0
        transport_attempt = 0
        while True:
            transport_attempt += 1
            response = None
            try:
                self.last_request_count += 1
                response = self.requester(
                    f"{base_url}/api/generate",
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                try:
                    payload_data = response.json()
                    if str(payload_data.get("done_reason") or "").casefold() == "length":
                        raise AIProviderError(
                            "Ollama truncou a resposta estruturada; reduza candidatas ou aumente o limite de tokens",
                            category="MALFORMED_RESPONSE",
                        )
                    self.last_raw_candidates = self._extract_raw_candidates(
                        payload_data, min(max(1, limit), 10),
                    )
                    candidates = list(dict.fromkeys(self.last_raw_candidates))
                    self.last_candidate_count = len(candidates)
                    self.last_attempts.append({
                        "attempt": transport_attempt,
                        "format_round": format_retry_count + 1,
                        "status": "SUCCESS",
                        "http_status": getattr(response, "status_code", 200),
                    })
                    return candidates
                except ValueError as exc:
                    raise AIProviderError("Ollama não retornou JSON estruturado") from exc
            except requests.RequestException as exc:
                if response is None:
                    response = getattr(exc, "response", None)
                status = getattr(response, "status_code", None)
                category = (
                    "AUTHENTICATION_OR_PERMISSION" if status in {401, 403}
                    else "RATE_LIMITED" if status == 429
                    else "TRANSIENT_UNAVAILABLE" if retryable_failure(exc)
                    else "REQUEST_REJECTED"
                )
                if retryable_failure(exc) and transport_attempt < attempts:
                    self.last_attempts.append({
                        "attempt": transport_attempt,
                        "format_round": format_retry_count + 1,
                        "status": category,
                        "http_status": status,
                    })
                    close_response(response)
                    response = None
                    time.sleep(retry_delay)
                    continue
                self.last_attempts.append({
                    "attempt": transport_attempt,
                    "format_round": format_retry_count + 1,
                    "status": category,
                    "http_status": status,
                })
                raise AIProviderError(
                    f"Ollama indisponível após {transport_attempt} tentativa(s): "
                    + (f"HTTP {status}" if status is not None else type(exc).__name__),
                    category=category,
                    status_code=status,
                ) from None
            except AIProviderError as exc:
                if not getattr(exc, "category", None) or exc.category == "PROVIDER_ERROR":
                    exc.category = "MALFORMED_RESPONSE"
                self.last_attempts.append({
                    "attempt": transport_attempt,
                    "format_round": format_retry_count + 1,
                    "status": exc.category,
                    "http_status": getattr(response, "status_code", None),
                })
                if exc.category == "MALFORMED_RESPONSE" and format_retry_count < int(format_retries):
                    format_retry_count += 1
                    payload["prompt"] = (
                        prompt
                        + f"\n\nCORREÇÃO DE FORMATO: {exc}. Responda somente com um objeto JSON completo que siga exatamente o formato solicitado; "
                        "não inclua raciocínio, markdown ou texto antes/depois. Retorne pelo menos uma e no máximo a quantidade pedida de opções distintas, somente com o texto principal, sem emoji nem hashtags."
                    )
                    transport_attempt = 0
                    close_response(response)
                    response = None
                    continue
                raise
            finally:
                close_response(response)

        raise AIProviderError("Ollama indisponível após todas as tentativas")
