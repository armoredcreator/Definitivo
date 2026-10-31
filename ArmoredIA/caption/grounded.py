from __future__ import annotations

import re
import unicodedata
from typing import Any

from .policy import caption_product_anchor_terms, caption_product_category_terms


_VISION_FEATURE_PATTERNS = (
    re.compile(r"\bsuper\s+amoled\b", re.IGNORECASE),
    re.compile(r"\bamoled\b", re.IGNORECASE),
    re.compile(r"\btela\s+(?:super\s+)?amoled\b", re.IGNORECASE),
    re.compile(r"\bantiaderente\b", re.IGNORECASE),
    re.compile(r"\bcom\s+brilho\b", re.IGNORECASE),
    re.compile(
        r"\borganiza[cç][aã]o\s+(?:da|de|para)\s+"
        r"(?:casa|cozinha|mesa|gaveta|arm[aá]rio|ambiente)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:a[cç]o\s+inoxid[aá]vel|alum[ií]nio|madeira|vidro|silicone|"
        r"pl[aá]stico|nylon|poli[eé]ster|couro)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bpo[aá]\b", re.IGNORECASE),
    # Preserve compound, distinctive title facts before broad shape/color
    # tokens. The broad "quadrado" match used to consume "digital quadrado"
    # first and leave unrelated products with the same generic fact.
    re.compile(r"\b(?:led\s+)?digital\s+quadrad[oa]\b", re.IGNORECASE),
    re.compile(r"\bvisor\s+digital(?:\s+quadrad[oa])?\b", re.IGNORECASE),
    re.compile(r"\bcorrente\s*(?:e|\+)\s*brinco\b", re.IGNORECASE),
    re.compile(r"\bcl[áa]ssic[oa]\b", re.IGNORECASE),
    re.compile(r"\bcom\s+case\b", re.IGNORECASE),
    re.compile(r"\bdescascador\s+de\s+legumes\s+apontador\b", re.IGNORECASE),
    # Capture only the clothing detail before a numeric seller specification;
    # the percentage is technical noise and must not leak into a caption.
    re.compile(r"\bestampad[oa](?=\s+\d)", re.IGNORECASE),
    re.compile(r"\b(?:tricot|tric[oô])\s+tran[cç]as?|tran[cç]as?\s+(?:tricot|tric[oô])\b", re.IGNORECASE),
    re.compile(r"\bmoda\s+(?:de\s+)?inverno\b", re.IGNORECASE),
    re.compile(r"\b(?:estampa\s+)?xadrez\b", re.IGNORECASE),
    re.compile(r"\b(?:material\s+)?sint[eé]tic[oa]\b", re.IGNORECASE),
    re.compile(r"\b(?:pel[úu]cia\s+interna|interna\s+pel[úu]cia)\b", re.IGNORECASE),
    re.compile(r"\bestilo\s+americano\b", re.IGNORECASE),
    re.compile(r"\bdupla\s+camada\b", re.IGNORECASE),
    re.compile(r"\bl[aã]\s+premium\b", re.IGNORECASE),
    re.compile(r"\breparador\s+de\s+pontas\b", re.IGNORECASE),
    re.compile(r"\b[óo]leo\s+nutritiv[oa]\b", re.IGNORECASE),
    # Keep two separate, title-confirmed backpack details together so the
    # fallback does not turn the single word "leve" into an unsupported
    # comfort claim.
    re.compile(r"\bleve\b.{0,80}\bgrande\s+capacidade\b", re.IGNORECASE),
    re.compile(r"\bleve\s+(?:e\s+)?confort[aá]vel\b", re.IGNORECASE),
    re.compile(r"\b(?:len[çc]o|cachecol|echarpe|pashmina|pashimina)\s+long[oa]\b", re.IGNORECASE),
    re.compile(r"\bcores?\s+variad[oa]s\b", re.IGNORECASE),
    re.compile(r"\b(?:detalhe\s+)?lateral\s+listra\s+dupla\b", re.IGNORECASE),
    re.compile(r"\bcaneta\s+(?:gel\s+)?apag[aá]vel\b", re.IGNORECASE),
    re.compile(r"\bmidi\b", re.IGNORECASE),
    re.compile(r"\bcintura\s+alta\b", re.IGNORECASE),
    re.compile(r"\bacinturad[oa]\b", re.IGNORECASE),
    re.compile(r"\bformato\s+semelhante\s+a\s+(?:um\s+)?apontador\b", re.IGNORECASE),
    re.compile(r"\bdivis[aã]o\s+(?:interna\s+)?(?:para|de)\s+refei[cç](?:[aã]o|[õo]es)\b", re.IGNORECASE),
    re.compile(r"\bcorte\s+a\s+laser\b", re.IGNORECASE),
    re.compile(r"\b(?:a\s+prova\s+d['’]?\s?[aá]gua|dobr[aá]vel|retr[aá]til|ajust[aá]vel|recarreg[aá]vel|transparente|inoxid[aá]vel|controle\s+remoto)\b", re.IGNORECASE),
    # Marketplace titles often use "estampa em cerejinhas" or "estampa com
    # flores". Capture the preposition and its object together; matching only
    # the first token used to reduce these facts to the dangling words "em"
    # or "com", which poisoned both the model prompt and Policy evidence.
    re.compile(r"\bestampa(?:do|da)?\s+(?:(?:de|em|com)\s+)?(?!(?:com|de|em|bojo|forro|cinto|manga|gola)\b)[\w-]+", re.IGNORECASE),
    re.compile(r"\bgola\s+(?:alta|redonda|v|polo|careca)\b", re.IGNORECASE),
    re.compile(r"\bmanga\s+(?:longa|curta|bufante|3/4)\b", re.IGNORECASE),
    re.compile(r"\bcano\s+(?:alto|baixo|m[eé]dio|longo|curto)\b", re.IGNORECASE),
    re.compile(r"\bfivelas?\b", re.IGNORECASE),
    re.compile(r"\bbico\s+(?:fino|quadrado|redondo)\b", re.IGNORECASE),
    re.compile(r"\bsalto\s+(?:alto|bloco|baixo|plataforma)\b", re.IGNORECASE),
    re.compile(r"\btiras?\s+(?:largas?|finas?|cruzadas?)\b", re.IGNORECASE),
    re.compile(r"\bcabo\s+de\s+a[cç]o\b", re.IGNORECASE),
    re.compile(r"\b(?:display|mostrador)\s+digital\b", re.IGNORECASE),
    re.compile(r"\bal[çc]as?\s+(?:finas?|largas?)\b", re.IGNORECASE),
    re.compile(r"\bisolad[oa]\s+acolchoad[oa]\b", re.IGNORECASE),
    re.compile(r"\bbebidas?\s+(?:quentes?|frias?)\b", re.IGNORECASE),
    re.compile(r"\bmatte\b", re.IGNORECASE),
    re.compile(r"\bcaf[eé]\b", re.IGNORECASE),
    re.compile(r"\bcompartimento(?:\s+de)?\s+almo[cç]o\b", re.IGNORECASE),
    re.compile(r"\bcompartimento(?:\s+de\s+almo[cç]o)?\s+(?:t[eé]rmico|isolado|acolchoado)\b", re.IGNORECASE),
    re.compile(r"\bformato\s+(?:quadrado|redondo|oval|retangular)\b", re.IGNORECASE),
    re.compile(r"\bilha\s+din[aâ]mica\b", re.IGNORECASE),
    re.compile(r"\bpingente\s+(?:de\s+)?cora[cç][aã]o\b", re.IGNORECASE),
    re.compile(r"\b(?:cora[cç][aã]o|pingente)\s+(?:liso|de\s+cora[cç][aã]o)\b", re.IGNORECASE),
    # Marketplace titles often invert the natural Portuguese order of a
    # shape and its descriptor ("Geométrico Coração"). Keep the full
    # confirmed detail together so a small local model is not handed the
    # unrelated tail words from the seller's title.
    re.compile(r"\b(?:geom[eé]tric[oa]s?\s+cora[cç][aã]o|cora[cç][aã]o\s+geom[eé]tric[oa]s?)\b", re.IGNORECASE),
    re.compile(r"\bbojo\s+(?:estruturado|refor[cç]ado)\b", re.IGNORECASE),
    # Keep simple apparel construction facts that appear plainly in product
    # titles/descriptions. The specific structured-bojo rule above takes
    # priority over this generic word match.
    re.compile(r"\bforro(?:\s+(?:interno|remov[ií]vel))?\b", re.IGNORECASE),
    re.compile(r"\bbojo\b", re.IGNORECASE),
    re.compile(r"\b(?:m[aá]scara\s+acidificante|acidificante\s+m[aá]scara)\b", re.IGNORECASE),
    re.compile(r"\bgel\s+de\s+limpeza(?:\s+suave)?\b", re.IGNORECASE),
    re.compile(r"\besfoliante\s+corporal(?:\s+[\wÀ-ÿ]+){0,3}\s+banho\b", re.IGNORECASE),
    re.compile(r"\besfoliante\s+corporal\b", re.IGNORECASE),
    re.compile(r"\bpresilha\s+de\s+flor\b", re.IGNORECASE),
    re.compile(r"\bbancada\s+suspensa\b", re.IGNORECASE),
    # Only "sem strass" is an explicit absence claim. Marketplace titles may
    # contain "NO STRASS" as a brand/style label even when the product has
    # decorative strass, so do not interpret that wording as negation.
    re.compile(r"\bsem\s+strass\b", re.IGNORECASE),
    re.compile(r"\bstrass\b", re.IGNORECASE),
    re.compile(r"\bprotetor\s+t[eé]rmico\b", re.IGNORECASE),
    re.compile(r"\bcrescimento\s+capilar\b", re.IGNORECASE),
    re.compile(r"\bcrescimento\b", re.IGNORECASE),
    re.compile(r"\bquadrad[oa]\b", re.IGNORECASE),
    re.compile(r"\bdigital(?:\s+quadrad[oa])?\b", re.IGNORECASE),
    re.compile(r"\b(?:trata|para|combate)\s+olheiras\b", re.IGNORECASE),
    re.compile(r"\b(?:creme\s+)?hidratante\s+(?:facial|corporal|capilar)\b", re.IGNORECASE),
    re.compile(r"\bhidratante\s+para\s+l[aá]bios\b", re.IGNORECASE),
    re.compile(r"\bplataforma\b", re.IGNORECASE),
    re.compile(r"\bbandeja\s+rosa\b", re.IGNORECASE),
    re.compile(r"\bmanga\s+variados\b", re.IGNORECASE),
    re.compile(r"\b[aâ]mbar\b", re.IGNORECASE),
    re.compile(r"\btreino\s+casual\b", re.IGNORECASE),
    re.compile(r"\bmaci[oa]\b", re.IGNORECASE),
    re.compile(r"\btreino\b", re.IGNORECASE),
    re.compile(r"\bleve\b", re.IGNORECASE),
    re.compile(r"\bdourad[oa]s?\b", re.IGNORECASE),
    re.compile(r"\bbluetooth\b", re.IGNORECASE),
    re.compile(r"\b(?:algod[aã]o|tric[oô]|suede|suplex|microfibra|moletinho|inox|inoxid[aá]vel|canelad[oa]|trancad[oa])\b", re.IGNORECASE),
)
_FACT_STOP_WORDS = {
    "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "e",
    "em", "para", "por", "pro", "pra", "um", "uma", "o", "os", "no", "na",
    "nos", "nas", "se", "tem", "possui", "produto", "modelo", "ideal", "perfeito",
    "excelente", "melhor", "incrivel", "incrível", "otimo", "ótimo", "oferta",
    "promocao", "promoção", "compre", "garanta", "descubra", "conforto",
    "solucao", "solução", "pratica", "prática", "pratico", "prático",
    "organizada", "organizado", "versatil", "versátil", "premium",
    "duravel", "durável", "confortavel", "confortável",
}
_TITLE_NOISE_WORDS = {
    "feminino", "feminina", "masculino", "masculina", "unissex",
    "adulto", "adulta", "infantil", "juvenil", "novo", "nova",
    "promocao", "promocional", "frete", "gratis", "gratuito", "grátis",
    "original", "importado", "atacado", "varejo", "kit", "conjunto",
}
_TITLE_CATEGORY_WORDS = {
    "abajur", "anel", "bolsa", "brinco", "blusa", "bota", "calca",
    "camisa", "camiseta", "caneca", "caneta", "chinelo", "colar", "copo",
    "descascador", "esfoliante", "gel", "luminaria", "mochila",
    "organizador", "panela", "pantufa", "pulseira", "sandalia", "sapato",
    "sapatilha", "tenis", "vestido", "relogio", "smartwatch",
}
_TITLE_FEATURE_HEADS = {
    "acabamento", "alca", "alcas", "braco", "bico", "bolso", "bolsos",
    "cabo", "cintura", "divisoria",
    "divisorias", "encaixe", "estampa", "formato", "gola", "ilhos",
    "ilha", "isolamento", "listra", "listras", "manga", "material", "cano",
    "modelagem", "pingente", "ponteira", "recorte", "salto", "textura",
    "tira", "tiras", "trama", "visor",
}


