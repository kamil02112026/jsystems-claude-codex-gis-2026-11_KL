# Podsumowanie - dzień 3, 12 listopada 2026

## Cel i zakres dnia

Dzień szkolenia poświęcono przygotowaniu projektu GIS Map QA do pracy z agentami kodującymi. Główne narzędzia to Claude Code i Codex; OpenCode omawiano jako dodatkowego agenta CLI do delegowania zadań. Praca obejmowała organizację repozytorium, dokumenty PRD i ADR, profilowanie danych lokalnych i danych Databricks oraz przygotowanie planu implementacji.

Plan implementacji przekazano agentowi do kontynuacji. Następnym krokiem było uruchomienie aplikacji i sprawdzenie jej zgodności z PRD, ADR oraz planem.

## Konta, limity i narzędzia

Do aktualizacji Codex CLI podano polecenie:

```text
codex update
```

Na zajęciach wskazano wersję 0.167.2. Stan limitu sprawdzisz w Codex przez `/usage`. Przy dostępnym resecie wybierz `Redeem reset`. Przed użyciem sprawdź zakres resetu i termin jego ważności. Reset konkretnego limitu nie musi zerować całego tygodniowego zużycia.

Do sprawdzenia uwierzytelnienia GitHub CLI użyto:

```text
gh auth status
```

Jeśli GitHub CLI nie widzi uwierzytelnienia w środowisku Codex, sprawdź je w zwykłym PowerShell poza sandboxem agenta. Omówiono zakres uprawnień obejmujący odczyt Actions i metadanych oraz odczyt i zapis kodu i pull requestów. Osobiste tokeny i inne poświadczenia należy wprowadzać wyłącznie lokalnie, nie wklejać ich do rozmów z agentem ani zapisywać w repozytorium.

W terminalowym edytorze Micro użyte skróty to `Ctrl+S` do zapisu i `Ctrl+Q` do wyjścia. `code .` otwiera bieżący katalog w Visual Studio Code. Wskazano też `Ctrl+G` do otwarcia edycji promptu w skonfigurowanym edytorze. W środowisku ćwiczenia `!` służyło do przejścia do trybu shell w Codex lub Claude.

## Instrukcje agentów i Git worktrees

Wspólna konwencja dla Git worktrees ma ułatwiać współpracę Claude Code, Codex i OpenCode:

```text
../<nazwa-folderu-projektu>-worktrees/<nazwa-gałęzi>
```

Przykładowo, worktree projektu `D:/project-name/` trafia do `D:/project-name-worktrees/worktree-1/`. Ważne jest, by Claude i pozostałe agenty korzystały z tej samej konwencji. Przenoszenie istniejącego worktree należy wykonywać poleceniami Git, a nie zwykłym przenoszeniem katalogu.

Powyższa ścieżka jest liczona względem katalogu głównego projektu.

Instrukcje globalne i projektowe należy rozdzielać: ustawienia użytkownika znajdują się w katalogach konfiguracyjnych danego agenta, a instrukcje projektu powinny być dostępne w repozytorium. W rozmowie wskazano m.in. `~/.claude/CLAUDE.md` dla Claude Code oraz `.codex/AGENTS.md` dla Codex. Instrukcje OpenCode należy umieścić w jego ustawieniach użytkownika. Treść wspólnych zasad warto utrzymywać spójną między agentami.

Uzgodniono pracę projektową na gałęzi `Map-App-Implementation`. Aktualizacje z repozytorium upstream można pobrać przez funkcję synchronizacji forka na GitHubie, a następnie lokalnie zaktualizować repozytorium.

## PRD, ADR i profil danych

PRD opisuje potrzeby użytkownika, funkcje i kryteria akceptacji. ADR zapisuje istotne decyzje architektoniczne, na przykład wybór komponentów, źródeł danych i modeli. Dokumenty są w Markdown. Diagramy Mermaid mogą przedstawiać przepływ użytkownika lub logikę systemu w sposób bardziej jednoznaczny niż sam opis tekstowy.

