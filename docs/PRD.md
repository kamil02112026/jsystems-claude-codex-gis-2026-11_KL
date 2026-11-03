# PRD: Map Attribute QA Copilot (PoC)

| | |
|---|---|
| Status | Szkic do akceptacji |
| Data | 2026-11-03 |
| Zakres | Proof of concept, wersja v1 |
| Powiązane | `docs/ADR/` (architektura i technologie — osobny dokument) |

## 1. Problem i cel

Analityk jakości danych mapowych ręcznie szuka miejsc, w których atrybuty dróg na mapie mogą nie zgadzać się z terenem. Większość porównań kończy się stwierdzeniem „wszystko się zgadza” albo „nie da się ocenić”, więc czas eksperta idzie na przypadki bez wartości.

**Cel PoC:** narzędzie, które na podstawie danych OSM, Overture i zdjęć ulic wskazuje **kandydatów** do ręcznej weryfikacji, uzasadnia każdy z nich i jawnie mówi, czego nie wie. Narzędzie **nie** rozstrzyga, że mapa jest błędna; decyzję podejmuje człowiek.

### Mierniki sukcesu PoC

- Raport z jednego uruchomienia da się przejrzeć w ≤ 30 min i każdy kandydat ma czytelny powód skierowania.
- Odczyt modelu spełnia progi jakości z sekcji 7 na etykietach `certain`.
- Uruchomienie mieści się w budżecie: ≤ 1 USD i ≤ 200 zapytań do modelu.

## 2. Użytkownik

**Analityk jakości danych mapowych** — zna OSM, tagowanie i GIS, nie musi znać szczegółów modeli językowych. Pracuje lokalnie w terminalu (Windows, PowerShell) i przegląda raport w przeglądarce lub edytorze Markdown.

## 3. Zakres

### W zakresie v1

| Atrybut | Mapa (OSM) | Mapa (Overture) | Pytanie do modelu | Etykiety referencyjne |
|---|---|---|---|---|
| Ograniczenie prędkości | `maxspeed`, `maxspeed:*` (surowe) | `speed_limits` (z `when`, `between`) | „Jaka wartość jest na znaku ograniczenia prędkości?” | `speed_limit_value` (`reference_labels.csv`), `signs/labels.csv` |
| Nawierzchnia | `surface` | `road_surface` | „Czy nawierzchnia drogi w kadrze jest utwardzona?” | `surface` |
| Oświetlenie | `lit` | — | „Czy w kadrze widać oprawę lampy ulicznej?” | `street_lighting_visible` |

- Interfejs: **CLI** + raport **Markdown i HTML**.
- Źródła danych: pliki lokalne (`course-materials/exercise-data/map-qa/`) albo Databricks (`workspace.map_qa`).
- Modele (OpenRouter), w **kaskadzie eskalacji** (F5):
  - poziom 1 — model decyzyjny `openai/gpt-6-luna-decisions`;
  - poziom 2 — zwykły model LLM ze średnim poziomem rozumowania, domyślnie `openai/gpt-6-luna` (`LLM_MODEL` z `.env.example`), `reasoning effort = medium`;
  - poziom 3 — człowiek: **kolejka ręcznej weryfikacji**;
  - model porównawczy `typesafe/jev-1.14` (tylko ewaluacja, poza kaskadą).

### Poza zakresem v1 (później)

- Dashboard z mapą i przyciskami „potwierdź / odrzuć / do sprawdzenia” (Streamlit albo PySide6).
- Zapis decyzji analityka i eksport poprawek jako zadań (np. Jira).
- Kolejne atrybuty: liczba pasów, chodnik, skrzyżowania i topologia, klasa drogi.
- Automatyczna edycja OSM lub jakiejkolwiek mapy.
- Pobieranie świeżych danych z API Mapillary/Panoramax/Overture w ramach uruchomienia (narzędzie korzysta z przypiętego snapshotu).
- Własny serwer MCP narzędzia oraz odczyt Databricks przez Managed MCP (agent może używać Databricks MCP sam, ale narzędzie v1 korzysta z REST/CLI). Interfejs CLI z `--output json` (F8.9) przygotowuje grunt pod MCP.
- Kolejne adaptery źródeł (PostGIS, S3/GeoParquet) — kontrakt F8.4 je umożliwia, ale v1 ich nie implementuje.

## 4. Przebieg pracy użytkownika