def extract_vision_caption_fact(context: dict[str, Any]) -> str | None:
    """Extract one literal product detail from Vision text or its product title."""
    product_name = str(context.get("productName") or "").strip()
    sources: list[str] = []
    for key in ("description", "attributes", "technicalCharacteristics"):
        value = context.get(key)
        if isinstance(value, dict):
            source = " ".join(
                f"{name} {detail}"
                for name, detail in value.items()
                if str(name).strip() and detail not in (None, "", [], {})
            )
        elif isinstance(value, (list, tuple)):
            source = " ".join(str(part) for part in value if str(part).strip())
        else:
            source = str(value or "").strip()
        if source:
            sources.append(source)
        for pattern in _VISION_FEATURE_PATTERNS:
            match = pattern.search(source)
            if match:
                if _is_no_strass_style_label(source, match.start(), match.group(0)):
                    continue
                fact = match.group(0).strip()
                return _normalize_vision_fact(fact)

    # Vision attributes are not limited to a fixed product catalog. If no
    # known phrase matched, choose a short, literal two- or three-word feature
    # from the structured Vision text, skipping marketing language and phrases
    # copied verbatim from the product title.
    title_tokens = _fold_words(product_name)
    for source in sources:
        for clause in re.split(r"[.;,|\n]+|\s+e\s+", source, flags=re.IGNORECASE):
            words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", clause)
            for size in (2, 3):
                for start in range(max(0, len(words) - size + 1)):
                    candidate_words = words[start:start + size]
                    folded = [_fold_word(word) for word in candidate_words]
                    if any(word in _FACT_STOP_WORDS for word in folded) or any(
                        any(char.isdigit() for char in word) for word in candidate_words
                    ):
                        continue
                    if any(
                        title_tokens[index:index + size] == folded
                        for index in range(max(0, len(title_tokens) - size + 1))
                    ):
                        continue
                    phrase = " ".join(candidate_words)
                    return _normalize_vision_fact(phrase)

    for pattern in _VISION_FEATURE_PATTERNS:
        match = pattern.search(product_name)
        if match:
            if _is_no_strass_style_label(product_name, match.start(), match.group(0)):
                continue
            return _normalize_vision_fact(match.group(0).strip())

    # Product titles are evidence too. When there is no recognized phrase,
    # select a short pair of descriptive title words, excluding category,
    # audience, brand/model, sales language, numbers and specifications.
    title_words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", product_name)
    category_words = {
        _fold_word(term)
        for term in caption_product_anchor_terms(context)
    } | _TITLE_CATEGORY_WORDS
    brand_model_words = {
        _fold_word(context.get(key))
        for key in ("brand", "brandName", "model", "modelName")
        if context.get(key)
    }
    candidates: list[tuple[int, str]] = []
    for index in range(len(title_words) - 1):
        pair = title_words[index:index + 2]
        folded = [_fold_word(word) for word in pair]
        if any(
            word in (_FACT_STOP_WORDS | {
                "muito", "muita", "muitos", "muitas", "lindo", "linda",
                "lindos", "lindas", "elegante", "elegantes", "moderno",
                "moderna", "modernos", "modernas", "estiloso", "estilosa",
            })
            or word in _TITLE_NOISE_WORDS
            or word in category_words
            or word in brand_model_words
            or any(char.isdigit() for char in word)
            for word in folded
        ):
            continue
        # The attribute noun must lead the pair. Accepting a material before
        # the noun produced fragments such as "Nylon cabo".
        if folded[0] not in _TITLE_FEATURE_HEADS:
            continue
        if folded[0] == "pingente" and folded[1] not in {
            "coracao", "cruz", "estrela", "flor", "foto", "inicial", "letra",
        }:
            continue
        # Only use a title pair anchored by a recognizable attribute noun;
        # arbitrary adjacent words often come from spammy marketplace titles.
        candidates.append((index, " ".join(pair)))
    if candidates:
        return _normalize_vision_fact(candidates[0][1])
    return None


