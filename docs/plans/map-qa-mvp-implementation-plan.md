# Plan implementacji: Map QA Copilot — MVP (plaster `signs/` end-to-end)

| | |
|---|---|
| Status | **ZREALIZOWANY (T01–T27); T28 = PR #3 otwarty** |
| Data | 2026-11-12 |
| Ścieżka | `docs/plans/map-qa-mvp-implementation-plan.md` |
| Gałąź | `map-app-implementation` (śledzi `origin/map-app-implementation`) |
| Źródła (nadrzędne wobec planu) | [PRD](../PRD.md) (§3, F1–F8, §7, §8, §9 „Zakres MVP”, §10, §11) · [ADR-000](../ADR/000-main-architecture.md) · [ADR-001](../ADR/001-data-sources.md) · [ADR-002](../ADR/002-spatial-matching-and-normalization.md) · [ADR-003](../ADR/003-model-cascade.md) · [ADR-004](../ADR/004-reporting-and-evaluation.md) · [profil danych](../../reports/map-qa/profile.md) · [AGENTS.md](../../AGENTS.md) · [specyfikacja planu](../../course-materials/Prompt%20examples/Plan-SubAgents-matrix-dependency-map.md) |

> **Planowanie nie autoryzuje wykonania.** Ten dokument nie uruchamia agentów, płatnych zapytań, publikacji ani merge'a. Wymagania, kontrakty i identyfikatory testów są w PRD i ADR; plan tylko je wskazuje i nie kopiuje treści. W razie sprzeczności rozstrzyga PRD (kwestie biznesowe) albo ADR właściwy dla obszaru (kwestie techniczne), zgodnie z ADR-000 §1.

Skróty w macierzy:
- `PRD F5.4` = wymaganie w PRD;
- `A0 §6` = ADR-000 §6, analogicznie `A1`–`A4` dla ADR-001–004;
- `kryt. N` = PRD §8, kryterium N.

Polecenia uruchamiamy z katalogu głównego repozytorium.

### Weryfikacja szkicu (2026-11-12, przed zapisem)

| Kontrola | Wynik |
|---|---|
| Identyfikatory testów, TAC i decyzji użyte w macierzy (111 sztuk, np. NRM-01, SCH-01, CAS-01..05, TAC-004-08, D-003-6, D13) | ✅ wszystkie istnieją w PRD/ADR |
| Numeracja kryteriów PRD §8 (1–20) i mapowanie kryteriów MVP | ✅ zgodne z PRD §9 „Kryteria akceptacji MVP” |
| Zakres plastra vs PRD §9 „Zakres MVP” i „Poza MVP” | ✅ zgodny, bez elementów P1–P5 |
| Flagi CLI (`--dataset`, `--model`, `--no-model`, `--yes`, `--max-queries`, `--split`, `--output`) i forma `uv run --project app` | ✅ zgodne z A0 §6 i §3 |
| Decyzje z 12.11: Jev jako poziom 1, opt-in `--model` z manifestem i `y/N`, limity 100 zapytań / 25 obrazów / 1 USD, bezpiecznik, timeout 60 s, DuckDB i argparse, Pillow 12.0.0, `PL:*` z tagów typu z zasadą „liczba wygrywa”, miniatury przez ścieżki względne, kod 4 | ✅ odzwierciedlone w wierszach T08, T13–T22 |
| Fakty o zestawie `signs/` z §1 (zapytania DuckDB, tylko odczyt) | ✅ potwierdzone: 95/24 źródła, 22 puste `maxspeed`, flagi 35/9/6/4/75 pustych, etykiety 115 `certain` / 4 `uncertain`, 89 liczbowych → 25 zgodnych / 46 różnych / 18 bez `maxspeed`, 73 drogi z typem `PL:*` po złączeniu, `heading_diff_deg` 0,01–87,86 |
| Zasady AGENTS.md: Red → Green → Refactor w każdym wierszu, nagrania przed mockami, osobne kontrole buildu, testów i startu, ręczne QA CLI, brak commitów na `main`, commity tylko orkiestratora | ✅ |

---

## 1. Stan wyjściowy (zweryfikowano 2026-11-12, tylko odczyt)

| Element | Stan | Dowód |
|---|---|---|
| `app/` | Tylko ogólny `README.md` (lista kontrolna Next.js, nie pasuje do stosu Python). Brak `pyproject.toml`, `uv.lock`, kodu, testów i punktu wejścia | `ls app` |
| Testy bazowe | **Brak.** Nie ma czego uruchomić, więc nie ma też błędów bazowych. Pierwsze zadanie tworzy szkielet zgodny z A0 §3 | — |
| Git | Czyste drzewo robocze. PR #3 (dokumentacja) otwarty, niescalony z `main` | `git status -sb`, `git log` |
| Narzędzia | uv 0.13.7, Python 3.12.16 (przez uv), DuckDB 1.5.6 + spatial | `uv run --python 3.12 course-materials/exercise-data/map-qa/profile_data.py` (kod 0, ~5–60 s) |
| OpenRouter | `OPENROUTER_API_KEY` ustawiony. Nie wysłano jeszcze żadnego zapytania. Pierwsze nagranie wymaga zgody (A3 D-003-6) | A0 §1 |
| Databricks | CLI 1.26.0 działa tylko w sesji PowerShell użytkownika. W MVP niepotrzebny (P1) | A0 §1, PRD §9 |
| Tracker | Zgłoszenia GitHub wyłączone w forku. Status prowadzimy w kolumnie „Status” macierzy (§4) i w liście kontrolnej PR | `gh issue list` |
| `.gitignore` | Ignorowane: `.agent-briefs/`, `/reports/map-qa/*` (oprócz `profile.md`), `course-materials/exercise-data/map-qa/data/`. **Nieignorowany:** `mapqa.toml` w katalogu głównym | `git check-ignore -v` |
| Harness | Claude Code jako orkiestrator (subagenci przez narzędzie Agent, tani wykonawca Haiku). Codex CLI (tani wykonawca Luna). opencode 2.2.5 zainstalowany, ale nieskonfigurowany i nieużywany. Windows 11, PowerShell 7, bez sandboksa Linux | — |

