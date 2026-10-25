from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

FORBIDDEN_WORDS = {"embalagem", "tampa", "frasco", "lacre"}
SALES_WORDS = {
    "compre", "comprar", "garanta", "garantir", "imperdivel", "imperdível",
    "aproveite", "oferta", "ofertas", "promocao", "promoção", "desconto",
    "corra", "nao perca", "não perca",
}
# Broad Unicode emoji ranges plus legacy emoji-presentation symbols.
# Also remove selectors, joiners, modifiers and keycap/tag components.
EMOJI_RE = re.compile(
    "[\\U0001F1E6-\\U0001F1FF\\U0001F300-\\U0001FAFF"
    "\\U00002300-\\U000023FF\\U00002600-\\U000027BF"
    "\\U00002B00-\\U00002BFF\\U0001FC00-\\U0001FFFF"
    "\\u00A9\\u00AE\\u203C\\u2049\\u2122\\u2139\\u3030\\u303D\\u3297\\u3299]"
)
EMOJI_COMPONENT_RE = re.compile(
    "[\\uFE0E\\uFE0F\\u200D\\u20E3\\U0001F3FB-\\U0001F3FF"
    "\\U000E0020-\\U000E007F]"
)
def _remove_emojis(text: str) -> str:
    value = str(text or "")
    for key in "#*0123456789":
        value = value.replace(key + "\ufe0f\u20e3", "")
        value = value.replace(key + "\u20e3", "")
    value = EMOJI_RE.sub("", value)
    return EMOJI_COMPONENT_RE.sub("", value)