def extract_vision_caption_facts(
    context: dict[str, Any], *, limit: int = 10
) -> tuple[str, ...]:
    """Collect distinct, explicit product details from all semantic Vision fields.

    Structured descriptions and attributes have priority over title text.
    Within each source, specific feature patterns are considered before broad
    words. Commercial metadata is deliberately ignored.
    """
    source_keys = (
        "description", "attributes", "technicalCharacteristics",
        "usage", "useCase", "style", "appearance", "productName",
    )
    sources: list[str] = []

    def flatten(value: Any) -> str:
        if isinstance(value, dict):
            return " ".join(
                f"{name} {flatten(detail)}"
                for name, detail in value.items()
                if str(name).strip() and detail not in (None, "", [], {})
            )
        if isinstance(value, (list, tuple, set)):
            return " ".join(flatten(part) for part in value if part not in (None, "", [], {}))
        return str(value or "").strip()

    for key in source_keys:
        source = flatten(context.get(key))
        if source:
            sources.append(source)

    facts: list[str] = []
    seen: set[str] = set()
    for source in sources:
        matches: list[tuple[int, int, int, str]] = []
        for priority, pattern in enumerate(_VISION_FEATURE_PATTERNS):
            for match in pattern.finditer(source):
                if _is_no_strass_style_label(source, match.start(), match.group(0)):
                    continue
                matches.append((priority, match.start(), match.end(), match.group(0).strip()))
        # The pattern list puts specific attributes ahead of generic words,
        # so an incidental material word cannot outrank a distinctive feature.
        matches.sort(key=lambda item: (item[0], item[1], -(item[2] - item[1])))
        occupied_spans: list[tuple[int, int]] = []
        for _priority, start, end, raw_fact in matches:
            if any(start < used_end and end > used_start for used_start, used_end in occupied_spans):
                continue
            fact = _normalize_vision_fact(raw_fact)
            folded = _fold_word(fact)
            if not fact or folded in seen:
                occupied_spans.append((start, end))
                continue
            seen.add(folded)
            facts.append(fact)
            occupied_spans.append((start, end))
            if len(facts) >= max(1, min(int(limit), 10)):
                return tuple(facts)

    # Preserve the existing conservative extractor for attributes that do not
    # match a known phrase pattern, rather than discarding a usable record.
    if not facts:
        fallback = extract_vision_caption_fact(context)
        if fallback:
            facts.append(fallback)
    return tuple(facts[:max(1, min(int(limit), 10))])


