from __future__ import annotations

import json
import os
from typing import Any

import requests

from ..caption.grounded import extract_vision_caption_fact
from .base import AIProviderError
from .context import context_text
from .gemini import GeminiProvider


class GeminiGroupedProvider(GeminiProvider):
    """Generate caption candidates for several products in one standard API call.

    This uses Gemini's regular ``generateContent`` endpoint with isolated product
    records in one structured prompt. It is distinct from Google's asynchronous
    Batch API, which may not be enabled for every project tier.
    """

    @staticmethod
    def _extract_grouped_candidates(
        data: dict[str, Any],
        expected_ids: tuple[str, ...],
        limit: int,
    ) -> dict[str, list[str]]:
        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            payload = json.loads(str(raw_text))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError("Gemini não retornou JSON estruturado por produto") from exc

        rows = payload.get("products") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise AIProviderError("Gemini não retornou a lista de produtos")

        result: dict[str, list[str]] = {}
        expected = set(expected_ids)
        for row in rows:
            if not isinstance(row, dict):
                continue
            product_id = str(row.get("id") or "").strip()
            if product_id not in expected or product_id in result:
                raise AIProviderError("Gemini retornou identificadores de produto inválidos")
            raw_candidates = row.get("captions")
            if not isinstance(raw_candidates, list):
                raise AIProviderError("Gemini não retornou candidatas para cada produto")
            candidates: list[str] = []
            for raw in raw_candidates:
                value = raw.get("text") if isinstance(raw, dict) else raw
                text = str(value or "").strip()
                if text and text not in candidates:
                    candidates.append(text)
                if len(candidates) >= max(1, min(limit, 10)):
                    break
            result[product_id] = candidates

        if set(result) != expected:
            raise AIProviderError("Gemini omitiu um ou mais produtos do lote")
        if any(not candidates for candidates in result.values()):
            raise AIProviderError("Gemini retornou zero candidatas para um produto")
        return result

    def generate_candidates_for_products(
        self,
        task: str,
        products: dict[str, dict[str, Any]],
        limit: int = 10,
    ) -> dict[str, list[str]]:
        if task != "caption":
            raise AIProviderError(f"Gemini task não suportada: {task}")
        if not isinstance(products, dict) or not products or len(products) > 8:
            raise AIProviderError("O lote Gemini deve conter de 1 a 8 produtos")
        try:
            candidate_limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise AIProviderError("Limite de candidatas Gemini inválido") from exc
        if not 1 <= candidate_limit <= 10:
            raise AIProviderError("Limite de candidatas Gemini deve estar entre 1 e 10")

        normalized: dict[str, dict[str, Any]] = {}
        for key, context in products.items():
            product_id = str(key).strip()
            if not product_id or product_id in normalized or not isinstance(context, dict):
                raise AIProviderError("Identificador ou contexto inválido no lote Gemini")
            normalized[product_id] = context

        api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise AIProviderError("GEMINI_API_KEY ausente; ArmoredIA Caption obrigatória")

        attempts_value = self._number("ARMORED_IA_MAX_ATTEMPTS", 5, 1, 10)
        if not attempts_value.is_integer():
            raise AIProviderError("Configuração Gemini inválida: ARMORED_IA_MAX_ATTEMPTS")
        attempts = int(attempts_value)
        retry_delay = self._number("ARMORED_IA_RETRY_DELAY", 2, 0, 60)
        max_delay = self._number("ARMORED_IA_MAX_RETRY_DELAY", 30, 0, 60)
        total_timeout = self._number("ARMORED_IA_TOTAL_TIMEOUT", 180, 1, 600)
        api_timeout = self._number("ARMORED_IA_API_TIMEOUT", 90, 1, 120)
        self.last_attempts = []

        prompt_products = []
        for product_id, context in normalized.items():
            prompt_products.append({
                "id": product_id,
                "vision_context": context_text(context),
                "one_clear_detail": extract_vision_caption_fact(context),
            })

        prompt = (
            "Você escreve legendas editoriais curtas em português brasileiro. Para cada item, gere opções naturais, "
            "específicas e não comerciais, usando somente fatos que estejam claramente escritos no contexto Vision. "
            "O campo one_clear_detail é um atalho para um detalhe confirmado, não uma licença para inventar. Cada opção "
            "deve comentar um único detalhe, sem repetir o título completo, marca, modelo, número ou medida. Não invente "
            "benefício, aparência, uso, sensação ou cenário; não use chamada de compra, promoção, elogio genérico ou frase "
            "de catálogo. A frase principal deve ter de 2 a 8 palavras, começar com 🧡 e terminar com uma ou duas hashtags "
            "comprovadas pelo contexto. Deixe a identificação da categoria nas hashtags, sem repetir o nome do produto no "
            "corpo. Varie a construção naturalmente; não use a mesma abertura em todas as opções nem acrescente informação "
            "para forçar variedade. Se o contexto não sustentar uma afirmação, não a use. Não transfira fatos entre itens. "
            "Retorne exclusivamente JSON no formato "
            "{\"products\":[{\"id\":\"id recebido\",\"captions\":[\"opções\"]}]}.\n"
            "REGISTROS VISION:\n"
            + json.dumps(prompt_products, ensure_ascii=False)
        )
        schema = {
            "type": "OBJECT",
            "properties": {
                "products": {
                    "type": "ARRAY",
                    "minItems": len(normalized),
                    "maxItems": len(normalized),
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "id": {"type": "STRING"},
                            "captions": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"},
                                "minItems": candidate_limit,
                                "maxItems": candidate_limit,
                            },
                        },
                        "required": ["id", "captions"],
                    },
                }
            },
            "required": ["products"],
        }
        request_body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": min(8192, max(1200, len(normalized) * candidate_limit * 45)),
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }

        model = self.configuration()["model"]
        deadline = self.clock() + total_timeout
        for attempt in range(1, attempts + 1):
            response = None
            retryable = False
            delay = None
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise self._failure(attempt - 1, "RETRY_BUDGET_EXHAUSTED")
            try:
                response = self.requester(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=request_body,
                    timeout=min(api_timeout, remaining),
                )
                response.raise_for_status()
                try:
                    candidates = self._extract_grouped_candidates(
                        response.json(), tuple(normalized), candidate_limit,
                    )
                except (ValueError, TypeError) as exc:
                    raise AIProviderError("Gemini não retornou JSON estruturado por produto") from exc
                self.last_attempts.append({
                    "attempt": attempt,
                    "status": "SUCCESS",
                    "http_status": getattr(response, "status_code", 200),
                    "product_count": len(normalized),
                })
                return candidates
            except requests.RequestException as exc:
                if response is None:
                    response = getattr(exc, "response", None)
                status = getattr(response, "status_code", None)
                retryable = self._retryable(exc)
                category = (
                    "AUTHENTICATION_OR_PERMISSION" if status in {401, 403}
                    else "RATE_LIMITED" if status == 429
                    else "TRANSIENT_UNAVAILABLE" if retryable
                    else "REQUEST_REJECTED"
                )
                delay = self._server_delay(response) if retryable else None
                failure = self._failure(attempt, category, status, delay)
            except AIProviderError:
                retryable = True
                failure = self._failure(attempt, "MALFORMED_RESPONSE", getattr(response, "status_code", None))
            finally:
                self._close(response)

            receipt = {"attempt": attempt, "status": failure.category, "http_status": failure.status_code}
            self.last_attempts.append(receipt)
            if not retryable or attempt >= attempts:
                raise failure
            if delay is None:
                delay = min(max_delay, retry_delay * (2 ** (attempt - 1)))
            if delay > max_delay or delay >= deadline - self.clock():
                receipt["retry_stopped"] = "SERVER_DELAY_EXCEEDS_BUDGET"
                raise failure
            receipt["retry_delay"] = delay
            self.sleeper(delay)

        raise AIProviderError("Gemini indisponível após todas as tentativas")
