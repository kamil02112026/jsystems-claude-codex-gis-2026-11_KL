# app/ — Map QA Copilot (Python 3.12, uv)

Run everything from the repository root, not from `app/`.

## Commands
- Install: `uv sync --project app`
- Tests: `uv run --project app pytest app/tests -q` (offline; `e2e` and `paid` are deselected by default)
- E2E (offline, real CLI on course data): `uv run --project app pytest app/tests -m e2e -q`
- Never run `-m paid` without explicit owner consent.

## Rules
- Markers: `e2e` (offline CLI run), `paid` (real OpenRouter requests).
- No pandas/geopandas/shapely/pyproj in `src/`; they are test oracles only.
- HTTP mocks come only from `app/tests/fixtures/captures/` (real recorded responses).
- To check cache behaviour use `mapqa run --cache-only` (0 requests, no HTTP client).
- Paid runs only after owner consent and after reading the printed manifest.

## Module map (`src/mapqa/`)
- `contract/` shared models, DB, hashing, bundle, schema (change only by proposal)
- `sources/` data adapters; `matching/` photo-to-road links; `normalize/` OSM tag normalization
- `models/` image prep, request builders, OpenRouter clients; `questions/` question catalog
- `cascade/` level 1 -> 2 -> human; `cache/` SQLite cache; `budget/` request and cost limits
- `candidates/` QA candidates and queue; `evaluation/` metrics, split, calibration
- `report/` Markdown/CSV output; `cli/` argparse entry; `pipeline.py` wires F2-F7

Details: `docs/ADR/000-main-architecture.md` (§3 structure, §6 CLI), plans in `docs/plans/`.
