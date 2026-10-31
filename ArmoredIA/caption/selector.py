from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any

from .policy import (
    CaptionNormalization,
    CaptionPolicyError,
    _MAIN_CONTEXT_ALIASES,
    _context_token_stems,
    PRODUCT_STOP_WORDS,
    _vision_fact_tokens,
    hashtag_context_score,
    normalize_caption,
    validate_caption,
)


class CaptionGenerationError(RuntimeError):
    """Gemini/Policy could not produce a usable caption."""

    def __init__(
        self,
        message: str,
        *,
        batch_id: str | None = None,
        evaluations: tuple["CaptionCandidateEvaluation", ...] = (),
        provider_requests: int = 0,
        feedback_rounds: tuple[tuple[str, ...], ...] = (),
        provider_attempts: tuple[dict[str, Any], ...] = (),
        provider_candidate_batches: tuple[tuple[str, ...], ...] = (),
    ):
        super().__init__(message)
        self.batch_id = batch_id
        self.evaluations = evaluations
        self.provider_requests = int(provider_requests)
        self.feedback_rounds = feedback_rounds
        self.provider_attempts = provider_attempts
        self.provider_candidate_batches = provider_candidate_batches


@dataclass(frozen=True)
class CaptionCandidateEvaluation:
    index: int
    caption: str
    policy_valid: bool
    rejection_reason: str | None
    score: float
    selected: bool = False
    raw_caption: str = ""
    normalization_corrections: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaptionSelection:
    caption: str
    index: int
    score: float


