from __future__ import annotations

import pytest

from ArmoredIA.caption.generator import CaptionGenerator
from ArmoredIA.caption.grounded import (
    compose_grounded_caption,
    compose_safe_caption_fallback,
    salvage_confirmed_fact_prefix,
)
from ArmoredIA.caption.selector import CaptionSelector
from ArmoredIA.caption.selector import CaptionGenerationError


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
    ],
)
def test_known_vision_patterns_produce_approved_grounded_caption(product_name, expected):
    assert compose_grounded_caption({"productName": product_name}) == expected


def test_unknown_product_pattern_falls_back_to_ai():
    assert compose_grounded_caption({"productName": "Bolsa para computador"}) is None


def test_grounded_example_is_still_generated_by_model_and_checked_by_policy(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        calls = 0

        def generate_candidates(self, *_args, **_kwargs):
            self.calls += 1
            return ["Parece até um apontador\n#descascador #legumes"]

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        {"productName": "Descascador de legumes apontador"},
        force_provider=True,
    )

    assert result.caption == "🧡 Parece até um apontador\n#descascador #legumes"
    assert provider.calls == 1
    assert result.provider_requests == 1
    assert len(result.evaluations) == 1
    assert result.evaluations[0].policy_valid
    assert result.evaluations[0].selected


@pytest.mark.parametrize(
    ("product_name", "expected"),
    [
        (
            "Tênis Feminino Casual Camurça Detalhe Lateral Listra Dupla Moderno Break GiGiL",
            "🧡 Listras duplas na lateral\n#tenis",
        ),
        (
            "Caneta Gel Apagável Amuleto Holic Delicata – Cores Sortidas – 0.7mm – Tris",
            "🧡 A escrita pode ser apagada\n#caneta",
        ),
        (
            "Copo Térmico de Cafe 450 ml Inox com Display Digital Tampa Trava Mantém Bebidas Quentes ou Frias",
            "🧡 O visor é digital\n#copo",
        ),
        (
            "Colar Feminino Dourado Pingente Coração, Banhado a Ouro 18k, Delicado Elegante Para Uso Diário",
            "🧡 Pingente de coração\n#colar",
        ),
        (
            "Sapatilha Feminina Confortável Bico Fino Sapatilha Terracota Cordão Trançado Elegante",
            "🧡 O bico é fino\n#sapatilha",
        ),
        (
            "Vestido Feminino Midi Plus Size Acinturado Modelador de Alta Compressão G1 ao G3",
            "🧡 Comprimento midi\n#vestido",
        ),
        (
            "Senhoras almoço bolsa computador portátil saco com compartimento de almoço isolado acolchoado grande capacidade bolsa de",
            "🧡 Compartimento para o almoço\n#bolsa",
        ),
        (
            "Principia Gel de Limpeza Suave - GL-02 c/ 200g",
            "🧡 Limpeza suave\n#gel",
        ),
        (
            "Esfoliante Corporal Hidratante Banho Estrias 150g Cicatribem",
            "🧡 Esfoliação corporal no banho\n#esfoliante",
        ),
    ],
)
def test_products_across_categories_use_model_and_pass_policy(
    monkeypatch, product_name, expected,
):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        calls = 0

        @staticmethod
        def configuration():
            return {"provider": "ollama"}

        def generate_candidates(self, task, context, limit):
            self.calls += 1
            assert task == "caption"
            assert context["productName"] == product_name
            assert limit == 10
            return [expected.removeprefix("🧡 ")]

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        {"productName": product_name},
        force_provider=True,
    )

    assert result.caption == expected
    assert provider.calls == 1
    assert result.provider_requests == 1
    assert result.evaluations[0].policy_valid


def test_published_caption_regeneration_can_force_the_local_provider(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def __init__(self):
            self.calls = 0

        def generate_candidates(self, *_args, **_kwargs):
            self.calls += 1
            return ["Corte a laser presente\n#tanga"]

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        {"productName": "Tanga feminina com corte a laser"},
        force_provider=True,
    )

    assert provider.calls == 1
    assert result.provider_requests == 1
    assert result.caption == "🧡 Corte a laser presente\n#tanga"
    assert result.evaluations[0].selected