1. Analityk uruchamia CLI z parametrami: `bbox` (WGS84), lista atrybutów (`speed_limit`, `surface`, `lit`), źródło (`files` | `databricks`), model, limity budżetu.
2. System wczytuje dane i wypisuje **profil wejścia**.
3. System łączy zdjęcia z drogami i oznacza niepewne połączenia.
4. System porównuje atrybuty OSM i Overture i wyznacza kandydatów rozbieżności.
5. System zadaje neutralne pytania o zdjęcia modelowi decyzyjnemu. Gdy ten nie jest pewny, pytanie trafia do zwykłego LLM. Gdy i ten nie zna odpowiedzi, przypadek trafia do kolejki ręcznej (z cache i limitami).
6. System zestawia odczyt ze zdjęcia z mapą, buduje kolejkę ręcznej weryfikacji i generuje raport MD + HTML.
7. Analityk przegląda kolejkę i raport i sam decyduje o poprawkach.

## 5. Wymagania funkcjonalne

### F1. Parametry uruchomienia

- F1.1 `bbox` w WGS84 (`minx,miny,maxx,maxy`); domyślnie bbox danych `19.80,49.95,20.15,50.15`. Niepoprawny bbox (odwrócone granice, poza zakresem współrzędnych) kończy uruchomienie czytelnym błędem przed wczytaniem danych.
- F1.2 Lista atrybutów z podzbioru `speed_limit`, `surface`, `lit`; domyślnie wszystkie trzy.
- F1.3 Źródło danych wybierane konfiguracją (F8): `files` (domyślne), `databricks` lub inne zdefiniowane w pliku konfiguracyjnym. Brak dostępu do wybranego źródła daje czytelny komunikat z sugestią alternatywy; narzędzie nie przełącza źródła po cichu.
- F1.4 Tryb `--no-model` uruchamia kroki 2–4 i raport bez wywołań modelu (do pracy offline i testów).
- F1.5 Sekrety (`OPENROUTER_API_KEY`, token Databricks) wyłącznie ze zmiennych środowiskowych; nigdy w logu, raporcie ani cache.

### F2. Wczytanie i profil danych

- F2.1 Wczytuje drogi OSM, segmenty Overture, manifest zdjęć (`photos.csv`, opcjonalnie `signs/signs.csv`) i dostępne pliki zdjęć.
- F2.2 Pliki wejściowe są tylko do odczytu; wyniki trafiają do `reports/map-qa/<run_id>/`, cache do `course-materials/exercise-data/map-qa/data/` (ignorowane przez Git).
- F2.3 Profil zawiera: liczbę rekordów na źródło, liczbę rekordów w bbox, kompletność tagów (`maxspeed`, `surface`, `lit`) w procentach z mianownikiem oraz **odrzucone rekordy z przyczyną** (np. brak pliku zdjęcia, niezgodny hash, brak geometrii, poza bbox).
- F2.4 `heading = 0.0` to poprawny kierunek północny; brak kierunku to wartość pusta/NULL i nigdy nie jest zamieniany na 0.
- F2.5 Liczności z plików i Databricks dla tego samego snapshotu są zgodne; rozbieżność jest raportowana jako ostrzeżenie.

### F3. Połączenie zdjęcia z drogą

- F3.1 Odległości liczone w metrach w **EPSG:2180**; obie warstwy przeliczane z EPSG:4326/OGC:CRS84.
- F3.2 Kandydaci w promieniu 25 m; ranking uwzględnia dystans i zgodność kierunku kamery z lokalnym kierunkiem drogi (oba kierunki geometrii).
- F3.3 Niepewne połączenia są **oznaczone, nie ukryte**. Flagi co najmniej: `ambiguous_candidates` (druga droga w zbliżonym wyniku), `junction_nearby`, `service_way`, `missing_heading`, `panorama_heading_ambiguous`, `poor_heading_alignment`, `no_osm_within_25m`.
- F3.4 Brak dopasowania jest stanem danych, nie dowodem błędu mapy, i nie tworzy kandydata rozbieżności.
- F3.5 Wynik własnego dopasowania jest porównany z `photo_road_links.csv`; odsetek zgodnych `osm_way_id` trafia do profilu (punkt odniesienia, nie wzorzec).

### F4. Porównanie OSM ↔ Overture

- F4.1 Dla każdej drogi powiązanej ze zdjęciem i każdego wybranego atrybutu system zestawia wartość OSM i Overture.
- F4.2 Wartości są normalizowane do porównania (np. `50`, `50 mph` → km/h; `asphalt`, `concrete`, `paving_stones` → `paved`), ale **surowe** wartości (`maxspeed:*`, `when`, `between`) są zachowane i pokazane w raporcie.
- F4.3 Wynik porównania: `agree`, `disagree`, `osm_missing`, `overture_missing`, `both_missing`, `not_comparable` (np. reguła warunkowa lub wartość tylko dla części segmentu).
- F4.4 Rozbieżność źródeł **nie jest** oznaczana jako błąd mapy. Raport pokazuje daty/wersje źródeł Overture, w tym czy wartość pochodzi z OSM.

### F5. Odczyt ze zdjęcia: kaskada eskalacji

