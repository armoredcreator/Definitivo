from __future__ import annotations

import argparse
from pathlib import Path

from armored_core.coordinator import Coordinator


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reavalia itens WAITING_VISION e tentativas VISION interrompidas, com URL de origem. "
            "Executa somente Vision; --limit 0 reavalia todos os elegíveis."
        )
    )
    parser.add_argument(
        "--limit", type=int, default=1,
        help="máximo de itens (padrão: 1; 1–1000 por lote; 0 = todos os elegíveis)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="lista os candidatos elegíveis sem chamar Vision nem alterar estados de itens",
    )
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(),
        help="raiz do projeto (padrão: diretório atual)",
    )
    args = parser.parse_args()
    if args.limit < 0 or args.limit > 1000:
        parser.error("--limit deve ser 0 (todos) ou estar entre 1 e 1000")

    coordinator = None
    try:
        # staged=True creates only the Sync/Vision/SQLite composition; no Studio,
        # RVC, IA, Hub publication or Telegram download is invoked by this script.
        coordinator = Coordinator.build(
            root=args.root,
            acquire_runtime_lock=True,
            staged=True,
        )
        candidates = coordinator.db.pending_waiting_vision_retries(limit=args.limit)
        print("ARMORED CREATOR — WAITING_VISION RETRY")
        print(f"modo={'DRY-RUN' if args.dry_run else 'VISION-ONLY'}")
        print(f"candidatos elegíveis: {len(candidates)}")
        if args.dry_run:
            for item in candidates[:20]:
                print(f"  {item.content_id} | source={item.source_id} | estado={item.state.value}")
            if len(candidates) > 20:
                print(f"  ... mais {len(candidates) - 20} candidato(s)")
            print("nenhum item alterado; nenhuma chamada à Vision realizada")
            return 0

        outcomes = coordinator.retry_waiting_vision(limit=args.limit)
        from collections import Counter
        totals = Counter(outcome["result"] for outcome in outcomes)
        technical_errors = [
            outcome for outcome in outcomes
            if outcome["result"] == "technical-error"
        ]
        print("RESULTADO")
        print(
            f"reavaliados={len(outcomes)} "
            f"aprovados={totals['approved']} "
            f"continuam_waiting={totals['unresolved']} "
            f"erros_tecnicos={len(technical_errors)}"
        )
        for outcome in technical_errors[:20]:
            print(
                f"  [ERRO] {outcome['content_id']} | "
                f"{outcome['state']} | {outcome['result']}"
            )
        if len(technical_errors) > 20:
            print(f"  ... mais {len(technical_errors) - 20} erro(s) técnico(s)")
        print("nenhum download, Studio, IA ou publicação executado")
        return 1 if technical_errors else 0
    finally:
        if coordinator is not None:
            coordinator.close()


if __name__ == "__main__":
    raise SystemExit(main())
