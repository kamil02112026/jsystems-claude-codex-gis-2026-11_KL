# Profil danych map-qa

Wygenerowano 2026-11-12 na gałęzi `map-app-implementation`. Wszystkie odczyty są lokalne i tylko do odczytu. Danych wejściowych nie zmieniano, płatnego API nie wywołano.

## Polecenia i wersje

| Krok | Polecenie | Wynik |
|---|---|---|
| Profil prowadzącego | `uv run --python 3.12 course-materials/exercise-data/map-qa/profile_data.py` | kod 0, ~5 s (z cache uv), wynik identyczny z wcześniejszym uruchomieniem |
| Zapytania uzupełniające | jednorazowe zapytania DuckDB (`DESCRIBE`, duplikaty, relacje kluczy, formaty `maxspeed`, braki); skrypt poza repozytorium | kod 0 |
| Databricks | **nie wykonano**: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_SQL_WAREHOUSE_ID` nieobecne w tej sesji (sprawdzono tylko obecność, nie wartości) | — |

Wersje: Python 3.12.16, DuckDB 1.5.6 + spatial (`memory_limit=3GB`, `threads=4`), uv 0.13.7. W poleceniu ćwiczenia pojawiła się nazwa `profiledata.py`; plik nazywa się `profile_data.py`.

### Wejścia (SHA-256, prefiks)

| Plik | Rozmiar | SHA-256 |
|---|---:|---|
| `osm_roads.parquet` | 9,8 MB | `b429a97aef4e9e9f…` |
| `overture_segments.parquet` | 12,8 MB | `cf4ee780992cfab9…` |
| `photos.csv` | 0,4 MB | `9cc6b79f5fc147a7…` |
| `photo_road_links.csv` | 0,1 MB | `d71d0857ae0ffc3e…` |
| `profile.sql` | <0,1 MB | `67ed2acc47086ba1…` |

## Liczności: pliki a Databricks

| Tabela | Pliki | Databricks `workspace.map_qa` (`DATABRICKS.md`) | Zgodność |
|---|---:|---:|---|
| `osm_roads` | 99 768 | 99 768 | ✅ |
| `overture_segments` | 85 405 | 85 405 | ✅ |
| `photos` | 561 | 561 | ✅ |
| `photo_road_links` | 561 | 561 | ✅ |
| `traffic_signs` | 1730 (`traffic_signs.geojson`) | 1730 | ✅ |

Kolumna Databricks to wartości z `DATABRICKS.md`. Użytkownik potwierdził je ręcznie 12.11.2026 zapytaniem `query_databricks.py` we własnym oknie PowerShell. **W tej sesji nie wykonano odczytu Databricks.** Do powtórzenia w sesji uruchomionej ze zmiennymi `DATABRICKS_*`.

Dodatkowe pliki lokalne: `reference_labels.csv` 320 wierszy (100 zdjęć), `signs/signs.csv`, `signs/labels.csv` i `signs/nearest_osm.csv` po 119 wierszy.

## Typy i CRS

| Źródło | Kolumny | Typy istotne dla projektu |
|---|---:|---|
| `osm_roads.parquet` | 26 | `osm_id` BIGINT, `maxspeed`/`surface`/`lanes`/`lit` **VARCHAR**, `tags` VARCHAR (JSON), `node_ids` BIGINT[], `osm_timestamp` VARCHAR, `geometry` `GEOMETRY('EPSG:4326')` |
| `overture_segments.parquet` | 14 | `id` VARCHAR (GERS), `speed_limits` LIST<STRUCT(min_speed, max_speed{value INT, unit}, is_max_speed_variable, when{…}, between DOUBLE[])>, `road_surface` LIST<STRUCT(value, between)>, `sources` LIST<STRUCT(…, record_id, between, …)>, `geometry` `GEOMETRY('OGC:CRS84')` |
| `photos.csv` | 21 | `photo_id` VARCHAR, `longitude`/`latitude`/`heading` DOUBLE, `captured_at` TIMESTAMPTZ, `is_panorama` BOOLEAN, `horizontal_accuracy_m` DOUBLE |
| `photo_road_links.csv` | 11 | `photo_id` VARCHAR, `osm_way_id` BIGINT, `overture_id` VARCHAR, `distance_m`, `bearing_diff`, `directed_bearing_diff` DOUBLE, `candidate_flags` VARCHAR (lista `;`) |
| `reference_labels.csv` | 8 | `photo_id`, `question`, `label`, `status` VARCHAR, `reviewed_at` DATE |
| `traffic_signs.geojson` | 11 | `object_value` VARCHAR, `image_ids` VARCHAR[], `geom` `GEOMETRY('EPSG:4326')` |

**CRS:** OSM deklaruje `EPSG:4326`, a Overture `OGC:CRS84`. README danych potwierdza, że w obu plikach współrzędne mają kolejność długość, szerokość. Transformacja do EPSG:2180 wymaga `always_xy`. Wszystkie 561 zdjęć leży w bbox `19.80,49.95,20.15,50.15`.

`photo_id` ma prefiks źródła: `mapillary_<liczba>` (25–27 znaków) albo `panoramax_<uuid>` (46 znaków).

## Poprawność geometrii i duplikaty

| Kontrola | Wynik |
|---|---:|
| Niepoprawne geometrie OSM / Overture (`ST_IsValid`) | 0 / 0 |
| Duplikaty `osm_id` / Overture `id` | 0 / 0 |
| Duplikaty geometrii (WKB) OSM / Overture | 0 / 0 |
| Duplikaty `photos.photo_id`, `photo_road_links.photo_id` | 0 / 0 |
| Duplikaty `photos.source_sha256` / `photos.sha256` | 0 / 0 |
| Duplikaty `reference_labels` po (`photo_id`, `question`) | 0 |

## Relacje kluczy `photo_id`

| Relacja | Wynik |
|---|---:|
| `photo_road_links.photo_id` ∉ `photos` | 0 |
| zdjęcia bez wiersza w `photo_road_links` | 0 (relacja 1:1, 561 = 561) |
| `reference_labels.photo_id` ∉ `photos` | 0; etykiety ma 100 zdjęć |
| `photo_road_links.osm_way_id` ∉ `osm_roads` | 0 (558 niepustych) |
| `photo_road_links.overture_id` ∉ `overture_segments` | 0 (558 niepustych) |

## `maxspeed`: rozkład i formaty

**Kolumna `maxspeed` zawiera wyłącznie liczby całkowite.** 16 290 wartości (16,3% dróg), bez jednostek, bez mph, bez `none`/`signals`/`walk`, bez wielu wartości (`;`) i bez `PL:*`.

| Wartość | 50 | 30 | 20 | 70 | 40 | 140 | 90 | 60 | 100 | 10 | 120 | 80 | 5 | 25 | 15 | 4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Dróg | 5737 | 4802 | 2053 | 1294 | 1245 | 214 | 184 | 181 | 167 | 157 | 134 | 61 | 48 | 7 | 4 | 2 |

**Oznaczenia `PL:*` są w osobnych tagach** `maxspeed:type` (2578 dróg) i `source:maxspeed` (11 671 dróg). Na 18 drogach te dwa tagi mają różne wartości. Najczęstsze: `PL:urban` 5852, `PL:zone30` 3515, `sign` 2324, `PL:living_street` 969, `PL:zone20` 329, `PL:zone40` 316, `PL:rural` 267, `PL:motorway` 209, `PL:expressway` 145, `PL:zone10` 42.

| Typ (`maxspeed:type` lub `source:maxspeed`) | Z wartością zgodną z domyślną | Z inną wartością | Bez `maxspeed` |
|---|---:|---:|---:|
| `PL:urban` | 4344 (50) | 107 (70, 30, 40, 60, 20) | **1401** |
| `PL:zone30` | 3507 (30) | 8 (20, 50) | 0 |
| `PL:living_street` | 960 (20) | 9 (30) | 0 |
| `PL:rural` | 131 (90) | 90 (100, 70, 50) | **46** |
| `PL:expressway` | 127 (120) | 11 (80, 100) | 7 |
| `PL:zone40` | 310 (40) | 4 (30) | 2 |
| `PL:motorway` | 209 (140) | 0 | 0 |
| `sign` | — | — | 19 |

Tagi kierunkowe: `maxspeed:forward` 261, `maxspeed:backward` 247. Na 223 drogach wartości forward i backward się różnią. 260 dróg ma **tylko** tagi kierunkowe, bez `maxspeed`. Jedyne nieliczbowe wartości prędkości w całym OSM to `PL:urban` w tagach kierunkowych (5 przypadków). `maxspeed:conditional`: 92 drogi, wszystkie `110 @ (Mo-Fr 06:00-18:00)`.

**Overture `speed_limits`:** 12 847 segmentów ma 14 205 reguł. 911 segmentów ma więcej niż jedną regułę (do 13). Reguł z `between` jest 1925, z `when` 880. Każda ma `max_speed`, żadna nie ma `min_speed`. Jedyna jednostka to `km/h`.

## Braki

| Pole | Braki |
|---|---|
| `photos.heading` | 15 (wszystkie Panoramax). Dodatkowo 23 zdjęcia mają `heading = 0`, co według README jest poprawnym kierunkiem północnym, a nie brakiem |
| `photos` pozostałe kluczowe pola | 0 braków `captured_at`, `sequence`, `longitude`, `latitude` |
| `photo_road_links` | 3 bez kandydata OSM, Overture i dystansu (`no_osm_within_25m`); 18 bez `bearing_diff` (15 bez heading + 3 bez drogi) |
| `candidate_flags` | 146 zdjęć z flagami: `ambiguous_candidates` 65, `camera_against_way_direction` 35, `panorama_heading_ambiguous` 31, `poor_heading_alignment` 27, `boundary_crossing` 27, `missing_heading` 15, `service_way` 14, `no_osm_within_25m` 3, `overture_spatial_only` 1 |
| Kompletność OSM | `maxspeed` 16,3%. Drogi `service` (72% OSM): `maxspeed` 2,8%, `surface` 24%, `lit` 4,7%. Drogi główne (`primary`, `secondary`): `maxspeed` 92–97% |
| Drogi połączone ze zdjęciami | **531 z 558 (95%) ma `maxspeed`**, wobec 16,3% w całym OSM |

## 5 faktów, które zmieniają projekt

1. **`PL:*` nie występuje w `maxspeed`, tylko w `maxspeed:type`/`source:maxspeed`.** Nasza reguła implicit (ADR-002 D-002-4, „`PL:urban` → 50 km/h”) musi czytać te tagi, a nie wartość `maxspeed`. Realnie dotyczy 1456 dróg bez liczby (`PL:urban` 1401, `PL:rural` 46, `PL:expressway` 7, `PL:zone40` 2). Normalizacja tekstu `maxspeed` (mph, `none`, `;`) jest w tym snapshocie praktycznie martwym kodem, poza 5 wartościami `PL:urban` w tagach kierunkowych.
2. **Typ i wartość bywają sprzeczne:** 229 dróg ma typ `PL:*` i inną liczbę niż domyślna dla typu (w tym 4 × `PL:zone40` z 30), np. `PL:urban` z 70 km/h (55 dróg). Potrzebna reguła pierwszeństwa (liczba czy typ) i osobny status rozbieżności wewnątrz OSM, zanim porównamy OSM z Overture.
3. **Próbka zdjęć jest silnie obciążona:** 95% połączonych dróg ma `maxspeed`, wobec 16% w całym OSM, a zdjęcia Mapillary dobrano przez znaki (README). Status `osm_missing` będzie w ewaluacji rzadki, a metryki z tej próbki nie przenoszą się na całe miasto. Raport musi to mówić wprost.
4. **Kierunek rozstrzyga często, a dane kierunkowe są słabe:** 223 drogi mają różne limity forward/backward, a 260 ma tylko tagi kierunkowe. Jednocześnie 15 zdjęć nie ma heading, 35 ma kamerę przeciwnie do kierunku geometrii, a 31 to niejednoznaczne panoramy. Dla tych przypadków nasze wnioskowanie kierunku (D-002-3) nie ma danych, więc potrzebny jest jawny status `not_comparable`.
5. **Overture to listy reguł, nie jedna wartość:** 911 segmentów ma kilka reguł, 1925 reguł ma `between`, a 880 ma `when`. Uproszczenie „pierwsza reguła” dałoby błędne porównania. Nasza decyzja „pozycja liniowa rzutu” dla `between` jest potrzebna, a do tego dochodzą reguły warunkowe `when`, których ADR jeszcze w pełni nie obsługuje.

## 3 pytania do człowieka (odpowiedzi 2026-11-12, wpisane do ADR-002 D-002-4 i PRD §7)

Odpowiedzi: 1. liczba wygrywa, sprzeczność tylko oznaczamy; 2. tak (`PL:rural` → 90, `PL:expressway` → 120, `sign` bez liczby → `unknown`); 3. MVP na obecnej próbce z adnotacją.

1. **Pierwszeństwo przy sprzeczności typu i wartości** (229 dróg, np. `PL:urban` + 70): czy liczba w `maxspeed` jest rozstrzygająca, a sprzeczność tylko oznaczamy, czy taka droga od razu staje się kandydatem do weryfikacji?
2. **Które domyślne wartości `PL:*` przyjmujemy dla dróg bez liczby?** `PL:urban` → 50 jest uzgodnione. Czy przyjmujemy też `PL:rural` → 90 i `PL:expressway` → 120 (oba jako implicit), a `sign` bez liczby (19) traktujemy jako `unknown`?
3. **Czy MVP oceniamy na obciążonej próbce?** Wybór jest taki: zaakceptować obecne 561 zdjęć z jawną adnotacją albo dobrać próbkę z dróg bez `maxspeed` i dróg serwisowych, żeby zmierzyć `osm_missing`. Dobór kosztuje pobranie zdjęć, ale nie płatne API.

## Odświeżanie

Profil prowadzącego: `uv run --python 3.12 course-materials/exercise-data/map-qa/profile_data.py` (zasada w `AGENTS.md`). Zapytania uzupełniające z tego profilu warto dopisać do repozytorium jako osobny plik SQL, jeśli mają być powtarzane.