```
poziom 1: model decyzyjny ──pewny──► odczyt
     │ niepewny / błąd / niepoprawna odpowiedź
     ▼
poziom 2: zwykły LLM (reasoning medium) ──pewny──► odczyt
     │ niepewny / błąd / niepoprawna odpowiedź
     ▼
poziom 3: człowiek ──► kolejka ręcznej weryfikacji (F6)
```

- F5.1 Model na każdym poziomie dostaje **wyłącznie** bajty obrazu (pełny kadr lub wycinek znaku) i neutralne pytanie zamknięte. Nie dostaje tagów mapy, etykiet referencyjnych, detekcji Mapillary, identyfikatorów, nazw plików ani **odpowiedzi modelu z poprzedniego poziomu**. Poziom 2 odpowiada niezależnie.
- F5.2 Pytania zamknięte i dozwolone odpowiedzi:
  - prędkość: `20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 140, brak znaku`, `nieczytelny`;
  - nawierzchnia: `utwardzona`, `nieutwardzona`, `nie widać`;
  - oświetlenie: `tak`, `nie`, `nie widać`.
- F5.3 Model zwraca odpowiedź i prawdopodobieństwo (0–1). Odpowiedź spoza listy lub niepoprawny format daje `invalid_response`.
- F5.4 **Poziom 1 → 2:** pytanie przechodzi do zwykłego LLM, gdy model decyzyjny zwróci prawdopodobieństwo poniżej progu (domyślnie **0,8**), `invalid_response` albo `model_unavailable` (błąd API, timeout). Odpowiedzi `nie widać` i `nieczytelny` z prawdopodobieństwem ≥ progu są **pewnymi odczytami**, nie powodem eskalacji.
- F5.5 **Poziom 2 → 3:** gdy zwykły LLM również zwróci wynik poniżej swojego progu (domyślnie **0,8**), `invalid_response` lub `model_unavailable`, końcowy status to `abstain` (albo `model_unavailable`, jeśli oba poziomy były niedostępne). Przypadek trafia do **kolejki ręcznej weryfikacji** (F6.5).
- F5.6 Progi są konfigurowalne osobno dla każdego poziomu i atrybutu. Model i `reasoning effort` poziomu 2 są konfigurowalne.
- F5.7 Każdy wynik zapisuje **ścieżkę kaskady**: odpowiedź i prawdopodobieństwo z każdego wywołanego poziomu, poziom rozstrzygający (`1`, `2` albo `human`) i powód eskalacji. Jedno nieudane zdjęcie nie przerywa uruchomienia.
- F5.8 **Cache** po `sha256(obraz) + id pytania + model + reasoning effort + wersja promptu`, osobno dla każdego poziomu. Trafienie w cache nie liczy się do limitu zapytań ani kosztu.
- F5.9 **Limity na uruchomienie:** domyślnie 200 zapytań i 1,00 USD **łącznie dla obu poziomów**. Po osiągnięciu limitu kolejne pytania dostają `budget_exceeded` i trafiają do kolejki ręcznej; raport nadal powstaje.
- F5.10 **Log kosztów** (JSONL): czas, poziom, model, reasoning effort, id pytania, hash obrazu, tokeny, koszt, cache hit/miss, status. Bez sekretów i bez treści obrazu.
- F5.11 Tryb porównawczy uruchamia model `typesafe/jev-1.14` na zestawie ewaluacyjnym poza kaskadą, w ramach wspólnego budżetu.

### F6. Zestawienie, kandydaci i kolejka ręcznej weryfikacji

- F6.1 Kandydat powstaje, gdy:
  - pewny odczyt z kaskady (poziom 1 lub 2) różni się od wartości OSM, **lub**
  - OSM i Overture się różnią, a zdjęcie wspiera jedną ze stron, **lub**
  - OSM nie ma wartości, a model podał pewny odczyt.
- F6.2 Każdy kandydat ma **powód skierowania** w języku polskim, np. „Znak 40 na zdjęciu, OSM `maxspeed=50`, Overture 50”.
- F6.3 Kandydat ma priorytet: `wysoki` (pewny odczyt, czyste połączenie, brak flag), `średni` (pewny odczyt, ale połączenie z flagami albo odczyt rozstrzygnięty dopiero na poziomie 2), `niski` (tylko rozbieżność źródeł).
- F6.4 Zgodność zdjęcia z mapą **nie** potwierdza poprawności mapy. Znak może dotyczyć innej jezdni, a zdjęcie może być starsze niż dane.
- F6.5 **Kolejka ręcznej weryfikacji** (`manual_queue.csv` + sekcja raportu) zawiera dwa typy pozycji:
  - `nierozstrzygnięty_odczyt` — oba modele nie podały pewnej odpowiedzi (`abstain`, `model_unavailable`, `budget_exceeded`), a zdjęcie jest połączone z drogą, dla której wynik ma znaczenie;
  - `kandydat_rozbieżności` — kandydaci z F6.1.
