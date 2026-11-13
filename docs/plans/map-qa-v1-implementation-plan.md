# Plan implementacji: Map QA Copilot v1 — wszystkie przyrosty PRD (P1–P5) w jednym przebiegu `/goal`

| | |
|---|---|
| Status | **ZAAKCEPTOWANY 2026-11-13** — §0 potwierdzone, U2–U6 = wartości domyślne |
| Data | 2026-11-13 |
| Ścieżka | `docs/plans/map-qa-v1-implementation-plan.md` |
| Gałąź | `map-app-implementation` (śledzi `origin/map-app-implementation`); push tylko do `origin` (fork) |
| Źródła (nadrzędne wobec planu) | [PRD](../PRD.md) (§3, F1–F8, §7, §8 kryt. 1–20, §9 „Poza MVP — kolejność przyrostów”) · [ADR-000](../ADR/000-main-architecture.md) · [ADR-001](../ADR/001-data-sources.md) · [ADR-002](../ADR/002-spatial-matching-and-normalization.md) · [ADR-003](../ADR/003-model-cascade.md) · [ADR-004](../ADR/004-reporting-and-evaluation.md) · [profil danych](../../reports/map-qa/profile.md) · [AGENTS.md](../../AGENTS.md) · [plan MVP (zakończony)](map-qa-mvp-implementation-plan.md) · [skill planowania](../../.agents/skills/plan-implementation/SKILL.md) |

> **Planowanie nie autoryzuje wykonania.** Plan nie uruchamia agentów, płatnych zapytań, pobierania danych, pushy, PR ani merge'ów. `/goal` przechodzi tylko przez bramki, które właściciel wcześniej zatwierdził w §0. Wymagania są w PRD i ADR, a plan tylko je wskazuje. W razie sprzeczności rozstrzyga PRD (biznes) albo właściwy ADR (technika), zgodnie z A0 §1.

Skróty: `A0 §6` = ADR-000 §6 (analogicznie `A1`–`A4`); `kryt. N` = PRD §8, kryterium N; `pt` = `uv run --project app pytest`. Polecenia uruchamiamy z katalogu głównego repozytorium.

---

## 0. Wcześniejsza zgoda właściciela (wypełnia właściciel przed `/goal`)

Proponowane wartości wymagają potwierdzenia. Pole bez potwierdzenia oznacza **brak zgody**: wiersz dostaje `blocked:<bramka>`, a `/goal` idzie dalej niezależnymi wierszami (§4.1).

| Pole | Proponowana wartość | Potwierdzam (T/N/inna) |
|---|---|---|
| A1. Maks. USD na jedno płatne uruchomienie (`--max-usd`) | 1,00 USD (domyślnie z PRD F5.9) | **T** (właściciel, 2026-11-13) |
| A2. Maks. zapytań / nowych obrazów na uruchomienie | 100 / 25 (PRD F5.9), bez podnoszenia limitów | **T** (właściciel, 2026-11-13) |
| A3. Łączny realny koszt całego `/goal` (suma `costs.jsonl`) | **2,00 USD**, po przekroczeniu stop. Realnie ~0,00005 USD za zapytanie, oczekiwane < 0,10 USD | **T** (właściciel, 2026-11-13) |
| A4. Maks. liczba płatnych uruchomień w całym `/goal` | 16 (nagrania, kalibracja i test oświetlenia, pełne kadry prędkości, model porównawczy) | **T** (właściciel, 2026-11-13) |
| A5. Płatne bramki objęte zgodą | GP1 (nagranie pytania o lampę, ≤ 4 zapytania, ≤ 0,10 USD), GP2 (ewaluacja oświetlenia i pełnych kadrów), GP3 (model porównawczy) | **T** (właściciel, 2026-11-13) |
| A6. Sieć: pobranie zdjęć (`download_photos.py`, zapis tylko do `data/photos/`) | tak (GNET); odświeżenie adresów Mapillary tylko z `MAPILLARY_TOKEN` ustawionym przez właściciela | **T** (właściciel, 2026-11-13) |
| A7. Sieć: instalacja z PyPI / zmiana `uv.lock` | **nie** (stop i pytanie) | **T** (właściciel, 2026-11-13) |
| A8. Databricks | tylko gdy `/goal` działa w oknie PowerShell właściciela ze zmiennymi `DATABRICKS_*`; agent sprawdza wyłącznie ich obecność; bez nich wiersze GDB dostają `blocked:GDB` | **T** (właściciel, 2026-11-13) |
| A9. Push | tylko `origin`, gałąź `map-app-implementation`, po każdej zakończonej fazie; nigdy `main` ani `upstream`, bez force-push. Wypełnione i potwierdzone §0 jest jawnym poleceniem push w rozumieniu AGENTS.md (Commit Rules). | **T** (właściciel, 2026-11-13) |
| A10. PR | PR do `main` forka na końcu (T58), z pełnym URL; **merge wykonuje człowiek** | **T** (właściciel, 2026-11-13) |
| A11. Repozytorium prowadzącego | zakaz jakichkolwiek zmian (push do `upstream` wyłączony); `git show upstream/...` tylko do odczytu | **T** (właściciel, 2026-11-13) |

---

## 1. Stan wyjściowy (zweryfikowano 2026-11-13, tylko odczyt)

