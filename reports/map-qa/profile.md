# Profil danych map-qa

Wygenerowano 2026-11-12 13:50 z commitu `3e5c22a` (gałąź `map-app-implementation`). Odświeżanie:

```powershell
uv run course-materials/exercise-data/map-qa/profile_data.py
```

Skrypt prowadzącego uruchamia zapytania z `profile.sql` w DuckDB 1.5.6 + spatial (`memory_limit=3GB`, `threads=4`), tylko na lokalnych plikach i tylko do odczytu. Czas: ~56 s. uv 0.13.7, Python 3.12.

## Wejścia

| Plik | Rozmiar | SHA-256 (prefiks) |
|---|---:|---|
| `osm_roads.parquet` | 9,8 MB | `b429a97aef4e9e9f…` |
| `overture_segments.parquet` | 12,8 MB | `cf4ee780992cfab9…` |
| `photos.csv` | 0,4 MB | `9cc6b79f5fc147a7…` |
| `photo_road_links.csv` | 0,1 MB | `d71d0857ae0ffc3e…` |
| `profile.sql` | <0,1 MB | `67ed2acc47086ba1…` |

## Liczności: pliki a Databricks

| Tabela | Pliki | Databricks `workspace.map_qa` |
|---|---:|---:|
| `osm_roads` | 99 768 | 99 768 |
| `overture_segments` | 85 405 | 85 405 |
| `photos` | 561 | 561 |
| `photo_road_links` | 561 | 561 |
| `traffic_signs` | brak w `profile.sql` | 1730 |

Kolumna Databricks to liczności sprawdzone ręcznie przez użytkownika 12.11.2026 (`query_databricks.py`) i zgodne z `DATABRICKS.md`. Wynik zapytania nie jest tu wklejony, bo sesja agenta nie miała dostępu do tokenu. Do uzupełnienia: wynik z sesji uruchomionej ze zmiennymi Databricks.

## Geometria i identyfikatory

| Źródło | Wiersze | Unikalne ID | Niepoprawne geometrie | Typ geometrii |
|---|---:|---:|---:|---|
| OSM | 99 768 | 99 768 | 0 | `GEOMETRY('EPSG:4326')` |
| Overture | 85 405 | 85 405 | 0 | `GEOMETRY('OGC:CRS84')` |

**Uwaga o CRS:** OSM deklaruje `EPSG:4326`, a Overture `OGC:CRS84`. To ten sam układ, ale `EPSG:4326` ma formalnie kolejność osi szerokość/długość, a CRS84 długość/szerokość. Transformacja do EPSG:2180 musi więc używać `always_xy` (ADR-002), inaczej punkty jednego źródła zamienią osie.

## Kompletność atrybutów OSM

| `highway` | Wiersze | `maxspeed` | `surface` | `lanes` | `lit` |
|---|---:|---:|---:|---:|---:|
| service | 72 113 | 1997 (2,8%) | 17 390 (24%) | 849 | 3379 (4,7%) |
| residential | 11 799 | 5467 (46%) | 9598 (81%) | 2334 | 5103 (43%) |
| track | 4296 | 2 | 1657 | 0 | 86 |
| tertiary | 3838 | 2839 (74%) | 3772 (98%) | 2888 | 2451 (64%) |
| secondary | 2073 | 1897 (92%) | 2065 | 2015 | 1633 (79%) |
| living_street | 1938 | 1140 (59%) | 1524 | 109 | 638 |
| primary | 1586 | 1539 (97%) | 1584 | 1562 | 1260 (79%) |
| unclassified | 880 | 316 | 770 | 342 | 331 |
| motorway | 459 | 453 | 453 | 454 | 213 |
| pozostałe (8 klas: `*_link`, trunk, road, busway) | 786 | 640 | 753 | 720 | 495 |
| **razem** | **99 768** | **16 290 (16,3%)** | | | |

Tagi kierunkowe i warunkowe: `maxspeed:forward` 261, `maxspeed:backward` 247, `maxspeed:conditional` 92. `boundary_crossing` = true: 560 dróg.

## Kompletność Overture

| `class` | Wiersze | Z regułami `speed_limits` | Z regułami `road_surface` |
|---|---:|---:|---:|
| service | 60 968 | 1624 | 14 027 |
| residential | 11 185 | 5129 | 8781 |
| track | 3663 | 2 | 1321 |
| tertiary | 3102 | 2180 | 3032 |
| living_street | 2278 | 1378 | 1768 |
| secondary | 1335 | 1192 | 1303 |
| primary | 916 | 840 | 896 |
| unknown | 844 | 2 | 8 |
| unclassified | 816 | 262 | 704 |
| motorway | 211 | 172 | 187 |
| trunk | 87 | 66 | 81 |

## Zdjęcia i dostarczone połączenia

| Źródło | Zdjęcia | Sekwencje | Z `heading` | Z autorem | Z licencją |
|---|---:|---:|---:|---:|---:|
| Mapillary | 100 | 52 | 100 | 100 | 100 |
| Panoramax | 461 | 56 | 446 | 461 | 461 |

`photo_road_links.csv`: 561 zdjęć, kandydat OSM dla 558, kandydat Overture dla 558. Metody: `osm_source_reference` 557, `spatial_fallback` 1, `none` 3. Dystans zdjęcie–droga: min 0,0 m, mediana 2,43 m, p95 9,82 m, max 22,17 m.

## Wnioski dla PRD i ADR

1. **Drogi `service` to 72% OSM i 71% Overture, a `maxspeed` ma tylko 2,8% z nich.** Flaga `service_or_restricted` (ADR-002) i filtr klas w raporcie są potrzebne, inaczej kandydaci utoną w drogach serwisowych bez danych.
2. **Ogólna kompletność `maxspeed` to 16,3%.** Wiele dróg trafi do `osm_missing`, więc implicit `PL:*` (ADR-002 D-002-4) ma realne znaczenie.
3. **15 zdjęć Panoramax nie ma `heading`.** Dla nich wnioskowanie kierunku (D-002-3) jest niemożliwe, a `maxspeed:forward/backward` (261/247 dróg) daje wtedy `not_comparable`. Do potwierdzenia w ADR-002.
4. **Dostarczone połączenia są prawie kompletne:** 557/561 to referencja OSM, a nie dopasowanie przestrzenne. Tylko 3 zdjęcia nie mają kandydata. Własny matcher z P1 ma mało przypadków do poprawy; jego wartość jest głównie w walidacji (`distance_mismatch`).
5. **Overture ma 844 segmenty klasy `unknown`.** Mapowanie klas w porównaniu musi to obsłużyć.
6. **Geometrie są poprawne, a ID unikalne w obu źródłach.** Kontrakt schematu (ADR-001) może to sprawdzać jako niezmiennik.

## Poza zakresem tego profilu (do uzupełnienia w M2)

- przeliczenie dystansów po transformacji obu warstw do EPSG:2180 i porównanie z `distance_m`;
- alternatywne drogi w pobliżu zdjęcia, kontrola `heading` i GPS;
- pełne reguły Overture `when`/`between` i `sources`;
- `sidewalk*` i pełne `tags`;
- zestaw `signs/` (wycinki i etykiety) oraz `traffic_signs` z Databricks;
- przykłady połączeń do ręcznego obejrzenia.
