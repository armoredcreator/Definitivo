from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path


TAGS = (
    "RESOLUTION_UNSUPPORTED",
    "NO_AFFILIATE_OFFER",
    "PRODUCT_LINK_MISSING",
    "INVALID_AFFILIATE_URL",
)


def classify(error: str | None) -> str:
    value = (error or "").upper()
    for tag in TAGS:
        if f"[VISION:{tag}]" in value:
            return tag
    if not value:
        return "NO_ERROR_RECORDED"
    if "TIMEOUT" in value or "CONNECTION" in value or "SHOPEE API" in value or "FALHA SHOPEE" in value:
        return "LEGACY_POSSIBLE_TECHNICAL_ERROR"
    if "NÃO CONSEGUIU IDENTIFICAR" in value or "NÃO FOI POSSÍVEL EXTRAIR" in value:
        return "LEGACY_RESOLUTION_FAILURE_UNCLASSIFIED"
    if "NÃO RESOLVEU O PRODUTO" in value or "PRODUTO NÃO ENCONTRADO" in value:
        return "LEGACY_NO_OFFER_OR_LOOKUP_FAILURE_UNCLASSIFIED"
    return "OTHER_OR_UNCLASSIFIED"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auditoria somente leitura dos resultados de Vision no SQLite."
    )
    parser.add_argument(
        "--db",
        default="storage/database/armoredcreator.db",
        help="Caminho do banco (padrão: storage/database/armoredcreator.db)",
    )
    args = parser.parse_args()
    db_path = Path(args.db).resolve()
    if not db_path.is_file():
        parser.error(f"Banco não encontrado: {db_path}")

    uri = db_path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        con.row_factory = sqlite3.Row
        columns = {
            row["name"] for row in con.execute('PRAGMA table_info("items")')
        }
        required = {"content_id", "source_id", "state", "last_error"}
        if not required.issubset(columns):
            parser.error("A tabela items não contém as colunas esperadas; banco não foi alterado.")

        rows = con.execute(
            "SELECT source_id, state, last_error FROM items ORDER BY source_id, state"
        ).fetchall()

    by_state = Counter()
    by_source_category = Counter()
    for row in rows:
        category = classify(row["last_error"])
        by_state[(str(row["state"]), category)] += 1
        by_source_category[(str(row["source_id"] or "(sem fonte)"), category)] += 1

    print(f"Banco (somente leitura): {db_path}")
    print(f"Itens examinados: {len(rows)}")
    print("\nCONTAGEM POR ESTADO E CATEGORIA")
    for (state, category), count in sorted(by_state.items()):
        print(f"{state:20} | {category:48} | {count}")

    print("\nCONTAGEM POR FONTE E CATEGORIA")
    for (source, category), count in sorted(by_source_category.items()):
        print(f"{source:22} | {category:48} | {count}")

    print("\nNOTAS")
    print("- Categorias LEGACY são inferências por texto antigo, não decisões definitivas.")
    print("- RESOLUTION_UNSUPPORTED não prova que o link não contenha produto.")
    print("- NO_AFFILIATE_OFFER não prova que o produto inexista ou esteja indisponível.")
    print("- Nenhum item, arquivo ou estado foi alterado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