**Fakty o zestawie `signs/`** (stdlib i DuckDB, tylko odczyt):
- **Pliki:** 119 wycinków `crops/`, 119 kadrów `photos/`, `nearest_osm.csv` ma 119 wierszy. Drogi pochodzą z `osm_roads.parquet` (95) albo z `osm_api` (24).
- **Etykiety `labels.csv`:** 115 `certain`, 4 `uncertain`. Wśród 89 liczbowych etykiet `certain` 25 zgadza się z OSM, **46 się różni**, a przy 18 brakuje `maxspeed` (potwierdza PRD §9).
- **`match_flags`:** `ambiguous_candidates` 35, `poor_heading_alignment` 9, `service_way` 6, `outside_standard_25m` 4, puste 75.
- **Kierunek:** `heading_diff_deg` mieści się w 0,01–87,86, czyli w zakresie 0–90°. Brak kierunku skierowanego.
- **Prędkość:** `maxspeed` puste w 22 wierszach, `maxspeed_forward`/`backward` w 2, `maxspeed_conditional` w 9.
- **Typ `PL:*`:** `nearest_osm.csv` nie ma `maxspeed:type` ani `source:maxspeed`. Po złączeniu z `osm_roads.parquet` po `osm_way_id` typ jest znany dla 73 ze 119 wierszy. 24 drogi z `osm_api` nie mają tagów w snapshocie (zob. U1).

---

## 2. Zakres plastra

**W zakresie:** dokładnie [PRD §9 „Zakres MVP”](../PRD.md) i „Kryteria akceptacji MVP”:
- CLI `mapqa run`, `sources list/check`, `--output json` i kody wyjścia;
- konfiguracja źródeł z jednym adapterem `files`;
- jeden atrybut, `speed_limit`, na wycinkach `signs/`;
- dopasowanie z `signs/nearest_osm.csv` z przeniesionymi flagami;
- pełna kaskada z progiem, cache, budżetem, bezpiecznikiem i logiem kosztów;
- porównanie z OSM `maxspeed` (A2 §3.5, w tym typy `PL:*` i zasada „liczba wygrywa”, zależnie od U1);
- kandydaci, priorytety i `manual_queue.csv`;
- `report.md` z miniaturami `thumbs/` i `evaluation.json`;
- ewaluacja po `sequence` z porównaniem z detektorem Mapillary;
- testy z mockami z nagrań i jedno prawdziwe uruchomienie `--model`.

**Kamienie milowe:**
- **M1:** offline `mapqa run --dataset signs` (bez `--model`), pełny przebieg bez płatnych wywołań (A4 E2E-01);
- **M2:** `--model` z mockami z nagrań i jedno prawdziwe uruchomienie (A3 PAID-01, A4 E2E-02);
- **M3:** ewaluacja, kalibracja i test, przegląd, PR.

**Poza zakresem** (PRD §9 „Poza MVP”, oznaczenia [P1]–[P5] w ADR):
- **[P1]:** adaptery `databricks` (REST i CLI), filtr bbox w SQL, własne dopasowanie EPSG:2180 i F3.5, flagi `grade_separated`, `service_or_restricted`, `distance_mismatch`, pełny profil F2, kryteria 1–4 i 16–18, `--dataset photos`;
- **[P2]:** oświetlenie;
- **[P3]:** porównanie z Overture i reguła `sources_only`;
- **[P4]:** `report.html` i model porównawczy F5.11;
- **[P5]:** nawierzchnia;
- **później:** dashboard, zapis decyzji, MCP.

Nagrania Databricks (DB-01, DB-02) nie są potrzebne w MVP.

**Mapowanie kryteriów MVP na zadania:**

| Kryterium | Zadania |
|---|---|
| 5 flagi widoczne | T10, T14 |
| 6 izolacja | T20 |
| 7 kaskada | T18, T21 |
| 8 cache | T21, T22 |
| 9 budżet | T16, T21 |
| 10 raport (prędkość, MD) | T13, T22 |
| 11 ewaluacja | T23, T24 |
| 12 progi na zbiorze testowym | T25 |
| 13 sekrety | T20, T26 |
| 14 stabilne id kolejki | T12, T26 |
| 15 wybór źródła | T04 |
| 19 JSON dla agenta | T05, T07, T14 |
| 20 płatne wywołania | T14, T21 |
| „46 rozbieżności”, liczby vs `none`, porównanie z detektorem | T23, T24 |

---

## 3. Fazy

Każda faza kończy się zielonymi testami w swoim zakresie i commitem na gałęzi funkcjonalnej. Fazy, które dotykają CLI, kończą się ręczną kontrolą CLI.

| Faza | Zadania | Cel |
|---|---|---|
| **F0** Szkielet i kontrakty | T01–T03 | projekt uv, przypięte wersje, kontrakt schematu z rzeczywistego `DESCRIBE`, typy domenowe, testy architektury |
| **F1** Konfiguracja, CLI, źródło `files` | T04–T07 | precedencja źródła, koperta JSON, kody wyjścia, `DataBundle` dla `signs` |
| **F2** Normalizacja i pytania | T08–T09 | czyste funkcje, testy tabelaryczne |
| **F3** Dostarczone połączenia i profil | T10–T11 | |
| **F4** Kandydaci, kolejka, raport, pipeline `--no-model` | T12–T14 | → **M1** |
| **F5** Odczyt modelem | T15–T22 | przygotowanie obrazu, budżet, cache i kaskada na atrapach naszych portów; potem bramka G2 (nagranie), klienci z mockami z nagrań, integracja `--model` i bramka G3 (płatne uruchomienie) → **M2** |
| **F6** Ewaluacja | T23–T25 | izolowany `Evaluator`, `eval run/calibrate`, bramka G4 |
| **F7** Domknięcie | T26–T28 | E2E i TAC, ręczne QA, niezależny przegląd, PR → **M3** |

---

## 4. Macierz zależności (jedyne źródło statusu wykonania)

W każdym wierszu najpierw powstaje test behawioralny, który ma paść z oczekiwanego powodu („Red”). Jeden wiersz to jeden commit w formacie `Area: summary`, wykonany przez orkiestratora. `pt` oznacza `uv run --project app pytest`.

