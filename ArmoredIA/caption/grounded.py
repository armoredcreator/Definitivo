from __future__ import annotations

import re
import unicodedata
from typing import Any


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