def _is_no_strass_style_label(source: str, start: int, fact: str) -> bool:
    """Do not turn the all-caps style label ``NO STRASS`` into a positive fact."""
    if _fold_word(fact) != "strass":
        return False
    return bool(re.search(r"\bno\s+$", source[:start], flags=re.IGNORECASE))


def salvage_confirmed_fact_prefix(candidate: str, context: dict[str, Any]) -> str | None:
    """Trim an unsupported model tail only when the remaining lead is Vision-backed.

    This is a safety repair for small local models that append benefits or filler
    to a real product fact. It never invents words: the kept content words must
    match an extracted Vision fact or a structured Vision attribute.
    """
    visible = re.sub(r"#[\wÀ-ÿ]+", " ", str(candidate or ""), flags=re.UNICODE)
    visible = visible.replace("🧡", " ").strip()
    matches = list(re.finditer(r"[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*", visible))
    if not matches:
        return None
    words = [_fold_word(match.group(0)) for match in matches]
    if any(word in {"nao", "nunca", "jamais", "sem"} for word in words):
        return None

    stop_words = _FACT_STOP_WORDS | {
        "em", "com", "de", "do", "da", "dos", "das", "no", "na", "nos", "nas",
        "para", "por", "pro", "pra", "e", "o", "a", "os", "as", "um", "uma",
        "tem", "possui", "esta", "estao", "e", "sao",
    }
    fact_sequences: set[tuple[str, ...]] = set()
    for fact in extract_vision_caption_facts(context):
        sequence = tuple(word for word in _fold_words(fact) if word not in stop_words)
        if len(sequence) >= 2:
            fact_sequences.add(sequence)

    def add_attribute_sequences(value: Any, parents: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                add_attribute_sequences(nested, (*parents, str(key)))
            return
        if isinstance(value, (list, tuple, set)):
            for nested in value:
                add_attribute_sequences(nested, parents)
            return
        if value in (None, "") or not parents:
            return
        combined = " ".join((*parents, str(value)))
        sequence = tuple(
            word for word in _fold_words(combined)
            if word not in stop_words and not any(char.isdigit() for char in word)
        )
        if len(sequence) >= 2:
            fact_sequences.add(sequence)

    for field in ("attributes", "technicalCharacteristics"):
        add_attribute_sequences(context.get(field))
    if not fact_sequences:
        return None

    safe_prefix_words = {
        "o", "a", "os", "as", "um", "uma", "esse", "essa", "este", "esta",
        "olha", "olhe", "veja", "parece", "ate",
    }
    connectors = {
        "a", "as", "ao", "aos", "com", "da", "das", "de", "do", "dos", "em",
        "na", "nas", "no", "nos", "para", "por", "pra", "pro", "e", "tem",
        "possui", "esta", "estao", "sao",
    }
    ordered_sequences = sorted(fact_sequences, key=lambda sequence: (-len(sequence), sequence))
    for start in range(len(words)):
        prefix = words[:start]
        if any(word not in safe_prefix_words for word in prefix):
            continue
        for sequence in ordered_sequences:
            cursor = start
            for fact_word in sequence:
                while cursor < len(words) and cursor > start and words[cursor] in connectors:
                    cursor += 1
                if cursor >= len(words) or words[cursor] != fact_word:
                    break
                cursor += 1
            else:
                end = matches[cursor - 1].end()
                repaired = visible[:end].strip(" \t\r\n.,;:!?")
                if len(re.findall(r"[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*", repaired)) >= 2:
                    return repaired

    # A local model may keep a Vision-supported comparison but append an
    # unsupported flourish (for example, "É como um apontador miniaturizado").
    # Preserve only the comparison through the first confirmed Vision noun;
    # this uses no fixed product catalog and never adds words.
    fact_words = {word for sequence in fact_sequences for word in sequence}
    category_words = {
        _fold_word(term) for term in caption_product_anchor_terms(context)
    }
    comparison_words = {"parece", "parecem", "lembra", "lembram", "como", "tipo"}
    supported_terms = {
        word for word in fact_words - stop_words - category_words - comparison_words
        if len(word) >= 4
    }
    comparison_markers = comparison_words | {"pareceu", "pareciam"}
    allowed_before_marker = safe_prefix_words | {"e", "ate"}
    articles = {"um", "uma", "o", "a", "os", "as"}
    optional_comparison_words = {"ate"}
    for marker_index, marker in enumerate(words):
        if marker not in comparison_markers:
            continue
        if any(word not in allowed_before_marker for word in words[:marker_index]):
            continue
        for noun_index in range(marker_index + 1, len(words)):
            if words[noun_index] not in supported_terms:
                continue
            between = words[marker_index + 1:noun_index]
            if len(between) > 4:
                continue
            # Keep the comparison and its article, but drop unsupported model
            # modifiers such as "pequeno". That preserves the idea grounded
            # in Vision without turning a guessed size/quality into a claim.
            article_index = next(
                (index for index in range(len(between) - 1, -1, -1) if between[index] in articles),
                None,
            )
            if article_index is None and any(
                word not in optional_comparison_words for word in between
            ):
                continue
            if article_index is not None and any(
                word not in optional_comparison_words
                for word in between[:article_index]
            ):
                continue
            prefix = visible[:matches[marker_index].start()].strip(" \t\r\n.,;:!?")
            marker_text = matches[marker_index].group(0)
            noun_text = matches[noun_index].group(0)
            phrase = [part for part in (prefix, marker_text) if part]
            if article_index is not None:
                phrase.extend(
                    matches[marker_index + 1 + index].group(0)
                    for index in range(len(between))
                    if between[index] == "ate"
                )
                phrase.append(matches[marker_index + 1 + article_index].group(0))
            phrase.append(noun_text)
            repaired = " ".join(phrase).strip(" \t\r\n.,;:!?")
            if len(re.findall(r"[A-Za-zÀ-ÿ]+(?:[-'][A-Za-zÀ-ÿ]+)*", repaired)) >= 2:
                return repaired
    return None


def _fold_words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold_word(value))