- F6.6 Pozycja kolejki zawiera: id pozycji, typ, atrybut, zdjęcie (ścieżka, atrybucja), droga OSM/Overture, wartości mapy, ścieżkę kaskady (odpowiedzi i prawdopodobieństwa obu poziomów), flagi połączenia, priorytet, powód po polsku oraz puste pola na decyzję człowieka (`decyzja`, `wartość_z_terenu`, `komentarz`).
- F6.7 Kolejka jest posortowana po priorytecie i stabilna między uruchomieniami (id pozycji = hash zdjęcia + atrybut + droga), aby decyzje wpisane ręcznie dało się później dopasować. Zapis decyzji w narzędziu jest poza zakresem v1.

### F7. Raport

- F7.1 Pliki: `report.md`, `report.html` (samodzielny HTML, miniatury osadzone lub z odnośnikiem względnym) i `manual_queue.csv`.
- F7.2 Sekcje: parametry uruchomienia, profil danych, **lejek kaskady** (pytania ogółem → rozstrzygnięte na poziomie 1 → eskalowane i rozstrzygnięte na poziomie 2 → przekazane człowiekowi, z liczbami i odsetkami), podsumowanie (kandydaci wg atrybutu i priorytetu, `abstain`, `model_unavailable`, `budget_exceeded`), kolejka ręcznej weryfikacji, metryki ewaluacji (jeśli dostępne etykiety), koszt osobno dla każdego poziomu.
- F7.3 Wiersz kandydata: identyfikator drogi (OSM way + Overture id), **miniatura zdjęcia z atrybucją** (autor, licencja, link do źródła, CC BY-SA 4.0), data zdjęcia, wartości OSM/Overture (surowe i znormalizowane), odczyt z prawdopodobieństwem i poziomem, który go rozstrzygnął (przy eskalacji także odpowiedź poziomu 1), flagi połączenia, powód skierowania.
- F7.4 Teksty raportu po polsku; identyfikatory i nazwy pól w oryginale.
- F7.5 Raport zawiera informację o licencjach ODbL (OSM, Overture) i CC BY-SA (zdjęcia) zgodnie z `ATTRIBUTION.md`.
- F7.6 Raport zapisuje użyte źródło danych (nazwa, typ, metoda dostępu, tabele/ścieżki, czas odczytu), bez sekretów.

### F8. Konfigurowalne źródła danych

Cel: analityk **albo agent AI korzystający z narzędzia** może wskazać, skąd pobrać dane, bez zmiany kodu. Testy zaczynamy na plikach lokalnych, ale Databricks jest pełnoprawnym źródłem v1.

- F8.1 **Wybór źródła**, w kolejności pierwszeństwa:
  1. flaga CLI `--source <nazwa>`;
  2. zmienna środowiskowa `MAPQA_SOURCE`;
  3. pole `default_source` w pliku konfiguracyjnym (`--config <ścieżka>`, `MAPQA_CONFIG` albo `mapqa.toml` w katalogu roboczym);
  4. domyślnie `files`.
- F8.2 **Plik konfiguracyjny** definiuje nazwane źródła. Przykład:

  ```toml
  default_source = "local"

  [sources.local]
  type = "files"
  path = "course-materials/exercise-data/map-qa"

  [sources.course-databricks]
  type = "databricks"
  access = "rest"                     # rest | cli
  host_env = "DATABRICKS_HOST"        # nazwa zmiennej, nie wartość
  token_env = "DATABRICKS_TOKEN"
  warehouse_id_env = "DATABRICKS_SQL_WAREHOUSE_ID"
  schema = "workspace.map_qa"
  photos_dir = "course-materials/exercise-data/map-qa/data/photos"
  ```

- F8.3 **Typy źródeł v1:**
  - `files` — GeoParquet/CSV/GeoJSON z katalogu `path` (nazwy plików jak w `course-materials/exercise-data/map-qa/`);
  - `databricks` z metodą dostępu `rest` (SQL Statement Execution API) albo `cli` (`databricks api post /api/2.0/sql/statements`). Tabele: `osm_roads`, `overture_segments`, `photos`, `photo_road_links`, `traffic_signs` w podanym `schema`.