def caption_policy_context_for(
    candidate: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild private evidence only for an exact local title-rule output."""
    source_context = dict(product_context or {})
    if product_name and not source_context.get("productName"):
        source_context["productName"] = product_name
    for key in tuple(source_context):
        if key.startswith("__title_rule_"):
            source_context.pop(key, None)

    from .title_rules import (
        compose_neutral_caption_fallback,
        compose_title_rule_caption,
        title_rules_enabled,
    )

    deterministic_rule = (
        compose_title_rule_caption(source_context)
        if title_rules_enabled() else None
    )
    neutral_fallback = compose_neutral_caption_fallback(source_context)
    raw = str(candidate or "")
    is_exact_rule = bool(deterministic_rule and raw == deterministic_rule.full_caption)
    is_neutral_fallback = bool(neutral_fallback and raw == neutral_fallback.full_caption)
    if not (is_exact_rule or is_neutral_fallback):
        return source_context

    trusted_rule = deterministic_rule if is_exact_rule else neutral_fallback
    candidate_context = dict(source_context)
    candidate_context["__title_rule_caption_main"] = trusted_rule.caption
    candidate_context["__title_rule_category"] = trusted_rule.category
    candidate_context["__title_rule_hashtag"] = trusted_rule.hashtag
    candidate_context["__title_rule_facts"] = list(trusted_rule.evidence)
    if is_neutral_fallback:
        candidate_context["__title_rule_neutral_fallback"] = True
    return candidate_context


def _context_tokens(product_context: dict[str, Any] | None) -> set[str]:
    if not product_context:
        return set()
    ignored = {
        "itemId", "shopId", "shopName",
        "priceMin", "priceMax", "sales", "ratingStar",
        "brand", "brandName", "model", "modelName",
        "imageUrl",
    }
    tokens: set[str] = set()
    excluded = set(PRODUCT_STOP_WORDS)
    for key in ("brand", "brandName", "model", "modelName"):
        value = str(product_context.get(key) or "")
        excluded.update(token.casefold() for token in re.findall(r"[A-Za-zÀ-ÿ0-9]+", value))
    for key, value in product_context.items():
        if key in ignored or value in (None, "", [], {}):
            continue
        folded = unicodedata.normalize("NFKD", str(value).casefold())
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        for token in re.findall(r"[a-z0-9]+", folded):
            if len(token) >= 3 and token not in excluded and not token.isdigit():
                tokens.add(token)
    return tokens


def _caption_score(
    caption: str,
    *,
    product_context: dict[str, Any] | None,
) -> float:
    context = product_context or {}
    provided_facts = context.get("__vision_confirmed_facts")
    if isinstance(provided_facts, (list, tuple, set)):
        facts = tuple(str(value).strip() for value in provided_facts if str(value).strip())
    else:
        # Use the same fact extractor supplied to Ollama. Seller title noise,
        # audience terms and commercial adjectives must not win a caption rank.
        from .grounded import extract_vision_caption_facts

        facts = extract_vision_caption_facts(context)
    vision_tokens = _vision_fact_tokens(
        str(context.get("productName") or ""), context,
    )

    main = re.sub(r"#[\wÀ-ÿ]+", "", caption, flags=re.UNICODE)
    main_tokens = [
        unicodedata.normalize("NFKD", token.casefold())
        for token in re.findall(r"[A-Za-zÀ-ÿ0-9]+", main)
    ]
    main_tokens = ["".join(ch for ch in token if not unicodedata.combining(ch)) for token in main_tokens]
    glue = {
        "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos",
        "e", "em", "na", "nas", "no", "nos", "o", "os", "para", "por",
        "pra", "pro", "um", "uma", "uns", "umas", "que", "se", "sua", "seu",
        "suas", "seus", "voce", "ate", "esse", "essa", "isso", "olha", "olhe",
        "parece", "parecem", "merece", "quentinho", "quentinha", "quentinhos",
        "quentinhas", "detalhe", "destaque", "toque", "clima", "presente",
    }

    def lexical_stems(token: str) -> set[str]:
        # Portuguese adjective/noun gender and number endings commonly differ
        # between a product context and a short caption (prática/prático,
        # organizado/organizada). This affects ranking only; it never rewrites
        # generated text or changes Policy acceptance.
        stems = {token}
        for plural, singular in (
            ("oes", "ao"), ("aes", "ao"), ("ais", "al"),
            ("eis", "el"), ("ois", "ol"),
        ):
            if len(token) > len(plural) + 2 and token.endswith(plural):
                stems.add(token[:-len(plural)] + singular)
        if len(token) >= 5 and token[-1:] in {"a", "o", "e", "s"}:
            stems.add(token[:-1])
        return stems

    score = 0.0
    content_tokens = [token for token in main_tokens if token not in glue]
    normalized_facts = [
        [
            "".join(
                ch for ch in unicodedata.normalize("NFKD", token.casefold())
                if not unicodedata.combining(ch)
            )
            for token in re.findall(r"[A-Za-zÀ-ÿ0-9]+", fact)
            if token.casefold() not in glue and len(token) > 1
        ]
        for fact in facts
    ]
    normalized_facts = [fact for fact in normalized_facts if fact]

    def matches(left: str, right: str) -> bool:
        return bool(
            lexical_stems(left) & lexical_stems(right)
            or (min(len(left), len(right)) >= 5 and (left.startswith(right) or right.startswith(left)))
        )

    supported = {
        token for token in set(content_tokens)
        if token in vision_tokens
        or any(matches(token, fact_token) for fact in normalized_facts for fact_token in fact)
        or bool(
            _MAIN_CONTEXT_ALIASES.get(token, set()) & vision_tokens
        )
        or bool(
            _MAIN_CONTEXT_ALIASES.get(
                token[:-1] if token.endswith("s") else token, set(),
            ) & vision_tokens
        )
    }
    # Reward confirmed product detail coverage, rather than overlap with every
    # noisy word in a marketplace title. Exact two-word facts outrank generic
    # fragments while a natural editorial frame remains eligible.
    score += 1.5 * len(supported)
    fact_scores: list[float] = []
    for fact in normalized_facts:
        matched_count = sum(
            any(matches(token, fact_token) for token in content_tokens)
            for fact_token in set(fact)
        )
        if matched_count:
            coverage = matched_count / len(set(fact))
            fact_scores.append(coverage + (0.65 if coverage == 1 else 0.0))
    if fact_scores:
        score += 1.75 * max(fact_scores)

    # When two captions carry the same fact, prefer a short, complete-sounding
    # observation over a bare catalog label. These small bonuses never rescue
    # a Policy violation or unsupported product claim.
    if len(main_tokens) in {3, 4} and main_tokens[0] in {"olha", "olhe", "parece"}:
        score += 0.4
    if len(main_tokens) == 3 and main_tokens[0] in {"o", "a"}:
        score += 0.2
    # A supported subject-predicate sentence is usually more natural than a
    # bare attribute label ("O visor é digital" vs. "Bebidas quentes").
    if (
        len(main_tokens) >= 4
        and main_tokens[0] in {"o", "a", "um", "uma"}
        and main_tokens[2] in {"e", "tem", "fica", "parece", "esta", "vem"}
    ):
        score += 2.25

    # Prefer a concise phrase; long strings have more room for awkwardness.
    if len(main_tokens) == 2:
        score += 0.1
    elif len(main_tokens) == 5:
        score -= 0.15

    # Penalize repetition inside the tiny caption surface.
    score -= 0.5 * (len(main_tokens) - len(set(main_tokens)))

    # A two-word stack made only of adjectives reads like a catalog fragment
    # ("acolchoado isolado"). Prefer a supported noun phrase when both are
    # available; conjunctions such as "leve e confortável" remain untouched.
    adjective_like_suffixes = ("ado", "ada", "ido", "ida", "oso", "osa", "avel", "ivel")
    has_connector = any(token in {"e", "ou", "com", "para", "de", "do", "da"} for token in main_tokens)
    if (
        len(content_tokens) == 2
        and not has_connector
        and all(token.endswith(adjective_like_suffixes) for token in content_tokens)
    ):
        score -= 1.25
    return round(score, 4)


def _caption_main_key(caption: str) -> str:
    main = re.sub(r"https?://\S+", " ", caption, flags=re.IGNORECASE)
    main = re.sub(r"#[\wÀ-ÿ]+", " ", main, flags=re.UNICODE)
    main = main.replace("🧡", " ")
    folded = unicodedata.normalize("NFKD", main.casefold())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", folded))


def _caption_content_tokens(caption: str) -> tuple[frozenset[str], ...]:
    """Return inflection-aware visible words, preserving the sentence frame."""
    return tuple(
        frozenset(_context_token_stems(token))
        for token in _caption_main_key(caption).split()
    )


def _is_near_duplicate(candidate: str, previous: str) -> bool:
    candidate_tokens = _caption_content_tokens(candidate)
    previous_tokens = _caption_content_tokens(previous)
    if not candidate_tokens or not previous_tokens:
        return False
    # Use maximum bipartite matching so singular/plural and other Portuguese
    # inflections count as the same word without collapsing different frames.
    matches: dict[int, int] = {}

    def match_candidate(candidate_index: int, seen: set[int]) -> bool:
        for previous_index, previous_stems in enumerate(previous_tokens):
            if previous_index in seen or not (
                candidate_tokens[candidate_index] & previous_stems
            ):
                continue
            seen.add(previous_index)
            if previous_index not in matches or match_candidate(
                matches[previous_index], seen,
            ):
                matches[previous_index] = candidate_index
                return True
        return False

    matched_count = sum(
        match_candidate(index, set())
        for index in range(len(candidate_tokens))
    )
    union_size = len(candidate_tokens) + len(previous_tokens) - matched_count
    similarity = matched_count / union_size
    # Retaining articles and reaction words lets a genuinely different frame
    # ("É como..." vs "Parece...") through while catching tiny edits such as
    # deleting one word or omitting the key detail from the prior caption.
    return similarity >= 0.75


class CaptionSelector:
    def evaluate(
        self,
        candidates: list[str],
        *,
        product_name: str = "",
        product_context: dict[str, Any] | None = None,
    ) -> tuple[CaptionCandidateEvaluation, ...]:
        evaluations: list[CaptionCandidateEvaluation] = []
        previous_caption = str((product_context or {}).get("__previous_caption_to_avoid") or "")
        previous_caption_key = _caption_main_key(previous_caption)
        for index, candidate in enumerate(candidates[:10], start=1):
            raw = str(candidate or "")
            candidate_context = caption_policy_context_for(
                raw,
                product_name=product_name,
                product_context=product_context,
            )
            is_exact_rule = bool(
                candidate_context.get("__title_rule_caption_main")
                and not candidate_context.get("__title_rule_neutral_fallback")
            )
            is_neutral_fallback = bool(
                candidate_context.get("__title_rule_neutral_fallback")
            )
            normalization = (
                CaptionNormalization(caption=raw, corrections=())
                if is_exact_rule or is_neutral_fallback
                else normalize_caption(
                    raw,
                    product_name=product_name,
                    product_context=candidate_context,
                )
            )
            normalized = normalization.caption
            try:
                caption = validate_caption(
                    normalized,
                    product_name=product_name,
                    product_context=candidate_context,
                )
                if previous_caption_key and _caption_main_key(caption) == previous_caption_key:
                    raise CaptionPolicyError("texto principal repete a legenda anterior")
                if previous_caption_key and _is_near_duplicate(caption, previous_caption):
                    raise CaptionPolicyError("texto principal muito semelhante à legenda anterior")
            except CaptionPolicyError as exc:
                evaluations.append(
                    CaptionCandidateEvaluation(
                        index=index,
                        caption=normalized,
                        policy_valid=False,
                        rejection_reason=str(exc),
                        score=0.0,
                        raw_caption=raw,
                        normalization_corrections=normalization.corrections,
                    )
                )
                continue

            evaluations.append(
                CaptionCandidateEvaluation(
                    index=index,
                    caption=caption,
                    policy_valid=True,
                    rejection_reason=None,
                    score=_caption_score(
                        caption,
                        product_context=candidate_context,
                    ),
                    raw_caption=raw,
                    normalization_corrections=normalization.corrections,
                )
            )
        return tuple(evaluations)

    def choose(
        self,
        evaluations: tuple[CaptionCandidateEvaluation, ...],
        *,
        prefer_first_valid: bool = False,
    ) -> tuple[CaptionSelection, tuple[CaptionCandidateEvaluation, ...]]:
        valid = [evaluation for evaluation in evaluations if evaluation.policy_valid]
        if not valid:
            detail = "; ".join(
                f"{evaluation.index}: {evaluation.rejection_reason}"
                for evaluation in evaluations
                if evaluation.rejection_reason
            ) or "nenhuma candidata retornada"
            raise CaptionGenerationError(
                f"Nenhuma das {len(evaluations)} candidata(s) passou pela Policy: {detail}",
            )

        # Ollama is asked to order its batch by editorial quality. Use that
        # order after the shared Policy filter; lexical Vision overlap alone
        # must not promote a title-like caption over the model's own ranking.
        # Other providers retain deterministic local relevance ranking.
        best = (
            min(valid, key=lambda evaluation: evaluation.index)
            if prefer_first_valid
            else max(valid, key=lambda evaluation: (evaluation.score, -evaluation.index))
        )
        marked = tuple(
            CaptionCandidateEvaluation(
                index=evaluation.index,
                caption=evaluation.caption,
                policy_valid=evaluation.policy_valid,
                rejection_reason=evaluation.rejection_reason,
                score=evaluation.score,
                selected=evaluation.index == best.index,
                raw_caption=evaluation.raw_caption,
                normalization_corrections=evaluation.normalization_corrections,
            )
            for evaluation in evaluations
        )
        return (
            CaptionSelection(
                caption=best.caption,
                index=best.index,
                score=best.score,
            ),
            marked,
        )

    def select(
        self,
        candidates: list[str],
        *,
        product_name: str = "",
        product_context: dict[str, Any] | None = None,
    ) -> CaptionSelection:
        evaluations = self.evaluate(
            candidates,
            product_name=product_name,
            product_context=product_context,
        )
        selection, _ = self.choose(evaluations)
        return selection
