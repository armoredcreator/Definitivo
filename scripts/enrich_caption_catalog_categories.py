from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ArmoredIA.caption.grounded import compose_safe_caption_candidates
from ArmoredVision.modules.v1.shopee_api import (
    ShopeeAPIError,
    ShopeeAffiliateAPI,
    ShopeeAuthenticationError,
    ShopeeProductNotFoundError,
    ShopeeRateLimitError,
)
from ArmoredVision.query_budget import ShopeeQueryBudget


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "storage" / "database" / "armoredcreator.db"
DEFAULT_BUDGET_DATABASE = ROOT / "storage" / "database" / "shopee-query-budget.sqlite3"
DEFAULT_OUTPUT = ROOT / "work" / "caption-product-categories.jsonl"


def _read_products(database_path: Path) -> list[dict[str, Any]]:
    database_uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        rows = connection.execute(
            "SELECT affiliate_name, ia_context_json FROM items "
            "WHERE affiliate_name IS NOT NULL AND trim(affiliate_name)<>'' "
            "ORDER BY affiliate_name"
        ).fetchall()
    finally:
        connection.close()

    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for title_value, raw_context in rows:
        title = str(title_value or "").strip()
        if not title:
            continue
        try:
            context = json.loads(raw_context or "{}")
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(context, dict):
            continue
        context.setdefault("productName", title)
        if compose_safe_caption_candidates(context):
            continue
        shop_id = str(context.get("shopId") or "").strip()
        item_id = str(context.get("itemId") or "").strip()
        if not shop_id or not item_id:
            continue
        unique.setdefault(
            (shop_id, item_id),
            {"shopId": shop_id, "itemId": item_id, "productName": title},
        )
    return list(unique.values())


def _read_completed(output_path: Path) -> set[tuple[str, str]]:
    completed: set[tuple[str, str]] = set()
    if not output_path.exists():
        return completed
    with output_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") in {"ok", "not_found", "api_error"}:
                completed.add((str(row.get("shopId") or ""), str(row.get("itemId") or "")))
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch productCatIds for catalog entries that currently have no "
            "caption candidate. Reads SQLite in read-only mode and writes a JSONL sidecar."
        ),
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--budget-database", type=Path, default=DEFAULT_BUDGET_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-api-calls", type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.max_api_calls <= 6109:
        parser.error("--max-api-calls must be between 1 and 6109")

    credentials = ROOT / "credentials" / "project.env"
    if credentials.is_file():
        load_dotenv(credentials, override=True)
    os.environ["ARMORED_IA_CAPTION_TITLE_RULES"] = "1"
    os.environ["SHOPEE_API_MAX_RETRIES"] = "1"

    products = _read_products(args.database)
    completed = _read_completed(args.output)
    pending = [
        product for product in products
        if (product["shopId"], product["itemId"]) not in completed
    ][:args.max_api_calls]
    if not pending:
        print("No pending product lookups.", flush=True)
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    budget = ShopeeQueryBudget(args.budget_database)
    api = ShopeeAffiliateAPI()
    started_at = datetime.now(timezone.utc)
    expires_at = started_at + timedelta(hours=12)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    call_count = 0
    api.request_authorizer = lambda _operation: budget.consume(
        budget_id=f"caption-catalog-categories-{run_id}-{call_count // 1000:02d}",
        request_limit=min(1000, max(1, len(pending) - (call_count // 1000) * 1000)),
        evidence=(
            "User explicitly requested catalog-wide caption enrichment using "
            "stored Shopee item/shop IDs; read-only productCatIds lookups."
        ),
        valid_until=expires_at.isoformat(timespec="seconds"),
    )

    ok = not_found = errors = 0
    try:
        with args.output.open("a", encoding="utf-8") as stream:
            for product in pending:
                status = "ok"
                categories: list[int] = []
                api_title = ""
                error_type = None
                try:
                    result = api.get_exact_product(
                        product["shopId"], product["itemId"],
                        allow_transient_retries=False,
                    )
                    api_title = str(result.get("productName") or "")
                    raw_categories = result.get("productCatIds")
                    if isinstance(raw_categories, (list, tuple)):
                        categories = [
                            int(value) for value in raw_categories
                            if str(value).isdigit() and int(value) > 0
                        ]
                    if not categories:
                        status = "api_error"
                        error_type = "ProductCategoryIdsMissing"
                        errors += 1
                    else:
                        ok += 1
                except ShopeeProductNotFoundError:
                    status = "not_found"
                    not_found += 1
                except (ShopeeAuthenticationError, ShopeeRateLimitError) as exc:
                    status = "rate_limited" if isinstance(exc, ShopeeRateLimitError) else "auth_error"
                    error_type = type(exc).__name__
                    errors += 1
                    row = {
                        **product,
                        "status": status,
                        "errorType": error_type,
                        "retryAfter": getattr(exc, "retry_after", None),
                        "responseMetadata": getattr(exc, "response_metadata", {}),
                        "productCatIds": categories,
                        "apiProductName": api_title,
                    }
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    print(
                        f"Stopped after {call_count + 1} request(s): {error_type}; "
                        f"ok={ok}, not_found={not_found}, errors={errors}",
                        flush=True,
                    )
                    return 2
                except ShopeeAPIError as exc:
                    status = "api_error"
                    error_type = type(exc).__name__
                    errors += 1

                row = {
                    **product,
                    "status": status,
                    "errorType": error_type,
                    "productCatIds": categories,
                    "apiProductName": api_title,
                }
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                stream.flush()
                call_count += 1
                if call_count % 25 == 0 or call_count == len(pending):
                    print(
                        f"lookups={call_count}/{len(pending)} ok={ok} "
                        f"not_found={not_found} errors={errors}",
                        flush=True,
                    )
    finally:
        api.close()
        budget.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