| Element | Stan | Dowód |
|---|---|---|
| Gałąź / HEAD | `map-app-implementation`, czyste drzewo; poprawki z przeglądu PR #3 zacommitowane (`ed4a44e`) | `git log --oneline -3`, `git status` |
| Plan MVP | T01–T27 `done`, w tym G2–G4 na prawdziwym OpenRouter; T28 = PR #3 otwarty | [plan MVP §4](map-qa-mvp-implementation-plan.md) |
| Testy | 348 passed + 5 E2E passed (czyste środowisko) | `pt app/tests -q`, `pt app/tests -m e2e -q` |
| Kod | `app/src/mapqa/{budget,cache,candidates,cascade,cli,config,contract,evaluation,matching(provided),models,normalize,profile,questions,report,sources(files)}` + `pipeline.py`; brak `compare/`, `sources/databricks_*`, własnego dopasowania, `report.html` | `app/src` |
| CLI | `--dataset photos` kończy się `dataset_not_available`; są `--cache-only`, `--max-images`, `--grid`, `--target-accuracy` | `app/src/mapqa/cli/main.py` |
| Zdjęcia | `photos.csv` 561 (461 Panoramax, 100 Mapillary); `offline/` 40 JPG, w tym 36 ze 100 etykietowanych (25 z etykietą oświetlenia `certain`); `data/photos/` pusty | DuckDB, `ls` |
| Etykiety | `street_lighting_visible`: 54 `yes`, 25 `no`, 21 `uncertain`; `surface`: 99 `paved`, 0 `unpaved`; `speed_limit_value` (pełne kadry): 14 `certain` | DuckDB na `reference_labels.csv` |
| Nagrania | tylko `fixtures/captures/openrouter/`; **brak nagrań Databricks** (A1 §8 DB-01/DB-02) | `ls app/tests/fixtures/captures` |
| Narzędzia | uv 0.13.7, Python 3.12.16, DuckDB 1.5.6 + spatial, Codex CLI 0.167.2, OpenCode 2.2.5, Claude Code `claude -p` | `--help` (2026-11-13) |
| Id modeli | Haiku 5.5: alias `haiku`; OpenCode: `xiaomi-token-plan-ams/mimo-v2.6-flash` (zapas `opencode/mimo-v2.6-flash-free`); Codex: Sol 6.1 = `gpt-6.1-sol`, Luna 6 = `gpt-6-luna` (lokalna lista modeli Codex, T31) | `opencode models`; T31 |

---

## 2. Zakres, poza zakresem, kamienie milowe

**W zakresie:** PRD §9 „Poza MVP — kolejność przyrostów”, punkty 1–5.
- **P1:** adapter `databricks` (`rest`, potem `cli`), bbox w SQL, profil F2 dla 561 zdjęć, własne dopasowanie w EPSG:2180 z flagami `grade_separated`, `service_or_restricted`, `distance_mismatch`, porównanie z `photo_road_links.csv` (F3.5), `--dataset photos`, kryt. 1–4 i 16–18, prędkość na pełnych kadrach.
- **P2:** oświetlenie (`download_photos.py`, `street_lamp_visible`, OSM `lit`, 79 etykiet `certain`).
- **P3:** Overture `speed_limits` (`when`/`between`), porównanie, reguły `sources_disagree_photo_supports` i `sources_only` (A0 D10-I3, A4 §3.1).
- **P4:** `report.html` z miniaturami (RPT-03) i tryb porównawczy F5.11.
- **P5:** nawierzchnia **ZABLOKOWANA** (brak etykiet `unpaved`, PRD §11); plan obejmuje tylko blokadę i adnotację EVL-04.

**Poza zakresem:** „Później” z PRD §9 (dashboard/UI, zapis i import decyzji, eksport do Jira, serwer MCP, kolejne adaptery). Funkcje z wersji prowadzącego, których nie ma w naszym PRD, wymagają najpierw zmiany PRD/ADR i są tylko w T59 (poza `/goal`).

**Kamienie milowe (pierwszy działa offline):** **M4** `mapqa run --dataset photos` bez modelu, z własnym dopasowaniem i pełnym profilem (0 USD) → **M5** zgodność `files` ↔ `databricks` (sesja właściciela) → **M6** oświetlenie z ewaluacją na zbiorze testowym → **M7** Overture i HTML z modelem porównawczym → **M8** przegląd i PR.

**Kryteria PRD §8 → zadania:** 1 → T32, T36, T37 · 2 → T32, T36 · 3 → T33 · 4 → T32, T34 · 5 → T34, T35, T37 · 6–9, 15, 20 → MVP, regresja w T57 · 10 → T44, T50, T52 · 11 → T45, T56 · 12 → T47 · 13 → T39, T57 · 14, 19 → T57 · 16 → T39 · 17 → T41 · 18 → T39, T40.

---

## 3. Fazy, priorytety i kolejność

| Faza | Priorytet | Wiersze | Cel | Bramki |
|---|---|---|---|---|
| **F0** Utwardzenie MVP i narzędzia | **P0** | T29–T31 | zielony baseline, zamknięte ustalenia z przeglądu, zweryfikowane id modeli | — |
| **F1** P1 offline: `photos` i własne dopasowanie | **P0** | T32–T37 | → **M4** | — |
| **F2** P1 Databricks | **P0** (zależy od sesji) | T38–T41 | → **M5** | GDB |
| **F3** P2 Oświetlenie | **P1** | T42–T47 | → **M6** | GNET, GP1, GP2 |
| **F4** P3 Overture | **P1** | T48–T51 | rozbieżności źródeł | — |
| **F5** P4 HTML i model porównawczy | **P1** | T52–T55 | → **M7** | GP3 |
| **F6** P5 Nawierzchnia (ZABLOKOWANA) | **P2** | T56 | blokada i adnotacja | — |
| **F7** Domknięcie | **P0** | T57–T58 | E2E, przegląd, PR → **M8** | push i PR (A9, A10) |
| **F8** Opcjonalne, poza PRD | **P2** | T59 | tylko propozycje PRD/ADR | decyzja właściciela |