def test_safe_grounded_fallback_recovers_when_model_caption_is_unsupported(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            return ["Hidratação profunda para o corpo\n#hidratante #banho"]

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": "Esfoliante Corporal Hidratante Banho Estrias 150g Cicatribem",
    }, force_provider=True)

    assert result.caption == "🧡 Esfoliação corporal no banho\n#esfoliante"
    assert result.provider_requests == 1
    assert len(result.evaluations) == 2
    assert not result.evaluations[0].policy_valid
    assert result.evaluations[1].policy_valid
    assert result.evaluations[1].selected


def test_refresh_keeps_previous_policy_valid_caption_when_model_batch_fails(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        calls = 0

        def generate_candidates(self, *_args, **_kwargs):
            self.calls += 1
            return ["Oferta imperdível", "Compre agora"]

    provider = Provider()
    previous = "🧡 O bico é quadrado\n#tamanco"
    result = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Tamanco feminino com bico quadrado",
        "__previous_caption_to_avoid": previous,
    }, force_provider=True)

    assert provider.calls == 1
    assert result.provider_requests == 1
    assert result.caption == previous
    assert result.evaluations[-1].policy_valid
    assert result.evaluations[-1].selected
    assert "previous_policy_valid_caption_retained_not_outscored" in (
        result.evaluations[-1].normalization_corrections
    )


def test_forced_caption_refresh_does_not_silently_reuse_the_previous_caption(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            return ["Oferta imperdível", "Compre agora"]

    previous = "🧡 Parece até um apontador\n#descascador"
    result = CaptionGenerator(provider=Provider()).generate_with_evidence(
        {
            "productName": "Descascador de legumes apontador",
            "description": "Parece até um apontador.",
            "__previous_caption_to_avoid": previous,
        },
        force_provider=True,
        preserve_previous_caption=False,
    )

    assert result.caption != previous
    assert all(
        "previous_policy_valid_caption_retained_not_outscored" not in evaluation.normalization_corrections
        for evaluation in result.evaluations
    )


def test_local_model_tail_is_trimmed_only_to_a_confirmed_vision_fact():
    context = {
        "productName": "Copo térmico de café inox com display digital e tampa com trava",
        "description": "Copo térmico em inox com display digital e tampa com trava.",
        "attributes": {
            "material": "inox",
            "display": "digital",
            "tampa": "com trava",
        },
    }

    assert salvage_confirmed_fact_prefix(
        "Material em inox para resistência", context,
    ) == "Material em inox"
    assert salvage_confirmed_fact_prefix(
        "Display digital mostra informações", context,
    ) == "Display digital"
    assert salvage_confirmed_fact_prefix(
        "Tampa com trava protege o produto", context,
    ) == "Tampa com trava"
    assert salvage_confirmed_fact_prefix(
        "Não tem display digital", context,
    ) is None


def test_local_model_comparison_keeps_only_vision_confirmed_noun():
    context = {
        "productName": "Descascador de legumes apontador",
        "description": "O título da Vision informa um descascador de legumes que parece até um apontador.",
    }

    assert salvage_confirmed_fact_prefix(
        "É como um apontador miniaturizado", context,
    ) == "É como um apontador"
    assert salvage_confirmed_fact_prefix(
        "Parece um pequeno apontador", context,
    ) == "Parece um apontador"
    assert salvage_confirmed_fact_prefix(
        "É como um pequeno apontador", context,
    ) == "É como um apontador"


def test_caption_generator_salvages_model_fact_without_second_slow_request(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "1")

    class Provider:
        def __init__(self):
            self.calls = 0

        @staticmethod
        def configuration():
            return {"provider": "ollama"}

        def generate_candidates(self, *_args, **_kwargs):
            self.calls += 1
            return [
                "Material em inox para resistência",
                "Display digital mostra informações",
                "Tampa com trava protege o produto",
            ]

    provider = Provider()
    context = {
        "productName": "Copo térmico de café inox com display digital e tampa com trava",
        "category": "copo",
        "description": "Copo térmico em inox com display digital e tampa com trava.",
        "attributes": {
            "material": "inox",
            "display": "digital",
            "tampa": "com trava",
        },
    }
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        context, force_provider=True,
    )

    assert provider.calls == 1
    assert result.provider_requests == 1
    assert result.evaluations[0].policy_valid is False
    salvaged = result.evaluations[-3:]
    assert all(item.policy_valid for item in salvaged)
    assert salvaged[0].raw_caption == "Material em inox para resistência"
    assert "unsupported_model_tail_trimmed_to_vision_fact" in salvaged[0].normalization_corrections
    selected = [item for item in salvaged if item.selected]
    assert len(selected) == 1
    assert result.caption == selected[0].caption
    assert selected[0].score == max(item.score for item in salvaged)


