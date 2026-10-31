from __future__ import annotations

import json
import os

import pytest
import requests

from ArmoredIA.caption.generator import CaptionGenerator, CaptionGenerationError
from ArmoredIA.caption.grounded import compose_grounded_caption, compose_safe_caption_fallback
from ArmoredIA.caption.policy import (
    CaptionPolicyError,
    _caption_is_title_keyword_list,
    _main_phrase_is_contextual,
    caption_generation_vocabulary,
    normalize_caption,
    validate_caption,
)
from ArmoredIA.providers.gemini import GeminiProvider
from ArmoredIA.providers.ollama import OllamaProvider
from ArmoredIA.providers.base import AIProviderError
from ArmoredIA.caption.selector import CaptionCandidateEvaluation, CaptionSelector


def _gemini_response(captions):
    return {
        "candidates": [{
            "content": {"parts": [{"text": json.dumps({"captions": captions}, ensure_ascii=False)}]}
        }]
    }


def _normalize_validate(raw, *, product_name="", product_context=None):
    result = normalize_caption(
        raw, product_name=product_name, product_context=product_context,
    )
    assert validate_caption(
        result.caption, product_name=product_name, product_context=product_context,
    ) == result.caption
    return result.caption


def test_camiseta_vision_category_is_valid_hashtag_support():
    context = {
        "productName": "Camiseta Básica de Algodão Manga Curta",
        "category": "camiseta",
        "description": "Tecido 100% algodão e manga curta.",
    }
    assert _normalize_validate(
        "Manga curta\n#camiseta",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Manga curta\n#camiseta"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("ARMORED_IA_ENABLED", raising=False)
    monkeypatch.delenv("ARMORED_IA_CAPTION_ENABLED", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ARMORED_IA_MODEL", raising=False)
    monkeypatch.delenv("ARMORED_IA_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("ARMORED_IA_RETRY_DELAY", raising=False)


def test_policy_accepts_contextual_caption():
    assert _normalize_validate(
        "Unhas organizadas 🧡\n#unhas #organizacao",
        product_name="Expositor de esmaltes com gavetas",
        product_context={"categoryName": "unhas beleza organização"},
    ) == "🧡 Unhas organizadas\n#unhas #organizacao"


@pytest.mark.parametrize(
    ("caption", "product_name", "expected"),
    [
        (
            "Parece até um apontador\n#descascador #legumes",
            "Descascador de Legumes Apontador",
            "🧡 Parece até um apontador\n#descascador #legumes",
        ),
        (
            "Olha esse corte a laser\n#tanga #laser",
            "Kit Calcinhas Sem costura Tanga corte a Laser Nao Marca na Roupa Invisível Academia Justo Conforto",
            "🧡 Olha esse corte a laser\n#tanga #laser",
        ),
        (
            "Compartimento pro almoço\n#bolsa #almoço",
            "Senhoras almoço bolsa computador portátil saco com compartimento de almoço isolado acolchoado grande capacidade bolsa de",
            "🧡 Compartimento pro almoço\n#bolsa #almoço",
        ),
    ],
)
def test_policy_accepts_approved_vision_text_samples(caption, product_name, expected):
    context = {"productName": product_name}
    assert _normalize_validate(
        caption, product_name=product_name, product_context=context,
    ) == expected


def test_policy_rejects_secondary_product_noun_without_comparison():
    product_name = "Descascador de Legumes Apontador"
    with pytest.raises(CaptionPolicyError, match="substantivo secundário"):
        validate_caption(
            "🧡 Apontador bonito\n#descascador #legumes",
            product_name=product_name,
            product_context={"productName": product_name},
        )


@pytest.mark.parametrize(
    ("caption", "product_name", "safe_main", "hashtag"),
    [
        (
            "🧡 Óculos quadrados\n#oculos",
            "Óculos de Sol Capri Feminino Quadrado",
            "Formato quadrado",
            "#oculos",
        ),
        (
            "🧡 Relógio digital\n#relogio",
            "Kit Relógio LED Digital Quadrado",
            "Visor digital quadrado",
            "#relogio",
        ),
    ],
)
def test_policy_allows_a_natural_product_name_with_a_confirmed_detail(
    caption, product_name, safe_main, hashtag,
):
    context = {"productName": product_name, "description": safe_main}
    assert validate_caption(
        caption, product_name=product_name, product_context=context,
    ) == caption
    assert validate_caption(
        f"🧡 {safe_main}\n{hashtag}",
        product_name=product_name,
        product_context=context,
    ) == f"🧡 {safe_main}\n{hashtag}"


@pytest.mark.parametrize(
    ("caption", "product_name"),
    [
        (
            "🧡 Casaco de lã\n#casaco",
            "Casaco Sobretudo Parca Feminino Lã Premium",
        ),
        (
            "🧡 Mochila leve\n#mochila",
            "Mochila feminina casual e versátil leve e à prova d'água com grande capacidade para estudantes",
        ),
    ],
)
def test_policy_allows_natural_product_reference_without_forcing_it(caption, product_name):
    context = {"productName": product_name}
    assert _normalize_validate(
        caption,
        product_name=product_name,
        product_context=context,
    ) == caption


def test_policy_rejects_title_noise_and_unlinked_product_name_suffix():
    product_name = "Tênis Casual Feminino Confortável Branco Original Vizzano Plataforma Alta - 1389"
    with pytest.raises(CaptionPolicyError):
        validate_caption(
            "🧡 Original solado tênis\n#tenis",
            product_name=product_name,
            product_context={"productName": product_name},
        )


def test_sparse_vision_context_requires_product_head_not_a_material_fragment():
    context = {"productName": "Escovas de Aço Multiuso Kit 3 Pcs Aço Latão Nylon Cabo Plástico"}
    with pytest.raises(CaptionPolicyError, match="sem suporte"):
        validate_caption(
            "🧡 Latão bonito\n#latão",
            product_name=context["productName"],
            product_context=context,
        )
    with pytest.raises(CaptionPolicyError, match="detalhe confirmado"):
        validate_caption(
            "🧡 Escovas bonitas\n#escovas",
            product_name=context["productName"],
            product_context=context,
        )

    peeler = {"productName": "Descascador de Legumes Apontador"}
    with pytest.raises(CaptionPolicyError, match="substantivo"):
        validate_caption(
            "🧡 Apontador bonito\n#apontador",
            product_name=peeler["productName"],
            product_context=peeler,
        )
    assert _normalize_validate(
        "Parece até um apontador\n#descascador #legumes",
        product_name=peeler["productName"],
        product_context=peeler,
    ) == "🧡 Parece até um apontador\n#descascador #legumes"
    assert _normalize_validate(
        "Descascador tipo apontador\n#descascador",
        product_name=peeler["productName"],
        product_context=peeler,
    ) == "🧡 Descascador tipo apontador\n#descascador"
    with pytest.raises(CaptionPolicyError, match="detalhe confirmado"):
        validate_caption(
            "🧡 Descascador em espiral\n#descascador",
            product_name=peeler["productName"],
            product_context=peeler,
        )


def test_policy_allows_natural_product_reference_in_caption_body():
    context = {"productName": "Xícara de Café em Cerâmica", "category": "café"}
    assert _normalize_validate(
        "Café quentinho\n#café",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Café quentinho\n#café"
    assert _normalize_validate(
        "O café que você merece\n#diaadia #café",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 O café que você merece\n#diaadia #café"


@pytest.mark.parametrize(
    ("product_name", "caption", "hashtag"),
    [
        (
            "Kit Sabonete e Creme Hidratante Facial Pele de Porcelana Kokeshi o Milagre do Arroz",
            "Hidratação facial",
            "#sabonete",
        ),
        (
            "Sandália Feminina Leve Confortável Leve De Dedo",
            "Leve e confortável",
            "#sandalia",
        ),
        (
            "Blusa Feminina Estampada Floral",
            "Um toque de estampa",
            "#blusa",
        ),
    ],
)
def test_policy_accepts_natural_rephrasing_grounded_in_the_vision_title(
    product_name, caption, hashtag,
):
    context = {"productName": product_name}
    assert validate_caption(
        f"🧡 {caption}\n{hashtag}",
        product_name=product_name,
        product_context=context,
    ) == f"🧡 {caption}\n{hashtag}"


def test_policy_uses_title_as_evidence_but_filters_marketplace_hype():
    product_name = (
        "Kit Sabonete e Creme Hidratante Facial Pele de Porcelana "
        "Kokeshi o Milagre do Arroz Premium"
    )
    with pytest.raises(CaptionPolicyError, match="sem suporte|marca ou modelo"):
        validate_caption(
            "🧡 Milagre para a pele\n#sabonete",
            product_name=product_name,
            product_context={"productName": product_name},
        )


def test_policy_rejects_stylized_brand_token_from_vision_title():
    product_name = (
        "Tênis Feminino Casual Camurça Detalhe Lateral "
        "Listra Dupla Moderno Break GiGiL"
    )
    with pytest.raises(CaptionPolicyError, match="marca ou modelo"):
        validate_caption(
            "🧡 Listras na lateral do GiGiL\n#tenis",
            product_name=product_name,
            product_context={"productName": product_name},
        )
    branded_phrase = (
        "Kit Sabonete e Creme Hidratante Facial Pele de Porcelana "
        "Kokeshi o Milagre do Arroz"
    )
    with pytest.raises(CaptionPolicyError, match="marca ou modelo"):
        validate_caption(
            "🧡 Hidratação facial com Kokeshi\n#sabonete",
            product_name=branded_phrase,
            product_context={"productName": branded_phrase},
        )


def test_policy_detects_brands_near_marketplace_model_markers():
    from ArmoredIA.caption.policy import _brand_model_tokens

    hawkins = "Moletom Canguru Hawkins 1983 Middle Modelo Estilo Americano Confortável"
    vizzano = "Tênis Casual Feminino Confortável Branco Original Vizzano Plataforma Alta - 1389"
    assert "hawkins" in _brand_model_tokens({"productName": hawkins})
    assert "middle" in _brand_model_tokens({"productName": hawkins})
    assert "vizzano" in _brand_model_tokens({"productName": vizzano})
    with pytest.raises(CaptionPolicyError):
        validate_caption(
            "🧡 Hawkins confortável em estilo americano\n#moletom",
            product_name=hawkins,
            product_context={"productName": hawkins},
        )
    with pytest.raises(CaptionPolicyError):
        validate_caption(
            "🧡 Vizzano branco\n#tenis",
            product_name=vizzano,
            product_context={"productName": vizzano},
        )


def test_policy_does_not_mistake_uppercase_product_attributes_for_brands():
    from ArmoredIA.caption.policy import _brand_model_tokens

    title = "Vestido Longo Com FORO e BOJO Feminino"
    tokens = _brand_model_tokens({"productName": title})
    assert "foro" not in tokens
    assert "bojo" not in tokens


def test_policy_allows_a_natural_grounded_caption_without_a_benefit_or_product_name():
    title = "Casaco Cardigan Aberto Manga Longa Tranças Tricô Inverno Lançamento"
    context = {"productName": title}

    assert validate_caption(
        "🧡 Tranças em tricô\n#casaco",
        product_name=title,
        product_context=context,
    ) == "🧡 Tranças em tricô\n#casaco"


def test_policy_allows_a_benefit_only_when_vision_confirms_it():
    context = {"productName": "Tênis casual leve confortável plataforma alta"}
    assert validate_caption(
        "🧡 Leve e confortável\n#tenis",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Leve e confortável\n#tenis"

    with pytest.raises(CaptionPolicyError, match="sem suporte"):
        validate_caption(
            "🧡 Perfeito e elegante\n#tenis",
            product_name=context["productName"],
            product_context=context,
        )


def test_policy_rejects_an_unconfirmed_relation_between_vision_details():
    title = "Casaco Cardigan Aberto Manga Longa Tranças Tricô Inverno Lançamento"
    context = {"productName": title}
    with pytest.raises(CaptionPolicyError, match="relação espacial"):
        validate_caption(
            "🧡 Tranças em tricô na manga\n#casaco",
            product_name=title,
            product_context=context,
        )


def test_policy_accepts_a_spatial_phrase_explicitly_confirmed_by_the_vision_description():
    title = (
        "Vestido Longo Com FORO e BOJO, Feminino Com manga Variados "
        "super confortáveis e leves qualidade e durabilidade"
    )
    context = {
        "productName": title,
        "description": (
            "O título da Vision informa vestido longo, com forro e bojo, "
            "leve e confortável, além de variações de manga."
        ),
    }
    assert validate_caption(
        "🧡 Variações nas mangas\n#vestido",
        product_name=title,
        product_context=context,
    ) == "🧡 Variações nas mangas\n#vestido"


def test_selector_rejects_a_plural_rewording_of_the_previous_published_caption():
    title = (
        "Vestido Longo Com FORO e BOJO, Feminino Com manga Variados "
        "super confortáveis e leves qualidade e durabilidade"
    )
    previous = "🧡 A variação nas mangas\n#vestido"
    context = {
        "productName": title,
        "description": "O produto tem variações de manga.",
        "__previous_caption_to_avoid": previous,
    }
    evaluation = CaptionSelector().evaluate(
        ["Variações nas mangas\n#vestido"],
        product_name=title,
        product_context=context,
    )[0]
    assert not evaluation.policy_valid
    assert evaluation.rejection_reason == "texto principal muito semelhante à legenda anterior"


def test_policy_rejects_unconfirmed_design_and_catalog_wording():
    sneaker = "Tênis Feminino Vizzano Plataforma Alta"
    with pytest.raises(CaptionPolicyError, match="sem suporte"):
        validate_caption(
            "🧡 Plataforma alta no design\n#tenis",
            product_name=sneaker,
            product_context={"productName": sneaker},
        )

    hoodie = "Moletom Canguru Hawkins 1983 Middle Modelo Estilo Americano Confortável"
    with pytest.raises(CaptionPolicyError, match="sem suporte|marca ou modelo"):
        validate_caption(
            "🧡 Modelo canguru de estilo americano\n#moletom",
            product_name=hoodie,
            product_context={"productName": hoodie},
        )


@pytest.mark.parametrize(
    ("product_name", "caption"),
    [
        (
            "Kit Sutiã com Bojo do P ao GG",
            "🧡 Bojo do P ao GG\n#sutia",
        ),
        (
            "Blusa Manga Bufante Blogueira",
            "🧡 Manga bufante para blogueiras\n#blusa",
        ),
        (
            "Copo térmico de Café em Cerâmica",
            "🧡 Algodão e pelúcia são aí\n#copo",
        ),
        (
            "Camiseta estampada floral premium",
            "🧡 Floral no tecido premium\n#camiseta",
        ),
        (
            "Colar com coração geométrico",
            "🧡 Coração delicado e elegante\n#colar",
        ),
        (
            "Sapatilha feminina de bico fino",
            "🧡 Fino e elegante em uma\n#sapatilha",
        ),
    ],
)
def test_policy_rejects_listing_noise_unsupported_claims_and_broken_closers(
    product_name, caption,
):
    evaluation = CaptionSelector().evaluate(
        [caption],
        product_name=product_name,
        product_context={"productName": product_name},
    )[0]

    assert not evaluation.policy_valid


def test_policy_keeps_the_owners_natural_coffee_caption_example():
    context = {"productName": "Xícara de Café em Cerâmica", "category": "café"}

    assert _normalize_validate(
        "Café quentinho\n#café",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Café quentinho\n#café"


def test_policy_rejects_category_material_fragments_and_reversed_material_order():
    sutia = {"productName": "Kit Sutiã Básico Reforçado de Microfibra Com Bojo"}
    with pytest.raises(CaptionPolicyError, match="fragmento de título"):
        validate_caption(
            "🧡 Sutiã microfibra\n#sutia",
            product_name=sutia["productName"],
            product_context=sutia,
        )

    moletom = {"productName": "Moletom Feminino Interna Pelúcia 50% Algodão 50% Poliéster"}
    with pytest.raises(CaptionPolicyError, match="fragmento de título"):
        validate_caption(
            "🧡 Algodão em moletom\n#moletom",
            product_name=moletom["productName"],
            product_context=moletom,
        )

    from ArmoredIA.caption.policy import _has_known_agreement_error
    assert _has_known_agreement_error(["Microfibra", "na", "sutiã"])


def test_policy_rejects_catalog_label_prefix():
    with pytest.raises(CaptionPolicyError, match="rótulo de catálogo"):
        validate_caption(
            "🧡 Detalhe: manga longa no pijama\n#pijama",
            product_name="Pijama Feminino de Manga Longa",
        )


def test_policy_matches_portuguese_plural_forms_to_vision_evidence():
    context = {
        "productName": "Kit 4 Brincos Feminino Texturizado Geométrico Coração Fio Design Moderno Garantia Banhado Ouro 18K",
    }
    assert _main_phrase_is_contextual(
        ["Brincos", "geométricos", "em", "corações"],
        product_name=context["productName"],
        product_context=context,
    )
    assert _normalize_validate(
        "Brincos geométricos em corações\n#brincos",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Brincos geométricos em corações\n#brincos"


@pytest.mark.parametrize(
    "caption",
    [
        "🧡 Design geométrico no coração, {brincos}\n#brincos",
        "🧡 Design geométrico [categoria]\n#brincos",
    ],
)
def test_policy_rejects_unresolved_model_placeholders(caption):
    with pytest.raises(CaptionPolicyError, match="marcador de preenchimento"):
        validate_caption(
            caption,
            product_name="Kit Brincos Geométrico Coração",
            product_context={"productName": "Kit Brincos Geométrico Coração"},
        )


def test_policy_rejects_the_recent_malformed_caption_regressions():
    earring = {
        "productName": "Kit 4 Brincos Feminino Texturizado Geométrico Coração Fio Design Moderno",
    }
    with pytest.raises(CaptionPolicyError, match="limite é de 2 a 5"):
        validate_caption(
            "🧡 Fio design geométrico em formato de coração\n#brincos",
            product_name=earring["productName"],
            product_context=earring,
        )
    shirt = {"productName": "Camiseta Feminina Estampada 100% Algodão", "category": "camiseta"}
    with pytest.raises(CaptionPolicyError, match="número"):
        validate_caption(
            "🧡 Estampada 100\n#camiseta",
            product_name=shirt["productName"],
            product_context=shirt,
        )

    vest = {"productName": "Colete Tricot Tranças", "category": "colete"}
    with pytest.raises(CaptionPolicyError, match="erro de digitação"):
        validate_caption(
            "🧡 Coleto bonito\n#colete",
            product_name=vest["productName"],
            product_context=vest,
        )


def test_policy_rejects_shortened_product_titles_as_catalog_captions():
    context = {
        "productName": "Kit 4 Brincos Feminino Texturizado Geométrico Coração Fio Design Moderno Garantia Banhado Ouro 18K",
    }
    for caption in (
        "🧡 Kit moderno de brincos\n#brincos",
        "🧡 Brinco geométrico coração\n#brincos",
        "🧡 Design banhado a ouro\n#brincos",
    ):
        main_words = caption.splitlines()[0].replace("🧡", "").split()
        assert _caption_is_title_keyword_list(
            main_words,
            product_name=context["productName"],
            product_context=context,
        )
        with pytest.raises(CaptionPolicyError):
            validate_caption(
                caption,
                product_name=context["productName"],
                product_context=context,
            )

    assert _normalize_validate(
        "Coração geométrico\n#brincos",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Coração geométrico\n#brincos"

def test_caption_ranking_uses_product_facts_from_vision_title():
    context = {
        "productName": "Kit 4 Brincos Feminino Texturizado Geométrico Coração Fio Design Moderno",
    }
    selector = CaptionSelector()
    evaluations = selector.evaluate(
        [
            "Coração bonito\n#brincos",
            "Coração geométrico\n#brincos",
        ],
        product_name=context["productName"],
        product_context=context,
    )
    selection, marked = selector.choose(evaluations)
    assert not evaluations[0].policy_valid
    assert evaluations[1].policy_valid
    assert evaluations[1].score > evaluations[0].score
    assert selection.caption == "🧡 Coração geométrico\n#brincos"
    assert marked[1].selected


def test_model_candidate_order_is_preserved_when_requested_after_policy_filter():
    evaluations = (
        CaptionCandidateEvaluation(
            index=1, caption="🧡 Comentário natural\n#caneta",
            policy_valid=True, rejection_reason=None, score=1.0,
        ),
        CaptionCandidateEvaluation(
            index=2, caption="🧡 Frase mais relevante\n#caneta",
            policy_valid=True, rejection_reason=None, score=100.0,
        ),
    )
    selection, marked = CaptionSelector().choose(evaluations, prefer_first_valid=True)
    assert all(item.policy_valid for item in evaluations)
    assert selection.index == 1
    assert marked[0].selected


def test_normalizer_replaces_only_unrelated_hashtags_with_a_grounded_product_tag():
    product_name = "Descascador de Legumes Apontador"
    context = {"productName": product_name}
    normalized = normalize_caption(
        "Parece até um apontador #cozinhacriativa #praticidade",
        product_name=product_name,
        product_context=context,
    )
    assert normalized.caption == "🧡 Parece até um apontador\n#Descascador"
    assert "grounded_hashtag_inserted" in normalized.corrections
    assert validate_caption(
        normalized.caption,
        product_name=product_name,
        product_context=context,
    ) == normalized.caption


def test_policy_rejects_repeated_product_word_as_an_unnatural_caption():
    context = {"productName": "Descascador de Legumes Apontador"}
    with pytest.raises(CaptionPolicyError, match="repete palavras"):
        validate_caption(
            "🧡 Descascador descascador descascador\n#descascador",
            product_name=context["productName"],
            product_context=context,
        )


def test_policy_allows_repeated_grammatical_preposition_in_natural_phrase():
    context = {
        "productName": "Blusa feminina de tricô",
        "category": "Blusa",
        "description": "Estampa de onça",
    }
    assert validate_caption(
        "🧡 Estampa de onça com tricô\n#blusa",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Estampa de onça com tricô\n#blusa"


def test_policy_rejects_unlinked_product_nouns():
    context = {"productName": "Descascador de Legumes Apontador"}
    with pytest.raises(CaptionPolicyError, match="sem ligação natural"):
        validate_caption(
            "🧡 Apontador descascador lindo\n#descascador",
            product_name=context["productName"],
            product_context=context,
        )


def test_policy_rejects_unidiomatic_bag_for_computer_caption():
    context = {
        "productName": "Senhoras almoço bolsa computador portátil saco com compartimento almoço",
    }
    with pytest.raises(CaptionPolicyError, match="relação pouco natural"):
        validate_caption(
            "🧡 Bolsa de computador\n#bolsa #computador",
            product_name=context["productName"],
            product_context=context,
        )
    with pytest.raises(CaptionPolicyError, match="fragmento de título"):
        validate_caption(
            "🧡 Bolsa para computador\n#bolsa #computador",
            product_name=context["productName"],
            product_context=context,
        )


def test_caption_generator_retries_unnatural_preposition_with_specific_guidance(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "1")

    class Provider:
        def __init__(self):
            self.calls = 0
            self.retry_context = None

        def generate_candidates(self, task, context, limit):
            self.calls += 1
            if self.calls == 1:
                return ["Bolsa de computador\n#bolsa #computador"]
            self.retry_context = context
            return ["Bolsa para computador\n#bolsa #computador"]

    provider = Provider()
    caption = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Senhoras almoço bolsa computador portátil saco com compartimento almoço",
    }, force_provider=True).caption

    assert caption == "🧡 Compartimento para o almoço\n#bolsa"
    assert provider.calls == 2
    assert any(
        "para computador" in value.casefold()
        for value in provider.retry_context["__policy_retry_feedback"]
    )


def test_policy_rejects_clear_gender_and_number_disagreement():
    context = {"productName": "Bolsa feminina tiracolo", "categoryName": "bolsas e acessórios"}
    with pytest.raises(CaptionPolicyError, match="concordância"):
        validate_caption(
            "🧡 Bolsas lindo\n#bolsas",
            product_name=context["productName"],
            product_context=context,
        )
    plural_context = {"productName": "Bolsa praia", "categoryName": "bolsas e acessórios"}
    with pytest.raises(CaptionPolicyError, match="concordância"):
        validate_caption(
            "🧡 Bolsas linda\n#bolsas",
            product_name=plural_context["productName"],
            product_context=plural_context,
        )
    corrected = normalize_caption(
        "🧡 Bolsas lindo\n#bolsas",
        product_name=context["productName"],
        product_context=context,
    )
    neutral = normalize_caption(
        "🧡 Bebidas quente\n#copo",
        product_name="Copo térmico que mantém bebidas quentes",
        product_context={"productName": "Copo térmico que mantém bebidas quentes"},
    )
    assert neutral.caption == "🧡 Bebidas quentes\n#copo"
    assert "known_adjective_agreement_inflected" in neutral.corrections

    thermal = {
        "productName": (
            "Copo Térmico de Cafe 450 ml Inox com Display Digital Tampa Trava "
            "Mantém Bebidas Quentes ou Frias"
        ),
    }
    raw = "🧡 Cafe quentes\n#copo #Cafe"
    with pytest.raises(CaptionPolicyError, match="concordância"):
        validate_caption(
            raw,
            product_name=thermal["productName"],
            product_context=thermal,
        )
    corrected = normalize_caption(
        raw,
        product_name=thermal["productName"],
        product_context=thermal,
    )
    assert corrected.caption == "🧡 Cafe quente\n#copo #Cafe"
    assert "known_adjective_agreement_inflected" in corrected.corrections
    assert validate_caption(
        corrected.caption,
        product_name=thermal["productName"],
        product_context=thermal,
    ) == corrected.caption


def test_caption_generator_safely_inflects_known_agreement_before_policy():
    class Provider:
        def __init__(self):
            self.calls = 0

        def generate_candidates(self, task, context, limit):
            self.calls += 1
            return ["Bebidas quente #copo"]

    provider = Provider()
    context = {"productName": "Copo térmico que mantém bebidas quentes"}
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        context, force_provider=True,
    )

    assert provider.calls == 1
    assert result.caption == "🧡 Bebidas quentes\n#copo"
    assert result.evaluations[0].policy_valid
    assert "known_adjective_agreement_inflected" in result.evaluations[0].normalization_corrections


def test_policy_allows_natural_overlap_with_description():
    assert _normalize_validate(
        "Cantinho resistente 🧡\n#casa",
        product_name="Bancada Suspensa",
        product_context={"description": "estrutura de aço carbono resistente"},
    ) == "🧡 Cantinho resistente\n#casa"


def test_policy_uses_vision_category_to_ground_footwear_words_and_hashtags():
    context = {
        "productName": "Chinelo feminino com detalhe em strass",
        "category": "calçados",
        "usage": "uso casual",
    }
    assert _normalize_validate(
        "Uso casual\n#chinelo",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Uso casual\n#chinelo"
    assert _normalize_validate(
        "Uso casual.\n#calçados #moda",
            product_name=context["productName"],
            product_context=context,
    ) == "🧡 Uso casual\n#calçados #moda"


def test_policy_does_not_treat_unverified_product_attributes_as_neutral_reactions():
    with pytest.raises(CaptionPolicyError, match="sem suporte"):
        validate_caption(
            "Acidificante 🧡 delicado\n#acidificante",
            product_name="Amend Essencial Acidificante Máscara Equilíbrio do PH - 250g",
            product_context={"productName": "Amend Essencial Acidificante Máscara Equilíbrio do PH - 250g"},
        )


def test_policy_rejects_marketing_claim_not_supported_by_display_feature():
    context = {
        "productName": "Copo térmico com display digital",
        "category": "copo",
    }
    with pytest.raises(CaptionPolicyError, match="sem suporte no contexto Vision"):
        validate_caption(
            "🧡 Tecnologia avançada\n#copo",
            product_name=context["productName"],
            product_context=context,
        )


def test_policy_allows_tampa_only_when_vision_confirms_the_feature():
    context = {
        "productName": "Copo térmico com tampa e trava",
        "category": "copo",
        "description": "Copo térmico com tampa e trava.",
        "attributes": {"tampa": "com trava"},
    }
    assert _normalize_validate(
        "Tampa com trava\n#copo",
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Tampa com trava\n#copo"

    with pytest.raises(CaptionPolicyError, match="palavra proibida: tampa"):
        validate_caption(
            "🧡 Tampa com trava\n#copo",
            product_name="Copo térmico",
            product_context={"productName": "Copo térmico", "category": "copo"},
        )


def test_policy_keeps_packaging_claims_blocked_even_when_context_mentions_them():
    context = {
        "productName": "Frasco com tampa",
        "category": "beleza",
        "description": "Frasco com tampa e lacre.",
    }
    with pytest.raises(CaptionPolicyError, match="palavra proibida"):
        validate_caption(
            "🧡 Frasco com tampa\n#beleza",
            product_name=context["productName"],
            product_context=context,
        )


def test_local_generation_vocabulary_excludes_brand_model_and_technical_terms():
    text_words, hashtags = caption_generation_vocabulary({
        "productName": "Amend Essencial Acidificante Máscara Equilíbrio do PH - 250g",
        "shopName": "AMEND OFICIAL",
        "category": "beleza",
    })
    folded_text = {word.casefold() for word in text_words}
    folded_tags = {word.casefold() for word in hashtags}
    assert {"acidificante", "máscara", "equilíbrio"} <= folded_text
    assert "bonita" not in folded_text and "elegante" not in folded_text
    assert "delicado" not in folded_text and "delicada" not in folded_text
    assert "detalhe" not in folded_text and "visual" not in folded_text
    assert "amend" not in folded_text and "essencial" not in folded_text
    assert "ph" not in folded_text and "250g" not in folded_text
    assert {"acidificante", "máscara", "equilíbrio"} <= folded_tags
    assert "amend" not in folded_tags and "ph" not in folded_tags


def test_policy_restores_accents_from_vision_product_name():
    assert _normalize_validate(
        "Leve e confortável\n#Sandália #Leve",
        product_name="Sandália Feminina Leve Confortável Leve De Dedo",
        product_context={"productName": "Sandália Feminina Leve Confortável Leve De Dedo"},
    ) == "🧡 Leve e confortável\n#Sandália #Leve"

    assert _normalize_validate(
        "Leve e confortável\n#Sandália #Leve",
        product_name="Sandália Feminina Leve Confortável Leve De Dedo",
        product_context={"productName": "Sandália Feminina Leve Confortável Leve De Dedo"},
    ) == "🧡 Leve e confortável\n#Sandália #Leve"


def test_grounded_caption_uses_only_a_supported_category_and_descriptor():
    context = {
        "productName": "Sandália Feminina Leve Confortável Leve De Dedo",
        "itemId": 22299195234,
        "shopId": 1662957095,
        "shopName": "Lessy Shoes",
        "sales": 33,
        "ratingStar": "4.8",
        "imageUrl": "https://example.invalid/image",
    }
    assert compose_safe_caption_fallback(context) == "🧡 Leve e confortável\n#sandalia"


def test_product_type_at_title_start_does_not_hide_following_grounded_descriptor():
    product_name = (
        "Vestido Longo Com FORO e BOJO, Feminino Com manga Variados "
        "super confortáveis e leves qualidade e durabilidade"
    )
    context = {
        "productName": product_name,
        "itemId": 22293819530,
        "description": "Mangas variadas e bojo interno.",
    }
    assert _normalize_validate(
        "Variação nas mangas\n#vestido",
        product_name=product_name,
        product_context=context,
    ) == "🧡 Variação nas mangas\n#vestido"


@pytest.mark.parametrize(
    ("product_name", "expected"),
    [
        (
            "Scarpin Feminino Shekinah Bico Fino Salto Alto Geométrico Taça Tiras Cruzadas Moda",
            "🧡 O bico é fino\n#scarpin",
        ),
        (
            "Amend Essencial Acidificante Máscara Equilíbrio do PH - 250g",
            "🧡 Ação acidificante\n#mascara",
        ),
        (
            "Smartwatch W29 Pro Serie 9 e Relogio inteligente S11 Ilha Dinamica Nfc Armazena e responde Original",
            "🧡 Ilha dinâmica\n#smartwatch",
        ),
    ],
)
def test_grounded_fallbacks_use_one_literal_vision_detail(product_name, expected):
    context = {"productName": product_name}
    raw = compose_safe_caption_fallback(context)
    assert raw == expected
    assert validate_caption(
        raw, product_name=product_name, product_context=context,
    ) == raw


def test_grounded_fallback_does_not_turn_a_negative_title_claim_into_caption():
    assert compose_safe_caption_fallback({
        "productName": "Chinelo feminino NO STRASS Verao 2026"
    }) is None


def test_grounded_fallback_can_use_supported_use_context_and_ignores_sales_copy():
    caption = compose_safe_caption_fallback({
        "productName": "Tênis Feminino Esportes Dia a Dia Treino Casual Promoção"
    })
    assert caption == "🧡 Treino casual\n#tenis"


def test_policy_blocks_only_hard_leaks():
    invalid = (
        "Compre agora 🔥\n#oferta",
        "🧡 Sandália leve essa!\n#sandalia",
        "🧡 A sandália da com.\n#sandalia",
        "Batom matte ✨\n#beleza",
        "Olha isso ✨\n#batommatte",
        "Tramontina linda ✨\n#casa",
        "Pro 900 lindo ✨\n#casa",
        "Medida 10ml ✨\n#beleza",
        "Equilíbrio do 🧡 PH\n#acidificante",
    )
    for caption in invalid:
        with pytest.raises(CaptionPolicyError):
            validate_caption(
                caption,
                product_name="Batom Matte Vermelho",
                product_context={"brand": "Tramontina", "model": "Pro 900"},
            )


def test_provider_makes_one_request_and_returns_up_to_ten(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "configured")
    calls = {"count": 0}
    prompts = []

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return _gemini_response([
                "Compre agora 🔥\n#oferta",
                "Olha esse charme 🧡\n#beleza",
                "Visual bonito 😍\n#beleza",
            ])

    def requester(*args, **kwargs):
        calls["count"] += 1
        prompts.append(kwargs["json"]["contents"][0]["parts"][0]["text"])
        return Response()

    provider = GeminiProvider(requester=requester)
    candidates = provider.generate_candidates("caption", {
        "productName": "Batom Matte Vermelho",
    }, 10)

    assert calls["count"] == 1
    assert len(candidates) == 3
    assert "Gere opções editoriais curtas, naturais e específicas" in prompts[0]
    assert "Não copie o título" in prompts[0]
    assert "não recebe nem deve inferir nada de imagens ou vídeos" in prompts[0]
    assert "Não é necessário declarar um benefício" in prompts[0]
    assert "A menção ao nome comum do produto ou à categoria na frase é opcional" in prompts[0]
    assert "Referência de tom aprovada" not in prompts[0]


def test_caption_selects_valid_candidate_without_second_gemini_call(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def __init__(self):
            self.calls = 0
        def generate_candidates(self, task, context, limit):
            self.calls += 1
            return [
                "Compre agora 🔥\n#oferta",
                "Acabamento matte 🧡\n#beleza",
            ]

    provider = Provider()
    caption = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Batom Matte Vermelho",
        "category": "beleza maquiagem",
    }, force_provider=True).caption

    assert caption == "🧡 Acabamento matte\n#beleza"
    assert provider.calls == 1


def test_caption_ranks_all_valid_candidates_and_keeps_one_provider_call(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")

    class Provider:
        def __init__(self):
            self.calls = 0

        def generate_candidates(self, task, context, limit):
            self.calls += 1
            return [
                    "Cozinha organizada ✨\n#cozinha",
                "Cantinho prático 🧡\n#cozinha",
                    "Organização para cozinha ✨\n#casa",
            ]

    provider = Provider()
    generator = CaptionGenerator(provider=provider)
    result = generator.generate_with_evidence({
        "productName": "Bancada Suspensa",
        "description": "solução prática para cozinha organizada",
    }, force_provider=True)

    assert provider.calls == 1
    assert result.selection.index == 1
    assert result.caption == "🧡 Cozinha organizada\n#cozinha"
    assert len(result.evaluations) == 3
    assert all(evaluation.policy_valid for evaluation in result.evaluations)
    assert result.evaluations[0].selected is True
    assert result.evaluations[0].score > result.evaluations[1].score


def test_all_policy_rejections_retry_once_then_recovery(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "1")

    class Provider:
        def __init__(self):
            self.calls = 0
            self.feedback_seen = []
            self.previous_seen = []
        def generate_candidates(self, task, context, limit):
            self.calls += 1
            self.feedback_seen.append(context.get("__policy_retry_feedback"))
            self.previous_seen.append(context.get("__policy_retry_previous_candidates"))
            if self.calls == 2:
                return [
                    "Cantinho prático 🧡\n#cozinha",
                    "Cozinha prática 🧡\n#cozinha",
                ]
            return [
                "Compre cozinha 🔥\n#cozinha",
                "Bancada suspensa cozinha ✨\n#cozinha",
                "Embalagem linda 😍✨\n#cozinha",
            ]

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Bancada Suspensa Cozinha",
        "category": "cozinha",
        "usage": "cozinha prática",
    }, force_provider=True)

    assert provider.calls == 2
    assert provider.feedback_seen[0] is None
    assert provider.feedback_seen[1]
    assert provider.previous_seen[0] is None
    assert len(provider.previous_seen[1]) == 3
    assert any(
        "linguagem comercial" in reason or "distintiva" in reason
        for reason in provider.feedback_seen[1]
    )
    assert result.provider_requests == 2
    assert result.feedback_rounds
    assert result.caption in {
        "🧡 Cantinho prático\n#cozinha",
        "🧡 Cozinha prática\n#cozinha",
    }


def test_sparse_context_feedback_constrains_retry_to_grounded_name_terms():
    guidance = CaptionGenerator._feedback_guidance(
        ("texto principal contém termo sem suporte no contexto Vision", "hashtag sem relação confiável"),
        product_context={"productName": "Máscara Acidificante PH 250g"},
    )
    assert any("contém apenas o nome do produto" in item for item in guidance)
    assert any("característica textual comprovada" in item for item in guidance)
    assert any("O formatador aplicará o coração e as hashtags" in item for item in guidance)
    assert any("não invente aparência" in item.casefold() for item in guidance)
    assert any("comparação clara" in item for item in guidance)


def test_emoji_feedback_matches_central_formatting_contract():
    guidance = CaptionGenerator._feedback_guidance(("a legenda precisa ter exatamente um coração laranja",))
    assert any("sem emoji" in item for item in guidance)
    assert any("formatador central aplica 🧡" in item for item in guidance)


def test_policy_normalization_is_idempotent_and_only_fixes_formatting():
    context = {"category": "cozinha organizacao", "productName": "Organizador de mesa"}
    first = normalize_caption(
        "  Mesa 😍   bonita 🧡✨\r\n#casa #casa #achados #organizacao  ",
        product_name="Organizador de mesa",
        product_context=context,
    )
    second = normalize_caption(
        first.caption,
        product_name="Organizador de mesa",
        product_context=context,
    )
    assert first.caption == "🧡 Mesa bonita\n#casa #organizacao"
    assert first.corrections
    assert second.caption == first.caption
    assert second.corrections == ()


def test_policy_normalizer_removes_trailing_punctuation_before_hashtags():
    context = {"productName": "Kit Brincos Geométrico Coração"}
    normalized = normalize_caption(
        "Fio geométrico do coração, #brincos",
        product_name=context["productName"],
        product_context=context,
    )
    assert normalized.caption == "🧡 Fio geométrico do coração\n#brincos"
    assert "trailing_punctuation_removed" in normalized.corrections


def test_policy_moves_orange_heart_to_caption_start_and_enforces_contract():
    context = {
        "categoryName": "organização doméstica",
        "description": "organização da mesa",
    }
    normalized = normalize_caption(
        "Mesa 🧡 organizada #casa",
        product_name="Organizador de mesa",
        product_context=context,
    )
    assert normalized.caption == "🧡 Mesa organizada\n#casa"
    assert "orange_heart_moved_to_start" in normalized.corrections
    assert validate_caption(
        normalized.caption, product_name="Organizador de mesa", product_context=context,
    ) == normalized.caption
    with pytest.raises(CaptionPolicyError, match="no início"):
        validate_caption(
            "Mesa 🧡 organizada\n#casa",
            product_name="Organizador de mesa",
            product_context=context,
        )


def test_normalizer_removes_model_meta_label_without_changing_caption_text():
    result = normalize_caption(
        "🧡 Legenda curta: divisão de refeição na bolsa\n#bolsa",
        product_name="Bolsa térmica com compartimento para almoço",
    )
    assert result.caption == "🧡 Divisão de refeição na bolsa\n#bolsa"
    assert "model_caption_label_removed" in result.corrections


def test_policy_accepts_owner_approved_product_grounded_caption_samples():
    samples = [
        (
            "Descascador de Legumes Apontador",
            "🧡 Parece até um apontador\n#descascador #legumes",
        ),
        (
            "Tênis Feminino Casual Camurça Detalhe Lateral Listra Dupla Moderno Break GiGiL",
            "🧡 Listras duplas na lateral\n#tenis",
        ),
        (
            "Senhoras almoço bolsa computador portátil saco com compartimento de almoço isolado acolchoado grande capacidade bolsa de",
            "🧡 Legenda curta: divisão isolada para refeições\n#bolsa",
        ),
        (
            "Copo Térmico de Cafe 450 ml Inox com Display Digital Tampa Trava Mantém Bebidas Quentes ou Frias",
            "🧡 O visor é digital\n#copo",
        ),
    ]
    for product_name, raw in samples:
        normalized = normalize_caption(
            raw,
            product_name=product_name,
            product_context={"productName": product_name},
        ).caption
        assert validate_caption(
            normalized,
            product_name=product_name,
            product_context={"productName": product_name},
        ) == normalized


def test_policy_rejects_vague_filler_after_a_product_fact():
    caption = "🧡 Acinturado, só isso\n#vestido"
    with pytest.raises(CaptionPolicyError, match="expressão vaga"):
        validate_caption(
            caption,
            product_name="Vestido feminino midi acinturado",
            product_context={"productName": "Vestido feminino midi acinturado"},
        )


@pytest.mark.parametrize(
    "caption",
    [
            "Mesa organizada\n#casa",
            "🧡 Mesa organizada 🧡\n#casa",
            "🧡 Mesa organizada\n#casa texto",
            "🧡 Mesa organizada\n#Casa #casa",
    ],
)
def test_policy_remains_strict_when_normalizer_is_bypassed(caption):
    with pytest.raises(CaptionPolicyError):
        validate_caption(
            caption,
            product_name="Organizador de mesa",
            product_context={"category": "casa cozinha organizacao"},
        )


def test_normalizer_does_not_invent_words_or_contextless_hashtags():
    result = normalize_caption("Texto alegre 😍\n#viral #achados")
    assert result.caption == "🧡 Texto alegre"
    with pytest.raises(CaptionPolicyError):
        validate_caption(result.caption)


def test_policy_rejects_unsupported_product_attributes_even_when_hashtag_is_valid():
    with pytest.raises(CaptionPolicyError, match="sem suporte no contexto Vision"):
        validate_caption(
            "Vestido 🧡 floral\n#moda",
            product_name="Chinelo Feminino Casual",
            product_context={"productName": "Chinelo Feminino Casual"},
        )


def test_policy_replaces_unrelated_long_hashtag_compounds_with_grounded_tag():
    result = normalize_caption(
        "Estilo leve 🧡\n#veraofashion",
        product_name="Chinelo feminino verão",
    )
    assert result.caption == "🧡 Estilo leve\n#Chinelo"
    assert "veraofashion" not in result.caption.casefold()
    with pytest.raises(CaptionPolicyError):
        validate_caption(result.caption, product_name="Chinelo feminino verão")


def test_sparse_title_prefix_is_reserved_for_possible_brand_or_product_line():
    context = {
        "productName": "Amend Essencial Acidificante Máscara Equilíbrio do PH 250g",
        "brand": "Amend",
        "model": "Essencial",
    }
    accepted = normalize_caption(
        "Ação acidificante #mascara",
        product_name=context["productName"],
        product_context=context,
    ).caption
    assert validate_caption(
        accepted,
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Ação acidificante\n#mascara"

    unsafe = normalize_caption(
        "Máscara Essencial #essencial",
        product_name=context["productName"],
        product_context=context,
    ).caption
    with pytest.raises(CaptionPolicyError):
        validate_caption(
            unsafe,
            product_name=context["productName"],
            product_context=context,
        )


def test_plain_product_title_prefix_is_not_assumed_to_be_brand_or_model():
    context = {
        "productName": "Moderna Caneca de Cerâmica",
        "attributes": {"material": "cerâmica vitrificada"},
    }
    caption = normalize_caption(
        "Cerâmica vitrificada\n#caneca",
        product_name=context["productName"],
        product_context=context,
    ).caption
    assert validate_caption(
        caption,
        product_name=context["productName"],
        product_context=context,
    ) == "🧡 Cerâmica vitrificada\n#caneca"


def test_provider_retries_transport_but_not_policy(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_POLICY_RETRIES", "0")
    monkeypatch.setenv("GEMINI_API_KEY", "configured")
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("ARMORED_IA_RETRY_DELAY", "0")

    calls = {"count": 0}

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return _gemini_response(["Barbearia prática 🧡\n#barbearia"])

    def requester(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.exceptions.ReadTimeout("temporary")
        return Response()

    provider = GeminiProvider(requester=requester)
    caption = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Bancada Suspensa",
        "usage": "barbearia prática",
    }, force_provider=True).caption

    assert calls["count"] == 3
    assert caption == "🧡 Barbearia prática\n#barbearia"



def test_policy_forces_orange_heart_and_removes_model_emojis():
    assert _normalize_validate(
        "Cantinho resistente 😍✨\n#casa #organizacao",
        product_name="Bancada suspensa",
        product_context={"description": "estrutura de aço carbono resistente"},
    ) == "🧡 Cantinho resistente\n#casa"


def test_policy_adds_orange_heart_when_model_returns_no_emoji():
    assert _normalize_validate(
        "Cantinho prático\n#cozinha",
        product_name="Bancada suspensa",
        product_context={"category": "cozinha", "usage": "prática"},
    ) == "🧡 Cantinho prático\n#cozinha"



def test_policy_deduplicates_hashtags_case_insensitively():
    assert _normalize_validate(
        "Cantinho resistente 😍\n#Casa #casa",
        product_name="Bancada suspensa",
        product_context={"description": "estrutura de aço carbono resistente"},
    ) == "🧡 Cantinho resistente\n#Casa"



@pytest.mark.parametrize(
    "emoji",
    [
        "™️", "©️", "®️", "🇧🇷", "👩🏽‍💻", "1️⃣", "🏳️‍🌈", "🛍️",
    ],
)
def test_policy_removes_compound_and_presentation_emojis(emoji):
    result = _normalize_validate(
        f"Luz suave {emoji} 🧡\n#casa",
        product_name="Abajur artesanal",
        product_context={"description": "luz suave para leitura"},
    )
    assert result == "🧡 Luz suave\n#Abajur"


@pytest.mark.parametrize(
    "caption",
    [
        "Mesa bonita #casa texto",
        "Mesa bonita #casa #",
        "Mesa bonita #casa##decor",
        "Mesa bonita #casa\ufffd",
        "Mesa bonita ?? #casa",
    ],
)
def test_policy_rejects_malformed_hashtags_extra_text_and_corrupted_unicode(caption):
    with pytest.raises(CaptionPolicyError):
        validate_caption(caption, product_name="Organizador")


def test_policy_detects_distinctive_phrase_when_title_stopwords_are_present():
    with pytest.raises(CaptionPolicyError, match="expressão distintiva"):
        validate_caption(
            "🧡 Bolsa feminina tiracolo\n#bolsa",
            product_name="Bolsa feminina tiracolo",
            product_context={"categoryName": "moda"},
        )


def test_separate_contextual_hashtags_are_not_recombined_as_title_phrase():
    assert validate_caption(
        "🧡 Alça fina\n#infantil #algodao",
        product_name="Blusinha regata alça fina infantil menina alcinha algodão",
        product_context={"category": "infantil", "attributes": {"alça": "fina"}},
    ) == "🧡 Alça fina\n#infantil #algodao"


def test_policy_deduplicates_repeated_candidate_hashtags_and_emoji():
    assert _normalize_validate(
        "Cantinho resistente 🛍️\n#Casa #casa",
        product_name="Bancada suspensa",
        product_context={"description": "estrutura de aço carbono resistente"},
    ) == "🧡 Cantinho resistente\n#Casa"



def test_ollama_and_gemini_candidates_share_central_caption_policy(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("ARMORED_IA_PROVIDER", "ollama")
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("ARMORED_IA_MAX_CANDIDATES", "3")
    monkeypatch.setenv("ARMORED_IA_OLLAMA_MAX_CANDIDATES", "3")
    monkeypatch.setenv("ARMORED_IA_RETRY_DELAY", "0")

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return {"response": json.dumps({"captions": [
                "Compre agora #oferta",
                "Cantinho prático 🛍️ #cozinha",
                "Lindo canto #legal",
            ]}, ensure_ascii=False)}

    provider = OllamaProvider(requester=lambda *_args, **_kwargs: Response())
    caption = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Bancada suspensa",
        "category": "cozinha",
        "usage": "prática",
    }, force_provider=True).caption
    assert caption == "🧡 Cantinho prático\n#cozinha"



def test_gemini_and_ollama_use_the_same_final_policy(monkeypatch):
    monkeypatch.setenv("ARMORED_IA_CAPTION_ENABLED", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "configured")
    monkeypatch.setenv("ARMORED_IA_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("ARMORED_IA_RETRY_DELAY", "0")
    calls = []

    class Response:
        def raise_for_status(self):
            return None
        def json(self):
            return _gemini_response([
                "Compre agora 🔥 #oferta",
                "Cantinho prático ™️ #cozinha",
            ])

    def requester(*args, **kwargs):
        calls.append(1)
        return Response()

    caption = CaptionGenerator(
        provider=GeminiProvider(requester=requester)
    ).generate_with_evidence(
        {"productName": "Bancada suspensa", "category": "cozinha", "usage": "prática"},
        force_provider=True,
    ).caption

    assert caption == "🧡 Cantinho prático\n#cozinha"
    assert len(calls) == 1


def test_policy_keeps_exactly_one_orange_heart_when_model_returns_multiple_emojis():
    result = _normalize_validate(
        "Mesa organizada 🧡🧡😍✨\n#casa",
        product_name="Organizador de mesa",
        product_context={"description": "organização da mesa"},
    )
    assert result == "🧡 Mesa organizada\n#casa"
    assert result.count("🧡") == 1


def test_policy_is_strict_while_normalizer_records_safe_formatting_repairs():
    raw = "Mesa organizada 😍🧡🧡  #Casa #casa"
    context = {
        "categoryName": "organização doméstica",
        "description": "organização da mesa",
    }
    with pytest.raises(CaptionPolicyError, match="exatamente um coração"):
        validate_caption(raw, product_name="Organizador de mesa", product_context=context)
    result = normalize_caption(
        raw, product_name="Organizador de mesa", product_context=context,
    )
    assert result.caption == "🧡 Mesa organizada\n#Casa"
    assert "excess_emojis_removed" in result.corrections
    assert "duplicate_hashtag_removed" in result.corrections
    assert "orange_heart_moved_to_start" in result.corrections
    assert validate_caption(
        result.caption, product_name="Organizador de mesa", product_context=context,
    ) == result.caption


def test_policy_replaces_unrelated_generic_hashtag_with_grounded_product_tag():
    result = normalize_caption(
        "Mesa organizada 🧡 #viral",
        product_name="Organizador de mesa",
        product_context={
            "categoryName": "organização doméstica",
            "description": "organização da mesa",
        },
    )
    assert result.caption == "🧡 Mesa organizada\n#Organizador"
    assert "#viral" not in result.caption
    assert result.corrections == (
        "unrelated_hashtag_removed",
        "grounded_hashtag_inserted",
        "orange_heart_moved_to_start",
    )
    assert validate_caption(
        result.caption,
        product_name="Organizador de mesa",
        product_context={
            "categoryName": "organização doméstica",
            "description": "organização da mesa",
        },
    ) == result.caption


def test_normalizer_does_not_rewrite_words_or_repair_policy_content():
    result = normalize_caption(
        "Compre imediatamente 500ml 😍 #oferta #casa",
        product_name="Garrafa térmica para casa",
    )
    assert " ".join(result.caption.split("\n", 1)[0].replace("🧡", "").split()) == "Compre imediatamente 500ml"
    with pytest.raises(CaptionPolicyError, match="linguagem comercial"):
        validate_caption(result.caption, product_name="Garrafa térmica para casa")


@pytest.mark.parametrize("ending", ["em foco", "em destaque"])
def test_policy_rejects_empty_editorial_fillers(ending: str) -> None:
    with pytest.raises(CaptionPolicyError, match="expressão vaga"):
        validate_caption(
            f"🧡 Kimono {ending}\n#kimono",
            product_name="Kimono feminino",
        )


def test_policy_keeps_one_word_product_label_exclusive_to_trusted_fallback() -> None:
    with pytest.raises(CaptionPolicyError, match="2 a 5"):
        validate_caption("🧡 Kimono\n#kimono", product_name="Kimono feminino")


@pytest.mark.parametrize(
    ("extract", "payload"),
    [
        (GeminiProvider._extract_candidates, {"candidates": []}),
        (OllamaProvider._extract_candidates, {"response": "{}"}),
    ],
)
def test_providers_reject_structurally_invalid_caption_payloads(extract, payload):
    with pytest.raises(AIProviderError):
        extract(payload, 10)


@pytest.mark.parametrize(
    ("extract", "payload"),
    [
        (GeminiProvider._extract_candidates, {"candidates": [{
            "content": {"parts": [{"text": json.dumps({"captions": []})}]}
        }]}),
        (OllamaProvider._extract_candidates, {"response": json.dumps({"captions": []})}),
    ],
)
def test_providers_reject_empty_caption_lists(extract, payload):
    with pytest.raises(AIProviderError):
        extract(payload, 10)
