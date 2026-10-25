from __future__ import annotations

from typing import Any


def context_text(product: dict[str, Any]) -> str:
    """Render only product-semantic Vision fields for caption generation."""
    fields = (
        ("Produto identificado pela Vision", "productName"),
        ("Categoria", "category"),
        ("Nome da categoria", "categoryName"),
        ("Categoria do produto", "productCategory"),
        ("Tipo de produto", "productType"),
        ("Uso", "usage"),
        ("Caso de uso", "useCase"),
        ("Estilo", "style"),
        ("Aparência", "appearance"),
        ("Descrição", "description"),
        ("Atributos", "attributes"),
        ("Características", "technicalCharacteristics"),
    )
    lines = []
    for label, key in fields:
        value = product.get(key)
        if value not in (None, "", [], {}):
            lines.append(f"{label}: {value}")
    return "\n".join(lines)