| Task | Observable outcome | PRD/ADR links | Prerequisites | Owner/model | Editable files | Verification and handoff | Status |
|---|---|---|---|---|---|---|---|
| T01 Szkielet `app/` | `uv run --project app mapqa --help` → kod 0; `pt app/tests -q` zbiera testy, `e2e`/`paid` domyślnie pominięte | A0 §2 (wersje `==`, zasada przypinania), §3, TAC-01, TAC-08, TAC-09 | G0, G1 | Orkiestrator (silny model), bo zmienia lockfile | `app/pyproject.toml`, `app/uv.lock`, `app/src/mapqa/__init__.py`, `app/src/mapqa/cli/__init__.py` (zaślepka `main(argv)->int`), `app/tests/conftest.py`, `app/tests/unit/test_packaging.py`, `app/README.md` | Red: `test_packaging.py` (wszystkie zależności z A0 §2, także dev, z `==`; `main(["--help"])==0`) pada przy braku pakietu. Green: `uv lock`, `uv sync --project app`. Sprawdzić, że pytest nie zbiera `course-materials/` (U3). Konflikt wersji: obniżyć jedną bibliotekę (nigdy Pillow) i opisać w „Odchylenia od ADR”. Commit `Backend: scaffold mapqa package with uv and pytest` | done |
| T02 Kontrakt schematu | `app/tests/fixtures/schema_expected.json` z rzeczywistego `DESCRIBE` 6 plików + `distinct_values` (`candidate_flags`, `match_flags`, `road_surface[].value`), data i `sha256` | A1 §3.7, SCH-01, SCH-02, TAC-001-07; profil | T01 | Haiku (skrypt i test); orkiestrator uruchamia snapshot | `app/scripts/snapshot_schema.py`, `app/tests/fixtures/schema_expected.json`, `app/tests/integration/test_schema_contract.py` | Red: brak fixture → czerwony. Snapshot raz, tylko odczyt. Liczby kolumn porównane z profilem (26/14/21/11). Kontrolowana mutacja typu w kopii w `tmp_path` → czerwony z nazwą tabeli i kolumny. `pt app/tests/integration/test_schema_contract.py -q`. Commit `Tests: add schema contract snapshot from real DESCRIBE` | done |
| T03 Kontrakt i typy domenowe | Modele A0 §5 (`RunParams`, `SourceDescriptor`, `RejectedRecord`, `PhotoRoadLink`, `AttributeValue`, `ModelAttempt`, `CascadeResult`, `Candidate`, `QueueItem`, `CostLogEntry`, `EvaluationReport`), koperta JSON, wyjątki → kody 1/2/3/4, `DataBundle` bez pól etykiet | A0 §4–§6, D10; A1 §3.2, §4; TAC-02, TAC-12, TAC-15; A4 ISO-03, TAC-004-07 | T01 | Orkiestrator (kontrakt współdzielony) | `app/src/mapqa/contract/{__init__,models,bundle,errors}.py`, `app/tests/unit/test_contract_models.py`, `app/tests/unit/test_architecture.py` | Red: walidacja koperty, mapowanie wyjątków na kody, test architektury. Kontrolowana mutacja (tymczasowy `import httpx` w module rdzenia → czerwony, potem cofnięcie). Commit `Backend: add data contract, domain models and architecture tests` | done |
| T04 Konfiguracja | `config.load(flags, env)`: precedencja `--source` > `MAPQA_SOURCE` > `default_source` > `files`, `resolved_by`, wbudowane `files`, `unknown_source` z listą, regex `*_env`; `app/mapqa.example.toml` z domyślnymi wartościami PRD | PRD F1.3, F8.1–F8.2, F8.8, kryt. 15; A1 §3.1, CFG-01..04; A0 D10-I7, §7, TAC-10 | T03 | Haiku | `app/src/mapqa/config/{__init__,loader,schema}.py`, `app/mapqa.example.toml`, `app/tests/unit/test_config.py` | Red: CFG-01..04, domyślne wartości TAC-10. `pt app/tests/unit/test_config.py -q`. Commit `Backend: add config loading with source precedence` | done |
| T05 Szkielet CLI | argparse: `run`, `sources list/check`, `eval run/calibrate` z flagami A0 §6; `--output json` → na stdout tylko koperta; walidacja bbox przed adapterem | PRD F1.1, F8.9, kryt. 19; A0 §6, D13, TAC-02, TAC-03 (kody 1/2) | T03, T04 | Codex Luna | `app/src/mapqa/cli/{main,output,bbox}.py`, `app/tests/unit/test_cli.py` | Red: `main(["run","--bbox","20.15,49.95,19.80,50.15","--output","json"])` → 1, `invalid_bbox`, adapter (atrapa) niewywołany. Ręcznie: to samo przez `uv run --project app mapqa ...` → jeden dokument JSON. Commit `Backend: add CLI skeleton with JSON envelope and exit codes` | done |
| T06 Adapter `files` | `FilesAdapter.load` → `DataBundle` z `signs` i `sign_nearest_osm` (mapowanie `compass_angle`→`heading`, `creator`→`author`), weryfikacja `crop_sha256` → `missing_file`/`hash_mismatch`, bbox tylko przy jawnym `--bbox`, lista przeczytanych plików, ewentualnie widok tagów OSM (U1); `check()` → liczności 5 tabel | PRD F2.2, F2.4, F8.3–F8.4; A1 §3.2–§3.3, §4; A0 D10-I2; FIL-01..06, CON-01 (część `files`) | T02, T04 | Haiku; SQL i bbox eskalowane do orkiestratora | `app/src/mapqa/sources/{__init__,base,files,registry}.py`, `app/src/mapqa/sql/files_*.sql`, `app/tests/contract/test_source_contract.py`, `app/tests/unit/test_files_adapter.py`, `app/tests/fixtures/data/signs_mini/**` | Red: FIL-02..06 na kopii w `tmp_path`, CON-01 na prawdziwych plikach (119/119). Adapter nie otwiera `labels.csv`. `pt app/tests/contract app/tests/unit/test_files_adapter.py -q`. Commit `Backend: add files source adapter for signs dataset` | done |
| T07 `sources list/check` | `uv run --project app mapqa sources list --output json` → `files` z `resolved_by`; `sources check` → 99 768 / 85 405 / 561 / 561 / 1730 | PRD F8.9, kryt. 19; A1 §5, TAC-001-02, FIL-01 | T05, T06 | Haiku | `app/src/mapqa/cli/sources_cmd.py`, `app/tests/unit/test_cli_sources.py`, `app/tests/e2e/test_sources_e2e.py` | Red: unit + e2e (`-m e2e`). Ręczne QA w PowerShell (text i json), wynik zapisany. Commit `Backend: add sources list and check commands` | done |
| T08 Normalizacja `maxspeed` | `normalize_maxspeed` → `AttributeValue` według tabeli A2 §3.5: typ z `maxspeed:type` > `source:maxspeed`, „liczba wygrywa” + `type_value_conflict`, `sign` bez liczby → `not_comparable`, `implicit`, warunkowe, kierunkowe (U2); równość \|Δ\| < 0,5 | PRD F4.2; A2 §3.5, D-002-2, D-002-4; NRM-01, NRM-02, NRM-03, TAC-002-03 | T03; decyzje U1, U2 | Codex Luna | `app/src/mapqa/normalize/{__init__,maxspeed,speed}.py`, `app/tests/unit/test_normalize_maxspeed.py`, `app/tests/integration/test_normalize_osm_raw.py` | Red: NRM-01 sparametryzowany wszystkimi przypadkami brzegowymi z A2 §8; TAC-002-03 na unikalnych `maxspeed` z `osm_roads.parquet`. `pt app/tests/unit/test_normalize_maxspeed.py app/tests/integration/test_normalize_osm_raw.py -q`. Commit `Backend: add OSM maxspeed normalization` | done |
| T09 Katalog pytań | `speed_limit_value`: 14 opcji, `value_options`, opisy `criteria`, `prompt_version` z `image_prep.v2`, mapowanie `none`/`unreadable`; pozostałe pytania w P2/P5 | PRD F5.2; A3 §3.1, D-003-1; A0 D10-I1 | T03 | Haiku; polskie `criteria` akceptuje orkiestrator (trafiają do płatnego promptu i nagrania) | `app/src/mapqa/questions/{__init__,catalog}.py`, `app/tests/unit/test_questions.py` | Red: opcje dokładnie z F5.2, zmiana tekstu → nowy `prompt_version`. Commit `Backend: add speed limit question catalog` | done |
| T10 Dostarczone połączenia | `ProvidedLinkMatcher` → 119 `PhotoRoadLink` (`link_source=provided`), flagi z `match_flags` bez zmian, `missing_heading` tylko dla null | PRD F3.3–F3.4, kryt. 5; A2 §3.3–§3.4; MAT-08 (wariant `signs`), HDG-02 | T06 | Haiku | `app/src/mapqa/matching/{__init__,provided}.py`, `app/tests/unit/test_provided_matcher.py`, `app/tests/integration/test_provided_links_signs.py` | Red: liczności flag zgodne z SCH-02 (35/9/6/4), żadne zdjęcie nie znika. Commit `Backend: map provided sign links to photo road links` | done |
| T11 Profil (zakres `signs`) | Liczności total/w bbox, odrzucone rekordy z przyczyną, kompletność `maxspeed` „x% (n/N)” z typami `PL:*`, adnotacja o obciążeniu próbki | PRD F2.3 (część), §7; A4 §3.6 sekcja 2; A0 §5 `RejectedRecord` | T06, T08 | Haiku | `app/src/mapqa/profile/{__init__,profile}.py`, `app/tests/unit/test_profile.py` | Red: jawne mianowniki, `outside_bbox` przy jawnym bbox. Commit `Backend: add signs input profile` | done |
| T12 Kandydaci i kolejka | `build_candidates` (`photo_vs_osm`, `osm_missing_photo_confident`), priorytety, `reason_pl` z „implicit” i flagami, `build_queue` z `item_id`, pozycje `nierozstrzygnięty_odczyt`, sortowanie | PRD F6.1–F6.7, kryt. 14; A4 §3.1–§3.4; A0 D10-I1, I4; CND-01..07, QUE-01, QUE-02, TAC-004-02 | T08, T09 (syntetyczne `CascadeResult`, bez F5) | Codex Luna | `app/src/mapqa/candidates/{__init__,rules,priority,reasons,queue}.py`, `app/tests/unit/test_candidates.py`, `app/tests/unit/test_queue.py` | Red: CND-01..07, QUE-01..02 (`skipped_no_model` → brak pozycji). Commit `Backend: add candidate rules and manual queue` | done |
| T13 Raport Markdown | `ReportViewModel`, `report.md.j2` z sekcjami 1–9 w kolejności A4 §3.6 (bez modelu: „Odczyt modelem nie był uruchomiony”), `manual_queue.csv` (UTF-8 z BOM, nagłówek z A4 §3.4), miniatury 320 px w `thumbs/` (ścieżki względne), `run.json`, format `run_id` | PRD F7.1–F7.6 (bez HTML); A4 §3.4–§3.6, D-004-1, D-004-2; RPT-01, RPT-02, RPT-04, QUE-03; A0 D6, TAC-11 | T11, T12 | Haiku; orkiestrator przegląda polskie teksty | `app/src/mapqa/report/{__init__,viewmodel,writer,thumbs}.py`, `app/src/mapqa/report/templates/report.md.j2`, `app/tests/unit/test_report_md.py`, `app/tests/unit/test_queue_csv.py` | Red: snapshot sekcji, BOM i kolumny, „Miniatura niedostępna”. Commit `Backend: add Markdown report and queue CSV writer` | done |
| T14 Pipeline `--no-model` → **M1** | `uv run --project app mapqa run --dataset signs` (i z `--no-model`) → `reports/map-qa/<run_id>/` z `report.md`, `manual_queue.csv`, `run.json`; `skipped_no_model`, 0 żądań HTTP, bez wymaganego klucza; `sha256` wejść przed i po, kod 4 przy zmianie (U4) | PRD F1.4, F2.2, kryt. 5, 20 (część); A0 §6, D11, D12, TAC-13, TAC-14; A3 NOM-01; A4 E2E-01, INP-01, TAC-004-08 | T07, T10, T13 | Orkiestrator (integracja); testy pisze Haiku | `app/src/mapqa/pipeline.py`, `app/src/mapqa/cli/run_cmd.py`, `app/tests/integration/test_pipeline_no_model.py`, `app/tests/e2e/test_run_no_model.py` | Red: E2E-01, NOM-01 (respx bez tras, środowisko bez klucza), INP-01. Potem `pt app/tests -q` i `pt app/tests -m e2e -q`, liczności testów i pominięć raportowane osobno. Ręczne QA w PowerShell: text i json, przegląd `report.md` i CSV, pomiar czasu. Commit `Backend: wire no-model pipeline for signs dataset` | done |
| T15 Przygotowanie obrazu | `ImagePreparer`: `exif_transpose`, skala 280–1568 px, JPEG q92 bez EXIF, `image_out_of_bounds`; `PreparedImage` = wyłącznie bajty i MIME | PRD F5.6a, F5.1; A3 §3.2, D-003-7; IMG-01, IMG-02, IMG-03 (część) | T03 | Haiku | `app/src/mapqa/models/{__init__,image_prep}.py`, `app/tests/unit/test_image_prep.py` | Red: syntetyczne obrazy w `tmp_path` (120×140, 4000×3000, EXIF 6, 40×400, GIF). Obserwacja na 119 wycinkach: liczba `image_out_of_bounds`. Commit `Backend: add image preparation for model input` | done |
| T16 Budżet i log kosztów | `Budget.reserve/commit/open_circuit` (limity zapytań, obrazów i USD, rezerwacja per rola), `costs.jsonl` z polami F5.10 | PRD F5.9–F5.10, kryt. 9; A3 §3.6, §3.8, D-003-5; BUD-01..03, LOG-01, TAC-003-03 | T03 | Codex Luna | `app/src/mapqa/budget/{__init__,budget,cost_log}.py`, `app/tests/unit/test_budget.py`, `app/tests/unit/test_cost_log.py` | Red: BUD-01..03, LOG-01 (brak klucza i base64 w logu). Commit `Backend: add query budget and cost log` | done |
| T17 Cache SQLite | Klucz z A3 §3.7; status przeliczany z pewności przy odczycie; `model_unavailable`/`budget_exceeded` nie trafiają do cache; katalog konfigurowalny | PRD F5.8; A3 §3.7, D-003-4; A0 D5; CAC-02, CAC-03 | T03 | Haiku | `app/src/mapqa/cache/{__init__,sqlite_cache}.py`, `app/tests/unit/test_cache.py` | Red: CAC-02 (ta sama treść pod inną nazwą pliku → ten sam klucz), CAC-03. Testy w `tmp_path`. Commit `Backend: add SQLite model answer cache` | done |
| T18 Kaskada (atrapy portów) | `Cascade.resolve` według A3 §3.5: kolejność cache → bezpiecznik → budżet, eskalacja tylko przy `below_threshold`/`invalid_response`, progi per poziom × model × atrybut z ostrzeżeniem „próg niekalibrowany” | PRD F5.4–F5.7, kryt. 7; A3 §3.5, D-003-3; CAS-01..05, THR-01, TAC-003-02, TAC-003-06 | T09, T15, T16, T17 | Brief: orkiestrator; wykonanie: Codex Luna; logika bezpiecznika eskalowana po 2 nieudanych rundach | `app/src/mapqa/cascade/{__init__,cascade,thresholds}.py`, `app/tests/unit/test_cascade.py` | Red: CAS-01..05, THR-01. Atrapy zastępują **nasz** port klienta (zwracają `ModelAttempt`), a nie HTTP, więc nie łamią zasady nagrań. Commit `Backend: add escalation cascade with circuit breaker` | done |
| T19 **Bramka G2:** nagranie OpenRouter | ≤ 6 prawdziwych zapytań, ≤ 0,20 USD; nagrania z metadanymi i redakcją; rozstrzygnięte: format obrazu w Decisions, pełne `probabilities`, nazwa `max_tokens`, `usage.cost` | A3 D-003-6, §2, §4 (`Capture`); AGENTS.md (nagrania przed mockami); A0 TAC-07 | T09, T15, zgoda G2 (U8) | Skrypt pisze Haiku przed zgodą; uruchamia orkiestrator po zgodzie | `app/scripts/capture_openrouter.py`, `app/tests/fixtures/captures/openrouter/*.json`, `app/tests/unit/test_captures_meta.py` | Najpierw tryb próbny bez sieci (plan żądań i maksymalny koszt). Po zgodzie: nagranie, skan wzorca klucza (0 trafień), TAC-07. Fakty sprzeczne z A3 → stop i aktualizacja ADR (`Docs:`) przed T20. Commit `Tests: add OpenRouter captures for decisions and chat` | done (G2 2026-11-13: 4 zapytania, ~0,00014 USD) |
| T20 Klienci i parsery | `DecisionsClient`/`ChatClient` (httpx, timeout 60 s, bez ponowień), `parse_decision`/`parse_chat`, klasyfikacja błędów; żądanie zawiera tylko obraz i pytanie | PRD F5.1, F5.3–F5.4, kryt. 6, 13; A3 §3.3–§3.4; A0 D4; ISO-01, ISO-02, PAR-01, PAR-02, ERR-01, ERR-02, SEC-01, TAC-003-01, TAC-003-04 | T18, T19 | Codex Luna; izolację przegląda orkiestrator | `app/src/mapqa/models/{http,decisions_client,chat_client,parse}.py`, `app/tests/integration/test_openrouter_clients.py` | Red: respx wyłącznie z nagrań T19; TAC-003-04 na 10 losowych wycinkach (stały seed). Commit `Backend: add OpenRouter decisions and chat clients` | done (atrapy wyłącznie z nagrań) |
| T21 Integracja `--model` | Manifest przed pierwszym żądaniem, `y/N`, `--yes`, wykrycie TTY, `confirmation_required` (kod 1, 0 żądań), odmowa → kod 0, `cache_only`, kod 3 z `warnings`, `costs.jsonl` | PRD F1.4, kryt. 7–9, 20; A0 §6, D11, TAC-03, TAC-05; A3 CNF-01, CAC-01, BUD-01; A4 QUE-01 | T14, T18, T20 | Orkiestrator (wspólne `cli/` i `pipeline.py`) | `app/src/mapqa/pipeline.py`, `app/src/mapqa/cli/run_cmd.py`, `app/src/mapqa/cli/confirm.py`, `app/tests/integration/test_run_model_respx.py` | Red: scenariusze (a)–(d) z A0 §10, kryt. 9 z `--max-queries 5`, CAC-01. Ręczne QA: `--model` bez TTY i bez `--yes` → kod 1, brak ruchu sieciowego. Commit `Backend: add confirmed model reading to run command` | done (prawdziwy port podłączony; płatne uruchomienie = T22) |
| T22 **Bramka G3:** płatne uruchomienie → **M2** | `uv run --project app mapqa run --dataset signs --model --yes`: ≤ 25 nowych obrazów, ≤ 100 zapytań, ≤ 1 USD; ponowne uruchomienie z tymi samymi parametrami → 0 nowych zapytań | A3 PAID-01; A4 E2E-02; PRD kryt. 8, 10, §9 (budżet) | T21, zgoda G3 | Orkiestrator i człowiek | brak (ewentualna korekta rezerwacji w `app/mapqa.example.toml`) | Dowody do opisu PR: suma `costs.jsonl`, lejek, kandydaci, zrzut CLI. Commit tylko przy korekcie rezerwacji (`Backend: adjust cost reservations from measured usage`) | done (G3 2026-11-13: 25 obrazów, 26 zapytań, 0,00135 USD; L1 22/24 trafnych; drugie uruchomienie omyłkowo +25 zapytań, 0,00108 USD) |
| T23 Moduł ewaluacji | `evaluation.labels` jako jedyny czytelnik etykiet, `split_by_sequence`, metryki A4 §3.8 (kaskada, poziomy, poziom 1 samodzielnie), podgrupy liczby vs `none`, baseline Mapillary, rozkład 46 rozbieżności, `evaluation.json` | PRD §7, §9, kryt. 11; A4 §3.7–§3.8, §3.10; EVL-01..03, ISO-03, TAC-004-04, TAC-004-05; A0 D10-I4, TAC-12 | T03, T09 (syntetyczne wyniki, bez F5) | Haiku albo Luna; brief nie przekazuje etykiet innym modułom | `app/src/mapqa/evaluation/{__init__,labels,split,metrics,baseline}.py`, `app/tests/unit/test_evaluation.py`, `app/tests/integration/test_split_signs.py` | Red: EVL-01..03, mianownik 0 → `null`, żadna sekwencja w obu częściach. Commit `Backend: add isolated evaluator for sign labels` | done |
| T24 `eval` w CLI i sekcje raportu | `mapqa eval calibrate --split calibration` → `calibration.json`; `mapqa eval run --split test` → `evaluation.json`; sekcje 6–8 raportu (także bez modelu: baseline i 46 rozbieżności) | PRD §7, kryt. 10–12; A0 §6 (`eval`); A4 §3.6, §3.9, D-004-3, CAL-01, TAC-004-01 | T13, T21, T23 | Orkiestrator; CAL-01 pisze Haiku | `app/src/mapqa/cli/eval_cmd.py`, `app/src/mapqa/evaluation/calibrate.py`, `app/src/mapqa/report/viewmodel.py`, `app/src/mapqa/report/templates/report.md.j2`, `app/src/mapqa/pipeline.py`, `app/tests/unit/test_calibrate.py`, `app/tests/integration/test_eval_cli.py` | Red: CAL-01; `eval` bez `--yes` i bez TTY → kod 1. Ręczne QA obu poleceń na ciepłym cache. Commit `Backend: add eval commands and evaluation report sections` | done (na atrapie portu) |
| T25 **Bramka G4:** kalibracja i test | `calibration.json` z części `calibration` (kilka uruchomień na ciepłym cache); człowiek przenosi progi (U6); `eval run --split test`; wynik kryt. 12 udokumentowany (niespełnienie = wynik PoC) | PRD §7, kryt. 12; A4 §3.9, D-004-3 | T24, zgoda G4 (U5) | Człowiek i orkiestrator | `mapqa.toml` według U6 | `evaluation.json` z `acceptance`, liczby z mianownikami do opisu PR | done (G4 2026-11-13: calibration 38 zapytań 0,0033 USD; test 38 zapytań 0,0020 USD; próg L1 0,80 utrzymany: trafność kaskady 57/61 = 93,4%, przekazanie 1/62, pokrycie 57/62, Mapillary 56/60; kryt. 12 spełnione) |
| T26 E2E, TAC i ręczne QA | Testy offline TAC-01 (liczności, pominięcia), TAC-03 dla kodów 0–4, TAC-06 (skan sekretów), TAC-004-01 (porównanie bajtowe), TAC-004-06; lista ręcznego QA wykonana | A0 §10 TAC-01..06, TAC-11..15; A4 TAC-004-01..08 | T22, T24 | Haiku pisze testy; orkiestrator akceptuje | `app/tests/e2e/test_mvp_e2e.py`, `app/tests/unit/test_exit_codes.py`, `app/tests/unit/test_secrets_scan.py` | `pt app/tests -q`, `pt app/tests -m e2e -q`; `paid` tylko świadomie. Kompilacja, testy i start CLI raportowane osobno. Commit `Tests: add MVP end-to-end and technical acceptance checks` | done |
| T27 Niezależny przegląd | Lista znalezisk z oceną; poprawki jako wiersze T27.x (brief, test, commit) | AGENTS.md (Completion Criteria); kryteria MVP PRD §9 | T26 | Silny model w świeżym kontekście (`/code-review high` na diffie względem `main`), opcjonalnie drugi przegląd w Codex; człowiek widzi podsumowanie | tylko w wierszach T27.x | Każda poprawka według TDD; ponowne T26 | done |
| T28 PR → **M3** | Opis PR: kryteria MVP → dowody, „Odchylenia od ADR”, zaktualizowana kolumna Status, koszty bramek | AGENTS.md (Commit Rules); A0 §2 (odchylenia) | T27, G5 | Orkiestrator; push i PR tylko na polecenie użytkownika | `docs/plans/map-qa-mvp-implementation-plan.md` (Status) | Kontrola diffu, linków i spójności. Commit `Docs: update MVP plan status`. Merge wykonuje człowiek | todo |

