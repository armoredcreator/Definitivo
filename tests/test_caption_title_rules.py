from __future__ import annotations

import pytest

from ArmoredIA.caption.grounded import compose_safe_caption_candidates
from ArmoredIA.caption.generator import CaptionGenerator
from ArmoredIA.caption.selector import CaptionSelector
from ArmoredIA.caption.title_rules import (
    compose_neutral_caption_fallback,
    compose_title_rule_caption,
)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Pantufa 3D Garra Sulley Azul Rosa Grande Cano Longo Quentinha",
            "🧡 Pantufa com cano longo\n#pantufa",
        ),
        (
            "Kit Máscaras Colágeno Trata Olheiras Adesivo Antirrugas Gel Pads Skin Care",
            "🧡 Gel para olheiras\n#mascara",
        ),
        (
            "KIT 4 Cintos Feminino Fino Fivela Básica Dourada Casual Social",
            "🧡 Cintos com fivelas douradas\n#cinto",
        ),
        (
            "Amend Essencial Acidificante Máscara Equilíbrio do PH",
            "🧡 Máscara acidificante capilar\n#mascara",
        ),
        (
            "Kit 2 Tshirt Feminina Blusa Casual Plus Size Moda Blogueira +10 Estampas",
            "🧡 Estampas variadas\n#tshirt",
        ),
        (
            "Bota feminina Gigil bico fino salto alto com zíper",
            "🧡 Zíper e bico fino\n#bota",
        ),
        (
            "Lenço Cachecol Longo Feminino Xadrez Pashimina Sintética Melhores Presentes Inverno",
            "🧡 Cachecol longo em xadrez\n#lenco",
        ),
    ],
)
def test_title_rule_candidates_pass_selector(
    monkeypatch: pytest.MonkeyPatch, title: str, expected: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {"productName": title}

    candidates = compose_safe_caption_candidates(context)
    result = CaptionSelector().evaluate(
        list(candidates), product_name=title, product_context=context,
    )
    selection, _ = CaptionSelector().choose(result, prefer_first_valid=True)

    assert candidates[0] == expected
    assert result[0].policy_valid, result[0].rejection_reason
    assert selection.caption == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Descascador de legumes tipo apontador", "🧡 Parece até um apontador"),
        ("Copo térmico com display digital", "🧡 Copo com display digital"),
        ("Scarpin feminino de bico fino", "🧡 Scarpin de bico fino"),
        ("Blusa feminina de manga longa", "🧡 Blusa de manga longa"),
        ("Bota feminina com bico fino", "🧡 Bota de bico fino"),
        ("Sapatilha feminina de bico fino", "🧡 Sapatilha de bico fino"),
        ("Kit calcinhas de algodão", "🧡 Calcinhas de algodão"),
        ("Casaco feminino de manga longa", "🧡 Casaco de manga longa"),
        ("Relógio de pulso digital", "🧡 Relógio digital"),
        ("Sandália feminina com strass", "🧡 Sandália com strass"),
        ("Pantufa feminina de cano longo", "🧡 Pantufa com cano longo"),
        ("Cintos femininos com fivela dourada", "🧡 Cintos com fivelas douradas"),
        ("Vestido feminino de manga longa", "🧡 Vestido de manga longa"),
    ],
)
def test_catalog_style_composes_product_and_confirmed_detail(
    monkeypatch: pytest.MonkeyPatch, title: str, expected: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {"productName": title}

    result = CaptionGenerator().generate_with_evidence(context)
    evaluation = CaptionSelector().evaluate(
        [result.caption], product_name=title, product_context=context,
    )[0]
    selection, _ = CaptionSelector().choose((evaluation,))

    assert result.caption.splitlines()[0] == expected
    assert result.caption.startswith("🧡 ")
    assert evaluation.policy_valid, evaluation.rejection_reason
    assert selection.caption == result.caption


def test_kimono_plus_size_uses_specific_supported_title_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {
        "productName": "Conjunto kimono Plus Size",
        "itemId": 23694645202,
        "shopId": 691504745,
    }

    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    selected = next(item for item in result.evaluations if item.selected)

    assert result.caption == "🧡 Kimono em versão plus size\n#kimono"
    assert selected.policy_valid, selected.rejection_reason


def test_neutral_fallback_is_only_the_confirmed_product_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "Kimono feminino"
    context = {"productName": title}
    fallback = compose_neutral_caption_fallback(context)

    assert fallback is not None
    assert fallback.full_caption == "🧡 Kimono\n#kimono"
    evaluation = CaptionSelector().evaluate(
        [fallback.full_caption], product_name=title, product_context=context,
    )[0]
    assert evaluation.policy_valid, evaluation.rejection_reason


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Bandas de metal para Apple Watch, pulseira de aço inoxidável", "🧡 Pulseira de metal para relógio"),
        ("Protetores solares faciais FPS 60", "🧡 Protetor solar facial"),
        ("Descascador de alimentos com reservatório", "🧡 Descascador com reservatório"),
        ("Café gourmet torrado e moído 100% arábica", "🧡 Café arábica"),
        ("Camiseta adulto e infantil Brasil comemorativa", "🧡 Camiseta do Brasil"),
        ("Caneca com frases e desenhos", "🧡 Caneca com frases e desenhos"),
        ("Kit sabonete, hidratante e esfoliante para corpo e rosto", "🧡 Cuidados para corpo e rosto"),
        ("Papel adesivo de parede 3D com efeito linho", "🧡 Papel de parede efeito linho"),
        ("Maca Power Collagen tratamento capilar", "🧡 Tratamento capilar com colágeno"),
        ("Estrela do mar de concreto porta-joias decorativo", "🧡 Estrela decorativa de concreto"),
    ],
)
def test_historical_catalog_titles_get_specific_policy_valid_captions(
    monkeypatch: pytest.MonkeyPatch, title: str, expected: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {"productName": title}

    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    evaluation = next(
        item for item in result.evaluations if item.caption == result.caption
    )

    assert result.caption.splitlines()[0] == expected
    assert evaluation.policy_valid, evaluation.rejection_reason


def test_rule_evidence_is_not_taken_from_untrusted_context_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "Pantufa 3D Garra Sulley Azul Rosa Grande Cano Longo Quentinha"
    candidate = "🧡 Exclusivo delicado\n#pantufa"
    context = {
        "productName": title,
        "__title_rule_caption_main": "Exclusivo delicado",
        "__title_rule_category": "pantufa",
        "__title_rule_facts": ["Exclusivo delicado"],
    }

    evaluation = CaptionSelector().evaluate(
        [candidate], product_name=title, product_context=context,
    )[0]

    assert not evaluation.policy_valid


def test_generator_uses_rule_caption_before_calling_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")

    class Provider:
        def generate_candidates(self, *_args: object, **_kwargs: object) -> list[str]:
            raise AssertionError("the local title rule should handle this item")

    title = "Kit Máscaras Colágeno Trata Olheiras Adesivo Antirrugas Gel Pads"
    result = CaptionGenerator(provider=Provider()).generate_with_evidence(
        {"productName": title},
    )

    assert result.caption == "🧡 Gel para olheiras\n#mascara"
    assert result.provider_requests == 0


def test_normal_generation_never_calls_an_injected_external_provider() -> None:
    class Provider:
        calls = 0

        def generate_candidates(self, *_args: object, **_kwargs: object) -> list[str]:
            self.calls += 1
            raise AssertionError("normal caption generation must stay local")

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence({
        "productName": "Livro de colorir com desenhos botânicos",
    })

    assert provider.calls == 0
    assert result.provider_requests == 0
    assert result.caption.startswith("🧡 ")
    assert result.evaluations[-1].policy_valid
    assert result.evaluations[-1].selected


@pytest.mark.parametrize(
    ("title", "expected_tag"),
    [
        ("Kit 6 Potes de Vidro com Tampa de Bambu", "#potes"),
        ("Brinquedo infantil para criança", "#brinquedo"),
        ("Sérum facial com niacinamida", "#serum"),
        ("Joelheiras para proteção do joelho", "#joelheiras"),
        ("Macaquinho feminino estilo vestido com alça ajustável", "#macaquinho"),
    ],
)
def test_neutral_caption_uses_recognized_product_head(
    monkeypatch: pytest.MonkeyPatch, title: str, expected_tag: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    result = CaptionGenerator().generate_with_evidence({"productName": title})

    assert result.caption.startswith("🧡 ")
    assert result.caption.splitlines()[-1] == expected_tag
    assert any(
        evaluation.policy_valid and evaluation.selected
        for evaluation in result.evaluations
    )


def test_coffee_caption_matches_the_owner_approved_editorial_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    result = CaptionGenerator().generate_with_evidence({
        "productName": "Xícara de café em cerâmica",
    })

    assert result.caption.splitlines()[-1] == "#cafe"
    assert result.caption.splitlines()[0] in {
        "🧡 Café quentinho",
        "🧡 O café que você merece",
        "🧡 Um café para acompanhar o dia",
        "🧡 Um momento para o café",
    }
    assert any(
        evaluation.selected and evaluation.policy_valid
        for evaluation in result.evaluations
    )


def test_title_detail_composer_uses_a_confirmed_fact_from_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {
        "productName": "Blusa feminina de algodão com estampa floral",
        "description": "Tecido em algodão com estampa floral.",
    }

    rule = compose_title_rule_caption(context)
    assert rule is not None
    assert rule.full_caption.startswith("🧡 Blusa ")
    candidates = compose_safe_caption_candidates(context)
    assert candidates
    assert candidates[0] == rule.full_caption


def test_empty_travel_bottles_do_not_get_shampoo_product_caption() -> None:
    title = (
        "Frasco Dividido Shampoo Gel de Ducha Condicionador Vazio "
        "Acessórios de Viagem"
    )
    context = {"productName": title}

    assert compose_title_rule_caption(context) is None
    assert "🧡 Shampoo e condicionador\n#shampoo" not in (
        compose_safe_caption_candidates(context)
    )
    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    assert result.caption == "🧡 Acessórios para viagem\n#viagem"
    assert any(item.selected and item.policy_valid for item in result.evaluations)


def test_detail_from_a_later_unrelated_title_clause_is_not_paired_with_product() -> None:
    title = (
        "Bolsa de mão feminina de grande capacidade, jaqueta de algodão leve, "
        "bolsa tote de plumas para ioga"
    )
    context = {"productName": title}

    rule = compose_title_rule_caption(context)
    candidates = compose_safe_caption_candidates(context)

    assert rule is not None
    assert rule.caption == "Bolsa de mão"
    assert "🧡 Bolsa de algodão\n#bolsa" not in candidates
    assert "🧡 É leve\n#bolsa" not in candidates


@pytest.mark.parametrize(
    "title",
    [
        (
            "Óculos de sol polarizados com cor de lente ajustável, "
            "equipados com filtro ND2-400 e lentes protetoras UV400"
        ),
        "Óculos de Natação Infantil com Protetor de Orelha Ajustável, Antiembaçante",
    ],
)
def test_component_adjustability_is_not_applied_to_the_glasses(
    monkeypatch: pytest.MonkeyPatch, title: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )

    assert result.caption != "🧡 Óculos ajustável\n#oculos"
    assert any(item.selected and item.policy_valid for item in result.evaluations)


def test_plural_product_head_agrees_with_its_adjective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "05 Potes de Vidro Hermético Transparente Tampa Bambu Porta Alimentos"
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )

    assert result.caption == "🧡 Potes de vidro\n#potes"
    assert any(item.selected and item.policy_valid for item in result.evaluations)


def test_unrecognized_english_tail_is_not_put_in_a_caption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = (
        "10cm Lovely Twice Plush Toys Animais TWICE Momo Doll Chaveiro "
        "Pingente Keybuckle Presentes Para Crianças"
    )
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )

    assert "keybuckle" not in result.caption.casefold()
    assert any(item.selected and item.policy_valid for item in result.evaluations)