def test_caption_generator_keeps_better_previous_comparison_over_salvaged_tail(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "1")

    class Provider:
        calls = 0

        @staticmethod
        def configuration():
            return {"provider": "ollama"}

        def generate_candidates(self, *_args, **_kwargs):
            self.calls += 1
            return ["É como um apontador miniaturizado"]

    provider = Provider()
    context = {
        "productName": "Descascador de legumes apontador",
        "category": "descascador",
        "description": "O título da Vision informa um descascador de legumes que parece até um apontador.",
        "__previous_caption_to_avoid": "🧡 Parece até um apontador\n#descascador #legumes",
    }
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        context, force_provider=True,
    )

    assert provider.calls == 1
    assert result.provider_requests == 1
    assert result.caption == "🧡 Parece até um apontador\n#descascador #legumes"
    selected = next(row for row in result.evaluations if row.selected)
    assert selected.raw_caption == "🧡 Parece até um apontador\n#descascador #legumes"
    assert "previous_policy_valid_caption_retained_not_outscored" in selected.normalization_corrections


def test_fallback_keeps_better_previous_confirmed_comparison(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            return ["Parece um apontador"]

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": "Descascador de legumes apontador",
        "category": "descascador",
        "description": "Um descascador de legumes que parece até um apontador.",
        "__previous_caption_to_avoid": "🧡 Parece até um apontador\n#descascador #legumes",
    }, force_provider=True)

    assert result.caption == "🧡 Parece até um apontador\n#descascador #legumes"
    assert result.provider_requests == 1
    assert any(evaluation.selected for evaluation in result.evaluations)


def test_safe_grounded_fallback_handles_provider_unavailable(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            from ArmoredIA.providers.base import AIProviderError
            raise AIProviderError("Ollama indisponível")

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": "Esfoliante Corporal Hidratante Banho Estrias 150g Cicatribem",
    }, force_provider=True)

    assert result.caption == "🧡 Esfoliação corporal no banho\n#esfoliante"
    assert result.provider_requests == 1
    assert result.evaluations[0].policy_valid


def test_local_fact_fallback_uses_one_confirmed_vision_detail(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            return ["Estampa de onça em uma estampa de onça\n#blusa #onça"]

    context = {
        "productName": (
            "Blusa de Frio Feminina Tricô Suéter Manga Longa Gola Redonda "
            "Estampa Onça Casual Inverno"
        ),
        "category": "Blusa",
    }
    result = CaptionGenerator(provider=Provider()).generate_with_evidence(
        context, force_provider=True,
    )

    assert result.caption == "🧡 Estampa de onça\n#blusa"
    assert result.provider_requests == 1
    assert result.evaluations[0].policy_valid is False
    assert any(evaluation.policy_valid for evaluation in result.evaluations)
    assert any(evaluation.selected for evaluation in result.evaluations)


def test_local_model_fact_trim_retains_topic_when_vision_context_is_rich(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            return ["Display digital em digital destaque\n#viral"]

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": "Copo com Display Digital de Temperatura",
        "category": "copo",
        "description": "Display digital no corpo do copo.",
    }, force_provider=True)

    assert result.caption == "🧡 Display digital\n#copo"
    assert result.evaluations[0].policy_valid is False
    assert result.evaluations[-1].policy_valid is True
    assert result.evaluations[-1].selected is True