- F8.4 **Kontrakt danych:** każde źródło zwraca te same zbiory o tym samym schemacie (kolumny, typy, CRS EPSG:4326, `heading` NULL ≠ 0). Pipeline nie zależy od typu źródła. Nowe źródło (np. PostGIS, S3/GeoParquet, inny katalog Databricks) to nowy adapter + wpis w konfiguracji, bez zmian w krokach F3–F7.
- F8.5 **Filtr bbox po stronie źródła:** Databricks dostaje bbox w zapytaniu SQL i nie pobiera całych tabel. Dla dróg zachowane są całe ways przecinające bbox.
- F8.6 **Zdjęcia:** Databricks przechowuje metadane zdjęć, nie pliki. Obrazy pochodzą z `photos_dir` (lokalnie lub z cache `download_photos.py`); brak pliku to odrzucony rekord w profilu (F2.3).
- F8.7 **Obsługa zapytań Databricks:** stany `PENDING`/`RUNNING` są odpytywane do limitu czasu (konfigurowalny, domyślnie 180 s). `FAILED` i `CANCELED` to błąd z komunikatem, nigdy pusty wynik. Wyniki dzielone na części (chunks) są czytane w całości. Zapytanie, które może nadal działać, nie jest automatycznie ponawiane.
- F8.8 **Sekrety:** plik konfiguracyjny zawiera tylko **nazwy** zmiennych środowiskowych. Wartości tokenów nie pojawiają się w konfiguracji, logach, raporcie, cache ani w komunikatach błędów.
- F8.9 **Interfejs dla agenta:**
  - `mapqa sources list` — nazwy, typy i metody dostępu skonfigurowanych źródeł;
  - `mapqa sources check [--source X]` — test połączenia i liczności tabel w bbox;
  - `--output json` dla wszystkich poleceń — wynik maszynowy dla agenta;
  - stałe kody wyjścia: `0` sukces, `1` błąd danych lub walidacji, `2` źródło niedostępne lub brak uprawnień, `3` przekroczony budżet modelu.
- F8.10 Wynik `--no-model` z tych samych danych jest identyczny dla źródeł `files` i `databricks` (te same kandydaci rozbieżności i liczności), z wyjątkiem pól metadanych źródła.

## 6. Wymagania niefunkcjonalne

- Uruchomienie w trybie `--no-model` na pełnym bbox kończy się w ≤ 2 min na maszynie kursowej (8 vCPU, 16 GB RAM).
- Ponowne uruchomienie z tymi samymi parametrami korzysta z cache i daje ten sam raport przy zerowym koszcie modelu.
- Narzędzie działa natywnie na Windows (PowerShell, uv, Python 3.12) bez WSL, Dockera ani conda.
- Wszystkie progi, limity i modele są konfigurowalne (CLI lub plik konfiguracyjny), z domyślnymi wartościami z tego PRD.

## 7. Ewaluacja odczytu modelu

Etykiety referencyjne są **roboczą referencją, nie prawdą terenową** (przygotowane przez agenta AI i drugi model).

### Zasady

- Do metryk używamy **tylko** etykiet `status = certain`. Etykiety `uncertain` są wykluczone, a ich liczba jest raportowana.
- Każda metryka ma **jawny mianownik**: liczba etykiet `certain`, liczba odpowiedzi modelu bez abstencji, liczba abstencji, `model_unavailable`.
- Definicje (liczone dla **końcowego wyniku kaskady**, a pomocniczo osobno dla każdego poziomu):
  - **trafność** = poprawne / pewne odpowiedzi (rozstrzygnięte na poziomie 1 lub 2);
  - **odsetek przekazania człowiekowi** (abstencja kaskady) = pozycje `nierozstrzygnięty_odczyt` / wszystkie pytania z etykietą `certain`;
  - **odsetek eskalacji do poziomu 2** = pytania przekazane z poziomu 1 / wszystkie pytania z etykietą `certain`;
  - **trafność poziomu 1** i **trafność poziomu 2 na eskalowanych pytaniach** — osobno, aby pokazać, czy poziom 2 faktycznie pomaga, czy tylko zgaduje;
  - **pokrycie** = poprawne odpowiedzi / wszystkie etykiety `certain`.
- Dla porównania raport podaje też wynik poziomu 1 bez kaskady (jego niepewne odpowiedzi liczone jako abstencja).
- Etykieta `none` przy prędkości odpowiada odpowiedzi `brak znaku`; `unreadable` odpowiada `nieczytelny`.
- Podział na zbiór kalibracyjny i testowy **po `sequence`**, nie po sąsiednich klatkach. Próg pewności ustalamy na zbiorze kalibracyjnym **przed** końcową próbą.

### Dostępne etykiety (stan 2026-11-03)

| Pytanie | Plik | `certain` | Rozkład `certain` | `uncertain` |
|---|---|---|---|---|
| Prędkość (wycinki znaków) | `signs/labels.csv` | 115 | 89 wartości liczbowych, 25 `none`, 1 `unreadable` | 4 |
| Prędkość (pełne kadry) | `reference_labels.csv` | 14 | 6 wartości, 8 `none` | 6 |
| Nawierzchnia | `reference_labels.csv` | 99 | **99 `paved`, 0 `unpaved`** | 1 |
| Oświetlenie | `reference_labels.csv` | 79 | 54 `yes`, 25 `no` | 21 |

### Progi akceptacji

Progi dotyczą końcowego wyniku kaskady.

