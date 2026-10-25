from __future__ import annotations

import pytest

from ArmoredIA.caption.generator import CaptionGenerator
from ArmoredIA.caption.grounded import compose_grounded_caption


@pytest.mark.parametrize(
    ("product_name", "expected"),
    [
        (
            "Descascador de legumes apontador",
            "Parece até um apontador\n#descascador #legumes",
        ),
        (
            "Tanga feminina com corte a laser",
            "Olha esse corte a laser\n#tanga #laser",
        ),
        (
            "Bolsa com compartimento de almoço",
            "Compartimento pro almoço\n#bolsa #almoço",
        ),
    ],
)
def test_known_vision_patterns_produce_approved_grounded_caption(product_name, expected):
    assert compose_grounded_caption({"productName": product_name}) == expected


def test_unknown_product_pattern_falls_back_to_ai():
    assert compose_grounded_caption({"productName": "Bolsa para computador"}) is None


def test_grounded_caption_uses_shared_policy_without_calling_provider(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            raise AssertionError("recognized text pattern should not call the model")

    result = CaptionGenerator(provider=Provider()).generate_with_evidence(
        {"productName": "Descascador de legumes apontador"}
    )

    assert result.caption == "🧡 Parece até um apontador\n#descascador #legumes"
    assert result.provider_requests == 0
    assert len(result.evaluations) == 1
    assert result.evaluations[0].policy_valid
    assert result.evaluations[0].selected


def test_safe_grounded_fallback_recovers_when_model_caption_is_unsupported(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            return ["Hidratação profunda para o corpo\n#hidratante #banho"]

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": "Esfoliante Corporal Hidratante Banho Estrias 150g Cicatribem",
    })

    assert result.caption == "🧡 Esfoliante para banho\n#esfoliante #banho"
    assert result.provider_requests == 1
    assert len(result.evaluations) == 2
    assert not result.evaluations[0].policy_valid
    assert result.evaluations[1].policy_valid
    assert result.evaluations[1].selected


def test_safe_grounded_fallback_handles_provider_unavailable(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            from ArmoredIA.providers.base import AIProviderError
            raise AIProviderError("Ollama indisponível")

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": "Kit c/3 Sutiã Básico Reforçado de Microfibra Com Bojo",
    })

    assert result.caption == "🧡 Sutiã com bojo\n#sutiã #bojo"
    assert result.provider_requests == 1
    assert result.evaluations[0].policy_valid
