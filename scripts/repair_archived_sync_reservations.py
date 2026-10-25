from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from armored_core.migrations import fence_reingested_archived_duplicates


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    database = root / "storage" / "database" / "armoredcreator.db"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = root / "storage" / "backups" / f"armoredcreator-before-archived-sync-repair-{stamp}.sqlite3"
    result = fence_reingested_archived_duplicates(
        database,
        project_root=root,
        backup_path=backup,
    )
    report_path = root / "storage" / "validation" / "archived-sync-reservation-repair.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