def test_bathroom_bottle_set_does_not_get_shampoo_product_caption() -> None:
    title = "Kit Banheiro 3 peças Frascos Brancos Shampoo Condicionador Sabonete"
    context = {"productName": title}

    assert compose_title_rule_caption(context) is None
    assert "🧡 Shampoo e condicionador\n#shampoo" not in (
        compose_safe_caption_candidates(context)
    )
    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    assert result.caption == "🧡 Itens para o banheiro\n#banheiro"
    assert any(item.selected and item.policy_valid for item in result.evaluations)


def test_high_waist_caption_is_a_natural_feature_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "Saia Longa Plus Size Viscolinho Cintura Alta com Bolsos"
    rule = compose_title_rule_caption({"productName": title})

    assert rule is not None
    assert rule.full_caption == "🧡 Saia de cintura alta\n#saia"


def test_product_specific_facts_distinguish_skirt_and_wide_leg_jeans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    skirt = compose_title_rule_caption({
        "productName": "Saia Longa Plus Size Viscolinho Cintura Alta com Bolsos e Fendas Laterais",
    })
    jeans = compose_title_rule_caption({
        "productName": "Calça Wide Leg Plus Size Jeans Feminina Levanta Bumbum cintura alta",
    })
    jeans_title_order = compose_title_rule_caption({
        "productName": "Calça Jeans Feminina Wide Leg Premium Cintura Alta Levanta Bumbum",
    })

    assert skirt is not None
    assert jeans is not None
    assert jeans_title_order is not None
    assert skirt.full_caption == "🧡 Saia com fendas laterais\n#saia"
    assert jeans.full_caption == "🧡 Calça jeans wide leg\n#calca"
    assert skirt.full_caption != jeans.full_caption
    assert jeans_title_order.full_caption == jeans.full_caption


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Suporte Para Celular Mãozinha Flexível Mesa", "🧡 Suporte para celular"),
        ("Fritadeira Elétrica PAF65A Redstone 6,5L 1700W Air Flow Philco", "🧡 Fritadeira elétrica"),
        ("Mini Árvore de Natal pinheirinho Decoração Natalina Madeira", "🧡 Árvore de madeira"),
        ("Espelho Redondo 50cm com LED Quente e Frio Retroiluminado", "🧡 Espelho redondo"),
        ("Capa De Sofá Com Babados Para Sala", "🧡 Capa de sofá"),
        ("Forma de Gelo Silicone Bandeja 21 Cubos", "🧡 Forma de silicone"),
        ("Rack Com Painel TV até 65 Polegadas Marrom Life Caemmun", "🧡 Rack com painel"),
        ("Gel de Limpeza Automotiva Remoção de Poeira para Saída de Ar", "🧡 Gel de limpeza"),
        ("Mesa de Cabeceira Sole 2 Gavetas Flex", "🧡 Mesa de cabeceira"),
        (
            "Celular Galaxy A17 4G Tela 6.7 128GB Super AMOLED Câmera Tripla 50MP Samsung",
            "🧡 Celular com tela Super AMOLED",
        ),
        (
            "Conjunto 4 Banquetas Ferro E Madeira Regulável e Giratória",
            "🧡 Banquetas de madeira",
        ),
        (
            "Troninho Privadinha Infantil Musical 2x1 Penico Assento Redutor Criança Menino Menina",
            "🧡 Troninho musical",
        ),
        (
            "Sanduicheira Mondial S-20 Master Grill 750W Antiaderente",
            "🧡 Sanduicheira antiaderente",
        ),
        ("Tapete Peludo 2,00 x 1,50 Mt", "🧡 Tapete peludo"),
        (
            "Umidificador De Ar Astronauta 220 ml LED Purificador De Ar",
            "🧡 Umidificador de ar",
        ),
        ("Kit 10 Potes de Vidro Hermético com Tampa de Bambu", "🧡 Potes de vidro"),
        ("Cafeteira Italiana 6 Xícaras Alumínio 300ml", "🧡 Cafeteira de alumínio"),
    ],
)
def test_title_phrase_composer_uses_short_explicit_relations_and_attributes(
    monkeypatch: pytest.MonkeyPatch, title: str, expected: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {"productName": title}

    rule = compose_title_rule_caption(context)
    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    evaluation = CaptionSelector().evaluate(
        [result.caption], product_name=title, product_context=context,
    )[0]

    assert rule is not None
    assert rule.caption == expected.removeprefix("🧡 ")
    assert result.caption.splitlines()[0] == expected
    assert evaluation.policy_valid, evaluation.rejection_reason


def test_title_phrase_composer_does_not_join_ambiguous_product_alternatives() -> None:
    title = "Cadeira Mochila Pesca Camping - Bolsa Térmica - Escolha a Sua"

    assert compose_title_rule_caption({"productName": title}) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Escova Multiuso 3 em 1 Para Limpeza de Garrafas", "🧡 Escova multiuso"),
        ("Caneta Hidrográfica Vai e Vem Com Estojo", "🧡 Caneta hidrográfica"),
        ("Sandália Papete Feminina Sola Alta", "🧡 Sandália papete"),
        ("Câmera DJI Osmo Pocket 3 Creator Combo", "🧡 Câmera de bolso"),
        ("Cadarços Elásticos Para Tênis Sem Amarrar", "🧡 Cadarços elásticos"),
        ("Gaveteiro Empilhável Porta Ovos Duplo", "🧡 Gaveteiro empilhável"),
        ("Móbile Safari com suporte", "🧡 Móbile safari"),
        (
            "Caneca Stitch 450ml Boca Presente Decorativa Oficial Disney Linda",
            "🧡 Caneca decorativa",
        ),
        (
            "Babá Eletrônica Com Monitor Visão Noturna, Câmera c/ Áudio",
            "🧡 Babá eletrônica",
        ),
        (
            "Liquidificador Electrolux 700w 1,5L Experience com Copo de Vidro",
            "🧡 Liquidificador com copo de vidro",
        ),
        ("Calendário de Mesa Permanente Versátil Decorativo", "🧡 Calendário de mesa"),
        ("Smart TV 55 Samsung Crystal UHD 4K", "🧡 Smart TV UHD"),
        (
            "Guarda-Roupa Solteiro 2 Portas de Correr",
            "🧡 Guarda-roupa com portas de correr",
        ),
        (
            "Calça Pantalona Social Alfaiataria Com Cinto De Couro Fino",
            "🧡 Calça pantalona",
        ),
    ],
)
def test_title_grammar_builds_short_grounded_captions(
    monkeypatch: pytest.MonkeyPatch, title: str, expected: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {"productName": title}

    rule = compose_title_rule_caption(context)
    assert rule is not None
    assert rule.caption == expected.removeprefix("🧡 ")

    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    evaluation = CaptionSelector().evaluate(
        [result.caption], product_name=title, product_context=context,
    )[0]
    assert result.caption.splitlines()[0] == expected
    assert evaluation.policy_valid, evaluation.rejection_reason


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Tênis Mormaii Urban Killian Original Masculino 203387",
            "🧡 Tênis masculino",
        ),
        (
            "Smartphone Motorola Moto G35 5G 256GB 4GB RAM Cinza",
            "🧡 Smartphone com conexão móvel",
        ),
        (
            "Kimono Feminino Cardigan Manga 3/4 Soltinho Viscose",
            "🧡 Kimono de manga média",
        ),
        (
            "Smart TV TCL 50 Polegadas QLED 4K P7K WiFi Bluetooth",
            "🧡 Smart TV com alta resolução",
        ),
        (
            "[Novo] Avançado LANEIGE NEO CUSHION MATTE SPF 46+ PA++",
            "🧡 Base cushion com acabamento matte",
        ),
        (
            "Gamesir X2S Tipo C Gamepad Para iPhone Android Controlador De Jogos",
            "🧡 Gamepad para celular",
        ),
        (
            "Presilha De Embalagem Sacos Lacre De Alimentos Tampa",
            "🧡 Presilha para sacos",
        ),
        (
            "Luminaria com Apontador Acoplado",
            "🧡 Luminária com apontador",
        ),
        (
            "Limpador Elétrico de Pincel de Maquiagem Automático USB",
            "🧡 Limpador elétrico",
        ),
    ],
)
def test_title_rule_captions_survive_catalog_policy_regressions(
    monkeypatch: pytest.MonkeyPatch, title: str, expected: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )
    evaluation = CaptionSelector().evaluate(
        [result.caption], product_name=title, product_context={"productName": title},
    )[0]

    assert result.caption.splitlines()[0] == expected
    assert evaluation.policy_valid, evaluation.rejection_reason