---

### Odchylenia od planu (2026-11-12)

- T08, T12, T13, T18, T23 wykonał subagent Claude **Sonnet** zamiast Codex Luna (nieinteraktywne uruchamianie Codex niezweryfikowane na tej maszynie); T09, T15, T16, T17 — Claude Haiku zgodnie z planem.
- ADR-003 §3.2 poprawiony: literalna reguła powiększania odrzucała 105/119 wycinków (T15).
- Klucz rezerwy modelu porównawczego to `compare` (zgodnie z ADR-003 §3.6).
- Dodano `--cache-only` (0 zapytań, bez klienta HTTP) i limity w manifeście po pomyłce z drugim płatnym uruchomieniem.
- G3 ujawnił błąd metryki eskalacji (liczyła odmowy budżetu); naprawiony z testem.
- Niezależny przegląd (T27) wykonany po T26; 7 ustaleń naprawionych z testami regresji (commit `c09677b`).

## 5. Właściciele i modele

| Rola | Kto | Zakres |
|---|---|---|
| Orkiestrator | Claude Code, silny model (Opus) | Architektura, kontrakty (`contract/`, `pyproject.toml`/`uv.lock`, `pipeline.py`, `cli/run_cmd.py`), briefy, rozstrzyganie sprzeczności, odtwarzanie testów, akceptacja, integracja, **jedyny** autor commitów |
| Tani wykonawca A | Subagent Claude Code z modelem Haiku (narzędzie Agent, brief ad hoc) | Ograniczone moduły i testy tabelaryczne: T02, T04, T06, T07, T09–T11, T13, T15, T17, T23, T26 |
| Tani wykonawca B | Codex CLI z modelem Luna (nazwę modelu i flagi sprawdzić przez `codex --help` przed pierwszym użyciem) | Logika z wieloma przypadkami: T05, T08, T12, T16, T18, T20 |
| Przegląd i akceptacja | Silny model w osobnym kontekście + człowiek | T27, bramki G0–G5 |