def _fold_word(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _normalize_vision_fact(fact: str) -> str:
    fact = re.sub(
        r"^(?:led\s+)?digital\s+quadrad[oa]$|^visor\s+digital\s+quadrad[oa]$",
        "Visor digital quadrado",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(r"^visor\s+digital$", "Visor digital", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^estilo\s+americano$", "Estilo americano", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^dupla\s+camada$", "Dupla camada", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^l[aã]\s+premium$", "Lã", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^reparador\s+de\s+pontas$", "Óleo para as pontas", fact, flags=re.IGNORECASE)
    # Keep this seller-title benefit as a natural, supported caption fact
    # instead of returning the exact category+attribute fragment that Policy
    # correctly rejects as a catalog label.
    fact = re.sub(r"^[óo]leo\s+nutritiv[oa]$", "Nutrição em óleo", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^po[aá]$", "Estampa de poá", fact, flags=re.IGNORECASE)
    if re.match(r"^esfoliante\s+corporal\b", fact, flags=re.IGNORECASE) and re.search(
        r"\bbanho$", fact, flags=re.IGNORECASE,
    ):
        fact = "Esfoliação corporal no banho"
    fact = re.sub(
        r"^leve\b.{0,80}\bgrande\s+capacidade$",
        "Leve e com grande capacidade",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(r"^leve\s+confort[aá]vel$", "Leve e confortável", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^strass$", "Detalhes em strass", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^matte$", "Acabamento matte", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^caf[eé]$", "Café", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^(?:estampa\s+)?xadrez$", "Estampa xadrez", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^(?:material\s+)?sint[eé]tic[oa]$", "Material sintético", fact, flags=re.IGNORECASE)
    fact = re.sub(
        r"^(?:pel[úu]cia\s+interna|interna\s+pel[úu]cia)$",
        "Pelúcia interna",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^(?:len[çc]o|cachecol|echarpe|pashmina|pashimina)\s+long[oa]$",
        "Comprimento longo",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(r"^cores?\s+variad[oa]s$", "Cores variadas", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^fivelas?$", "Detalhes com fivelas", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^canelad[oa]$", "Textura canelada", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^algod[aã]o$", "Algodão", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^cl[áa]ssic[oa]$", "Estilo clássico", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^com\s+case$", "Acompanha case", fact, flags=re.IGNORECASE)
    fact = re.sub(
        r"^corrente\s*(?:e|\+)\s*brinco$",
        "Corrente e brinco no conjunto",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^(?:tricot|tric[oô])\s+tran[cç]as?$|^tran[cç]as?\s+(?:tricot|tric[oô])$",
        "Tranças em tricô",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(r"^moda\s+(?:de\s+)?inverno$", "Clima de inverno", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^estampad[oa]$", "Um toque de estampa", fact, flags=re.IGNORECASE)
    fact = re.sub(
        r"^descascador\s+de\s+legumes\s+apontador$",
        "Parece até um apontador",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^(?:detalhe\s+)?lateral\s+listra\s+dupla$",
        "Listras duplas na lateral",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^caneta\s+(?:gel\s+)?apag[aá]vel$",
        "Caneta apagável",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^formato\s+semelhante\s+a\s+(?:um\s+)?apontador$",
        "Parece até um apontador",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^acidificante\s+m[aá]scara$",
        "Máscara acidificante",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^estampa\s+(?:de|em|com)\s+([\w-]+)$",
        r"Estampa de \1",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^estampa\s+(?:de\s+)?([\w-]+)$",
        r"Estampa de \1",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^pingente\s+(?:de\s+)?cora[cç][aã]o$",
        "Pingente de coração",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(
        r"^geom[eé]tric[oa]s?\s+cora[cç][aã]o$",
        "Coração geométrico",
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(r"^presilha\s+de\s+flor$", "Detalhe floral", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^bandeja\s+rosa$", "Tonalidade rosa", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^estampado\s+floral$", "Estampa floral", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^protetor\s+t[eé]rmico$", "Proteção térmica", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^crescimento\s+capilar$", "Foco no crescimento capilar", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^crescimento$", "Foco no crescimento", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^quadrad[oa]$", "Formato quadrado", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^digital(?:\s+quadrad[oa])?$", "Visor digital quadrado", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^(?:trata|para|combate)\s+olheiras$", "Cuidado para olheiras", fact, flags=re.IGNORECASE)
    fact = re.sub(
        r"^(?:creme\s+)?hidratante\s+(facial|corporal|capilar)$",
        lambda match: "Hidratação " + match.group(1).casefold(),
        fact,
        flags=re.IGNORECASE,
    )
    fact = re.sub(r"^hidratante\s+para\s+l[aá]bios$", "Hidratação labial", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^plataforma$", "Solado plataforma", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^cintura\s+alta$", "Cintura alta", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^manga\s+variados$", "Variação nas mangas", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^treino\s+casual$", "Treino casual", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^[aâ]mbar$", "Tom âmbar", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^ilha\s+din[aâ]mica$", "Ilha dinâmica", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^maci[oa]$", "Toque macio", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^treino$", "Uso no treino", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^leve$", "Leve", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^dourad[oa]s?$", "Acabamento dourado", fact, flags=re.IGNORECASE)
    fact = re.sub(r"^bluetooth$", "Conexão Bluetooth", fact, flags=re.IGNORECASE)
    fact = fact.lower()
    return fact[:1].upper() + fact[1:]


def caption_prompt_context(context: dict[str, Any]) -> dict[str, Any]:
    """Give local models the Vision title and semantic fields, excluding commerce data."""
    categories = [
        str(context.get(key) or "").strip()
        for key in ("category", "categoryName", "productCategory", "productType")
        if str(context.get(key) or "").strip()
    ]
    if not categories:
        categories = list(caption_product_anchor_terms(context))
    title = str(context.get("productName") or "")
    category_terms = caption_product_category_terms(title, context)
    category = categories[0] if categories else (
        category_terms[0] if category_terms else title[:80] or "produto"
    )
    facts = extract_vision_caption_facts(context)
    prompt_context: dict[str, Any] = {
        "__vision_category": category,
        "__vision_confirmed_facts": list(facts),
    }
    # A product title is often the only substantive evidence returned by the
    # Vision lookup. Keep it available to the model for broad catalog coverage;
    # the prompt instructs the model to understand the item from it without
    # copying it into the caption. Preserve structured Vision fields as well.
    for key in (
        "productName", "category", "categoryName", "productCategory", "productType",
        "description", "attributes", "technicalCharacteristics",
        "usage", "useCase", "style", "appearance",
    ):
        value = context.get(key)
        if value not in (None, "", [], {}):
            prompt_context[key] = value
    return prompt_context


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


def compose_grounded_caption(context: dict[str, Any]) -> str | None:
    """Return a specifically approved editorial form for known examples.

    Other product details are handled as separate grounded candidates below;
    this function intentionally avoids broad, repetitive title templates.
    """
    title = _fold(str(context.get("productName") or ""))
    if not title:
        return None

    if re.search(r"\bdescascador\b.*\bapontador\b", title):
        return "Parece até um apontador\n#descascador #legumes"

    if re.search(r"\bcorte\s+a\s+laser\b", title) and re.search(
        r"\b(tanga|calcinha|calcinhas)\b", title
    ):
        return "Olha esse corte a laser\n#tanga #laser"

    return None


def compose_safe_caption_fallback(context: dict[str, Any]) -> str | None:
    """Compose a short, local caption from Vision facts, including title details."""
    candidates = compose_safe_caption_candidates(context, limit=1)
    return candidates[0] if candidates else None


def compose_safe_caption_candidates(
    context: dict[str, Any], *, limit: int = 10
) -> tuple[str, ...]:
    """Create one policy-checkable caption candidate per supported Vision fact."""
    # Prefer short editorial forms built from closed title patterns. These
    # rules are category-gated and carry explicit source evidence; unmatched
    # titles continue through the existing Vision-fact composer below.
    from .title_rules import compose_title_rule_caption, title_rules_enabled

    rule_caption = compose_title_rule_caption(context) if title_rules_enabled() else None
    candidates: list[str] = [rule_caption.full_caption] if rule_caption else []
    if len(candidates) >= max(1, min(int(limit), 10)):
        return tuple(candidates)

    facts = extract_vision_caption_facts(context, limit=limit)
    title = str(context.get("productName") or "").strip()
    categories = caption_product_category_terms(title, context)
    if facts and title and categories:
        from .title_rules import title_fact_is_attached_to_product

        facts = tuple(
            fact for fact in facts
            if title_fact_is_attached_to_product(title, categories[0], fact)
        )
    if not facts:
        return tuple(candidates)

    anchors = caption_product_anchor_terms(context)
    if not anchors:
        # Rich Vision descriptions intentionally do not force the product name
        # into the sentence. The safe fallback still needs one grounded topic
        # hashtag, so resolve it from a known product head or explicit category.
        anchors = caption_product_anchor_terms({
            "productName": str(context.get("productName") or ""),
        })
    if not anchors:
        category = next((
            str(context.get(key) or "").strip()
            for key in ("category", "categoryName", "productCategory", "productType")
            if str(context.get(key) or "").strip()
        ), "")
        category_tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]+", category)
        if category_tokens:
            anchors = (category_tokens[0],)
    if not anchors:
        return tuple(candidates)
    seen: set[str] = {_fold(value) for value in candidates}
    fact_labels = {_fold(fact) for fact in facts}
    has_print = any(
        fact == "um toque de estampa" or fact.startswith("estampa ")
        for fact in fact_labels
    )
    has_cotton = any(fact in {"algodao", "tecido em algodao"} for fact in fact_labels)
    if has_cotton and has_print:
        combined = f"🧡 Algodão com estampa\n#{anchors[0].casefold()}"
        if _fold(combined) not in seen:
            candidates.append(combined)
            seen.add(_fold(combined))
    candidate_limit = max(1, min(int(limit), 10))
    for fact in facts:
        main_variants = [_compose_fallback_main(fact)]
        comparison = re.fullmatch(
            r"parece(?:\s+até)?\s+(um|uma)\s+(.+)",
            str(fact).strip(),
            flags=re.IGNORECASE,
        )
        if comparison:
            main_variants.append(f"É como {comparison.group(1).casefold()} {comparison.group(2)}")
        for main in main_variants:
            caption = f"🧡 {main}\n#{anchors[0].casefold()}"
            folded_caption = _fold(caption)
            if folded_caption not in seen:
                candidates.append(caption)
                seen.add(folded_caption)
            if len(candidates) >= candidate_limit:
                break
        if len(candidates) >= candidate_limit:
            break
    return tuple(candidates)


def _compose_fallback_main(fact: str) -> str:
    if _fold(fact).startswith("parece ate um apontador"):
        return fact
    fact_folded = _fold(fact)
    if fact_folded == "estilo classico":
        return "Estilo clássico"
    if fact_folded == "estilo americano":
        return "Estilo americano"
    if fact_folded == "leve":
        return "É leve"
    if fact_folded == "acompanha case":
        return "Acompanha case"
    if fact_folded == "corrente e brinco no conjunto":
        return "Corrente e brinco no conjunto"
    if fact_folded == "caneta apagavel":
        return "A escrita pode ser apagada"
    if fact_folded == "midi":
        return "Comprimento midi"
    if fact_folded in {"acinturado", "acinturada"}:
        return "Cintura marcada"
    if fact_folded == "oversized":
        return "Modelagem oversized"
    if fact_folded in {"algodao", "la", "microfibra", "moletinho", "suede", "suplex", "trico"}:
        material = {
            "algodao": "algodão", "la": "lã", "microfibra": "microfibra", "moletinho": "moletinho",
            "suede": "suede", "suplex": "suplex", "trico": "tricô",
        }[fact_folded]
        return f"Tecido em {material}"
    if fact_folded == "canelada":
        return "Textura canelada"
    if fact_folded == "cabo plastico":
        return "Cabo em plástico"
    if fact_folded == "tonalidade rosa":
        return fact
    if fact_folded == "cintura alta":
        return "Modelagem de cintura alta"
    if fact_folded == "variacao nas mangas":
        return fact
    if fact_folded == "treino casual":
        return fact
    if fact_folded == "tom ambar":
        return fact
    if fact_folded == "formato quadrado":
        return fact
    if fact_folded == "visor digital quadrado":
        return fact
    if fact_folded == "conexao bluetooth":
        return "Conexão Bluetooth"
    if fact_folded in {"detalhe floral", "estampa floral"}:
        return fact
    if fact_folded == "ilha dinamica":
        return "Ilha dinâmica"
    if fact_folded == "protecao termica":
        return "Proteção térmica para os fios"
    if fact_folded.startswith("foco no crescimento"):
        return fact
    if fact_folded == "cuidado para olheiras":
        return fact
    if fact_folded == "hidratacao labial":
        return fact
    if fact_folded == "solado plataforma":
        return "Plataforma no solado"
    if fact_folded == "toque macio":
        return fact
    if fact_folded == "uso no treino":
        return fact
    if fact_folded == "leve e confortavel":
        return fact
    if fact_folded == "acabamento dourado":
        return fact
    if fact_folded == "inox":
        return "Acabamento em inox"
    if fact_folded == "mascara acidificante":
        return "Ação acidificante"
    if fact_folded == "esfoliante corporal":
        return "Esfoliação corporal"
    if fact_folded.startswith("gel de limpeza"):
        return fact.replace("Gel de limpeza", "Limpeza", 1)
    if fact_folded.startswith("bico "):
        return "O bico é " + fact.split(maxsplit=1)[1].casefold()
    if fact_folded.startswith("braco "):
        return "O braço é " + fact.split(maxsplit=1)[1].casefold()
    if fact_folded.startswith("display "):
        return "O visor é " + fact.split(maxsplit=1)[1].casefold()
    if fact_folded.startswith("divisao") or fact_folded.startswith("sem strass"):
        return fact
    if fact_folded == "listras duplas na lateral":
        return fact
    if fact_folded.startswith("listras "):
        return "Listras nas laterais"
    if fact_folded == "lateral listra dupla":
        return "Listras duplas na lateral"
    if fact_folded.startswith("compartimento de almoco"):
        return "Compartimento para o almoço"
    if fact_folded.startswith("compartimento almoco"):
        return "Compartimento para o almoço"
    return fact