def test_local_fact_fallback_stops_when_vision_has_no_trusted_detail():
    assert compose_safe_caption_fallback({"productName": "Tênis Feminino Casual Promoção"}) is None


def test_facial_moisturizer_title_produces_natural_safe_fallback():
    from ArmoredIA.caption.grounded import extract_vision_caption_facts
    from ArmoredIA.caption.selector import CaptionSelector

    context = {
        "productName": (
            "Kit Sabonete e Creme Hidratante Facial Pele de Porcelana "
            "Kokeshi o Milagre do Arroz"
        ),
    }

    assert extract_vision_caption_facts(context) == ("Hidratação facial",)
    caption = compose_safe_caption_fallback(context)
    assert caption == "🧡 Hidratação facial\n#sabonete"
    evaluation = CaptionSelector().evaluate(
        [caption],
        product_name=context["productName"],
        product_context=context,
    )[0]
    assert evaluation.policy_valid


def test_ten_rejected_options_use_one_inference_then_grounded_fallback(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.delenv("ARMORED_IA_POLICY_RETRIES", raising=False)
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", "10")

    class Provider:
        def __init__(self):
            self.calls = 0

        @staticmethod
        def configuration():
            return {"provider": "ollama"}

        def generate_candidates(self, _task, _context, limit):
            self.calls += 1
            assert limit == 10
            return [
                "Hidratação facial com Kokeshi",
                *["Creme hidratante facial é ótimo"] * 9,
            ]

    context = {
        "productName": (
            "Kit Sabonete e Creme Hidratante Facial Pele de Porcelana "
            "Kokeshi o Milagre do Arroz"
        ),
    }
    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        context, force_provider=True,
    )

    assert provider.calls == 1
    assert result.provider_requests == 1
    assert len(result.provider_candidate_batches) == 1
    assert len(result.provider_candidate_batches[0]) == 10
    assert result.caption == "🧡 Hidratação facial\n#sabonete"
    assert result.evaluations[-1].policy_valid
    assert result.evaluations[-1].selected


@pytest.mark.parametrize(
    ("product_name", "description", "expected_fact", "expected_tag"),
    [
        (
            "Luminária de Mesa Articulada com Base Redonda",
            "Braço articulado e base redonda.",
            "Braço articulado",
            "#luminaria",
        ),
        (
            "Organizador de Gaveta Modular com Divisórias",
            "Divisórias modulares para gaveta.",
            "Divisórias modulares",
            "#organizador",
        ),
    ],
)
def test_local_fact_fallback_extracts_unlisted_vision_attributes(
    product_name, description, expected_fact, expected_tag,
):
    from ArmoredIA.caption.grounded import extract_vision_caption_fact

    context = {
        "productName": product_name,
        "description": description,
    }
    assert extract_vision_caption_fact(context) == expected_fact
    expected_main = {
        "Braço articulado": "O braço é articulado",
        "Divisórias modulares": "Divisórias modulares",
    }[expected_fact]
    assert compose_safe_caption_fallback(context) == (
        f"🧡 {expected_main}\n{expected_tag}"
    )


def test_estampa_preposition_and_pattern_are_kept_together_in_vision_fact():
    from ArmoredIA.caption.grounded import caption_prompt_context, extract_vision_caption_fact
    from ArmoredIA.caption.selector import CaptionSelector

    context = {
        "productName": "Blusa de frio delicada com estampa em cerejinhas",
        "description": "A blusa de frio tem estampa com cerejinhas.",
    }

    assert extract_vision_caption_fact(context) == "Estampa de cerejinhas"
    prompt_context = caption_prompt_context(context)
    assert prompt_context["productName"] == context["productName"]
    assert prompt_context["description"] == context["description"]
    assert prompt_context["__vision_confirmed_facts"] == ["Estampa de cerejinhas"]
    caption = compose_safe_caption_fallback(context)
    assert caption == "🧡 Estampa de cerejinhas\n#blusa"
    result = CaptionSelector().evaluate(
        [caption], product_name=context["productName"], product_context=context,
    )[0]
    assert result.policy_valid