**Kolejność (ścisła):** F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7; F8 nie wchodzi do `/goal`. W fazie wiersze idą w kolejności numerów, z wyjątkiem fal z §6. F4 zależy tylko od F1, więc gdy F2 albo F3 są `blocked`, F4 rusza od razu.

**Ścieżka krytyczna:** T30 → T32 → T33 → T34 → T37 (M4) → T48 → T49 → T50 → T51 → T52 → T57 → T58. Ścieżki zależne od sieci i pieniędzy (F2, F3, T55) są bocznymi gałęziami.

---

## 4. Macierz zależności (jedyne źródło statusu)

Każdy wiersz zaczyna się od testu, który ma paść z oczekiwanego powodu (Red). Jeden wiersz = jeden commit `Area: summary` wykonany przez orkiestratora. Statusy: `todo`, `in_progress`, `done`, `blocked:<powód>`, `skipped`.

| Task | Observable outcome | PRD/ADR links | Prerequisites | Owner/model | Editable files | Verification and handoff | Status |
|---|---|---|---|---|---|---|---|
| T29 Poprawki z przeglądu PR #3 | 8 ustaleń z testami regresji: nieczytelny obraz nie przerywa płatnej pętli, klient zamykany w `finally`, `calibrate` tylko na `calibration` i z `--grid`, koszt BYOK w skrypcie nagrań, walidacja współrzędnych, duplikat `photo_id` → `ContractViolation`, sekcje ewaluacji zgodne z bbox/split, unikalny katalog uruchomienia, wspólna wartość OSM w profilu, jeden helper `sha256` i ścisły MIME | PRD F2.3, F5.7, §7; A4 §3.9, D-004-3; A3 §3.2 | — | Orkiestrator | — | `test_review_fixes.py` 14/14, pełny zestaw 348 + 5 E2E | done (`ed4a44e`) |
| T30 Pozostałe ustalenia | (a) kolizje `item_id` wykrywane przy budowie kolejki; (b) `invalid_response` w cache: zostaje zgodnie z A3 §3.7 (U3), dokumentacja | PRD F6.7, kryt. 14; A4 §3.4; A3 §3.7, D-003-4 | T29 | Haiku 5.5 (`haiku`), 2 rundy | `app/src/mapqa/candidates/queue.py`, `app/tests/unit/test_queue.py` | Red: dwa zdjęcia z tym samym hashem wycinka → ostrzeżenie/rozróżnienie. Commit `Backend: guard queue id collisions` | done (Haiku 5.5, 1 runda) |
| T31 Weryfikacja narzędzi | Prawdziwe id modeli wpisane do §5 (Codex: config / `/model` w oknie właściciela, bez płatnego `exec`; `opencode models`; `claude --help`); projektowy `opencode.jsonc` blokujący push/force/`main`/sekrety albo decyzja „OpenCode bez `--auto`” | skill „Headless delegation”; AGENTS.md (Documentation lookup) | T29 | Orkiestrator | `docs/plans/map-qa-v1-implementation-plan.md` (§5), opcjonalnie `opencode.jsonc` | Gdy id Codex niepotwierdzone, jego wiersze przejmuje Haiku albo orkiestrator. Commit `Docs: record verified worker model ids` | done (`gpt-6.1-sol`, `gpt-6-luna`, `xiaomi-token-plan-ams/mimo-v2.6-flash`; OpenCode bez `--auto`) |
| T32 `--dataset photos` w adapterze `files` | `photos.csv`, `photo_road_links.csv`, `osm_roads`, `overture_segments`; `photos_dir` = `offline/` + `data/photos/`; `missing_file`/`hash_mismatch`; `heading` NULL ≠ 0; całe drogi przecinające bbox | PRD F2.1–F2.4, F8.3–F8.6, kryt. 1, 2, 4; A1 §3.3, §4; FIL-01..06, CON-01, SCH-01 | T29 | Haiku 5.5; SQL i bbox przegląda orkiestrator | `app/src/mapqa/sources/files.py`, `app/src/mapqa/sql/files_photos_*.sql`, `app/tests/unit/test_files_adapter.py`, `app/tests/contract/test_source_contract.py` | Red: FIL-02 (15 NULL, 23 × 0.0), FIL-03..05 na kopii, CON-01. Commit `Backend: load photos dataset in files adapter` | done (Haiku 5.5; 561 zdjęć, 521 missing_file przed T42) |
| T33 CRS i azymut | Funkcje metryczne odrzucają kolumny bez `_2180`; `ST_Transform(..., always_xy := true)`; azymut zgodny z `pyproj.Geod` do 0,1° | PRD F3.1, kryt. 3; A2 §3.1; CRS-01, CRS-02, TAC-002-01, TAC-002-06; A0 TAC-15 | T29 | Codex Luna 6 (id: T31) albo Haiku | `app/src/mapqa/matching/crs.py`, `app/tests/integration/test_crs.py` | Red: CRS-01 (100,00 ± 0,01 m), strażnik zamiany osi. Commit `Backend: add EPSG:2180 distance and bearing helpers` | done (Codex gpt-6-luna headless: kod OK, ale sandbox blokował cache uv — testy uruchomił orkiestrator; przy Codex dodać --add-dir z cache uv) |
| T34 Własne dopasowanie zdjęcie → droga | Kandydaci ≤ 25 m, ranking, remisy, Overture przez `record_id`, flagi A2 §3.3 (w tym `grade_separated`, `service_or_restricted`), wynik deterministyczny | PRD F3.1–F3.4, kryt. 4, 5; A2 §3.2–§3.3, D-002-1, D-002-3; MAT-01..06, MAT-09, HDG-01, HDG-02, TAC-002-04, TAC-002-05 | T32, T33 | **Codex Sol 6.1** (id: T31), 2 rundy | `app/src/mapqa/matching/spatial.py`, `app/src/mapqa/sql/match_*.sql`, `app/tests/unit/test_spatial_matcher.py` | Red: syntetyczne geometrie, GeoPandas jako wyrocznia (dev). Commit `Backend: add EPSG:2180 photo-to-road matcher` | todo |
| T35 Flagi połączeń dostarczonych i tagi kierunkowe | `distance_mismatch` (> 0,5 m) i flagi P1 dla `link_source=provided`; pełna reguła `forward`/`backward` z `directed_bearing_diff` (zamyka MVP U2) | PRD F3.3, F4.2; A2 §3.3, §3.5; MAT-10, NRM-02 | T34 | Haiku 5.5 | `app/src/mapqa/matching/provided.py`, `app/src/mapqa/normalize/{maxspeed,osm}.py`, `app/tests/integration/test_provided_links_photos.py`, `app/tests/unit/test_normalize_maxspeed.py` | Red: MAT-10 (+0,4 / +0,6 m). Commit `Backend: add P1 link flags and directional maxspeed rule` | todo |
| T36 Pełny profil F2 i F3.5 | Liczności total/w bbox, kompletność `maxspeed`/`surface`/`lit` „x% (n/N)”, odrzucenia z przyczyną, zgodność `osm_way_id` z `photo_road_links.csv` z mianownikiem | PRD F2.3, F3.5, kryt. 1, 2; A4 §3.6; MAT-07, TAC-002-02 | T32, T34 | Haiku 5.5 | `app/src/mapqa/profile/profile.py`, `app/tests/unit/test_profile.py` | Red: mianowniki, `missing_file` przed T42. Zgodność < 95% → `blocked:TAC-002-02` z analizą. Commit `Backend: add full input profile and link agreement` | todo |
| T37 Pipeline `photos` bez modelu → **M4** | `mapqa run --dataset photos --attributes speed_limit` → raport, kolejka, profil; 0 żądań; ≤ 2 min | PRD F1, §6, kryt. 1–5, 20; A0 §6; MAT-07, MAT-08; A4 E2E-01 | T35, T36 | Orkiestrator; testy Haiku | `app/src/mapqa/pipeline.py`, `app/src/mapqa/cli/main.py`, `app/tests/e2e/test_run_photos_e2e.py` | `pt -q`, `pt -m e2e -q`; ręczne QA (tekst i JSON), pomiar czasu. Commit `Backend: run photos dataset with own matching` | todo |
| T38 **GDB:** nagrania Databricks | Skrypt w trybie próbnym bez sieci, potem w sesji właściciela DB-01 (mały bbox), DB-02 (pełny `osm_roads`, chunki), DB-05 (FAILED), DB-06 (401); redakcja `<WAREHOUSE>`, bez `Authorization` | PRD F8.3, F8.5, F8.7; A1 §3.4, §8, D-001-2, D-001-3 | T29; A8 | Skrypt: Haiku 5.5; uruchamia orkiestrator w oknie właściciela | `app/scripts/capture_databricks.py`, `app/tests/fixtures/captures/databricks/*.json`, `app/tests/unit/test_capture_databricks.py` | Skan sekretów (0 trafień), TAC-001-03. Fakt sprzeczny z A1 → stop wiersza i aktualizacja ADR-001. Bez env: `blocked:GDB`. Commit `Tests: add Databricks statement captures` | todo |
| T39 Adapter `databricks` REST | 1 POST, odpytywanie, chunki, `cancel` po timeout, bbox tylko w `parameters`, typy, `hex(WKB)`, redakcja | PRD F8.3–F8.8, kryt. 13, 16, 18; A1 §3.4, §3.6, D-001-4, D-001-5; DB-03..07, CON-01, TAC-001-01, TAC-001-03..05 | T38 | **Codex Sol 6.1**; respx wyłącznie z nagrań T38 | `app/src/mapqa/sources/databricks_rest.py`, `app/src/mapqa/sources/registry.py`, `app/src/mapqa/sql/databricks_*.sql`, `app/tests/integration/test_databricks_rest.py` | Red: DB-03..07 z licznikiem tras. Commit `Backend: add Databricks REST source adapter` | todo |
| T40 Adapter `databricks` CLI | `subprocess` bez `shell=True`, bez tokenu w argumentach; brak programu → kod 2 z podpowiedzią | PRD F8.3, kryt. 18; A1 §3.5; CLI-01 | T39 | Codex Luna 6 albo OpenCode MiMo | `app/src/mapqa/sources/databricks_cli.py`, `app/tests/integration/test_databricks_cli.py` | Red: fałszywy `databricks` w PATH testu. Commit `Backend: add Databricks CLI source adapter` | todo |
| T41 **GDB:** zgodność źródeł → **M5** | `sources check --source course-databricks` → 99 768 / 85 405 / 561 / 561 / 1730; `run --no-model --dataset photos` na obu źródłach → te same id kandydatów | PRD F2.5, F8.10, kryt. 17; A1 DB-08, TAC-001-06 | T37, T40; A8 | Orkiestrator w oknie właściciela | `app/tests/e2e/test_databricks_parity.py` | Wynik obu uruchomień w opisie PR. Commit `Tests: add files-databricks parity e2e` | todo |
| T42 **GNET:** pobranie zdjęć | `download_photos.py --limit 10`, potem pełne, na końcu `--verify-only`; zapis tylko do `data/photos/` | PRD F8.6, §9 P2; README danych | T37; A6 | Orkiestrator | — (dane ignorowane przez Git) | `--verify-only` kod 0; wygasłe adresy Mapillary bez tokenu → `blocked:GNET` (offline 25/79). Bez commita | todo |
| T43 Normalizacja `lit` i pytanie o lampę | `normalize_lit` (`yes`/`yes_conditional`/`no`/`unknown_value`/`missing`); `street_lamp_visible` z nowym `prompt_version` | PRD F5.2, F4.2; A2 §3.5; A3 §3.1, D-003-1; NRM-05 (`lit`) | T29 | OpenCode MiMo-V2.6-Flash, 2 rundy; zapas Haiku | `app/src/mapqa/normalize/lit.py`, `app/src/mapqa/questions/catalog.py`, `app/tests/unit/test_normalize_lit.py`, `app/tests/unit/test_questions.py` | Red: tabela NRM-05. Polskie `criteria` akceptuje orkiestrator. Commit `Backend: add lit normalization and street lamp question` | done (Haiku 5.5 zamiast OpenCode: bez --auto brak zapisu w trybie headless) |
| T44 Kandydaci i raport dla `lit` | Reguły F6.1 dla `lit`; `yes_conditional` jako `yes` z notatką; sekcje raportu | PRD F6.1–F6.3, kryt. 10; A4 §3.1–§3.3, §3.6 | T43 | Haiku 5.5 | `app/src/mapqa/candidates/{rules,reasons}.py`, `app/src/mapqa/report/viewmodel.py`, `app/tests/unit/test_candidates.py`, `app/tests/unit/test_report_md.py` | Red: CND-01..07 dla `lit`. Commit `Backend: add lit candidates and report rows` | todo |
| T45 Ewaluacja oświetlenia i pełnych kadrów | `labels.py` czyta `street_lighting_visible` i `speed_limit_value` z `reference_labels.csv`; podział po `sequence`; pełne kadry prędkości (14) opisowo; adnotacja obciążenia próbki | PRD §7, kryt. 11; A4 §3.7–§3.10; EVL-01..03, ISO-03, A0 TAC-12 | T43 | Haiku 5.5 | `app/src/mapqa/evaluation/{labels,metrics,split}.py`, `app/tests/unit/test_evaluation.py` | Red: 79 `certain` / 21 wykluczonych, brak sekwencji w obu częściach. Commit `Backend: evaluate lighting and full-frame speed labels` | todo |
| T46 **GP1:** nagranie pytania o lampę i integracja | Tryb próbny, potem ≤ 4 zapytania (L1, L2), ≤ 0,10 USD; respx z nowych nagrań; `run --attributes speed_limit,lit --dataset photos` | PRD F5.1–F5.4, kryt. 6, 7; A3 §3.3, D-003-6; ISO-01, IMG-03; AGENTS.md | T42 (lub offline), T44, T45; A5 | Orkiestrator | `app/scripts/capture_openrouter.py`, `app/tests/fixtures/captures/openrouter/*lamp*.json`, `app/src/mapqa/pipeline.py`, `app/tests/integration/test_run_lit_respx.py` | Skan klucza (0 trafień). Commit `Backend: wire lighting question with recorded captures` | todo |
| T47 **GP2:** kalibracja i test → **M6** | `eval calibrate --split calibration` i `eval run --split test` dla `lit` (≤ 25 obrazów na uruchomienie) + jeden opisowy przebieg pełnych kadrów; progi przenosi człowiek (U5) | PRD §7, kryt. 11, 12; A4 §3.9, D-004-3; A3 PAID-01, TAC-003-05 | T46; A1–A5 | Orkiestrator | `mapqa.toml` tylko według U5 | Przed każdym płatnym uruchomieniem manifest; kontrola cache **tylko** `--cache-only`. Koszt z `costs.jsonl` do PR. Commit `Docs: record lighting calibration and test results` | todo |
| T48 Normalizacja Overture `speed_limits` | `between` (pozycja rzutu), `when.heading`, pozostałe `when` → `not_comparable` z `raw`, mph | PRD F4.2, F4.3; A2 §3.5; NRM-04, NRM-06 | T34 | **Codex Sol 6.1** | `app/src/mapqa/normalize/overture.py`, `app/tests/unit/test_normalize_overture.py` | Red: NRM-04, NRM-06; test właściwości `raw` na 911 segmentach z wieloma regułami. Commit `Backend: normalize Overture speed limits` | todo |
| T49 Moduł `compare` | `compare(osm, overture)` według A2 §3.6; `implicit`; `overture_from_osm`; wydanie i `osm_timestamp` | PRD F4.1, F4.3, F4.4; A2 §3.6; CMP-01, NRM-07; A0 TAC-12 | T48 | Codex Luna 6 albo OpenCode MiMo | `app/src/mapqa/compare/{__init__,compare}.py`, `app/tests/unit/test_compare.py` | Red: CMP-01 dla wszystkich kombinacji; `compare` bez `httpx`. Commit `Backend: add OSM-Overture comparison` | todo |
| T50 Reguły `sources_*` i raport Overture | `sources_disagree_photo_supports`, `sources_only` (`niski`); w raporcie surowe `when`/`between`, źródło i data | PRD F4.4, F6.1, F6.3, F7.3, kryt. 10; A4 §3.1–§3.3; A0 D10-I3 | T49 | Haiku 5.5; teksty akceptuje orkiestrator | `app/src/mapqa/candidates/{rules,priority,reasons}.py`, `app/src/mapqa/report/{viewmodel.py,templates/report.md.j2}`, testy kandydatów i raportu | Red: CND z `sources_only`. Commit `Backend: add source disagreement candidates` | todo |
| T51 Pipeline z Overture | `run --dataset photos` liczy `compare` dla każdego połączenia; E2E offline; TAC-001-06 po T41 | PRD F4, kryt. 10, 17; A4 E2E-01 | T37, T50 | Orkiestrator | `app/src/mapqa/pipeline.py`, `app/tests/e2e/test_run_photos_e2e.py` | `pt -q`, `-m e2e`, ręczne QA. Commit `Backend: wire Overture comparison into run` | todo |
| T52 `report.html` | Te same sekcje z tego samego modelu widoku; CSS w `<style>`, bez skryptów i base64; względne `thumbs/` | PRD F7.1–F7.5, kryt. 10; A4 §3.6, D-004-1; A0 D6; RPT-03, TAC-004-03 | T51 | Haiku 5.5; wygląd sprawdza orkiestrator (Playwright CLI) | `app/src/mapqa/report/{writer.py,templates/report.html.j2}`, `app/tests/unit/test_report_html.py` | Red: RPT-03; ręczne QA ze zrzutem ekranu. Commit `Backend: add static HTML report` | todo |
| T53 Interfejs trybu porównawczego (proponowany ADR) | A0 §6 nie ma flagi F5.11; propozycja `eval run --compare` (domyślnie wyłączone, A0 D10-I5) z `models.comparison`; aktualizacja A0 §6 i A3 przed kodem (U2) | PRD F5.11; A0 D9, D10-I5; A3 §3.6 | T47 lub T29 | Orkiestrator | `docs/ADR/000-main-architecture.md`, `docs/ADR/003-model-cascade.md` | Spójność linków i ID; bez zgody na U2 → T53–T55 `blocked:U2`. Commit `Docs: specify comparison mode interface` | todo |
| T54 Tryb porównawczy | Drugi model decyzyjny poza kaskadą na zestawie ewaluacyjnym, wspólny budżet (`reserve_usd.compare`), te same bajty obrazu | PRD F5.9, F5.11; A3 §3.6; IMG-03; A4 §3.8 | T53 | Codex Sol 6.1; respx z istniejących nagrań Luna decisions | `app/src/mapqa/evaluation/compare_mode.py`, `app/src/mapqa/cli/main.py`, `app/tests/integration/test_compare_mode.py` | Red: IMG-03, budżet obejmuje `compare`. Commit `Backend: add comparison decision model mode` | todo |
| T55 **GP3:** płatny przebieg porównawczy → **M7** | `eval run --split test --compare` dla `signs` i `lit`; tabela Jev ↔ Luna decisions z mianownikami | PRD F5.11, §7; A0 D10-I5 | T54; A1–A5 | Orkiestrator | — | Manifest, kontrola `--cache-only`, koszt do PR | todo |
| T56 Blokada nawierzchni (P5) | `--attributes surface` → kod 1 i komunikat „nawierzchnia od P5 (brak etykiet `unpaved`)” (U4); adnotacja `no_negative_class` | PRD §7, §9 P5, §11; A4 EVL-04 | T29 | OpenCode MiMo-V2.6-Flash; zapas Haiku | `app/src/mapqa/cli/main.py`, `app/tests/unit/test_cli.py`, `app/tests/unit/test_evaluation.py` | Red: komunikat i kod; EVL-04. Commit `Backend: guard surface attribute until unpaved labels exist` | done (orkiestrator) |
| T57 E2E, kryteria 1–20, ręczne QA | Macierz kryt. 1–20 → dowody; E2E w czystym środowisku (bez `PYTHONUTF8`/`PYTHONIOENCODING`, zamknięty stdin); TAC-03 dla kodów 0–4; TAC-06; czas ≤ 2 min | PRD §6, §8; A0 TAC-01..15; TAC z A1/A2/A4 | T51, T52, T56 (+ T41, T47, T55, jeśli nie `blocked`) | Haiku 5.5 pisze testy; orkiestrator akceptuje | `app/tests/e2e/test_v1_e2e.py`, `app/tests/unit/test_secrets_scan.py` | Kompilacja, testy i start CLI raportowane osobno. Commit `Tests: add v1 end-to-end acceptance checks` | todo |
| T58 Niezależny przegląd i PR → **M8** | `/code-review high` z pełnym URL PR w świeżym kontekście + `codex exec review` (Sol 6.1, read-only); poprawki jako T58.x według TDD; Status i odchylenia; push i PR według A9/A10 | AGENTS.md (Completion Criteria, Commit Rules) | T57 | Silny model w świeżym kontekście + Codex Sol; orkiestrator | tylko w T58.x; ten plan | `gh pr create` z pełnym URL forka. Merge: człowiek. Commit `Docs: update v1 plan status` | todo |
| T59 (opcjonalne, poza PRD) | Propozycje zmian PRD/ADR dla funkcji z wersji prowadzącego: strona ręcznego przeglądu (PR #11), podsumowanie dla kierownictwa (PR #10), `ARROW_STREAM`+`EXTERNAL_LINKS` tylko przy warunku rewizji A1 D-001-2 | PRD §3, §9 „Później”; A1 D-001-2 | T58 i decyzja właściciela | Codex Luna 6 (badanie `git show upstream/...`, read-only) | tylko szkice w `docs/` po zgodzie | **Niewykonywane w `/goal`** | todo |

### 4.1 Zasady przebiegu `/goal`
- **Wznawianie:** od pierwszego wiersza `todo`/`in_progress` w kolejności §3; Status aktualizowany w tym pliku w tym samym commicie co wiersz.
- **Koniec fazy:** `pt -q` i `pt -m e2e -q` zielone dla zmienionego zakresu, commit, push według A9.
- **Blokady:** brak zgody z §0, brak środowiska (Databricks), czerwone kryterium blokujące (TAC-002-02) albo 2 nieudane rundy → `blocked:<powód>` dla wiersza i zależnych; `/goal` idzie dalej niezależnymi wierszami. **Stop** tylko przy przekroczeniu A3/A4, czerwonym baseline, sprzeczności PRD↔ADR na ścieżce krytycznej albo potrzebie zmiany `uv.lock` (A7).
- **Pieniądze:** płatne uruchomienia wyłącznie w GP1–GP3, każde po manifeście; kontrola cache wyłącznie `--cache-only` (0 zapytań); kodu 3 nie ponawiamy automatycznie.

---

## 5. Właściciele i modele

| Rola | Agent / model | Wiersze |
|---|---|---|
| Orkiestrator | Claude Code, silny model (sesja `/goal`) | kontrakty, `pipeline.py`, `cli/main.py`, `uv.lock`, briefy, płatne bramki, integracja, akceptacja; **jedyny** autor commitów |
| Wykonawca domyślny | subagent Claude Code **Haiku 5.5** (`model: haiku`) | T30, T32, T35, T36, T38 (skrypt), T44, T45, T50, T52, T57 |
| Złożone zadania i przegląd | Codex **Sol 6.1** `gpt-6.1-sol` | T34, T39, T48, T54, przegląd T58 |
| Proste zadania i badania | Codex **Luna 6** `gpt-6-luna` | T33, T40, T49, T59 |
| Bardzo proste zadania | OpenCode **MiMo-V2.6-Flash** `xiaomi-token-plan-ams/mimo-v2.6-flash` (zapas `opencode/mimo-v2.6-flash-free`) | T43, T56 |

- **Rundy i eskalacja:** jeden brief i najwyżej 2 rundy poprawek. Eskalacja, gdy test nadal pada, potrzebny jest plik spoza listy albo zmiana kontraktu, lub wykonawca znajdzie sprzeczność w specyfikacji. Kolejność: Haiku/MiMo/Luna → Sol → orkiestrator.
- **Niepotwierdzony model:** wiersz przejmuje Haiku albo orkiestrator; model i liczba rund trafiają do Status.

## 6. Równoległość (najwyżej 3 wykonawców, rozłączne pliki, jedna kopia robocza)

| Fala | Równolegle | Warunek |
|---|---|---|
| A (po T29) | T30 ‖ T33 ‖ T43 | `candidates/queue.py` ≠ `matching/crs.py` ≠ `normalize/lit.py` + `questions/` |
| B (po T32, T33) | T34 ‖ T38 (skrypt) ‖ T56 | `matching/spatial.py` ≠ `scripts/` ≠ `cli/main.py` (T56 przed T37) |
| C (po T34) | T35 ‖ T36 ‖ T48 | `provided.py` + `normalize/{maxspeed,osm}.py` ≠ `profile/` ≠ `normalize/overture.py` |
| D | T44 ‖ T45 ‖ T49 | `candidates/` ≠ `evaluation/` ≠ `compare/` |
| Szeregowo | T37 → T46 → T51 → T54 (`pipeline.py`, `cli/main.py`); T44 → T50 → T52 (`report/`); T39 → T40 (`registry.py`) | wspólne pliki |

Worktree nie jest potrzebny. Gdyby był, najpierw pytamy właściciela; konwencja `../<projekt>-worktrees/<gałąź>`.

## 7. Ryzyka, wycofanie, wariant awaryjny

- **Gorące pliki:** `pipeline.py`, `cli/main.py`, `contract/models.py` (tylko orkiestrator); `report/viewmodel.py` i szablony; `candidates/rules.py`; `mapqa.example.toml`; `uv.lock` (bez zmian, A7).
- **Ryzyka:**
  - Databricks dostępny tylko w oknie właściciela;
  - wygasające adresy Mapillary;
  - zgodność dopasowania < 95% (TAC-002-02);
  - składnia `ST_*` albo limit 25 MiB w Databricks (A1 D-001-2: podział na 4 pasy).
- **Wycofanie:** `git revert <sha>` jednego wiersza; nigdy `reset`, force-push ani push do `upstream`. Diff wykonawcy bez zielonych testów odrzucamy (`git checkout -- <pliki wiersza>`).
- **Wariant awaryjny (od najmniejszego):**
  1. F0 + F1 (M4, offline, 0 USD);
  2. dodatkowo F4 + T52 (Overture i HTML offline);
  3. dodatkowo F3 na 25 zdjęciach offline z etykietą `certain`;
  4. pełny plan.

## 8. Briefy

Brief powstaje tuż przed wysłaniem, w `.agent-briefs/<task>.md` (ignorowane przez Git). Zawiera:
- wycinki PRD/ADR z linkami;
- aktualne sygnatury `contract/`;
- dokładną listę plików do edycji;
- wiersze wykonywane równolegle;
- kroki Red → Green → Refactor;
- wejścia i oczekiwane liczby z §1;
- polecenia weryfikacji;
- warunki eskalacji.

Wykonawca zwraca diff i krótki raport. Nie wykonuje zapisów w Git i nie akceptuje własnej pracy. Brief nie zawiera sekretów, tylko **nazwy** zmiennych.

## 9. Delegowanie w trybie headless (flagi z `--help`, 2026-11-13)

Uruchamiamy z katalogu głównego repozytorium w PowerShell. Codex: `codex` albo `& 'D:\AI\labuser\bin\codex\codex.exe'`.

| Wykonawca | Polecenie (PowerShell) | Uwagi |
|---|---|---|
| Codex (implementacja) | `Get-Content .agent-briefs\T34.md -Raw \| codex exec -C . -m gpt-6.1-sol -s workspace-write --json -o .agent-briefs\T34.result.md -` | prompt ze stdin (`-`); `workspace-write` ogranicza zapis do repozytorium; `--ephemeral` pomija pliki sesji |
| Codex (przegląd) | `codex exec review` albo `codex exec -m gpt-6.1-sol -s read-only "Review the diff origin/main...HEAD against docs/PRD.md and docs/ADR/ ..."` | tylko odczyt |
| OpenCode | `opencode run -m xiaomi-token-plan-ams/mimo-v2.6-flash --title T43 --format json -f .agent-briefs\T43.md "Execute the attached brief."` | `--auto` tylko z projektowym `opencode.jsonc` z regułami `deny` (T31) |
| Claude Code | `claude -p (Get-Content .agent-briefs\T32.md -Raw) --model haiku --output-format json --permission-mode acceptEdits --allowedTools "Read,Edit,Write,Bash(uv run *)"` | zalecane: narzędzie Agent z sesji orkiestratora |

Zasady:
- jeden wykonawca na wiersz, najwyżej 3 naraz; orkiestrator czeka na wszystkie wyniki;
- żadnych flag automatycznej zgody bez reguł `deny` dla push, `main` i sekretów;
- orkiestrator sam odtwarza testy wiersza i czyta diff przed commitem.

## 10. Bramki wymagające człowieka

| Bramka | Wiersz | Warunek przejścia w `/goal` |
|---|---|---|
| G-plan | przed T30 | akceptacja planu, wypełnione §0, odpowiedzi na U2–U6 |
| GDB | T38, T41 | A8: sesja właściciela ze zmiennymi `DATABRICKS_*` |
| GNET | T42 | A6 |
| GP1 / GP2 / GP3 | T46 / T47 / T55 | A1–A5; każde uruchomienie po manifeście; `--yes` tylko w ramach zgody |
| U5 progi | T47 | przeniesienie progów robi człowiek (A4 D-004-3); `/goal` zapisuje propozycję w `calibration.json` i idzie dalej |
| Push / PR | koniec faz, T58 | A9, A10; merge wykonuje człowiek |

## 11. Nierozstrzygnięte decyzje (z proponowaną wartością domyślną)

- **U1 (rozstrzygnięte):** poprawki z przeglądu zostały zintegrowane i zacommitowane (`ed4a44e`).
- *(2026-11-13: właściciel przyjął wartości domyślne U2–U6.)*
- **U2, interfejs F5.11:** zgoda na `eval run --compare` i aktualizację A0 §6 / A3 (domyślnie: tak).
- **U3, `invalid_response` w cache:** zostaje zgodnie z A3 §3.7. Wpis unieważnia zmiana `prompt_version`.
- **U4, `--attributes surface` przed P5:** domyślnie kod 1 `attribute_not_available` z podpowiedzią.
- **U5, zapis progów `lit`:** jak w MVP U6. Domyślnie lokalny `mapqa.toml` bez commita, a wartości w PR i `evaluation.json`.
- **U6, PR #3 / T28 planu MVP:** domyślnie PR v1 zależy od #3 (ta sama gałąź); kolejność merge'ów ustala właściciel.

## 12. Weryfikacja szkicu

| Kontrola | Wynik |
|---|---|
| Identyfikatory testów, TAC i decyzji w macierzy | ✅ grep po `docs/ADR/*.md` i `docs/PRD.md` (planista + orkiestrator, 2026-11-13) |
| Zakres kontra PRD §9 P1–P5 i „Później” | ✅ P5 tylko blokada; „Później” i funkcje prowadzącego wyłącznie w T59 |
| Flagi CLI | ✅ istnieją w `cli/main.py`; `--compare` **nie istnieje** w A0 §6 → T53/U2 |
| Fakty o danych (§1) | ✅ DuckDB i `ls`, tylko odczyt, 2026-11-13 |
| Flagi headless (§9) | ✅ `codex exec --help` 0.167.2, `opencode run --help` 2.2.5, `claude --help` |
| Linki względne | ✅ sprawdzone przy zapisie |

## 13. Pierwsze ograniczone zadanie i bramka przeglądu

- **Pierwsze zadanie po G-plan:** T30 (kolizje `item_id`) równolegle z T33 i T43 (fala A). T31 można wykonać od razu, bo tylko czyta i zapisuje id modeli w planie.
- **Bramka przeglądu:** właściciel wypełnia §0 i odpowiada na U2–U6. Najlepiej uruchomić `/goal` z okna PowerShell ze zmiennymi `DATABRICKS_*`. Do tego czasu nie powstają briefy, agenci, płatne zapytania ani commity kodu.