def test_generator_uses_neutral_fallback_after_policy_rejects_provider_caption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")

    class Provider:
        calls = 0

        def generate_candidates(self, *_args: object, **_kwargs: object) -> list[str]:
            self.calls += 1
            return ["Premium imperdível para você\n#oferta"]

    provider = Provider()
    result = CaptionGenerator(provider=provider).generate_with_evidence(
        {"productName": "Saída de Praia Plus Size Saída de Banho Grande"},
        force_provider=True,
    )

    assert provider.calls == 1
    assert result.caption.startswith("🧡 ")
    assert result.caption.splitlines()[-1] == "#saidadepraia"
    assert result.evaluations[-1].policy_valid
    assert result.provider_requests == 1


@pytest.mark.parametrize(
    ("title", "expected_main"),
    [
        ("iPhone 18 Pro Max 2TB Prateado", "🧡 Celular no cotidiano"),
        (
            "Apple iPad Mini 7 A17 Pro Tela 8,3 polegadas Wi-fi 128GB",
            "🧡 Tablet no cotidiano",
        ),
    ],
)
def test_phone_and_tablet_titles_do_not_fail_word_count(
    monkeypatch: pytest.MonkeyPatch, title: str, expected_main: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )
    selected = next(item for item in result.evaluations if item.selected)

    assert result.caption.splitlines()[0] == expected_main
    assert selected.policy_valid, selected.rejection_reason