def test_geometric_heart_title_is_reduced_to_one_confirmed_vision_fact():
    from ArmoredIA.caption.grounded import caption_prompt_context, extract_vision_caption_fact
    from ArmoredIA.caption.selector import CaptionSelector

    context = {
        "productName": "Kit 4 Brincos Feminino Texturizado Geométrico Coração Fio Design Moderno Garantia Banhado Ouro 18K",
    }

    assert extract_vision_caption_fact(context) == "Coração geométrico"
    prompt_context = caption_prompt_context(context)
    assert prompt_context["productName"] == context["productName"]
    assert prompt_context["__vision_confirmed_facts"] == ["Coração geométrico"]
    result = CaptionSelector().evaluate(
        ["🧡 Coração geométrico\n#brincos"],
        product_name=context["productName"],
        product_context=context,
    )[0]
    assert result.policy_valid


@pytest.mark.parametrize(
    ("product_name", "expected_fact", "expected_caption"),
    [
        (
            "Colete Tricot Tranças Moda Feminina Inverno",
            "Tranças em tricô",
            "🧡 Tranças em tricô\n#colete",
        ),
        (
            "Lenço Cachecol Pashmina Echarpe Unissex Versátil Despojado Moda Inverno",
            "Clima de inverno",
            "🧡 Clima de inverno\n#lenco",
        ),
        (
            "Kit 3 Camiseta Feminina Estampada 100% Algodão T-shirt Estilosa",
            "Um toque de estampa",
            "🧡 Um toque de estampa\n#camiseta",
        ),
    ],
)
def test_grounded_fallback_uses_clean_facts_without_marketplace_numbers(
    product_name, expected_fact, expected_caption,
):
    from ArmoredIA.caption.grounded import extract_vision_caption_fact
    from ArmoredIA.caption.selector import CaptionSelector

    context = {"productName": product_name}
    assert extract_vision_caption_fact(context) == expected_fact
    caption = compose_safe_caption_fallback(context)
    assert caption == expected_caption
    evaluation = CaptionSelector().evaluate(
        [caption], product_name=product_name, product_context=context,
    )[0]
    assert evaluation.policy_valid


def test_boot_shaft_height_is_a_grounded_caption_fact():
    from ArmoredIA.caption.grounded import extract_vision_caption_fact
    from ArmoredIA.caption.selector import CaptionSelector

    context = {
        "productName": "Bota Montaria Feminina Cano Alto Tratorada Fivelas Biker Rasteira Domidona",
    }
    assert extract_vision_caption_fact(context) == "Cano alto"
    caption = compose_safe_caption_fallback(context)
    assert caption == "🧡 Cano alto\n#bota"
    assert CaptionSelector().evaluate(
        [caption], product_name=context["productName"], product_context=context,
    )[0].policy_valid


@pytest.mark.parametrize(
    ("product_name", "expected_caption"),
    [
        (
            "Moletom Canguru Hawkins 1983 Middle Modelo Estilo Americano Confortável",
            "🧡 Estilo americano\n#moletom",
        ),
        (
            "Tênis Casual Feminino Confortável Branco Original Vizzano Plataforma Alta - 1389",
            "🧡 Plataforma no solado\n#tenis",
        ),
        (
            "Kit ZERO FRIZZ Touca de Cetim Premium Anti Frizz com Regulador e Dupla Camada + Scrunchie de Cetim",
            "🧡 Dupla camada\n#touca",
        ),
        (
            "Casaco Sobretudo Parca Feminino Lã Premium",
            "🧡 Tecido em lã\n#casaco",
        ),
        (
            "Óleo Nutritivo 3 Em 1 Ox Nutre 120ml Reparador De Pontas",
            "🧡 Óleo para as pontas\n#oleo",
        ),
        (
            "Sandália Papete Feminina Rasteirinha Birken Sandalia Femenina Strass Brilho Chinelo Feminino Confort",
            "🧡 Detalhes em strass\n#sandalia",
        ),
        (
            "Mochila feminina casual e versátil leve e à prova d'água com grande capacidade para estudantes",
            "🧡 Leve e com grande capacidade\n#mochila",
        ),
    ],
)
def test_caption_fallback_stays_natural_and_grounded_for_open_batch_titles(
    product_name, expected_caption,
):
    from ArmoredIA.caption.grounded import extract_vision_caption_facts

    context = {"productName": product_name}
    assert extract_vision_caption_facts(context)
    caption = compose_safe_caption_fallback(context)
    assert caption == expected_caption
    evaluation = CaptionSelector().evaluate(
        [caption], product_name=product_name, product_context=context,
    )[0]
    assert evaluation.policy_valid, evaluation.rejection_reason