| Pytanie | Trafność | Przekazanie człowiekowi |
|---|---|---|
| Prędkość (wycinki `signs/`) | ≥ 90% | ≤ 30% |
| Oświetlenie | ≥ 90% | ≤ 30% |
| Nawierzchnia | **raportowana, bez progu akceptacji** | ≤ 30% |

Dodatkowo trafność poziomu 2 na eskalowanych pytaniach musi wynosić ≥ 90%. Niższa oznacza, że poziom 2 obniża jakość, i wtedy jego próg pewności trzeba podnieść (na zbiorze kalibracyjnym), aby więcej przypadków trafiało do człowieka.

**Nawierzchnia:** zbiór zawiera tylko klasę `paved`, więc trafność nie mierzy rozpoznania nawierzchni nieutwardzonej. Raport pokazuje wynik z dopiskiem o braku klasy negatywnej. Próg zostanie ustalony po dodaniu etykiet `unpaved`.

Z kilkunastu pełnych kadrów z prędkością nie wyciągamy wniosków o kalibracji ani o przewadze jednego modelu; raportujemy je opisowo.

### Koszt

- Jedno pełne uruchomienie ewaluacji (wszystkie etykiety `certain`, kaskada poziom 1 + 2, zimny cache): **≤ 1,00 USD i ≤ 200 zapytań łącznie**. Gdy pytań jest więcej niż limit, ewaluacja używa deterministycznej próbki (stały seed) i raportuje jej wielkość.
- Raport podaje koszt całkowity, koszt każdego poziomu, koszt na zapytanie i koszt na kandydata.

## 8. Kryteria akceptacji

1. **Profil:** `--no-model` na danych z plików wypisuje liczności zgodne z README danych (99 768 dróg OSM, 85 405 segmentów Overture, 561 zdjęć) oraz kompletność `maxspeed`, `surface`, `lit` z mianownikami.
2. **Odrzucenia:** brakujący plik zdjęcia lub niezgodny hash pojawia się w profilu jako odrzucony rekord z przyczyną i nie przerywa uruchomienia.
3. **CRS:** test jednostkowy potwierdza, że dystans liczony jest w EPSG:2180 (znany odcinek ma długość w metrach z tolerancją ≤ 0,5 m).
4. **Heading:** zdjęcie z `heading = 0.0` jest traktowane jako północ; zdjęcie bez kierunku dostaje flagę `missing_heading` i nie dostaje kierunku 0.
5. **Niepewne połączenia:** każde zdjęcie z flagą jest widoczne w wyniku z tą flagą; żadne nie znika.
6. **Izolacja modelu:** test sprawdza, że żądanie do modelu zawiera tylko obraz i tekst pytania z listy (brak tagów, etykiet, identyfikatorów, nazw plików).
7. **Kaskada:** test z zamockowanym API:
   - poziom 1 pewny → poziom 2 nie jest wywoływany;
   - poziom 1 poniżej progu, `invalid_response` lub błąd HTTP/timeout → wywołany poziom 2, a wynik ma poziom rozstrzygający `2`;
   - oba poziomy poniżej progu → `abstain`, pozycja `nierozstrzygnięty_odczyt` w `manual_queue.csv`;
   - oba poziomy niedostępne → `model_unavailable` i pozycja w kolejce;
   - żądanie do poziomu 2 nie zawiera odpowiedzi poziomu 1.
   Uruchomienie kończy się raportem.
