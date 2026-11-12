"""Write app/tests/fixtures/schema_expected.json from the real DESCRIBE (ADR-001 §3.7, TAC-001-07).

Read-only on the course data. Run once from the repository root:
    uv run --project app python app/scripts/snapshot_schema.py
Re-run only deliberately when the course data changes, then review the diff.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from mapqa.contract.schema import CONTRACT_FILES, describe_inputs, distinct_values, sha256_file

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "course-materials" / "exercise-data" / "map-qa"
OUT = REPO / "app" / "tests" / "fixtures" / "schema_expected.json"


def main() -> int:
    described = describe_inputs(DATA)
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "duckdb DESCRIBE on course data files",
        "data_dir": "course-materials/exercise-data/map-qa",
        "tables": {
            rel: {"sha256": sha256_file(DATA / rel), "columns": described[rel]} for rel in CONTRACT_FILES
        },
        "distinct_values": distinct_values(DATA),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"written {OUT.relative_to(REPO)}: {len(snapshot['tables'])} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