def test_local_fallback_uses_descriptive_words_from_title_when_description_is_absent(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            from ArmoredIA.providers.base import AIProviderError
            raise AIProviderError("local model unavailable")

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": "Luminária de Mesa com Braço Flexível",
    })

    assert result.caption == "🧡 O braço é flexível\n#luminaria"
    assert result.evaluations[-1].policy_valid
    assert any(evaluation.selected for evaluation in result.evaluations)


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (
            {
                "productName": "Sapatilha feminina de bico fino",
                "category": "Sapatilha",
                "description": "Bico fino.",
            },
            "🧡 O bico é fino\n#sapatilha",
        ),
        (
            {
                "productName": "Bolsa com divisão para refeições",
                "category": "Bolsa",
                "description": "Divisão interna para refeições.",
            },
            "🧡 Divisão interna para refeições\n#bolsa",
        ),
        (
            {
                "productName": "Descascador de legumes formato de apontador",
                "category": "Descascador",
                "description": "Formato semelhante a um apontador.",
            },
            "🧡 Parece até um apontador\n#descascador",
        ),
        (
            {
                "productName": "Caneta Gel Apagável Amuleto Cores Sortidas 0.7mm",
                "category": "Caneta",
            },
            "🧡 A escrita pode ser apagada\n#caneta",
        ),
        (
            {
                "productName": "Vestido Feminino Midi Plus Size Acinturado Modelador G1 ao G3",
                "category": "Vestido",
            },
            "🧡 Comprimento midi\n#vestido",
        ),
        (
            {
                "productName": "Body Feminino Mula Manca Suplex Bory Collant",
                "category": "Body",
            },
            "🧡 Tecido em suplex\n#body",
        ),
    ],
)
def test_safe_fallback_turns_confirmed_title_and_vision_facts_into_captions(
    monkeypatch, context, expected,
):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            from ArmoredIA.providers.base import AIProviderError
            raise AIProviderError("local model unavailable")

    result = CaptionGenerator(provider=Provider()).generate_with_evidence(context)
    assert result.caption == expected
    assert result.evaluations[-1].policy_valid
    assert any(evaluation.selected for evaluation in result.evaluations)