@pytest.mark.parametrize(
    ("title", "wrong_class"),
    [
        ("Pantufa Chinelo Feminino Conforto Peluciada Aberta Borracha", "escrever"),
        ("Sapatilha Feminina Domidona Slingback Bicolor Bico Quadrado Boneca Off White Mocassim", "bonecas"),
        ("Tapete Espuma Peças Pelúcia Quebra Cabeça Macio Criança Piso Quarto Decoração 30x30", "quebra-cabeça para montar"),
        ("Gel de Limpeza Automotiva Remoção de Poeira para Saída de Ar de Carro Teclado e Mais", "teclas"),
        ("Flanela para limpar lentes de óculos e tela de celular", "celular no cotidiano"),
        ("Kit Desenho Infantil para Colorir Patrulha Canina, Lapis de Cor, Adesivos e Massinha", "livro para colorir"),
        ("Cola De Vedação De Furo De Parede Ar Condicionado Tubo De Pia", "climatização para casa"),
        ("Kit Churrasco e Copo Térmico Com Mochila Saco de Presente Dia Dos Pais Cerveja Abridor", "cerveja para compartilhar"),
        ("Kit Manta Cobertor Cobre Leito Colcha Canelada Microfibra Aveludada", "em percal"),
        ("Conjunto Banheiro Lavabo Vidro Sabonete Líquido Porta Escova Casamento", "vidro âmbar"),
        ("Alça Flutuante em neoprene, universal à prova d'água para celular / câmera", "celular no cotidiano"),
        ("KIT 2 CAPAS PROTETOR SOLAR | BLOQUEIA CALOR E SOL NA HORA", "proteção solar na rotina"),
        ("Engraçado Pet Gato Cão Desgaste Chucky Deadly Boneca Cosplay Festa Traje", "bonecas para brincar"),
        ("Glaco Repelente De Água para parabrisa Vidros", "repelente para a rotina"),
        ("Petisqueira De Madeira Arvore De Natal", "árvore de madeira"),
        ("Kit 4 Ejetor Natal Decoração Bolo Cookie Confeitaria Natalino Papai Noel Arvore", "papai noel musical"),
        ("Globo De Neve Natalino M Com LED Vermelho E Azul Papai Noel", "papai noel musical"),
    ],
)
def test_secondary_title_terms_do_not_override_the_primary_product(
    monkeypatch: pytest.MonkeyPatch, title: str, wrong_class: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )
    selected = next(item for item in result.evaluations if item.selected)

    assert selected.policy_valid, selected.rejection_reason
    assert wrong_class.casefold() not in result.caption.casefold()


