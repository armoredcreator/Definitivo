from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from ..providers.base import AIProviderError
from ..providers.gemini_grouped import GeminiGroupedProvider
from .selector import (
    CaptionCandidateEvaluation,
    CaptionGenerationError,
    CaptionSelection,
    CaptionSelector,
)


@dataclass(frozen=True)
class CaptionGroupItemResult:
    product_id: str
    candidates: tuple[CaptionCandidateEvaluation, ...]
    selection: CaptionSelection | None
    error: str | None = None


@dataclass(frozen=True)
class CaptionGroupResult:
    batch_id: str
    provider_requests: int
    items: tuple[CaptionGroupItemResult, ...]
    provider_attempts: tuple[dict[str, Any], ...] = ()


class CaptionGroupGenerator:
    """Review-only grouped generation with the shared local caption Policy."""

    def __init__(self, provider: GeminiGroupedProvider | None = None, selector: CaptionSelector | None = None):
        self.provider = provider or GeminiGroupedProvider()
        self.selector = selector or CaptionSelector()

    def generate_with_evidence(
        self,
        products: dict[str, dict[str, Any]],
        *,
        candidates_per_product: int = 10,
    ) -> CaptionGroupResult:
        if not products:
            raise CaptionGenerationError("Nenhum produto foi enviado para a geração agrupada")
        if not 1 <= int(candidates_per_product) <= 10:
            raise CaptionGenerationError("candidates_per_product deve estar entre 1 e 10")
        if any(not isinstance(context, dict) for context in products.values()):
            raise CaptionGenerationError("Contexto inválido no lote de produtos")

        batch_id = uuid.uuid4().hex
        try:
            generated = self.provider.generate_candidates_for_products(
                "caption", products, int(candidates_per_product),
            )
        except AIProviderError as exc:
            raise CaptionGenerationError(
                str(exc), batch_id=batch_id, provider_requests=1,
                provider_attempts=tuple(getattr(self.provider, "last_attempts", ())),
            ) from exc

        items: list[CaptionGroupItemResult] = []
        for product_id, context in products.items():
            candidates = generated.get(str(product_id), [])
            evaluations = self.selector.evaluate(
                candidates,
                product_name=str(context.get("productName") or ""),
                product_context=context,
            )
            try:
                selection, marked = self.selector.choose(evaluations)
            except CaptionGenerationError as exc:
                items.append(CaptionGroupItemResult(
                    product_id=str(product_id),
                    candidates=evaluations,
                    selection=None,
                    error=str(exc),
                ))
            else:
                items.append(CaptionGroupItemResult(
                    product_id=str(product_id),
                    candidates=marked,
                    selection=selection,
                ))
        attempts = tuple(
            receipt
            for receipt in (getattr(self.provider, "last_attempts", ()) or ())
            if isinstance(receipt, dict)
        )
        return CaptionGroupResult(batch_id, 1, tuple(items), attempts)