8. **Cache:** drugie uruchomienie z tymi samymi parametrami ma 0 nowych zapytań i koszt 0 USD w logu.
9. **Budżet:** przy limicie 5 zapytań wykonanych jest ≤ 5 zapytań łącznie na obu poziomach, pozostałe pytania mają `budget_exceeded` i trafiają do kolejki ręcznej, a raport powstaje.
10. **Raport:** `report.md` i `report.html` zawierają lejek kaskady oraz co najmniej jednego kandydata dla każdego wybranego atrybutu (jeśli dane go dają), z miniaturą, atrybucją, wartością mapy, odczytem z prawdopodobieństwem, poziomem rozstrzygającym i powodem.
11. **Ewaluacja:** raport pokazuje trafność, odsetek eskalacji, odsetek przekazania człowiekowi i pokrycie per pytanie (kaskada i każdy poziom osobno) z mianownikami i liczbą wykluczonych `uncertain`; nawierzchnia ma adnotację o braku klasy `unpaved`.
12. **Progi:** końcowy wynik kaskady (i poziom 2 na eskalowanych pytaniach) spełnia progi z sekcji 7 na zbiorze testowym (podział po `sequence`). Niespełnienie jest wynikiem PoC do udokumentowania, nie powodem do zmiany etykiet lub progów po fakcie.
13. **Sekrety:** w repozytorium, logach, cache i raporcie nie ma wartości `OPENROUTER_API_KEY` ani tokenów.
14. **Kolejka ręczna:** `manual_queue.csv` zawiera wszystkie pozycje `nierozstrzygnięty_odczyt` i `kandydat_rozbieżności`, z polami z F6.6. Dwa uruchomienia na tych samych danych dają te same id pozycji.
15. **Wybór źródła:** test potwierdza pierwszeństwo `--source` > `MAPQA_SOURCE` > `default_source` z pliku > `files`. Nieznana nazwa źródła kończy się kodem `1` i listą dostępnych źródeł.
16. **Kontrakt źródeł:** ten sam zestaw testów kontraktowych przechodzi dla adaptera `files` i (z nagranym, prawdziwym wynikiem zapytania) dla adaptera `databricks`.
17. **Zgodność Databricks:** `mapqa sources check --source course-databricks` zwraca liczności 99 768 / 85 405 / 561 / 561 / 1730 zgodne z plikami. Uruchomienie `--no-model` na obu źródłach daje tych samych kandydatów rozbieżności.
18. **Błędy Databricks:** brak tokenu lub HTTP 401/403 → kod `2` i komunikat bez wartości tokenu; stan `FAILED` → błąd, nie pusty wynik.
19. **Agent:** `mapqa sources list --output json` i `mapqa run ... --output json` zwracają poprawny JSON z wynikiem lub błędem, który agent może przetworzyć bez czytania tekstu dla człowieka.

## 9. Etapy wdrożenia: MVP i kolejne przyrosty

Sekcje 3–8 opisują docelowe v1. Pierwszy etap (**MVP**) ma jak najszybciej uruchomić cały przepływ end-to-end na jednym atrybucie i zmierzyć, jak działa model decyzyjny. Pozostałe elementy dochodzą przyrostowo.

### Analiza dostępnych danych (2026-11-03)

| Fakt | Wniosek dla MVP |
|---|---|
| `signs/`: 119 wycinków i 119 pełnych kadrów **lokalnie w repo**, 115 etykiet `certain` (89 wartości 20–120, 25 `none`, 1 `unreadable`), 103 sekwencje | Gotowy zestaw do testu modelu bez pobierania zdjęć; podział po `sequence` jest wykonalny |
| `signs/nearest_osm.csv` ma gotowe dopasowanie do drogi OSM z `maxspeed`, `maxspeed:forward/backward/conditional`, dystansem i flagami | Porównanie z mapą bez własnego łączenia przestrzennego i bez czytania GeoParquet |
| Wśród 71 znaków liczbowych `certain` z `maxspeed` w OSM: **25 zgodnych, 46 różnych**; dodatkowo 18 znaków na drogach bez `maxspeed` | Dużo realnych kandydatów do kolejki ręcznej. Wiele różnic to prawdopodobnie krótkie odcinki (np. 20 przy progach), strefy lub dopasowanie do sąsiedniej drogi, a nie błędy mapy |
| Detektor Mapillary zgadza się ze wszystkimi 89 etykietami liczbowymi | Wycinki wybrano na podstawie detekcji, więc zbiór jest łatwy (obciążenie wyborem). Detektor to punkt odniesienia: model decyzyjny musi go co najmniej dorównać, a kluczowe są negatywy `none` |
| `reference_labels.csv`: 100 zdjęć Panoramax/Mapillary, z czego tylko 36 jest w `offline/`, 0 pobranych | Oświetlenie wymaga pobrania zdjęć (sieć) — kolejny przyrost |
| Nawierzchnia: 99 × `paved`, 0 × `unpaved` | Brak możliwości oceny — poza MVP |
| `signs/` nie ma w tabelach Databricks (`workspace.map_qa` ma 5 innych tabel) | Test MVP na plikach; adapter Databricks w przyroście 1 na danych `photos`/`photo_road_links`/`osm_roads` |
| Na maszynie kursowej nie ma `uv` ani pakietów GIS | Instalacja `uv` jest warunkiem wstępnym implementacji (wymaga zgody) |

### Zakres MVP

| W MVP | Wymagania |
|---|---|
| CLI `mapqa run` i `mapqa sources list/check`, `--output json`, kody wyjścia | F1, F8.1, F8.9 |
| Mechanizm konfiguracji źródeł (`--source`, `MAPQA_SOURCE`, `mapqa.toml`) z **jednym adapterem `files`** i kontraktem danych | F8.1–F8.4, F8.8 |
| Jeden atrybut: **ograniczenie prędkości** na zestawie `signs/` (wycinki) | F5.2 (prędkość) |
| Połączenie zdjęcie → droga z gotowego `signs/nearest_osm.csv`, flagi przenoszone do wyniku | F3.3, F3.4 (bez F3.1–F3.2, F3.5) |
| Pełna kaskada: model decyzyjny → zwykły LLM (reasoning medium) → kolejka ręczna, z progiem, cache, budżetem i logiem kosztów | F5.1–F5.10 |
| Porównanie odczytu z OSM `maxspeed` (surowe tagi kierunkowe i warunkowe zachowane), kandydaci i priorytety | F4.2 (część OSM), F6.1–F6.7 |
| Raport **Markdown** + `manual_queue.csv` + `evaluation.json` | F7.1–F7.3 (bez HTML), F7.5, F7.6 |
| Ewaluacja kaskady na etykietach `certain`, podział po `sequence`, porównanie z detektorem Mapillary | Sekcja 7 (prędkość) |
| Testy z zamockowanym API; jedno prawdziwe uruchomienie na OpenRouter | Kryteria 6–9, 12–15, 19 |