HASHTAG_RE = re.compile(r"(?<!\w)#([\wÀ-ÿ]+)", re.UNICODE)
WORD_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]+(?:['-][A-Za-zÀ-ÿ0-9]+)?", re.UNICODE)
PRODUCT_STOP_WORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e",
    "em", "para", "por", "pro", "pra", "sem", "um", "uma", "o", "os",
    "kit", "conjunto", "original", "novo", "nova", "olha", "olhe",
    "esse", "essa", "isso", "ate",
    # Generic marketplace placeholders do not identify a product category.
    "produto", "produtos", "tipo",
}

_CONTEXT_FIELDS = (
    "productName", "category", "categoryName", "productCategory", "productType",
    "description", "usage", "useCase", "style", "appearance", "attributes",
)
_CATEGORY_FIELDS = ("category", "categoryName", "productCategory", "productType")
_HASHTAG_CONTEXT_ALIASES = {
    "casa": {"casa", "cozinha", "bancada", "mesa", "sala", "quarto", "banheiro", "organizador", "utensilio", "decoracao"},
    "cozinha": {"cozinha", "bancada", "utensilio", "preparo", "culinaria", "cozinhar", "descascador", "legumes", "vegetais"},
    "decor": {"decor", "decoracao", "sala", "quarto", "ambiente", "casa"},
    "decoracao": {"decor", "decoracao", "sala", "quarto", "ambiente", "casa"},
    "organizacao": {"organizacao", "organizador", "gaveta", "prateleira", "armazenamento", "casa", "cozinha"},
    "moda": {"moda", "tenis", "calcado", "calcados", "sapato", "sandalia", "vestuario", "roupa", "feminino", "masculino", "casual", "camurca"},
    "beleza": {"beleza", "batom", "esmalte", "maquiagem", "cosmetico", "unha", "skincare"},
    "iluminacao": {"iluminacao", "luz", "abajur", "luminaria", "lampada"},
    "chinelo": {"calcado", "calcados", "sapato", "sandalia", "tenis", "bota", "sapatilha"},
    "sandalia": {"calcado", "calcados", "sapato", "chinelo", "tenis", "bota", "sapatilha"},
    "tenis": {"calcado", "calcados", "sapato", "sandalia", "chinelo", "bota", "sapatilha"},
    "calcado": {"calcado", "calcados", "sapato", "sandalia", "chinelo", "tenis", "bota", "sapatilha"},
}
_GENERIC_HASHTAGS = {
    "achados", "comprinhas", "viral", "fyp", "trending", "top", "legal",
    "show", "insta", "instagram", "produto", "produtos", "oficial",
}
_NEUTRAL_REACTION_WORDS = {
    "beleza", "bonito", "bonita", "lindo", "linda", "charme", "charmoso",
    "charmosa", "elegante", "visual", "estilo", "look", "cantinho", "canto",
    "olhar", "detalhe", "especial", "parece", "parecem", "olha", "olhe",
    "curti", "gostei", "ate", "esse", "essa", "isso", "um", "uma", "o", "a", "pro", "pra",
}
_GENERATION_REACTION_WORDS = {
    "parece", "olha", "olhe", "curti", "gostei", "bonito", "bonita",
    "lindo", "linda", "charmoso", "charmosa", "elegante", "especial",
}
_COMPARISON_MARKERS = {"parece", "tipo", "como", "lembra"}
_COMPARATIVE_TITLE_NOUNS = {"apontador", "apontadores"}
# Product nouns and the short reaction adjectives exposed to Ollama. The
# caption has only two or three words, so a small morphology check catches
# high-impact agreement errors without pretending to be a full Portuguese
# grammar engine.
_GENDERED_PRODUCT_NOUNS = {
    "escova": ("f", "s"), "escovas": ("f", "p"),
    "descascador": ("m", "s"), "descascadores": ("m", "p"),
    "apontador": ("m", "s"), "apontadores": ("m", "p"),
    "bolsa": ("f", "s"), "bolsas": ("f", "p"),
    "caneca": ("f", "s"), "canecas": ("f", "p"),
    "mesa": ("f", "s"), "mesas": ("f", "p"),
    "cadeira": ("f", "s"), "cadeiras": ("f", "p"),
    "blusa": ("f", "s"), "blusas": ("f", "p"),
    "camisa": ("f", "s"), "camisas": ("f", "p"),
    "sandalia": ("f", "s"), "sandalias": ("f", "p"),
    "panela": ("f", "s"), "panelas": ("f", "p"),
    "mochila": ("f", "s"), "mochilas": ("f", "p"),
    "mascara": ("f", "s"), "mascaras": ("f", "p"),
    "luminaria": ("f", "s"), "luminarias": ("f", "p"),
    "bebida": ("f", "s"), "bebidas": ("f", "p"),
    "chinelo": ("m", "s"), "chinelos": ("m", "p"),
    "cafe": ("m", "s"), "cafes": ("m", "p"),
    # "tênis" has the same written form in singular and plural.
    "tenis": ("m", None), "sapato": ("m", "s"), "sapatos": ("m", "p"),
    "radio": ("m", "s"), "radios": ("m", "p"),
    "sofa": ("m", "s"), "sofas": ("m", "p"),
    "organizador": ("m", "s"), "organizadores": ("m", "p"),
    "abajur": ("m", "s"), "abajures": ("m", "p"),
    "celular": ("m", "s"), "celulares": ("m", "p"),
    "fone": ("m", "s"), "fones": ("m", "p"),
}
_KNOWN_PRODUCT_HEAD_TERMS = (
    (
        set(_GENDERED_PRODUCT_NOUNS)
        | {
        "calcado", "calcados", "chinelo", "sandalia", "sapato", "tenis",
        "bota", "sapatilha", "roupa", "vestuario", "luz", "abajur",
        "luminaria", "lampada", "batom", "esmalte", "maquiagem",
        "cosmetico", "unha", "skincare", "utensilio", "panela",
        "frigideira", "talher", "mesa", "bancada", "escova", "escovas",
        "descascador", "descascadores", "calcinhas", "calcinha", "tanga",
        "esfoliante", "vestido", "poncho", "sutia", "moletom", "pijama",
        "blusa", "blusas", "bandeja", "pincel", "pinceis",
        }
    )
    - {"apontador", "apontadores"}
)
_REACTION_ADJECTIVE_PARADIGMS = {
    "bonit": {("m", "s"): "bonito", ("m", "p"): "bonitos", ("f", "s"): "bonita", ("f", "p"): "bonitas"},
    "lind": {("m", "s"): "lindo", ("m", "p"): "lindos", ("f", "s"): "linda", ("f", "p"): "lindas"},
    "charmos": {("m", "s"): "charmoso", ("m", "p"): "charmosos", ("f", "s"): "charmosa", ("f", "p"): "charmosas"},
    # Temperature terms are common in product captions and must agree in
    # number even though "quente" itself does not change for gender.
    "quent": {("m", "s"): "quente", ("m", "p"): "quentes", ("f", "s"): "quente", ("f", "p"): "quentes"},
    "fri": {("m", "s"): "frio", ("m", "p"): "frios", ("f", "s"): "fria", ("f", "p"): "frias"},
}
_GENDERED_REACTION_ADJECTIVES = {
    form: agreement
    for paradigm in _REACTION_ADJECTIVE_PARADIGMS.values()
    for agreement, form in paradigm.items()
}
_GENDERED_REACTION_ADJECTIVES.update({"quente": ("x", "s"), "quentes": ("x", "p")})
_REACTION_ADJECTIVE_BASE = {
    form: base
    for base, paradigm in _REACTION_ADJECTIVE_PARADIGMS.items()
    for form in paradigm.values()
}
_MAIN_CONTEXT_ALIASES = {
    "descascar": {"descascador", "descascadores", "legumes", "vegetais"},
    "vegetais": {"legumes", "descascador", "descascadores"},
    "infantil": {"infantil", "menina", "menino", "crianca", "roupa"},
    "chinelo": {"calcado", "calcados", "uso", "casual"},
    "sandalia": {"calcado", "calcados", "uso", "casual"},
    "tenis": {"calcado", "calcados", "moda", "casual"},
    "calcado": {"calcado", "calcados", "moda", "casual"},
    "organizada": {"organizador", "organizacao"},
    "organizado": {"organizador", "organizacao"},
    "organizadas": {"organizador", "organizacao"},
    "organizados": {"organizador", "organizacao"},
    "moda": {"feminino", "masculino", "casual", "tenis", "calcado", "sapato", "sandalia", "roupa", "vestuario"},
    "casa": {"cozinha", "bancada", "mesa", "sala", "quarto", "banheiro", "organizador", "utensilio"},
    "cozinha": {"bancada", "utensilio", "preparo", "culinaria", "cozinhar", "descascador", "legumes", "vegetais"},
    "beleza": {"batom", "esmalte", "maquiagem", "cosmetico", "unha", "skincare"},
    "decoracao": {"decor", "sala", "quarto", "ambiente", "casa"},
    "organizacao": {"organizador", "gaveta", "prateleira", "armazenamento", "casa", "cozinha", "mesa"},
    "iluminacao": {"luz", "abajur", "luminaria", "lampada"},
}


@dataclass(frozen=True)
class CaptionNormalization:
    caption: str
    corrections: tuple[str, ...]


class CaptionPolicyError(ValueError):
    pass


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", _fold(value)) if len(token) >= 4]


def _product_phrases(product_name: str) -> set[str]:
    tokens = [token for token in _tokens(product_name) if token not in PRODUCT_STOP_WORDS]
    phrases: set[str] = set()
    if len(tokens) == 2:
        phrases.add(" ".join(tokens))
    # A compact two-word category phrase can be the clearest accurate caption.
    # Reject copied short titles and three-token listing fragments, not short
    # category names drawn from richer Vision context.
    for size in (3,):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrases.add(" ".join(tokens[index:index + size]))
    return phrases


def _hashtag_sequences(product_name: str) -> set[str]:
    tokens = [token for token in _tokens(product_name) if token not in PRODUCT_STOP_WORDS]
    sequences: set[str] = set()
    for size in range(2, min(3, len(tokens)) + 1):
        for index in range(0, len(tokens) - size + 1):
            sequences.add("".join(tokens[index:index + size]))
    return sequences


def _brand_model_tokens(context: dict[str, Any] | None) -> set[str]:
    if not context:
        return set()
    leaked: set[str] = set()
    for key in ("brand", "brandName"):
        value = context.get(key)
        if value:
            leaked.update(_tokens(str(value)))
    for key in ("model", "modelName"):
        value = context.get(key)
        if value:
            for token in re.findall(r"[a-z0-9]+", _fold(str(value))):
                if len(token) >= 2:
                    leaked.add(token)
    # With only a product title, the first two meaningful tokens are
    # ambiguous: marketplaces commonly place a brand, line, or model before
    # the product type. Fail closed on those tokens until Vision supplies
    # structured brand/model metadata; later contextual words remain usable.
    has_structured_identity = any(
        str(context.get(key) or "").strip()
        for key in ("brand", "brandName", "model", "modelName")
    )
    if not has_structured_identity:
        category_tokens: set[str] = set()
        for key in ("category", "categoryName", "productCategory", "productType"):
            category_tokens.update(_tokens(str(context.get(key) or "")))
        title_tokens = [
            token for token in _tokens(str(context.get("productName") or ""))
            if token not in PRODUCT_STOP_WORDS
        ]
        if len(title_tokens) >= 3:
            # Clear product nouns remain usable even in legacy rows whose
            # persisted context contains no structured category.
            known_category_types: set[str] = {
                "calcado", "calcados", "chinelo", "sandalia", "sapato",
                "tenis", "bota", "sapatilha", "roupa", "vestuario",
                "luz", "abajur", "luminaria", "lampada", "batom",
                "esmalte", "maquiagem", "cosmetico", "unha", "skincare",
                "utensilio", "panela", "frigideira", "talher", "organizador",
                "escova", "escovas", "descascador", "descascadores",
                "calcinha", "calcinhas", "tanga", "legumes", "multiuso",
                "almoco", "compartimento", "laser",
                "esfoliante", "vestido", "poncho", "sutia", "moletom",
                "pijama", "blusa", "blusas", "bandeja", "pincel", "pinceis",
            }
            # Older approved Vision rows may have only a product title and a
            # broad category. Recognize the category's product nouns before
            # applying the conservative first-two-token brand/model rule;
            # otherwise ordinary titles such as "Tênis Feminino ..." and
            # "Luminária de mesa ..." lose the very noun needed by the Policy.
            if category_tokens & {
                "calcado", "calcados", "calcadofeminino", "calcadomasculino",
                "moda", "vestuario",
            }:
                known_category_types.update({
                    "calcado", "calcados", "chinelo", "sandalia", "sapato",
                    "tenis", "bota", "sapatilha", "roupa", "vestuario",
                })
            if category_tokens & {"iluminacao", "luz", "lampada"}:
                known_category_types.update({"luz", "abajur", "luminaria", "lampada"})
            if category_tokens & {"beleza", "cosmetico", "cosmeticos"}:
                known_category_types.update({
                    "batom", "esmalte", "maquiagem", "cosmetico", "unha", "skincare",
                })
            if category_tokens & {"cozinha", "utensilio", "utensilios"}:
                known_category_types.update({
                    "utensilio", "panela", "frigideira", "cozinha", "talher",
                })
            leaked.update(token for token in title_tokens[:2] if token not in known_category_types)
    return leaked


def _commercial_or_package_match(text: str) -> str | None:
    folded = _fold(text)
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{re.escape(_fold(word))}\b", folded):
            return f"palavra proibida: {word}"
    for word in SALES_WORDS:
        folded_word = _fold(word)
        if re.search(rf"(?<![a-z0-9]){re.escape(folded_word)}(?![a-z0-9])", folded):
            return f"linguagem comercial proibida: {word}"
    return None


def _technical_leak(text: str) -> bool:
    folded = _fold(text)
    pattern = r"\b\d+(?:[\.,]\d+)?\s?(?:ml|l|litros?|cm|mm|m|kg|g|v|volts?|w|watts?)\b"
    technical_terms = r"\b(?:ph|voltagem|especifica(?:cao|coes))\b"
    return bool(re.search(pattern, folded) or re.search(technical_terms, folded))


def _context_tokens(product_name: str, product_context: dict[str, Any] | None) -> set[str]:
    values = [str(product_name or "")]
    if product_context:
        values.extend(
            str(product_context.get(key) or "")
            for key in _CONTEXT_FIELDS
            if product_context.get(key) not in (None, "", [], {})
        )
    excluded = _brand_model_tokens(product_context)
    tokens: set[str] = set()
    for value in values:
        tokens.update(token for token in _tokens(value) if token not in excluded)
    return tokens


def _context_token_stems(token: str) -> set[str]:
    """Match common Portuguese singular/plural and gender inflections safely."""
    value = str(token)
    variants = {value}
    if len(value) >= 5 and value.endswith("s"):
        variants.add(value[:-1])
    if len(value) >= 5 and value.endswith(("a", "o", "e")):
        variants.add(value[:-1])
    return variants


def caption_product_anchor_terms(
    product_context: dict[str, Any] | None,
    *,
    product_name: str = "",
) -> tuple[str, ...]:
    """Return the category/head terms a short caption should identify.

    Vision's legacy records often contain only a product title plus IDs,
    ratings, and an image URL. In that sparse case, the first meaningful title
    term is the safest available product identity. Rich descriptions or usage
    evidence can support a contextual reaction without forcing title wording.
    """
    context = product_context or {}
    rich_fields = ("description", "usage", "useCase", "appearance", "attributes")
    if any(str(context.get(key) or "").strip() for key in rich_fields):
        return ()

    category_terms: list[str] = []
    for key in _CATEGORY_FIELDS:
        for token in _tokens(str(context.get(key) or "")):
            if token not in PRODUCT_STOP_WORDS and len(token) >= 3:
                category_terms.append(token)
    title = str(product_name or context.get("productName") or "")
    excluded = _brand_model_tokens(context)
    title_tokens = [
        token for token in _tokens(title)
        if token not in PRODUCT_STOP_WORDS and len(token) >= 3
    ]
    product_terms = [token for token in title_tokens if token in _KNOWN_PRODUCT_HEAD_TERMS]
    return tuple(dict.fromkeys((*category_terms, *product_terms)))


def _main_phrase_has_product_anchor(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    anchors = set(caption_product_anchor_terms(
        product_context, product_name=product_name,
    ))
    if not anchors:
        return True

    expanded = set(anchors)
    for term, related in _MAIN_CONTEXT_ALIASES.items():
        if term in anchors:
            expanded.update(related)
        if related & anchors:
            expanded.add(term)

    def stem(token: str) -> str:
        return token[:-1] if len(token) >= 5 and token.endswith(("a", "o", "e", "s")) else token

    expanded_stems = {stem(token) for token in expanded}
    return any(
        _fold(word) in expanded or stem(_fold(word)) in expanded_stems
        for word in words
    )


def _hashtags_have_product_anchor(
    hashtags: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    anchors = {
        _fold(term)
        for term in caption_product_anchor_terms(
            product_context, product_name=product_name,
        )
    }
    if not anchors:
        return True
    for raw_tag in hashtags:
        tag = _fold(raw_tag)
        if tag in anchors:
            return True
        aliases = _HASHTAG_CONTEXT_ALIASES.get(tag)
        if not aliases and tag.endswith("s"):
            aliases = _HASHTAG_CONTEXT_ALIASES.get(tag[:-1])
        if aliases and aliases & anchors:
            return True
    return False


def _secondary_product_noun_is_comparative(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    """Require an explicit comparison before using a secondary product noun."""
    title_nouns = set(_tokens(product_name)) & _COMPARATIVE_TITLE_NOUNS
    primary = set()
    for token in _tokens(product_name):
        if token in _KNOWN_PRODUCT_HEAD_TERMS or token in _GENDERED_PRODUCT_NOUNS:
            primary.add(token)
            break
    secondary = title_nouns - primary
    caption_nouns = {_fold(word) for word in words} & secondary
    if not caption_nouns:
        return True
    for noun in caption_nouns:
        noun_index = next(index for index, word in enumerate(words) if _fold(word) == noun)
        if not any(_fold(word) in _COMPARISON_MARKERS for word in words[:noun_index]):
            return False
    return True


def _main_phrase_is_contextual(
    words: list[str],
    *,
    product_name: str,
    product_context: dict[str, Any] | None,
) -> bool:
    context = _context_tokens(product_name, product_context)
    context_stems = set().union(*(_context_token_stems(value) for value in context)) if context else set()
    grounded = False
    for raw in words:
        token = _fold(raw)
        if token in PRODUCT_STOP_WORDS or len(token) < 3:
            continue
        stem = token[:-1] if len(token) >= 5 and token[-1:] in {"a", "o", "e", "s"} else token
        if token in context or _context_token_stems(token) & context_stems:
            grounded = True
            continue
        if (_MAIN_CONTEXT_ALIASES.get(token, set()) | _MAIN_CONTEXT_ALIASES.get(stem, set())) & context:
            grounded = True
            continue
        if token in _NEUTRAL_REACTION_WORDS or (
            token.endswith("s") and token[:-1] in _NEUTRAL_REACTION_WORDS
        ):
            continue
        return False
    return grounded


def _has_known_agreement_error(words: list[str]) -> bool:
    """Reject clear gender/number mismatches in familiar product phrases."""
    nouns = [
        (index, _GENDERED_PRODUCT_NOUNS[_fold(word)])
        for index, word in enumerate(words)
        if _fold(word) in _GENDERED_PRODUCT_NOUNS
    ]
    adjectives = [
        (index, _GENDERED_REACTION_ADJECTIVES[_fold(word)])
        for index, word in enumerate(words)
        if _fold(word) in _GENDERED_REACTION_ADJECTIVES
    ]
    for adjective_index, adjective in adjectives:
        if not nouns:
            continue
        _noun_index, noun = min(nouns, key=lambda candidate: abs(candidate[0] - adjective_index))
        if (adjective[0] != "x" and adjective[0] != noun[0]) or (
            noun[1] is not None and adjective[1] != noun[1]
        ):
            return True
    return False


def _has_unlinked_product_nouns(words: list[str]) -> bool:
    """Reject a string of product nouns with no natural relation between them."""
    noun_positions = [
        index for index, word in enumerate(words)
        if _fold(word) in _GENDERED_PRODUCT_NOUNS
    ]
    if len(noun_positions) < 2:
        return False
    for left, right in zip(noun_positions, noun_positions[1:]):
        if not any(_fold(word) in PRODUCT_STOP_WORDS for word in words[left + 1:right]):
            return True
    return False


def _has_unnatural_bag_device_relation(words: list[str]) -> bool:
    """Reject a literal ``bag de computer`` construction in Brazilian Portuguese."""
    folded = [_fold(word) for word in words]
    bags = {"bolsa", "bolsas", "mochila", "mochilas", "pasta", "pastas"}
    devices = {"computador", "computadores", "notebook", "notebooks", "laptop", "laptops", "tablet", "tablets"}
    return any(
        folded[index] in bags
        and index + 2 < len(folded)
        and folded[index + 1] == "de"
        and folded[index + 2] in devices
        for index in range(len(folded))
    )


def _normalize_known_agreement(text: str) -> tuple[str, bool]:
    """Safely inflect a known reaction adjective to match its product noun."""
    matches = list(WORD_RE.finditer(text))
    words = [match.group(0) for match in matches]
    nouns = [
        (index, _GENDERED_PRODUCT_NOUNS[_fold(word)])
        for index, word in enumerate(words)
        if _fold(word) in _GENDERED_PRODUCT_NOUNS
    ]
    if not nouns:
        return text, False

    replacements: list[tuple[int, int, str]] = []
    for adjective_index, word in enumerate(words):
        folded = _fold(word)
        base = _REACTION_ADJECTIVE_BASE.get(folded)
        if base is None:
            continue
        _noun_index, noun_form = min(
            nouns, key=lambda candidate: abs(candidate[0] - adjective_index),
        )
        adjective_number = _GENDERED_REACTION_ADJECTIVES[folded][1]
        desired = _REACTION_ADJECTIVE_PARADIGMS[base].get(
            (noun_form[0], noun_form[1] or adjective_number),
        )
        if desired is not None and desired != folded:
            match = matches[adjective_index]
            # Keep initial capitalization while changing only a recognized
            # inflection; accent and semantic content are otherwise stable.
            if word[:1].isupper():
                desired = desired.capitalize()
            replacements.append((match.start(), match.end(), desired))

    if not replacements:
        return text, False
    corrected = text
    for start, end, replacement in reversed(replacements):
        corrected = corrected[:start] + replacement + corrected[end:]
    return corrected, True


def hashtag_context_score(
    hashtag: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> int:
    """Return positive only when the hashtag has persisted product-context support."""
    tag = _fold(str(hashtag or "").lstrip("#"))
    tag_tokens = [token for token in re.findall(r"[a-z0-9]+", tag) if len(token) >= 3]
    if not tag_tokens or any(token in _GENERIC_HASHTAGS for token in tag_tokens):
        return 0
    context = _context_tokens(product_name, product_context)
    score = 0
    for token in tag_tokens:
        if token in context or any(
            len(token) >= 5
            and abs(len(token) - len(other)) <= 2
            and (token.startswith(other) or other.startswith(token))
            for other in context
        ):
            score += 2
            continue
        aliases = _HASHTAG_CONTEXT_ALIASES.get(token, set())
        if not aliases and token.endswith("s"):
            aliases = _HASHTAG_CONTEXT_ALIASES.get(token[:-1], set())
        if aliases & context:
            score += 1
            continue
        for alias, related in _HASHTAG_CONTEXT_ALIASES.items():
            if token == alias and related & context:
                score += 1
                break
    return score if score == len(tag_tokens) * 2 or score > 0 else 0


def caption_generation_vocabulary(
    product_context: dict[str, Any] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return grounded text terms and hashtags safe to constrain an IA schema."""
    context = product_context or {}
    product_name = str(context.get("productName") or "")
    excluded = _brand_model_tokens(context)
    grounded: dict[str, str] = {}
    for key in _CONTEXT_FIELDS:
        value = context.get(key)
        if value in (None, "", [], {}):
            continue
        for surface in WORD_RE.findall(str(value)):
            folded = _fold(surface)
            if (
                len(folded) < 4
                or any(char.isdigit() for char in folded)
                or folded in PRODUCT_STOP_WORDS
                or folded in excluded
                or _technical_leak(surface)
                or _commercial_or_package_match(surface)
            ):
                continue
            grounded.setdefault(folded, surface)

    text_words: list[str] = []
    seen_text: set[str] = set()
    safe_glue = ("de", "da", "do", "para", "com", "em", "a", "o", "um", "uma", "até", "esse", "essa", "pro", "pra")
    for surface in (*grounded.values(), *safe_glue, *_GENERATION_REACTION_WORDS):
        folded = _fold(surface)
        if folded not in seen_text:
            seen_text.add(folded)
            text_words.append(surface)
    hashtags = [
        surface
        for surface in grounded.values()
        if hashtag_context_score(
            surface,
            product_name=product_name,
            product_context=context,
        ) > 0
    ]
    return tuple(text_words[:64]), tuple(hashtags[:32])


def _start_heart(main: str) -> str:
    text = re.sub(r"\s+", " ", main.replace("🧡", " ")).strip()
    return f"🧡 {text}" if text else "🧡"


def normalize_caption(
    caption: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> CaptionNormalization:
    """Apply safe, auditable formatting and known adjective-inflection fixes."""
    raw = str(caption or "")
    corrections: list[str] = []
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if text != raw:
        corrections.append("line_endings_normalized")
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"(?<=[,;:])(?=\S)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text).strip()
    if text != raw.strip():
        corrections.append("whitespace_and_punctuation_normalized")

    matches = list(HASHTAG_RE.finditer(text))
    hashtags = [match.group(1) for match in matches]
    main = HASHTAG_RE.sub("", text)
    main = re.sub(r"\s+", " ", main).strip()

    unique: list[str] = []
    seen: set[str] = set()
    for tag in hashtags:
        folded = _fold(tag)
        if folded in seen:
            corrections.append("duplicate_hashtag_removed")
            continue
        seen.add(folded)
        if hashtag_context_score(
            tag, product_name=product_name, product_context=product_context,
        ) <= 0:
            corrections.append("unrelated_hashtag_removed")
            continue
        unique.append(tag)
    if not unique:
        grounded_context = dict(product_context or {})
        if product_name and not grounded_context.get("productName"):
            grounded_context["productName"] = product_name
        _text_terms, grounded_hashtags = caption_generation_vocabulary(grounded_context)
        for tag in grounded_hashtags:
            if hashtag_context_score(
                tag,
                product_name=product_name,
                product_context=grounded_context,
            ) > 0:
                unique.append(tag)
                corrections.append("grounded_hashtag_inserted")
                break
    if len(unique) > 2:
        ranked = sorted(
            enumerate(unique),
            key=lambda entry: (
                -hashtag_context_score(
                    entry[1], product_name=product_name, product_context=product_context,
                ),
                entry[0],
            ),
        )
        keep_indices = {index for index, _tag in ranked[:2]}
        if len(unique) > 2:
            corrections.append("hashtags_limited_to_two_contextual_tags")
        unique = [tag for index, tag in enumerate(unique) if index in keep_indices]

    main_without_heart = main.replace("🧡", "")
    without_emoji = _remove_emojis(main_without_heart)
    if without_emoji != main_without_heart:
        corrections.append("excess_emojis_removed")
    without_emoji = re.sub(r"\s+", " ", without_emoji).strip()
    without_emoji, agreement_corrected = _normalize_known_agreement(without_emoji)
    if agreement_corrected:
        corrections.append("known_adjective_agreement_inflected")
    heart_at_start = _start_heart(without_emoji)
    raw_heart_count = raw.count("🧡")
    marker = "ARMORED_ORANGE_HEART_MARKER"
    raw_main_with_marker = main.replace("🧡", marker)
    raw_main_keep_heart = _remove_emojis(raw_main_with_marker).replace(marker, "🧡")
    raw_main_keep_heart = re.sub(r"\s+", " ", raw_main_keep_heart).strip()
    if raw_heart_count == 0:
        corrections.append("orange_heart_inserted")
    elif raw_heart_count != 1 or heart_at_start != raw_main_keep_heart:
        corrections.append("orange_heart_moved_to_start")

    normalized = heart_at_start
    if unique:
        normalized += "\n" + " ".join("#" + tag for tag in unique)
    return CaptionNormalization(
        caption=normalized,
        corrections=tuple(dict.fromkeys(corrections)),
    )


def validate_caption(
    caption: str,
    *,
    product_name: str = "",
    product_context: dict[str, Any] | None = None,
) -> str:
    text = str(caption or "")
    if not text:
        raise CaptionPolicyError("legenda vazia")
    if text.count("🧡") != 1:
        raise CaptionPolicyError("a legenda precisa ter exatamente um coração laranja")
    emoji_free = text.replace("🧡", "")
    if EMOJI_RE.search(emoji_free) or EMOJI_COMPONENT_RE.search(emoji_free):
        raise CaptionPolicyError("a legenda contém emoji além do coração laranja")
    if text != text.strip() or "\r" in text or re.search(r"[ \t]{2,}", text):
        raise CaptionPolicyError("formatação não normalizada")
    if re.search(r"\s+[,.;:!?]", text) or re.search(r"[,;:](?=\S)", text):
        raise CaptionPolicyError("pontuação não normalizada")
    if "\ufffd" in text or re.search(r"\?{2,}", text):
        raise CaptionPolicyError("resposta contém Unicode corrompido")

    hashtag_matches = list(HASHTAG_RE.finditer(text))
    raw_hashtags = [match.group(1) for match in hashtag_matches]
    if text.count("#") != len(hashtag_matches):
        raise CaptionPolicyError("hashtag malformada")
    if hashtag_matches:
        if text[hashtag_matches[-1].end():].strip():
            raise CaptionPolicyError("texto extra após as hashtags")
        for left, right in zip(hashtag_matches, hashtag_matches[1:]):
            if text[left.end():right.start()].strip():
                raise CaptionPolicyError("hashtags devem ficar juntas no final")

    hashtags = raw_hashtags
    if len({_fold(tag) for tag in hashtags}) != len(hashtags):
        raise CaptionPolicyError("hashtag duplicada")
    if not 1 <= len(hashtags) <= 2:
        raise CaptionPolicyError("a legenda precisa ter 1 ou 2 hashtags distintas")
    if any(len(tag) > 20 for tag in hashtags):
        raise CaptionPolicyError("hashtag longa demais")

    hard_error = _commercial_or_package_match(text)
    if hard_error:
        raise CaptionPolicyError(hard_error)

    main_text = HASHTAG_RE.sub("", text)
    main = main_text.strip()
    words = WORD_RE.findall(main.replace("🧡", ""))
    if not 2 <= len(words) <= 6:
        raise CaptionPolicyError("texto principal deve conter de 2 a 6 palavras")
    folded_words = [_fold(word) for word in words]
    if len(folded_words) != len(set(folded_words)):
        raise CaptionPolicyError("texto principal repete palavras")
    if not _main_phrase_is_contextual(
        words,
        product_name=product_name,
        product_context=product_context,
    ):
        raise CaptionPolicyError("texto principal contém termo sem suporte no contexto Vision")
    main_has_anchor = _main_phrase_has_product_anchor(
        words, product_name=product_name, product_context=product_context,
    )
    hashtags_have_anchor = _hashtags_have_product_anchor(
        hashtags, product_name=product_name, product_context=product_context,
    )
    if not main_has_anchor and not hashtags_have_anchor:
        raise CaptionPolicyError(
            "legenda precisa identificar a categoria ou substantivo principal no texto ou nas hashtags"
        )
    if _has_unlinked_product_nouns(words):
        raise CaptionPolicyError("texto principal combina substantivos de produto sem ligação natural")
    if not _secondary_product_noun_is_comparative(
        words, product_name=product_name, product_context=product_context,
    ):
        raise CaptionPolicyError(
            "substantivo secundário do título sem ligação natural; use comparação explícita"
        )
    if _has_unnatural_bag_device_relation(words):
        raise CaptionPolicyError(
            "relação pouco natural: bolsa para computador descreve finalidade; não use bolsa de computador"
        )
    if _has_known_agreement_error(words):
        raise CaptionPolicyError("texto principal contém erro de concordância de gênero ou número")

    if not main.startswith("🧡 "):
        raise CaptionPolicyError("coração laranja deve estar no início da legenda")

    if _technical_leak(text):
        raise CaptionPolicyError("legenda revela medida ou especificação técnica")

    # Check copied title phrases only against the main sentence. Separate
    # contextual hashtags can appear next to one another and must not be
    # accidentally recombined into a product-title phrase.
    main_only = HASHTAG_RE.sub("", text)
    folded_caption = _fold(_remove_emojis(main_only))
    normalized_caption_tokens = [
        token for token in WORD_RE.findall(folded_caption)
        if token.casefold() not in PRODUCT_STOP_WORDS
    ]
    normalized_caption = " ".join(normalized_caption_tokens)

    for phrase in _product_phrases(product_name):
        if re.search(rf"\b{re.escape(phrase)}\b", normalized_caption):
            raise CaptionPolicyError("legenda copia expressão distintiva do produto")

    hashtag_tokens = {_fold(tag) for tag in hashtags}
    if hashtag_tokens & _hashtag_sequences(product_name):
        raise CaptionPolicyError("hashtag recompõe explicitamente o produto")

    if _brand_model_tokens(product_context) & set(re.findall(r"[a-z0-9]+", folded_caption)):
        raise CaptionPolicyError("legenda revela marca ou modelo do contexto V1")

    for tag in hashtags:
        if hashtag_context_score(
            tag, product_name=product_name, product_context=product_context,
        ) <= 0:
            raise CaptionPolicyError("hashtag sem relação confiável com o produto")

    # Description/category overlap is deliberately allowed. With only 2–3
    # words available, rejecting ordinary contextual vocabulary causes false
    # negatives and unnecessary Gemini calls.
    if not hashtag_matches or text != f"{main}\n{' '.join('#' + tag for tag in hashtags)}":
        raise CaptionPolicyError("legenda não está na forma canonical da Policy")
    return text