Zasady:
- **Budżet na wiersz:** jeden brief i najwyżej 2 rundy poprawek wykonawcy. Model i liczbę rund wpisujemy w kolumnie Owner/model po wykonaniu.
- **Budżet płatnego API** jest osobny: G2 ≤ 0,20 USD, G3 i G4 ≤ 1 USD na uruchomienie, limit łączny według U5.
- **Eskalacja:** wykonawca zatrzymuje się i raportuje, gdy:
  1. ten sam test nie przechodzi po 2 rundach,
  2. potrzebuje pliku spoza listy albo zmiany kontraktu,
  3. znajdzie sprzeczność ze specyfikacją.

  Orkiestrator wtedy poprawia brief, przejmuje zadanie albo daje je silniejszemu modelowi.
- **Mechanizm:** domyślnie subagenci ad hoc. Nowych plików ról nie tworzymy, bo żadna rola się nie powtarza. Gdy subagenci są niedostępni, orkiestrator wykonuje tę samą macierz sekwencyjnie.

## 6. Równoległość

Równolegle uruchamiamy tylko zadania z niezależnymi wejściami i rozłącznymi plikami, najwyżej 3 wykonawców naraz, żeby orkiestrator nadążał z przeglądem. Każdy brief wymienia zadania, które biegną w tym samym czasie.