### Poza MVP — kolejność przyrostów

1. **Przyrost 1 — Databricks i własne dopasowanie:** adapter `databricks` (REST, potem CLI), filtr bbox w SQL, profil danych z 561 zdjęć (F2), własne łączenie w EPSG:2180 i porównanie z `photo_road_links.csv` (F3), test zgodności `files` ↔ `databricks` (kryteria 16–18). Prędkość na pełnych kadrach `photos.csv`.
2. **Przyrost 2 — oświetlenie:** pobranie zdjęć `download_photos.py`, pytanie o lampę, OSM `lit`, ewaluacja na 79 etykietach `certain`.
3. **Przyrost 3 — Overture:** porównanie z `speed_limits` (reguły `when`/`between`), źródła i daty Overture (F4.1, F4.3, F4.4).
4. **Przyrost 4 — raport HTML z miniaturami** i model porównawczy `typesafe/jev-1.14` (F7.1, F5.11).
5. **Przyrost 5 — nawierzchnia:** po dodaniu etykiet `unpaved`.
6. **Później:** interfejs użytkownika (dashboard), zapis decyzji, eksport do Jira, serwer MCP narzędzia.

### Kryteria akceptacji MVP

- Kryteria 5–9, 12–15 i 19 z sekcji 8 oraz 10–11 w zakresie prędkości (raport Markdown zamiast HTML). Kryteria 1–4 i 16–18 przechodzą do przyrostu 1.
- Uruchomienie MVP na 119 wycinkach mieści się w budżecie 1 USD i 200 zapytań (poziom 2 tylko dla eskalowanych pytań; drugie uruchomienie z cache = 0 zapytań).
- Raport pokazuje, ile z 46 rozbieżności znak ↔ OSM model potwierdził odczytem, ile poszło do człowieka i dlaczego.
- Trafność i odsetek przekazania człowiekowi są podane osobno dla znaków liczbowych i negatywów `none`, obok wyniku detektora Mapillary na tych samych zdjęciach.

## 10. Ryzyka i założenia

| Ryzyko | Skutek | Mitygacja |
|---|---|---|
| Etykiety referencyjne zawierają błędy | Zaniżona/zawyżona trafność | Status `certain/uncertain`, ręczny przegląd niezgodności, korekta etykiety z powodem |
| Overture częściowo pochodzi z OSM | Fałszywa „zgodność” źródeł | Pokazanie źródła i daty wartości Overture |
| Różne daty zdjęć i mapy | Rozbieżność bez błędu mapy | Data zdjęcia i wersji drogi w raporcie; decyzja człowieka |
| Znak dotyczy innej jezdni / kierunku | Fałszywy kandydat | Flagi połączenia, priorytet `średni` przy flagach |
| Wygasające URL Mapillary | Brak zdjęć | Zdjęcia offline i lokalne pliki; brak pliku = odrzucony rekord |
| Brak klasy `unpaved` w etykietach | Nawierzchnia nieoceniona | Brak progu akceptacji do czasu dodania etykiet |
| Dostępność modeli OpenRouter | Brak odczytów | Eskalacja do poziomu 2, `model_unavailable` → kolejka ręczna, tryb `--no-model`, cache |
| Poziom 2 „zgaduje” z wysoką deklarowaną pewnością | Błędne odczyty zamiast przekazania człowiekowi | Osobna trafność poziomu 2 na eskalowanych pytaniach, próg z kalibracji, priorytet `średni` dla odczytów z poziomu 2 |
| Eskalacja zjada budżet | Mniej zdjęć przeanalizowanych | Wspólny limit, koszt per poziom w logu i raporcie |

## 11. Otwarte pytania

- Czy progi pewności 0,8 (poziom 1 i 2) utrzymać wspólne, czy kalibrować osobno per poziom i atrybut po pierwszej próbie?
- Czy `openai/gpt-6-luna` z `reasoning effort = medium` to docelowy „zwykły” model poziomu 2, czy wybieramy inny?
- Kto i jak doda etykiety `unpaved`, aby objąć nawierzchnię progiem akceptacji?
