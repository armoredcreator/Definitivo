from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, replace
from typing import Any

from ..providers.base import AIProvider, AIProviderError
from .grounded import (
    compose_safe_caption_candidates,
    salvage_confirmed_fact_prefix,
)
from .selector import (
    CaptionCandidateEvaluation,
    CaptionGenerationError,
    CaptionSelection,
    CaptionSelector,
)


@dataclass(frozen=True)
class CaptionGenerationResult:
    caption: str
    selection: CaptionSelection
    evaluations: tuple[CaptionCandidateEvaluation, ...]
    batch_id: str
    provider_requests: int = 0
    feedback_rounds: tuple[tuple[str, ...], ...] = ()
    provider_attempts: tuple[dict[str, Any], ...] = ()
    provider_candidate_batches: tuple[tuple[str, ...], ...] = ()


class CaptionGenerator:
    """Generate grounded captions locally; providers are an explicit opt-in."""

    def __init__(self, provider: AIProvider | None = None, selector: CaptionSelector | None = None):
        # Normal START runs are model-free. A provider is created only when a
        # caller explicitly injects one or requests force_provider=True.
        self.provider = provider
        self.selector = selector or CaptionSelector()

    def generate_with_evidence(
        self,
        product_context: dict[str, Any],
        *,
        force_provider: bool = False,
        preserve_previous_caption: bool = True,
    ) -> CaptionGenerationResult:
        if os.getenv("ARMORED_IA_CAPTION_ENABLED", "1") != "1":
            raise CaptionGenerationError("gerador de legenda desativado")

        provider = self.provider
        if force_provider and provider is None:
            raise CaptionGenerationError(
                "a geração operacional de legendas é local; não há provedor externo configurado",
            )

        provider_configuration = getattr(provider, "configuration", None)
        provider_name = ""
        if callable(provider_configuration):
            try:
                provider_name = str((provider_configuration() or {}).get("provider") or "").casefold()
            except Exception:
                provider_name = ""

        batch_id = uuid.uuid4().hex
        all_evaluations: list[CaptionCandidateEvaluation] = []
        feedback: tuple[str, ...] = ()
        feedback_rounds: list[tuple[str, ...]] = []
        provider_attempts: list[dict[str, Any]] = []
        provider_candidate_batches: list[tuple[str, ...]] = []
        previous_candidates: list[str] = []
        provider_requests = 0
        last_error: CaptionGenerationError | None = None
        # Normal generation is local-only. The optional provider path is
        # reserved for callers that explicitly inject/force a provider.
        if not force_provider:
            grounded = self._safe_fallback_result(
                product_context,
                batch_id=batch_id,
                evaluations=all_evaluations,
                provider_requests=0,
                feedback_rounds=feedback_rounds,
                provider_attempts=provider_attempts,
                provider_candidate_batches=tuple(provider_candidate_batches),
                preserve_previous_caption=preserve_previous_caption,
                allow_neutral_fallback=True,
            )
            if grounded is not None:
                return grounded
            raise CaptionGenerationError(
                "não foi possível compor uma legenda local a partir do contexto Vision",
                batch_id=batch_id,
                evaluations=tuple(all_evaluations),
                provider_requests=0,
            )

        if provider is None:
            raise CaptionGenerationError(
                "nenhum provedor explícito foi configurado para esta geração",
                batch_id=batch_id,
            )

        candidate_setting = (
            "ARMORED_IA_OLLAMA_MAX_CANDIDATES"
            if provider_name == "ollama"
            else "ARMORED_IA_MAX_CANDIDATES"
        )
        default_candidate_limit = "10" if provider_name == "ollama" else "3"
        model_limit = max(1, int(os.getenv(candidate_setting, default_candidate_limit)))
        candidate_limit = min(model_limit, 10)
        try:
            policy_retries = int(os.getenv("ARMORED_IA_POLICY_RETRIES", "0"))
        except ValueError as exc:
            raise CaptionGenerationError("ARMORED_IA_POLICY_RETRIES deve ser inteiro entre 0 e 2") from exc
        if policy_retries < 0 or policy_retries > 2:
            raise CaptionGenerationError("ARMORED_IA_POLICY_RETRIES deve ser inteiro entre 0 e 2")

        for attempt in range(policy_retries + 1):
            request_context = dict(product_context)
            if feedback:
                request_context["__policy_retry_feedback"] = list(feedback)
                request_context["__policy_retry_previous_candidates"] = list(previous_candidates[-10:])
            try:
                candidates = provider.generate_candidates(
                    "caption", request_context, candidate_limit,
                )
            except AIProviderError as exc:
                attempts = [
                    {"policy_round": attempt + 1, **receipt}
                    for receipt in (getattr(provider, "last_attempts", ()) or ())
                    if isinstance(receipt, dict)
                ]
                exc.provider_requests = provider_requests + 1
                exc.request_count = max(0, int(getattr(provider, "last_request_count", 0) or 0))
                exc.feedback_rounds = tuple(feedback_rounds)
                exc.provider_attempts = tuple((*provider_attempts, *attempts))
                fallback = self._safe_fallback_result(
                    product_context,
                    batch_id=batch_id,
                    evaluations=all_evaluations,
                    provider_requests=provider_requests + 1,
                    feedback_rounds=feedback_rounds,
                    provider_attempts=(*provider_attempts, *attempts),
                    provider_candidate_batches=tuple(provider_candidate_batches),
                    preserve_previous_caption=preserve_previous_caption,
                )
                if fallback is not None:
                    return fallback
                raise
            provider_requests += 1
            raw_candidates = getattr(provider, "last_raw_candidates", None)
            batch_candidates = raw_candidates if raw_candidates is not None else candidates
            provider_candidate_batches.append(tuple(str(value) for value in batch_candidates))
            for receipt in getattr(provider, "last_attempts", ()) or ():
                if isinstance(receipt, dict):
                    provider_attempts.append({"policy_round": attempt + 1, **receipt})
            evaluations = self.selector.evaluate(
                candidates,
                product_name=str(product_context.get("productName") or ""),
                product_context=product_context,
            )
            offset = len(all_evaluations)
            indexed = tuple(
                replace(evaluation, index=offset + evaluation.index)
                for evaluation in evaluations
            )
            try:
                selection, marked = self.selector.choose(
                    evaluations,
                )
            except CaptionGenerationError as exc:
                all_evaluations.extend(indexed)
                last_error = exc

                # Small local models often append unsupported benefits to an
                # otherwise grounded phrase. Before paying for another slow
                # inference, keep only a leading Vision-confirmed fact when
                # every removed word is outside that fact.
                salvage_sources: list[tuple[str, str]] = []
                seen_salvage: set[str] = set()
                fallback_candidates = compose_safe_caption_candidates(product_context, limit=1)
                fallback_tags = (
                    re.findall(r"#[\wÀ-ÿ]+", fallback_candidates[0], flags=re.UNICODE)
                    if fallback_candidates else []
                )
                for candidate in candidates[:10]:
                    raw_candidate = str(candidate or "").strip()
                    salvaged = salvage_confirmed_fact_prefix(raw_candidate, product_context)
                    if not salvaged or salvaged.casefold() == raw_candidate.casefold():
                        continue
                    if fallback_tags and "#" not in salvaged:
                        salvaged += "\n" + " ".join(fallback_tags)
                    folded_salvage = salvaged.casefold()
                    if folded_salvage in seen_salvage:
                        continue
                    seen_salvage.add(folded_salvage)
                    salvage_sources.append((raw_candidate, salvaged))

                non_salvageable_reasons = (
                    "fragmento de título",
                    "sequência de palavras-chave",
                    "expressão distintiva",
                    "categoria do produto",
                )
                title_copy_rejected = any(
                    any(marker in str(evaluation.rejection_reason or "") for marker in non_salvageable_reasons)
                    for evaluation in evaluations
                )
                if salvage_sources and not title_copy_rejected:
                    salvage_evaluations = self.selector.evaluate(
                        [caption for _source, caption in salvage_sources],
                        product_name=str(product_context.get("productName") or ""),
                        product_context=product_context,
                    )
                    try:
                        salvage_selection, salvage_marked = self.selector.choose(
                            salvage_evaluations,
                        )
                    except CaptionGenerationError:
                        pass
                    else:
                        salvage_offset = len(all_evaluations)
                        absolute_salvaged = tuple(
                            replace(
                                evaluation,
                                index=salvage_offset + evaluation.index,
                                raw_caption=salvage_sources[evaluation.index - 1][0],
                                selected=(evaluation.index == salvage_selection.index),
                                normalization_corrections=tuple(dict.fromkeys((
                                    *evaluation.normalization_corrections,
                                    "unsupported_model_tail_trimmed_to_vision_fact",
                                ))),
                            )
                            for evaluation in salvage_marked
                        )
                        all_evaluations.extend(absolute_salvaged)
                        selected_index = salvage_offset + salvage_selection.index
                        retained = self._previous_caption_result(
                            product_context,
                            candidate_score=salvage_selection.score,
                            batch_id=batch_id,
                            evaluations=tuple(all_evaluations),
                            provider_requests=provider_requests,
                            feedback_rounds=feedback_rounds,
                            provider_attempts=provider_attempts,
                            provider_candidate_batches=tuple(provider_candidate_batches),
                        ) if preserve_previous_caption else None
                        if retained is not None:
                            return retained
                        return CaptionGenerationResult(
                            caption=salvage_selection.caption,
                            selection=replace(salvage_selection, index=selected_index),
                            evaluations=tuple(all_evaluations),
                            batch_id=batch_id,
                            provider_requests=provider_requests,
                            feedback_rounds=tuple(feedback_rounds),
                            provider_attempts=tuple(provider_attempts),
                            provider_candidate_batches=tuple(provider_candidate_batches),
                        )

                if attempt >= policy_retries:
                    fallback = self._safe_fallback_result(
                        product_context,
                        batch_id=batch_id,
                        evaluations=all_evaluations,
                        provider_requests=provider_requests,
                        feedback_rounds=feedback_rounds,
                        provider_attempts=provider_attempts,
                        provider_candidate_batches=tuple(provider_candidate_batches),
                        preserve_previous_caption=preserve_previous_caption,
                    )
                    if fallback is not None:
                        return fallback
                    raise CaptionGenerationError(
                        str(exc), batch_id=batch_id, evaluations=tuple(all_evaluations),
                        provider_requests=provider_requests,
                        feedback_rounds=tuple(feedback_rounds),
                        provider_attempts=tuple(provider_attempts),
                        provider_candidate_batches=tuple(provider_candidate_batches),
                    ) from exc
                rejection_reasons = tuple(dict.fromkeys(
                    evaluation.rejection_reason
                    for evaluation in evaluations
                    if evaluation.rejection_reason
                ))[:4]
                actionable = self._feedback_guidance(
                    rejection_reasons,
                    product_context=product_context,
                )
                feedback = rejection_reasons
                feedback = tuple(dict.fromkeys((*feedback, *actionable)))[:8]
                previous_candidates.extend(
                    evaluation.raw_caption or evaluation.caption
                    for evaluation in evaluations
                    if (evaluation.raw_caption or evaluation.caption).strip()
                )
                feedback_rounds.append(feedback)
                continue

            selected_index = offset + selection.index
            all_evaluations.extend(
                replace(
                    evaluation,
                    index=offset + evaluation.index,
                    selected=(offset + evaluation.index) == selected_index,
                )
                for evaluation in marked
            )
            retained = self._previous_caption_result(
                product_context,
                candidate_score=selection.score,
                batch_id=batch_id,
                evaluations=tuple(all_evaluations),
                provider_requests=provider_requests,
                feedback_rounds=feedback_rounds,
                provider_attempts=provider_attempts,
                provider_candidate_batches=tuple(provider_candidate_batches),
            ) if preserve_previous_caption else None
            if retained is not None:
                return retained
            return CaptionGenerationResult(
                caption=selection.caption,
                selection=replace(selection, index=selected_index),
                evaluations=tuple(all_evaluations),
                batch_id=batch_id,
                provider_requests=provider_requests,
                feedback_rounds=tuple(feedback_rounds),
                provider_attempts=tuple(provider_attempts),
                provider_candidate_batches=tuple(provider_candidate_batches),
            )

        # The loop either returned a valid selection or raised with its evidence.
        raise last_error or CaptionGenerationError("caption-policy-retry-exhausted", batch_id=batch_id)

    def _previous_caption_result(
        self,
        product_context: dict[str, Any],
        *,
        candidate_score: float,
        batch_id: str,
        evaluations: tuple[CaptionCandidateEvaluation, ...],
        provider_requests: int,
        feedback_rounds: list[tuple[str, ...]] | tuple[tuple[str, ...], ...],
        provider_attempts: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        provider_candidate_batches: tuple[tuple[str, ...], ...],
    ) -> CaptionGenerationResult | None:
        """Keep a valid published caption when a new selection scores no better."""
        previous_caption = str(
            product_context.get("__previous_caption_to_avoid") or ""
        ).strip()
        if not previous_caption:
            return None
        previous_context = dict(product_context)
        previous_context.pop("__previous_caption_to_avoid", None)
        previous_evaluations = self.selector.evaluate(
            [previous_caption],
            product_name=str(product_context.get("productName") or ""),
            product_context=previous_context,
        )
        try:
            previous_selection, previous_marked = self.selector.choose(
                previous_evaluations,
            )
        except CaptionGenerationError:
            return None
        if previous_selection.score < candidate_score:
            return None

        offset = len(evaluations)
        selected_index = offset + previous_selection.index
        retained = tuple(
            replace(
                evaluation,
                index=offset + evaluation.index,
                selected=(offset + evaluation.index) == selected_index,
                normalization_corrections=tuple(dict.fromkeys((
                    *evaluation.normalization_corrections,
                    "previous_policy_valid_caption_retained_not_outscored",
                ))),
            )
            for evaluation in previous_marked
        )
        return CaptionGenerationResult(
            caption=previous_selection.caption,
            selection=replace(previous_selection, index=selected_index),
            evaluations=tuple((
                *(replace(evaluation, selected=False) for evaluation in evaluations),
                *retained,
            )),
            batch_id=batch_id,
            provider_requests=provider_requests,
            feedback_rounds=tuple(feedback_rounds),
            provider_attempts=tuple(provider_attempts),
            provider_candidate_batches=provider_candidate_batches,
        )

    def _safe_fallback_result(
        self,
        product_context: dict[str, Any],
        *,
        batch_id: str,
        evaluations: list[CaptionCandidateEvaluation],
        provider_requests: int,
        feedback_rounds: list[tuple[str, ...]],
        provider_attempts: list[dict[str, Any]] | tuple[dict[str, Any], ...],
        provider_candidate_batches: tuple[tuple[str, ...], ...],
        preserve_previous_caption: bool = True,
        allow_neutral_fallback: bool = False,
    ) -> CaptionGenerationResult | None:
        captions = compose_safe_caption_candidates(product_context)
        fallback_evaluations: tuple[CaptionCandidateEvaluation, ...] = ()
        if captions:
            fallback_evaluations = self.selector.evaluate(
                list(captions),
                product_name=str(product_context.get("productName") or ""),
                product_context=product_context,
            )

        # If no supported feature can be composed, a neutral category-level
        # caption is still available locally. It makes no claim about product
        # construction, benefits, or performance and avoids a model request.
        if (provider_requests > 0 or allow_neutral_fallback) and not any(
            evaluation.policy_valid for evaluation in fallback_evaluations
        ):
            try:
                from .title_rules import (
                    compose_neutral_caption_fallback,
                )

                neutral = compose_neutral_caption_fallback(product_context)
            except (ImportError, ValueError):
                neutral = None
            if neutral is not None:
                neutral_evaluations = self.selector.evaluate(
                    [neutral.full_caption],
                    product_name=str(product_context.get("productName") or ""),
                    product_context=product_context,
                )
                if any(evaluation.policy_valid for evaluation in neutral_evaluations):
                    captions = (neutral.full_caption,)
                    fallback_evaluations = neutral_evaluations

        if not fallback_evaluations:
            return self._previous_caption_result(
                product_context,
                candidate_score=float("-inf"),
                batch_id=batch_id,
                evaluations=tuple(evaluations),
                provider_requests=provider_requests,
                feedback_rounds=feedback_rounds,
                provider_attempts=provider_attempts,
                provider_candidate_batches=provider_candidate_batches,
            ) if preserve_previous_caption else None
        try:
            from .title_rules import title_rules_enabled

            selection, marked = self.selector.choose(
                fallback_evaluations,
                prefer_first_valid=title_rules_enabled(),
            )
        except CaptionGenerationError:
            return self._previous_caption_result(
                product_context,
                candidate_score=float("-inf"),
                batch_id=batch_id,
                evaluations=tuple(evaluations),
                provider_requests=provider_requests,
                feedback_rounds=feedback_rounds,
                provider_attempts=provider_attempts,
                provider_candidate_batches=provider_candidate_batches,
            ) if preserve_previous_caption else None
        offset = len(evaluations)
        selected_index = offset + selection.index
        absolute_evaluations = tuple(
            replace(
                evaluation,
                index=offset + evaluation.index,
                selected=(offset + evaluation.index) == selected_index,
            )
            for evaluation in marked
        )
        fallback_result = CaptionGenerationResult(
            caption=selection.caption,
            selection=replace(selection, index=selected_index),
            evaluations=tuple((*evaluations, *absolute_evaluations)),
            batch_id=batch_id,
            provider_requests=provider_requests,
            feedback_rounds=tuple(feedback_rounds),
            provider_attempts=tuple(provider_attempts),
            provider_candidate_batches=provider_candidate_batches,
        )
        retained = self._previous_caption_result(
            product_context,
            candidate_score=selection.score,
            batch_id=batch_id,
            evaluations=tuple((*evaluations, *absolute_evaluations)),
            provider_requests=provider_requests,
            feedback_rounds=feedback_rounds,
            provider_attempts=provider_attempts,
            provider_candidate_batches=provider_candidate_batches,
        ) if preserve_previous_caption else None
        return retained or fallback_result

    @staticmethod
    def _feedback_guidance(
        reasons: tuple[str, ...],
        *,
        product_context: dict[str, Any] | None = None,
    ) -> tuple[str, ...]:
        """Turn Policy reasons into concise, actionable model feedback."""
        text = " ".join(reasons).casefold()
        guidance: list[str] = []
        if "palavras" in text:
            guidance.append(
                "Reescreva o texto principal com duas a cinco palavras naturais. "
                "Não repita substantivos nem outras palavras de conteúdo; conectivos podem se repetir quando a gramática exigir."
            )
        if "concordância" in text:
            guidance.append(
                "Faça o adjetivo concordar em gênero e número com o substantivo do produto."
            )
        if "relação pouco natural" in text:
            guidance.append(
                "Reescreva como português brasileiro natural. Para bolsa destinada a computador, "
                "use 'para computador'; 'bolsa de computador' soa como se o computador fosse o material."
            )
        if "expressão vaga" in text:
            guidance.append(
                "Retire o complemento vago e escreva uma observação completa e natural sobre o detalhe confirmado."
            )
        if "coração" in text or "emoji" in text:
            guidance.append(
                "Retorne somente o texto principal, sem emoji; o formatador central aplica 🧡 no início."
            )
        if "marcador de preenchimento" in text or "placeholder" in text:
            guidance.append(
                "Retorne somente o texto principal da legenda, sem variáveis, marcações, emoji ou hashtags."
            )
        if "hashtag" in text:
            guidance.append("Não gere hashtags; o formatador central seleciona apenas hashtags relacionadas ao contexto persistido.")
        if "marca" in text or "modelo" in text:
            guidance.append("Retire marcas e modelos do texto principal e das hashtags.")
        if "fragmento de título" in text:
            guidance.append(
                "Não encurte nem enumere palavras do título. Escolha um único detalhe confirmado e formule-o com construção própria, como comentário natural, sem uma abertura fixa."
            )
        if "medida" in text or "técnica" in text:
            guidance.append("Não use números, unidades, medidas ou especificações técnicas.")
        if "distintiva" in text or "produto" in text:
            guidance.append("Evite repetir sequências do título; expresse uma reação curta sem inventar benefícios.")
        if "identificar a categoria" in text:
            guidance.append("Comente uma característica comprovada; não force o nome do produto na frase.")
        if "substantivo secundário" in text:
            guidance.append("Use substantivo secundário somente com comparação clara, como parece, tipo, como ou lembra.")
        if "vazia" in text or "nenhuma candidata" in text:
            guidance.append("Retorne opções não vazias no formato JSON solicitado.")
        if "sem suporte no contexto vision" in text:
            guidance.append(
                "Remova palavras descritivas ausentes do nome, categoria, uso ou descrição Vision; "
                "não invente atributo, benefício ou cenário."
            )
        if "hashtag" in text:
            guidance.append(
                "Concentre-se na frase principal, sem hashtags; não acrescente tag ao texto principal."
            )
        context = product_context or {}
        has_richer_context = any(
            context.get(key) not in (None, "", [], {})
            for key in (
                "category", "categoryName", "productCategory", "productType",
                "description", "usage", "useCase", "style", "appearance", "attributes",
            )
        )
        if not has_richer_context and any(
            marker in text for marker in ("contexto vision", "hashtag", "suporte")
        ):
            title = str(context.get("productName") or "")
            terms = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ-]*", title)
            stop = {"a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e", "em", "para", "por", "sem", "um", "uma"}
            meaningful = [term for term in terms if term.casefold() not in stop]
            safe_terms = []
            forbidden = {"ph", "voltagem", "medida", "especificacao", "especificações", "ml", "cm", "mm", "kg", "litros", "volts", "watts"}
            for term in meaningful[2:]:
                folded = term.casefold()
                if len(term) < 4:
                    continue
                if folded in forbidden or any(char.isdigit() for char in term):
                    continue
                if term != term.lower() and term != term.capitalize():
                    continue
                if folded not in {value.casefold() for value in safe_terms}:
                    safe_terms.append(term)
            allowed = ", ".join(safe_terms[:12]) if safe_terms else "nenhum termo seguro disponível"
            guidance.append(
                "O contexto Vision contém apenas o nome do produto. Use uma característica "
                "textual comprovada na frase principal. Não invente aparência, benefícios, uso ou cenário. "
                "Se usar outro substantivo de produto citado no título, expresse comparação "
                f"clara. O formatador aplicará o coração e as hashtags. Fatos disponíveis no título: {allowed}."
            )
        return tuple(guidance)

    def generate(self, product_context: dict[str, Any]) -> str:
        return self.generate_with_evidence(product_context).caption
