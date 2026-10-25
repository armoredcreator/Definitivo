from __future__ import annotations

import re
import unicodedata
from typing import Any

from .policy import caption_product_anchor_terms


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return "".join(char for char in text if not unicodedata.combining(char))


def compose_grounded_caption(context: dict[str, Any]) -> str | None:
    """Compose editorial captions from explicit, recognized Vision title patterns.

    These closed patterns are fast, text-only paths for product facts that can be
    expressed without asking a small local model to invent or reinterpret them.
    Unknown title structures return None and continue through the configured AI.
    """
    title = _fold(str(context.get("productName") or ""))
    if not title:
        return None

    if re.search(r"\bdescascador\b.*\bapontador\b", title):
        return "Parece até um apontador\n#descascador #legumes"

    if re.search(r"\bcorte\s+a\s+laser\b", title) and re.search(r"\b(tanga|calcinha|calcinhas)\b", title):
        return "Olha esse corte a laser\n#tanga #laser"

    if re.search(r"\bcompartimento\s+de\s+almoco\b", title) and re.search(r"\bbolsa\b", title):
        return "Compartimento pro almoço\n#bolsa #almoço"

    if re.search(r"\bscarpin\b", title) and re.search(r"\bsalto\b", title) and re.search(r"\bgeometrico\b", title):
        return "Scarpin de salto geométrico\n#Scarpin #Salto"

    if re.search(r"\bmascara\b", title) and re.search(r"\bacidificante\b", title):
        return "Máscara acidificante\n#Máscara #Acidificante"

    if re.search(r"\bchinelo\b", title) and re.search(r"\bverao\b", title):
        return "Chinelo de verão\n#Chinelo #Verão"

    # Prefer the concrete use/material fact in noisy footwear titles over the
    # generic marketplace tag "casual". These patterns also keep two distinct
    # tennis products from collapsing to the same generic caption.
    if re.search(r"\btenis\b", title):
        if re.search(r"\b(treino|esportes?)\b", title):
            return "Tênis para treino\n#Tênis #Treino"
        if re.search(r"\bmacio\b", title):
            return "Tênis macio\n#Tênis #Macio"

    if re.search(r"\b(smartwatch|relogio inteligente)\b", title) and re.search(r"\bnfc\b", title):
        if re.search(r"\bilha dinamica\b", title):
            return "Relógio com ilha dinâmica\n#Smartwatch #Relógio"
        return "Relógio inteligente\n#Relógio #Smartwatch"

    # Sparse Vision records often contain only a long marketplace title. For
    # common product heads, use one explicit, non-promotional descriptor from
    # that title instead of asking a small model to recombine a bag of words.
    # Unknown heads and descriptors still go through the configured provider.
    product_name = str(context.get("productName") or "")
    anchors = set(caption_product_anchor_terms(context, product_name=product_name))
    anchors.difference_update({
        "beleza", "casa", "calcados", "cozinha", "decoracao", "iluminacao",
        "infantil", "moda", "organizacao",
    })
    safe_descriptors = {
        "acinturado", "acinturada", "casual", "confortavel", "leve", "macio",
        "macia", "midi", "listrado", "listrada", "estampado", "estampada",
        "floral", "redondo", "redonda", "quadrado", "quadrada", "impermeavel",
        "jeans", "algodao", "camurca", "couro", "colorido", "colorida",
        "metalico", "metalica", "versatil", "alto", "alta", "fino", "fina",
        "longo", "longa", "curto", "curta", "ortopedico", "ortopedica", "verao",
    }
    skip_terms = {
        "feminina", "feminino", "masculina", "masculino", "unissex", "para",
        "com", "sem", "novo", "nova", "lancamento", "promocao", "oferta",
    }
    words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", product_name)
    head_index = next(
        (index for index, word in enumerate(words) if _fold(word) in anchors),
        None,
    )
    if head_index is not None:
        head = words[head_index]
        descriptor = next(
            (
                word for word in words[head_index + 1:]
                if _fold(word) in safe_descriptors and _fold(word) not in skip_terms
            ),
            None,
        )
        if descriptor:
            if _fold(descriptor) == "verao":
                return f"{head} de verão\n#{head} #Verão"
            return f"{head} {descriptor}\n#{head} #{descriptor}"

    return None


def compose_safe_caption_fallback(context: dict[str, Any]) -> str | None:
    """Return a small, factual caption when the model cannot pass Policy.

    These are semantic product/use patterns, not item IDs. Every fallback is
    still re-evaluated by the shared Policy before it can be returned.
    """
    title = _fold(str(context.get("productName") or ""))
    if re.search(r"\besfoliante\b", title) and re.search(r"\bbanho\b", title):
        return "Esfoliante para banho\n#esfoliante #banho"
    if re.search(r"\bsutia\b", title) and re.search(r"\bbojo\b", title):
        return "Sutiã com bojo\n#sutiã #bojo"
    if re.search(r"\bvestido\b", title) and re.search(r"\bbojo\b", title):
        return "Vestido com bojo\n#vestido #bojo"
    if re.search(r"\bsandalia\b", title) and re.search(r"\bplataforma\b", title):
        return "Sandália com plataforma\n#sandália #plataforma"
    if re.search(r"\bmoletom\b", title) and re.search(r"\bpelucia\b", title):
        return "Pelúcia para o inverno\n#moletom #inverno"
    if re.search(r"\bpijama\b", title) and re.search(r"\bmanga\s+longa\b", title):
        return "Pijama de manga longa\n#pijama #inverno"
    return None