Jeśli prosty projekt nie ma jeszcze ADR, agent może zaproponować decyzje na podstawie PRD. Przykład polecenia użytego na szkoleniu:

```text
/write-adr make architectural decisions and create ADR for the PRD file: @docs/PRD.md
```

Przygotowanie ADR dla aplikacji mapowej wymagało informacji o danych. Udostępniony skrypt profilu danych uruchamia się z katalogu głównego repozytorium:

```text
uv run --python 3.12 course-materials/exercise-data/map-qa/profile_data.py
```

Jeśli UV nie jest zainstalowane w Windows, polecenie instalacji podane w czacie to:

```powershell
winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements
```

Profil ma pomagać agentowi zrozumieć lokalne pliki CSV i dane dostępne w Databricks. Po uzyskaniu profilu i dostępu do danych należy zaktualizować ADR o nowe informacje. Do generowania ADR udostępniono osobny prompt w materiałach kursu.

## Databricks i bezpieczna praca z danymi

Do instalacji aktualnego Databricks CLI w Windows podano:

```powershell
winget install Databricks.DatabricksCLI --accept-source-agreements --accept-package-agreements
```

Po instalacji należy otworzyć nowy PowerShell, aby odświeżyła się ścieżka `PATH`. W ćwiczeniu potrzebne były zmienne `DATABRICKS_HOST`, `DATABRICKS_TOKEN` i `DATABRICKS_SQL_WAREHOUSE_ID`. Ich wartości należy pobierać z przeznaczonych do tego materiałów i ustawiać lokalnie. Nie należy ujawniać ich agentowi, wyświetlać w podsumowaniach ani commitować do repozytorium. Zmienne ustawione tylko w bieżącej sesji PowerShell znikają po jej zamknięciu; jeśli potrzebują być dostępne następnego dnia, sposób ich trwałego zapisania trzeba dobrać ostrożnie i chronić token.

W trakcie zajęć pokazano odczyt SQL przez Databricks REST API. Status zapytania testowego został zwrócony jako `SUCCEEDED`, co potwierdziło działanie tego odczytu. Po połączeniu można porównać wyniki odczytu z profilem plików lokalnych.

## Planowanie i delegowanie pracy

Claude Code udostępnia różne tryby pracy, w tym Plan Mode przełączany przez `Shift+Tab`. Omówiono także alternatywę: jawny workflow zapisany w skillu lub planie. Plan powinien odnosić się do PRD, ADR i instrukcji projektu, dzielić implementację na logiczne etapy, ustalać priorytety i wskazywać sposób delegowania. Przed wykonaniem warto sprawdzić dokumenty pod kątem sprzeczności.

Modele warto dobierać do roli i wielkości zadania. W omawianym podziale Codex Sol 6.1 wskazywano dla trudniejszych zadań i przeglądu kodu, a Luna 6 dla prostszych zadań i researchu. Dla OpenCode wskazano MiMo-V2.6-Flash w trybie CLI. Praktyczna zasada pozostaje taka: małe, dobrze określone zadania delegować tańszym modelom, a model orchestratora przeznaczać na koordynację i trudniejsze decyzje.

Do uruchamiania agentów CLI w trybie headless wskazano:

```text
codex exec
opencode run
claude -p "prompt"
```

Plan powinien podawać konkretne zadania, wybranych agentów i sposób uruchomienia ich w trybie headless.

W planie aplikacji zaznaczono, by nie zastępować rzeczywistych testów makietami. Testy ręczne i end-to-end modeli decyzyjnych oraz chatowych powinny używać prawdziwych endpointów i sprawdzać rzeczywiste formaty żądań oraz odpowiedzi. Mocki mogą być użyte w testach jednostkowych i integracyjnych, ale przed ich przygotowaniem trzeba poznać rzeczywisty kontrakt API.

## Modele decyzyjne przez OpenRouter