| Fala | Zadania równoległe | Warunek |
|---|---|---|
| A (po T03) | T04 ‖ T08 ‖ T09, potem T15 ‖ T16 ‖ T17 | Osobne katalogi `config/`, `normalize/`, `questions/`, `models/image_prep.py`, `budget/`, `cache/` |
| B | T05 ‖ T06 (po T02 i T04); T12 ‖ T18 ‖ T23; pisanie skryptu T19 (uruchomienie czeka na G2) | `cli/` ≠ `sources/`; `candidates/` ≠ `cascade/` ≠ `evaluation/` |
| C | T10 ‖ T11 | `matching/` ≠ `profile/` |
| Sekwencyjnie | T01, T03 (kontrakty i lockfile); T07 → T14 → T21 → T24 (`cli/`, `pipeline.py`); T13 → T24 (szablon raportu) | Wspólne pliki |

Wystarczy jedna kopia robocza. Worktree prawdopodobnie nie będzie potrzebny, bo żadne dwa równoległe zadania nie edytują tego samego pliku. Gdyby to się zmieniło, orkiestrator najpierw pyta o zgodę (AGENTS.md, Git Worktrees).

## 7. Ścieżka krytyczna, ryzyka, wycofanie, wariant awaryjny

**Ścieżka krytyczna:** T01 → T03 → T04 → T06 → T10 → T13 → T14 (M1) → T21 (wymaga T20 ← T19/G2) → T22 (G3) → T24 → T25 (G4) → T26 → T27 → T28.

