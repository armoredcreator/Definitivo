import pytest

from ArmoredIA.caption.grounded import compose_safe_caption_fallback
from ArmoredIA.caption.policy import (
    caption_product_category_terms,
    normalize_caption,
    validate_caption,
)


def test_pantufa_is_the_primary_product_head_before_a_chinelo_search_alias():
    title = (
        "Pantufa 3D Garra Sulley Azul Rosa Grande Cano Longo Quentinha "
        "Personagem Infantil Adulto - Chinelo Desenho Monstros Sa"
    )
    context = {"productName": title}

    assert caption_product_category_terms(title, context) == ("pantufa",)
    normalized = normalize_caption(
        "Cano longo", product_name=title, product_context=context,
    )
    assert normalized.caption == "🧡 Cano longo\n#Pantufa"


def test_all_caps_strass_attribute_is_not_mistaken_for_a_brand_or_model():
    title = "Chinelo feminino NO STRASS Verao 2026"
    context = {"productName": title, "description": "strass presente"}

    assert validate_caption(
        "🧡 Detalhes em strass\n#chinelo",
        product_name=title,
        product_context=context,
    ) == "🧡 Detalhes em strass\n#chinelo"


def test_oil_nutritive_title_gets_a_natural_grounded_fallback():
    title = "Óleo Nutritivo 3 Em 1 Ox Nutre 120ml"
    context = {"productName": title}

    caption = compose_safe_caption_fallback(context)

    assert caption == "🧡 Nutrição em óleo\n#oleo"
    assert validate_caption(caption, product_name=title, product_context=context) == caption


def test_impecavel_seller_superlative_cannot_pass_by_being_in_title():
    title = "Conjunto Feminino Poá Alfaiataria elegante Colete Miriam e Calça Pantalona Caimento Impecável"
    caption = "🧡 Impecável em miriam e caimento\n#Alfaiataria"

    with pytest.raises(ValueError, match="termo sem suporte"):
        validate_caption(caption, product_name=title, product_context={"productName": title})


def test_product_line_words_not_reused_from_the_title_in_caption():
    title = "Óleo Nutritivo 3 Em 1 Ox Nutre 120ml"
    caption = "🧡 Nutrição em óleo ox nutre\n#oleo"

    with pytest.raises(ValueError, match="termo sem suporte"):
        validate_caption(caption, product_name=title, product_context={"productName": title})


def test_poa_fallback_uses_the_confirmed_pattern_and_product_head():
    title = "Conjunto Feminino Poá Alfaiataria elegante Colete Miriam e Calça Pantalona Caimento Impecável"
    context = {"productName": title}
    caption = compose_safe_caption_fallback(context)

    assert caption == "🧡 Estampa de poá\n#colete"
    assert validate_caption(caption, product_name=title, product_context=context) == caption
