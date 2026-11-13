# Jira jobs: snapshot rzeczywistego API

Pracujesz z 40 zgłoszeniami utworzonymi w rzeczywistej Jira Cloud: 7 epiców zamówień, 29 tasków, 2 błędy i 2 podzadania, oraz z 5 stronami Confluence i 10 PR-ami GitHub. Treść zamówień, role, obszary i ścieżki są syntetyczne. Statusy to 25 To Do, 11 In Progress i 4 Done. Zbiór zawiera 16 komentarzy Jira i 12 relacji strukturalnych. Nie potrzebujesz dostępu do strony prowadzącego ani tokenu.

`tickets.json` zachowuje kopertę wyszukiwania `{"issues": [...]}` i komplet pól eksportu, w tym puste wartości, niestandardowe `customfield_*`, ID, statusy, relacje, rodziców, podzadania i znaczniki czasu. Nie dodano sztucznego `total`: źródłowy eksport nie zawierał paginacji. `issue-example.json` jest zbudowany ze zgłoszenia TEST-1 w tym samym eksporcie i pokazuje kształt GET issue: `expand`, `id`, `self`, `key`, `fields`. Dodatkowe `webUrl` pozostaje w wynikach wyszukiwania z konektora.

## Pliki i odwołania

| Plik | Kształt i przeznaczenie |
|---|---|
| `tickets.json` | Koperta wyszukiwania Jira REST v3, 40 zgłoszeń z priorytetem, duedate, hierarchią i komentarzami |
| `issue-example.json` | TEST-1 w kształcie GET issue z tego samego eksportu |
| `confluence-pages.json` | Kolekcja `results`: id, title, parentId, spaceId, version, body.storage.value i _links; rodzic oraz 4 strony potomne |
| `github-prs.json` | Pakiet `repo` i `pull_requests`; każdy rekord zawiera REST `pr`, `commits`, `comments`, `review_comments` i `files` z patchami |
| `job-params.schema.json` | Kontrakt szkicu konfiguracji, nie zgoda na wykonanie |
| `seed-spec.json` | Starsze definicje 34 zgłoszeń dla prowadzącego; nie opisują całego snapshotu v2 |

W pakiecie GitHub pola `pr.comments` i `pr.commits` pozostają licznikami REST; tablice zasobów są obok obiektu `pr`. Zachowano SHA, ID komentarzy, gałęzie, SQL i diff YAML, aby można było wskazać dokładny dowód. W komentarzach znajdują się także automatyczne komunikaty o limicie review; nie dowodzą wykonania ani odbioru pracy.

Jira, Confluence i GitHub nie są zintegrowane: nie ma linków panelu development, synchronizacji statusów ani automatycznego zamykania przez frazę `Closes TEST-9`. Tak jak w pracy, odwołania są rozsiane po URL-ach, gołych kluczach, gałęziach, commitach i komentarzach; występują małe litery, spacje, literówki, stare prefiksy, numery zamawiającego i dopasowania tylko po treści. Nie każda wzmianka oznacza prawidłowy link.

Strony odczytujesz przez `pages [tekst]` / `page ID`, a PR-y przez `prs [tekst]` / `pr N`, zawsze z `jira_read.py --offline`; odpowiedniki MCP to `search_pages`, `get_page`, `list_prs`, `get_pr`. Nie otwieraj snapshotów JSON zamiast narzędzi. Strona "Konwencje parametrów zleceń" (220135425) jest źródłem zasad normalizacji; kalendarz może być nieaktualny. Porównuj wersję, treść i komentarze z zakresem konkretnego zamówienia.

Anonimizacja obejmuje także URL Confluence i GitHub: przestrzeń osobista to `~course-user`, właściciel repozytorium to `course-org`, identyfikatory kont GitHub są technicznymi aliasami (ID PR-ów i komentarzy pozostają bez zmian), a nazwa `map-data-jobs-sim` i ID stron pozostają bez zmian. URL-e kursowe służą jako dowody w snapshocie, nie zapewniają dostępu online. HTML stron pochodzi z eksportu autora; został opakowany w reprezentację REST v2, bez udawania bajtowej kopii HTTP ani dopisywania dat wersji.

## Jak powstały pliki

Prowadzący utworzył zgłoszenia na podstawie `seed-spec.json`, wyeksportował pełne pola i komentarze przez konektor, a następnie uruchomił `sanitize_export.py`. Surowy eksport i mapowanie tożsamości pozostają poza repozytorium. To snapshot rzeczywistych odpowiedzi po anonimizacji i odtworzeniu reprezentacji REST v3, nie bajtowa kopia odpowiedzi HTTP.

Zastosowano: fikcyjny host `course-site.atlassian.net`, zerowy cloud ID, stabilne `accountId` w formacie `712020:course-user-1`, nazwę użytkownika `Analityk (kurs)`, nazwę projektu `Projekt kursowy` i ogólne awatary. Usunięto `emailAddress`, zastąpiono wystąpienia tożsamości także w adresach i tekście. `timeZone` zachowano. Ścieżki `self` pozostały bez zmian, zmieniły się host i identyfikatory użytkowników lub cloud ID.