def test_airpods_max_builtin_smart_case_still_uses_the_headphone_caption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "AirPods Max USB-C Bluetooth Cancelamento de Ruído Smart Case"
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )
    selected = next(item for item in result.evaluations if item.selected)

    assert result.caption.startswith("🧡 Fone com cancelamento de ruído")
    assert selected.policy_valid, selected.rejection_reason


def test_airpods_max_case_accessory_is_not_captioned_as_a_headphone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "Capa protetora compatível com AirPods Max Smart Case"
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )

    assert "fone com" not in result.caption.casefold()


def test_pet_cosplay_caption_uses_the_costume_as_the_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "Engraçado Pet Gato Cão Desgaste Chucky Deadly Boneca Cosplay Festa Traje"
    result = CaptionGenerator().generate_with_evidence(
        {"productName": title}, preserve_previous_caption=False,
    )
    selected = next(item for item in result.evaluations if item.selected)

    assert result.caption.startswith("🧡 Fantasia para pets")
    assert selected.policy_valid, selected.rejection_reason


def test_neutral_fallback_names_product_category_and_ignores_generic_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    title = "Jogo de Toalhas Banhão Gigante 2 Peças Fios Penteados Lumina Karsten"
    context = {"productName": title, "category": "achados"}

    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    selected = next(item for item in result.evaluations if item.selected)

    assert result.caption.startswith("🧡 Toalhas ")
    assert "#achados" not in result.caption
    assert result.caption.splitlines()[-1] in {"#toalha", "#toalhas"}
    assert selected.policy_valid, selected.rejection_reason