Dla chatowego LLM wskazano `openai/gpt-6-luna`. Jako model decyzyjny wskazano `typesafe/jev-1.14`, a jako alternatywę `openai/gpt-6-luna-decisions`. Omówiono obsługę obrazów jako wejścia oraz porównywanie modeli pod kątem ceny, opóźnienia i typów pytań. Konfiguracja ma korzystać z endpointów i API OpenRouter. Klucz API powinien pozostać w bezpiecznej konfiguracji środowiska, a nie w promptach lub repozytorium.

Przykładowe polecenia do dalszej pracy z sesjami i planem:

```text
/new
/clear
/goal implement the plan from @docs/plans/implementation-plan.md Before completing the plan, make sure that all conditions from the ADR and PRD files are met.
```

`claude --continue` wznawia ostatnią sesję, a `/resume` pozwala wybrać wcześniejszą. `/subagents` wyświetla subagentów Codex. `/goal` pozwala wskazać agentowi cel realizacji.

## Dalsze działania

Do kontynuacji po zajęciach należą: sprawdzenie i uzupełnienie PRD oraz ADR, wygenerowanie lub odświeżenie profilu danych, aktualizacja ADR o dostępne dane Databricks, przejrzenie planu przed implementacją oraz bezpieczne skonfigurowanie zmiennych środowiskowych. Plan implementacji aplikacji GIS Map QA został przekazany do dalszej realizacji i weryfikacji. Po implementacji trzeba uruchomić aplikację i przejść jej główny scenariusz ręcznie.

Na kolejny dzień zaplanowano sprawdzenie stanu implementacji, wznowienie planu lub debugging w razie potrzeby, a także omówienie `/goal`, Spec Driven Development, delegowania do subagentów i agentów CLI, TDD, ręcznego QA, przeglądu kodu i CI/CD. Wśród propozycji znalazły się również integracje Jira/Confluence, porównanie Connectors, Plugins, MCP i CLI, oraz inne formaty pracy z agentami. 

## Materiały i odnośniki

- [Repozytorium dokumentów PRD i ADR](https://github.com/LucasMatuszewski/jsystems-claude-codex-gis-2026-11/tree/Map-App-Implementation/docs)
- [Skrypt profilu danych](https://github.com/LucasMatuszewski/jsystems-claude-codex-gis-2026-11/blob/Map-App-Implementation/course-materials/exercise-data/map-qa/profile_data.py) i [zapytanie SQL profilu](https://github.com/LucasMatuszewski/jsystems-claude-codex-gis-2026-11/blob/Map-App-Implementation/course-materials/exercise-data/map-qa/profile.sql)
- [Prompt do generowania ADR dla GIS Map QA](https://github.com/LucasMatuszewski/jsystems-claude-codex-gis-2026-11/blob/Map-App-Implementation/course-materials/Prompt%20examples/ADR-generation-python-gis-map-qa.md)
- [Konfiguracja providerów dla agentów](https://github.com/LucasMatuszewski/jsystems-claude-codex-gis-2026-11/blob/main/course-materials/agent-configs/.bashrc-agents)
- [Przykłady subagentów Claude Code](https://github.com/LucasMatuszewski/jsystems-claude-codex-gis-2026-11/tree/Map-App-Implementation/course-materials/agent-configs/claude/agents)
- [Prompt do planowania z macierzą subagentów i zależności](https://github.com/LucasMatuszewski/jsystems-claude-codex-gis-2026-11/blob/Map-App-Implementation/course-materials/Prompt%20examples/Plan-SubAgents-matrix-dependency-map.md)
- [Jev 1.14 w OpenRouter](https://openrouter.ai/typesafe/jev-1.14) i [Luna Decisions w OpenRouter](https://openrouter.ai/openai/gpt-6-luna-decisions)
- [Beads, narzędzie opisywane jako Jira dla agentów](https://github.com/gastownhall/beads)
- [Artificial Analysis](https://artificialanalysis.ai/)
- [Ustawienia GitHub Personal Access Tokens](https://github.com/settings/personal-access-tokens)
- [Informacja o planowanym resecie limitu](https://x.com/thsottiaux/status/2120410006273380750) i [wpis o Plan Mode](https://x.com/trq212/status/2102813194196758746)