W eksporcie v2 opisy są już ADF; zachowano je bez ponownego parsowania. Markdown w komentarzach przekonwertowano do `body` ADF tak jak zwraca REST v3. Sanitizer potrafi też przekonwertować starsze opisy Markdown. Zachowano akapity, nagłówki, listy, bloki kodu z językiem, tabele, pogrubienia, kursywę i kod inline. Dosłowne sekwencje `\n` w opisach odtworzono jako podziały wierszy. Dodane przez konektor `\[` i `\]` w komentarzach odtworzono jako nawiasy. Gotowe węzły ADF nie są ponownie interpretowane. Alias autora w tekście komentarza oznacza rolę, a `author.displayName` jest kontem technicznym.

To celowo zagęszczona kolejka szkoleniowa. Prawdziwy kształt API nie potwierdza istnienia notebooków, storage ani wyników przetwarzania. `seed-spec.json` to lista definicji dla prowadzącego, nie odpowiedź REST. Nie używaj jej zamiast narzędzi w ćwiczeniu.

## Gdzie szukać parametrów

| Źródło | Pola API | Co z niego odczytasz |
|---|---|---|
| Zamówienie | `fields.issuetype`, `fields.summary`, `fields.description` | Epic, numer źródłowy, tabela lub opis parametrów |
| Taski pod epikiem | `fields.parent.key` w wynikach wyszukiwania | Kroki, SQL, historyczne komórki YAML, warunki odbioru |
| Podzadania | `fields.subtasks` oraz `fields.parent.key` | Zakres bbox i wyjaśnienie kolejności osi |
| Komentarze | `fields.comment.comments[].body`, `id`, `created` | Korekty parametrów, potwierdzenia i blokady |
| Linki | `fields.issuelinks[].type`, `inwardIssue`, `outwardIssue` | Zależności i podejrzenie duplikatu, z zachowaniem kierunku |
| Wyszukiwanie tekstowe | Tytuł, opis i komentarze całej kolejki | Zadania bez parenta lub linku, wskazane numerem zamówienia albo tytułem |

`subtasks` nie jest listą wszystkich tasków epika. Wyszukaj także `parent = TEST-1`, a następnie dzieci tasków. Powiązania tekstowe mogą prowadzić do zgłoszenia poza hierarchią. Dane biznesowe region/deadline/format są w treści, nie w specjalnie utworzonych polach Jira. Nie utożsamiaj autora technicznego ani statusu Jira z zamawiającym lub zgodą na wykonanie.

## Kontrakt wyniku v2

Zapisz jeden plik `reports/jira-jobs/jobs/<klucz-zamówienia>.yaml` na każde zamówienie. Zachowaj także kandydata będącego możliwym duplikatem; nie usuwaj go i nie planuj drugiego runu bez rozstrzygnięcia. Taski i podzadania kroków są dowodami, nie osobnymi jobami. Samodzielne nowe zamówienia TEST-38 i TEST-39 zachowaj jako osobne szkice do decyzji, bez dopisywania epika lub zgody na dostawę. Błędy uruchomień i kontrola dzienna to dowody operacyjne. Zgłoszenia dostępu i błędów UI bez zamówienia danych opisz jako `ignore_non_job` w `issues.md`, bez generowania konfiguracji.

Każdy YAML zawiera 13 pól: `job_id`, `region`, `area_name`, `bbox`, `layers`, `data_release`, `start_step`, `steps`, `output_format`, `output_path`, `deadline`, `requester_team`, `notes`, oraz obowiązkowe `unknown_reasons`. `job_id` to rzeczywisty klucz epika, np. `TEST-1`, albo klucz samodzielnego nowego zamówienia TEST-38/TEST-39. Numer zamawiającego jest osobnym dowodem w notes, nie zastępuje klucza Jira. `notes` to lista napisów. Release i deadline zapisuj w cudzysłowach, np. `'2026.11'` i `'2026-11-19'`. Schemat waliduje jeden obiekt YAML, nie listę wszystkich zgłoszeń.

Normalizuj wydanie do `YYYY.MM`, datę do `YYYY-MM-DD`, region do potwierdzonego ISO 3166-2, format i kroki do małych liter. Warstwy to lista: `roads`, `junctions`, `poi`, `speed_limits`, `addresses`. `steps` to kroki pozostałe od `start_step`, w kolejności wykonania. Nie dodawaj zakończonych etapów na podstawie liczby tasków. Bbox to `[west, south, east, north]` w EPSG:4326. Zamiana osi wymaga dowodu w źródle, nie tylko legalnych zakresów liczb.