def test_local_fact_fallback_covers_jewelry_head(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            from ArmoredIA.providers.base import AIProviderError
            raise AIProviderError("local model unavailable")

    result = CaptionGenerator(provider=Provider()).generate_with_evidence({
        "productName": (
            "Colar Feminino Dourado Pingente Coração, Banhado a Ouro 18k, "
            "Delicado Elegante Para Uso Diário"
        )
    }, force_provider=True)

    assert result.caption == "🧡 Acabamento dourado\n#colar"
    assert result.provider_requests == 1
    assert result.evaluations[0].policy_valid


def test_local_fact_fallback_uses_varied_vision_details(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        def generate_candidates(self, *_args, **_kwargs):
            from ArmoredIA.providers.base import AIProviderError
            raise AIProviderError("local model unavailable")

    generator = CaptionGenerator(provider=Provider())
    gel = generator.generate_with_evidence({
        "productName": "Principia Gel de Limpeza Suave - GL-02 c/ 200g",
    })
    cup = generator.generate_with_evidence({
        "productName": "Copo Térmico de Cafe 450 ml Inox com Display Digital",
    })

    assert gel.caption == "🧡 Limpeza suave\n#gel"
    assert cup.caption == "🧡 O visor é digital\n#copo"
    assert gel.evaluations[0].policy_valid
    assert cup.evaluations[0].policy_valid


def test_title_fact_extraction_keeps_compound_and_distinct_details():
    from ArmoredIA.caption.grounded import extract_vision_caption_facts

    glasses = {
        "productName": (
            "Óculos de Sol Capri Feminino Quadrado Grande Premium Clássico "
            "Blogueira Com Case uv400"
        )
    }
    watch = {
        "productName": "KIT RELOGIO LED DIGITAL QUADRADO FEMININO + CORRENTE E BRINCO LUXO"
    }

    assert extract_vision_caption_facts(glasses) == (
        "Estilo clássico", "Acompanha case", "Formato quadrado",
    )
    assert extract_vision_caption_facts(watch) == (
        "Visor digital quadrado", "Corrente e brinco no conjunto",
    )


def test_title_fact_extraction_recovers_fabric_pattern_and_lining_details():
    from ArmoredIA.caption.grounded import extract_vision_caption_facts

    hoodie = {
        "productName": (
            "Moletom Feminino Jesus Moda De Inverno Lançamento Interna Pelucia "
            "50% Algodao 50% Poliester"
        )
    }
    scarf = {
        "productName": (
            "Lenço Cachecol Longo Feminino Xadrez Pashimina Sintética "
            "Melhores Presentes Inverno"
        )
    }

    hoodie_facts = set(extract_vision_caption_facts(hoodie))
    scarf_facts = set(extract_vision_caption_facts(scarf))

    assert {"Pelúcia interna", "Clima de inverno", "Algodão"} <= hoodie_facts
    assert {"Estampa de xadrez", "Material sintético", "Comprimento longo"} <= scarf_facts


def test_title_fact_extraction_keeps_multiple_lunch_bag_details():
    from ArmoredIA.caption.grounded import extract_vision_caption_facts

    context = {
        "productName": (
            "Bolsa com compartimento de almoço isolado acolchoado grande capacidade"
        )
    }
    facts = set(extract_vision_caption_facts(context))
    assert "Compartimento de almoço" in facts
    assert "Isolado acolchoado" in facts


def test_title_fact_extraction_keeps_lining_and_bodice_details_for_vision_prompt():
    from ArmoredIA.caption.grounded import caption_prompt_context, extract_vision_caption_facts

    context = {
        "productName": (
            "Vestido Longo Com FORRO e BOJO, Feminino Com manga Variados "
            "super confortáveis e leves qualidade e durabilidade"
        ),
        "description": (
            "O título da Vision informa vestido longo, com forro e bojo, "
            "leve e confortável, além de variações de manga."
        ),
    }

    facts = set(extract_vision_caption_facts(context))
    assert {"Forro", "Bojo", "Leve e confortável", "Variação nas mangas"} <= facts
    prompt_context = caption_prompt_context(context)
    assert prompt_context["__vision_category"] == "vestido"
    assert {"Forro", "Bojo", "Leve e confortável", "Variação nas mangas"} <= set(
        prompt_context["__vision_confirmed_facts"]
    )


def test_ollama_model_handles_sparse_titles_across_product_categories(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", "10")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")

    class Provider:
        calls = 0

        @staticmethod
        def configuration():
            return {"provider": "ollama", "model": "qwen2.5:3b"}

        def generate_candidates(self, _task, context, limit):
            self.calls += 1
            assert limit == 10
            title = str(context["productName"])
            if "Óculos" in title:
                return ["Estilo clássico\n#oculos"]
            return ["Corrente e brinco no conjunto\n#relogio"]

    provider = Provider()
    generator = CaptionGenerator(provider=provider)
    glasses = generator.generate_with_evidence({
        "productName": (
            "Óculos de Sol Capri Feminino Quadrado Grande Premium Clássico "
            "Blogueira Com Case uv400"
        )
    }, force_provider=True)
    watch = generator.generate_with_evidence({
        "productName": "KIT RELOGIO LED DIGITAL QUADRADO FEMININO + CORRENTE E BRINCO LUXO"
    }, force_provider=True)

    assert provider.calls == 2
    assert glasses.caption.startswith("🧡 Estilo clássico")
    assert watch.caption.startswith("🧡 Corrente e brinco no conjunto")
    assert glasses.evaluations[0].policy_valid
    assert watch.evaluations[0].policy_valid