Na ścieżce leżą bramki wymagające człowieka. O zgodę G2 prosimy od razu po T09 i T15, żeby T19 i T20 powstały równolegle z F3–F4.

**Gorące pliki:**
- `app/pyproject.toml` i `app/uv.lock`: tylko T01; wszystkie zależności z A0 §2 deklarujemy od razu.
- `contract/models.py` i `contract/errors.py`: zmienia tylko orkiestrator; wykonawca może zaproponować pole.
- `cli/run_cmd.py` i `pipeline.py`: T14, T21, T24.
- `report/templates/report.md.j2` i `report/viewmodel.py`: T13, T24.
- `app/mapqa.example.toml`: T04, potem tylko orkiestrator.

**Awarie i wycofanie:**
- Diff wykonawcy, który nie przechodzi odtworzonych testów, nie jest stosowany.
- Jeden wiersz = jeden commit; wycofanie przez `git revert <sha>`, bez `reset` i bez force-push.
- Brak spójnego zestawu wersji w `uv lock`: reguła z A0 §2.
- Czerwony SCH-01 albo kod 4: stop i odświeżenie profilu (AGENTS.md, Map QA data profile).
- Nagranie sprzeczne z A3: stop F5 i aktualizacja ADR przed kodem klientów.
- Kod 3 w płatnym uruchomieniu: bez automatycznego ponowienia, decyduje człowiek (A0 §6).
- Skrypt nagrań ma twardy limit 6 zapytań i 0,20 USD.

**Wariant awaryjny (od najmniejszego):**
1. **Tylko M1:** raport offline z profilem, połączeniami, normalizacją i pustą kolejką; po T23 i T24 także baseline Mapillary i sekcja 46 rozbieżności. Brakujące kryteria (6–9, 11–12) wypisujemy w PR.
2. **Brak zgody na nagranie:** kaskada, budżet, cache i kandydaci testowani na atrapach naszych portów. Klientów HTTP nie piszemy, bo AGENTS.md zabrania mocków bez nagrania, i raportujemy brakujący warunek.
3. **Nagranie i jedno płatne uruchomienie bez kalibracji:** kryt. 12 odłożone, domyślny próg 0,8 z ostrzeżeniem.

## 8. Briefy

- Brief powstaje **tuż przed wysłaniem zadania**, po autoryzacji wykonania, w `.agent-briefs/<task>.md`, np. `.agent-briefs/T08-normalize-maxspeed.md`. Katalog jest ignorowany przez Git (sprawdzone).
- Zawartość briefu:
  - cel i obserwowalny wynik z macierzy;
  - **wycinki** odpowiednich sekcji PRD/ADR z linkami źródłowymi;
  - aktualne sygnatury z `contract/`;
  - wyniki poprzedników (ścieżki, API);
  - dokładna lista plików do edycji;
  - zadania biegnące równolegle;
  - kroki Red → Green → Refactor;
  - wejścia testowe i oczekiwane wyniki (w tym liczby z §1);
  - polecenia weryfikacji;
  - warunki eskalacji.
- Wykonawca zwraca diff, logi Red i Green oraz zauważone sprzeczności. Nie wykonuje żadnych zapisów w Git, nie zmienia zakresu i nie akceptuje własnej pracy.
- Orkiestrator czyta diff, odtwarza testy, w razie potrzeby uruchamia CLI ręcznie, integruje i commituje.

## 9. Bramki wymagające człowieka