def test_reprocessing_keeps_a_valid_caption_when_new_candidates_are_not_better(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    previous = "🧡 Shampoo e condicionador\n#shampoo"
    context = {
        "productName": "Kit Jaborandi Bio Extratus Shampoo e Condicionador - 1L Antiqueda e Crescimento",
        "__previous_caption_to_avoid": previous,
    }

    result = CaptionGenerator().generate_with_evidence(
        context,
        preserve_previous_caption=True,
    )

    assert result.caption == previous


@pytest.mark.parametrize(
    ("title", "expected_main"),
    [
        ("A mulher na suíte 11", "🧡 Uma leitura para a pausa"),
        ("Toque Perolado Metalizado Masterfix 1kg", "🧡 Efeito perolado metalizado"),
        ("REDMAGIC 11S Pro Snapdragon 8 Elite Gen 5", "🧡 Celular no cotidiano"),
        ("Memória Rise Mode Z Series 16GB DDR4 3200Mhz", "🧡 Memória para computador"),
        ("SmartBand Xiaomi Smart Band 9, Tela Amoled", "🧡 Rotina acompanhada no pulso"),
        ("Eletrodomésticos Realista elétrico, cozinha", "🧡 Eletrodomésticos para brincar"),
        ("KIT 2 F. BALLERINE COELHO G 28cmx17cmx5cm", "🧡 Toque lúdico no visual"),
        ("medicube collagen night wrapping mask large 75ml", "🧡 Máscara facial na rotina"),
        ("Uranyx A18 Pro Max NFC 16.128 Gb Memoria", "🧡 Celular no cotidiano"),
        ("BLISTER OVO DE PÁSCOA 150g 10~50 UNIDADES (CHOCO)", "🧡 Doce em preparo"),
        ("Ovo de Pascoa Ursinhos Carinhosos Cacau Show Pascoa 2026", "🧡 Uma surpresa especial"),
        ("Conjunto 1 Tecla Simples + 1 Tomada 20a", "🧡 Interruptor e tomada"),
        ("Garra Pegador De Objetos Flexivel Para Canos", "🧡 Garra flexível para objetos"),
        ("Lorena Media Duarts Atacado", "🧡 Visual para a rotina"),
        ("Prevenção de Estrias na Gravidez: Cuidado Completo", "🧡 Cuidado na gestação"),
    ],
)
def test_catalog_gap_rules_generate_policy_valid_captions(
    monkeypatch: pytest.MonkeyPatch, title: str, expected_main: str,
) -> None:
    monkeypatch.setenv("ARMORED_IA_CAPTION_TITLE_RULES", "1")
    context = {"productName": title}
    result = CaptionGenerator().generate_with_evidence(
        context, preserve_previous_caption=False,
    )
    evaluation = CaptionSelector().evaluate(
        [result.caption], product_name=title, product_context=context,
    )[0]

    assert result.caption.splitlines()[0] == expected_main
    assert evaluation.policy_valid, evaluation.rejection_reason