Każde nieznane lub nierozstrzygnięte pole ma `null` i konkretny powód w `unknown_reasons`. Jawnie zamówiony cały region może mieć `bbox: null`; wtedy powód wyjaśnia brak dodatkowego wycinka, a nie brak informacji. Brak docelowej ścieżki blokuje wykonanie, chociaż szkic z `null` i powodem przechodzi schemat. HOLD, BLOCKED i warunki odbioru zachowaj w `notes` oraz `issues.md`. Poprawna walidacja nie jest zgodą na uruchomienie.

W `issues.md` podaj dla problemu klucz zamówienia i zgłoszenia dowodowego, pole, cytat, źródło (opis lub ID i data komentarza), wartość, pewność z uzasadnieniem i pytanie do człowieka. Rozróżnij: duplikaty, podobne odrębne zamówienia, konflikty, zatwierdzone nadpisania, braki, wartości historyczne i szum. Późniejszy komentarz zmienia parametry tylko tam, gdzie jawnie zatwierdzono zmianę. Nie przenoś korekty do innego epika automatycznie.

Sprawdź YAML względem `job-params.schema.json`, daty kalendarzowe, kolejność kroków i relacje bbox. Walidator kursowy uruchomisz z katalogu głównego repozytorium:

```powershell
uv run --with pyyaml --with jsonschema course-materials/exercises/jira-mcp/validate_jobs.py reports/jira-jobs/jobs
```

Oczekujesz 7 kandydatów pod epicami i 2 nowych szkiców do potwierdzenia, razem 9. Każdy z 40 kluczy musi mieć wyjaśnioną rolę: zamówienie, dowód albo szum. Nie zmieniaj Jira i nie uruchamiaj Databricks ani pipeline GIS.

## Kontrakt powiązań J3

Zapisz `reports/jira-jobs/links.csv` w UTF-8 z nagłówkiem `source,source_id,mention_text,jira_key,confidence,action,evidence`. Dozwolone wartości: source = pr/page/comment, confidence = high/medium/low, action = link/flag_for_human/ignore. Commity, gałęzie i pliki to source=pr z lokalizacją w source_id; komentarze Jira i GitHub to source=comment z nazwą usługi, kluczem/PR i ID. source_id, mention_text i evidence nie mogą być puste; fragment z przecinkami lub nową linią zapisz jako poprawnie cytowaną komórkę CSV. PowerShell 5 może dodać BOM UTF-8, walidator go obsługuje.

`jira_key` zawiera istniejący rozwiązany klucz albo puste pole. Nieistniejący klucz zachowaj w mention_text, a pole jira_key pozostaw puste; action=link wymaga celu. Jeden wiersz opisuje wzmiankę i jeden cel, więc przy kilku kandydatach zapisz kilka wierszy. `link` oznacza wyłącznie propozycję. Prawidłowy klucz nie rozstrzyga konfliktu parametrów: wtedy confidence może być high, a action nadal flag_for_human. Literówki, migracje prefiksu, dopasowania tylko po treści oraz nieustalona intencja dostawy wymagają człowieka. Komentarz bez dowodu biznesowego może mieć action=ignore.

W `links.md` opisz proponowane linki, abstencje, konflikty YAML PR kontra ticket, kalendarza kontra duedate/komentarze Jira i brakujące odnośniki. Nie ma jednej wymaganej liczby wierszy: identyczny klucz może wystąpić w kilku miejscach, a dowód bez klucza też wymaga oceny. Walidator sprawdza format i istnienie rozwiązanych kluczy, nie prawdę semantyczną ani kompletność dowodów.

```powershell
uv run course-materials/exercises/jira-mcp/validate_links.py reports/jira-jobs/links.csv
```

## Odtworzenie snapshotu przez prowadzącego

Surowy eksport trzymaj poza repozytorium, np. w `D:\trainer-private\jira-export.json`. Polecenie nadpisuje tylko cztery jawne pliki docelowe; nie zapisuje danych surowych ani mapowania użytkowników.

```powershell
python course-materials/exercises/jira-mcp/sanitize_export.py D:\trainer-private\export-raw-v2.json course-materials/exercise-data/jira-jobs/tickets.json --example course-materials/exercise-data/jira-jobs/issue-example.json --pages-raw D:\trainer-private\confluence-pages.json --pages course-materials/exercise-data/jira-jobs/confluence-pages.json --prs-raw D:\trainer-private\github-prs-export.json --prs course-materials/exercise-data/jira-jobs/github-prs.json
```

`seed_jira.py` jest narzędziem legacy dla płaskiego formatu zgłoszeń. Nie obsługuje `seed-spec.json`, nie odtwarza epiców, parentów ani workflow v2. Nie używaj go do odtworzenia bieżącego zbioru. Użyj procedury seedowania v2 prowadzącego, potem wyeksportuj i zanonimizuj dane. Dokumentacja ADF: [format dokumentu Atlassiana](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/).

Kontrakty źródłowe: [Confluence REST v2 Page](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/), [GitHub REST PR](https://docs.github.com/en/rest/pulls/pulls), [komentarze dyskusji](https://docs.github.com/en/rest/issues/comments), [komentarze review](https://docs.github.com/en/rest/pulls/comments).