| Bramka | Kiedy | Decyzja |
|---|---|---|
| G0 | Przed T01 | Akceptacja planu i odpowiedzi na U1–U10 (blokujące: U1 i U2 dla T08, U3 dla T01) |
| G1 | T01, T02 | Zgoda na pobranie zależności z PyPI i pierwszą instalację rozszerzenia `spatial` (sieć) |
| G2 | T19 | Zgoda na nagranie OpenRouter (≤ 6 zapytań, ≤ 0,20 USD; ewentualnie darmowe nagranie błędu, U8) |
| G3 | T22 | Zgoda na płatne uruchomienie MVP po obejrzeniu manifestu |
| G4 | T25 | Zgoda na serię uruchomień kalibracji i testu (limit łączny według U5); ręczne przeniesienie progów |
| G5 | T28 | Polecenie push i utworzenia PR; przegląd i merge wykonuje człowiek |
| — | — | Databricks: w MVP brak bramki (P1); nagrania DB-01/DB-02 odłożone |

## 10. Nierozstrzygnięte decyzje

- **U1: źródło typu `PL:*` w MVP.** `nearest_osm.csv` nie ma `maxspeed:type` ani `source:maxspeed` (§1), a A2 §3.5 i D-002-4 opierają regułę `implicit` na tych tagach. PRD §9 i A2 §3.3 zakładają tymczasem MVP „bez czytania GeoParquet”.
  - Propozycja: adapter `files` złącza tagi z `osm_roads.parquet` po `osm_way_id`. Dla 24 dróg z `osm_api` typ pozostaje nieznany i dostaje notatkę.
  - Skutek: 3 drogi bez liczby dostają `implicit` (2 × `PL:expressway` → 120, 1 × `PL:rural` → 90), więc zmienia się podział „18 bez `maxspeed`”.
  - Do rozstrzygnięcia także `PL:zone` bez liczby przy `maxspeed=20` (1 wiersz).
- **U2: tagi kierunkowe.** `heading_diff_deg` mieści się w 0–90° i nie ma `directed_bearing_diff`, którego wymaga reguła A2 §3.5. Propozycja: przy różnych `forward`/`backward` w MVP zwracać `not_comparable` z notatką „kierunek nieznany” (2 wiersze), a pełną regułę dodać w P1.
- **U3: forma poleceń.** A0 §3 wymaga `uv run --project app ...` z katalogu głównego, bo ścieżki w konfiguracji są względne do katalogu roboczego. Wariant `--directory app` zmienia katalog roboczy i psuje ścieżki `course-materials/...`. Polecenie TAC-01 bez ścieżki może zbierać testy z całego repozytorium. Plan używa `pt app/tests`; T01 to weryfikuje, a w razie potrzeby poprawiamy tekst TAC-01.
- **U4: kod 4 (D12) w MVP.** Nie ma go na liście kryteriów MVP, ale TAC-03 i TAC-14 nie mają oznaczenia zakresu, a F2.2 go wymaga. Plan włącza go do T14, bo jest tani. Do potwierdzenia.
- **U5: łączny budżet płatny.** Pokrycie 119 wycinków oraz kalibracja i test (kryt. 12) to co najmniej 5–6 uruchomień po ≤ 1 USD według rezerwacji; realny koszt Jev jest prawdopodobnie znacznie niższy. Potrzebny łączny limit (propozycja ≤ 5 USD) i decyzja, czy jedna zgoda G4 obejmuje całą serię.
- **U6: gdzie zapisać skalibrowane progi.** `mapqa.toml` w katalogu głównym nie jest ignorowany przez Git, a A4 D-004-3 mówi tylko, że progi wpisuje człowiek. Opcje: lokalny, niezatwierdzony plik z wartościami podanymi w PR i `evaluation.json` albo zatwierdzony plik konfiguracyjny.
- **U7: gałąź i PR.** `map-app-implementation` zawiera commity dokumentacji z niescalonego PR #3. Przed T28 trzeba zdecydować: czekać na merge #3 albo zrobić PR zależny.
- **U8: mocki błędów HTTP.** A3 ERR-01 dopuszcza ciało błędu z OpenAPI, a AGENTS.md wymaga nagrania. Propozycja: w ramach G2 jedno darmowe żądanie z celowo błędnym kluczem (401), ponad limit 6 z D-003-6, co wymaga zgody. Timeout i błąd połączenia symulujemy wyjątkiem transportu, bez ciała odpowiedzi.
- **U9: generowanie `schema_expected.json`.** A1 §3.7 mówi, że test „generuje plik ponownie”. Plan rozdziela: skrypt zapisuje plik raz, test tylko porównuje. Do potwierdzenia.
- **U10: status dokumentów** *(rozstrzygnięte 2026-11-13: PRD „Zaakceptowany”, D10 „Accepted”).* Stan z 2026-11-12: PRD miał status „Szkic do akceptacji”, A0 D10 „Proposed”. Implementacja trzyma się interpretacji D10 i progu 0,8 do czasu kalibracji (PRD §11). Właściciel potwierdza albo aktualizuje PRD.

## 11. Pierwsze ograniczone zadanie i bramka przeglądu

- **Pierwsze zadanie po G0 i G1:** T01, czyli szkielet `app/` z przypiętymi wersjami, `uv.lock`, zaślepką `mapqa --help` i testem `test_packaging.py` napisanym przed kodem. Wykonuje orkiestrator; commit `Backend: scaffold mapqa package with uv and pytest`.
- **Bramka przeglądu:** właściciel przegląda szkic, odpowiada na U1–U10 (co najmniej U1–U3) i wprost autoryzuje wykonanie. Do tego czasu nie powstają briefy, agenci, płatne zapytania ani commity kodu.

## 12. Wskazówki do pracy z agentami (poza zakresem wykonania)

- Po T01 warto dodać krótki, zagnieżdżony `app/AGENTS.md` ze zweryfikowanymi poleceniami, markerami `e2e`/`paid` i zakazem pandas w `src/`. Główny `AGENTS.md` zostaje wtedy krótki i uniwersalny. Zmiana wymaga zgody właściciela.
- Szczegóły bibliotek w briefach (respx 0.23.1, Jinja2 3.1.6, Pillow 12.0.0) sprawdzać przez Context7 dla przypiętej wersji, a nie z pamięci modelu.
- T27 uruchamiać w świeżym kontekście (`/code-review`), żeby przegląd był niezależny od autora.
- Po zakończeniu zamienić ten proces planowania w `SKILL.md`, zgodnie z ćwiczeniem w specyfikacji planu.
