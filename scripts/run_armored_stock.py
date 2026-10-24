from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from ArmoredStock.service import ArmoredStock
from armored_core.coordinator import Coordinator


def main() -> int:
    """Run only ArmoredStock materialization and exit."""
    root = Path(os.getenv("ARMORED_ROOT") or Path(__file__).resolve().parents[1]).resolve()
    os.environ.setdefault("ARMORED_ROOT", str(root))
    os.environ["ARMORED_REAL_TELEGRAM"] = "1"
    os.environ["ARMORED_REQUIRED_SOURCE_COUNT"] = "3"
    os.environ["ARMORED_SYNC_VERBOSE_PROGRESS"] = "0"

    logging.basicConfig(
        level=os.getenv("ARMORED_LOG_LEVEL", "ERROR").upper(),
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True,
    )
    for logger_name in (
        "telethon", "telethon.network", "telethon.network.mtprotosender",
        "httpx", "httpcore", "asyncio", "torch", "transformers",
        "armored_core.pipeline", "armored_core.services", "ArmoredSync.service",
        "armored_core.catch_up_stages",
    ):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)

    coordinator = None
    try:
        # The Coordinator remains the only composition root and holds the SQLite
        # runtime lease. staged=True deliberately omits Studio/RVC, IA, and Hub.
        coordinator = Coordinator.build(
            root=root,
            acquire_runtime_lock=True,
            staged=True,
        )
        print("[ARMOREDSTOCK] INÍCIO")
        report = asyncio.run(ArmoredStock(coordinator).run())
        source_counts = report.get("per_source", {})
        routes = tuple(coordinator.source.sources)
        source_summary = ",".join(
            f"F{index}[{route.source_id}]={source_counts.get(str(route.source_id), 0)}"
            for index, route in enumerate(routes, start=1)
        )
        outcomes = report["outcomes"]
        errors = report["errors"]
        status = "FALHOU" if errors else "OK"
        print(
            f"[ARMOREDSTOCK] {status} baixados={outcomes['downloaded']} "
            f"{source_summary} "
            f"originais_existentes={outcomes['skipped_existing_original']} "
            f"faltantes={outcomes['approved_missing_original']} "
            f"erros={len(errors)} checkpoint=preservado"
        )
        for error in errors[:10]:
            print(f"[ARMOREDSTOCK][ERRO] {error}")
        if len(errors) > 10:
            print(f"[ARMOREDSTOCK][ERRO] ... mais {len(errors) - 10} erro(s) omitido(s)")
        return 1 if errors else 0
    except KeyboardInterrupt:
        print("[ARMOREDSTOCK] Interrompido; SQLite e originais já concluídos foram preservados.")
        return 130
    except Exception as exc:
        logging.error("[ARMOREDSTOCK] Execução encerrada: %s", exc)
        return 1
    finally:
        if coordinator is not None:
            coordinator.close()


if __name__ == "__main__":
    raise SystemExit(main())
