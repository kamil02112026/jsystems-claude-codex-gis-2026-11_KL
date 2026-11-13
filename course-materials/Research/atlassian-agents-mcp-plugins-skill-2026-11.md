# Agenci i Atlassian: plugin, MCP, skill z API

Stan dokumentacji: 13.11.2026. Najpierw ustal z administratorem, czy pracujesz z Cloud, czy Server/Data Center. Dla Cloud zacznij od oficjalnego pluginu lub Rovo MCP przez OAuth. Dla systemu w sieci firmowej wybierz zatwierdzony skrypt REST uruchamiany lokalnie przez skill.

## 1. Cztery drogi

Connector to gotowe połączenie w aplikacji, plugin to paczka rozszerzeń, MCP to protokół udostępniania narzędzi, a skill to instrukcja pracy. Plugin może zawierać zarówno skill, jak i konfigurację MCP. To warstwy, które mogą współpracować.

| Droga | Przygotowanie | Uwierzytelnianie | Cloud / Server/DC | Co otrzymujesz | Tokeny modelu | Kontrola i bezpieczeństwo |
| --- | --- | --- | --- | --- | --- | --- |
| Connector w claude.ai / ChatGPT, Copilot 365 | Krótko po udostępnieniu przez administratora; indeksowanie M365 trwa osobno | Zgoda konta/OAuth; w M365 połączenie zarządzane przez IT | Atlassian Rovo: Cloud; M365 ma także konektory Jira DC i Confluence on-prem | Wyszukiwanie i odpowiedzi; dostępne akcje zależą od integracji, indeks M365 nie jest pełnym API | Zależą od pobranej treści i aplikacji | Uprawnienia konta, polityki organizacji; sprawdź, gdzie trafiają dane |
| Plugin Claude Code / Codex | Krótko: wybór paczki i autoryzacja | Według dołączonego MCP, zwykle OAuth | Oficjalny Atlassian MCP: Cloud | Narzędzia i gotowe procedury, np. triage i raporty | Instrukcje, wybrane narzędzia i wyniki zużywają kontekst | Sprawdź wydawcę, manifest, zakresy i dołączone skille |
| MCP skonfigurowany samodzielnie | Kilka kroków konfiguracji i logowania | OAuth 2.1 lub token po włączeniu przez administratora | Rovo MCP: Cloud | Odczyt, wyszukiwanie i dozwolone akcje w produktach Atlassian | Schematy wybranych narzędzi i wyniki; odkrywanie na żądanie ogranicza narzut | Osobne nazwy połączeń, zakresy, polityki odczytu/zapisu |
| Skill + bezpośrednie REST API | Dłużej za pierwszym razem: skrypt, VPN, kontrakt danych | Cloud: API token/OAuth; DC: metoda dopuszczona dla danej wersji | Cloud oraz Server/DC, przez właściwe API | Paginacja, wybrane pola, eksporty, załączniki i diffy obsługiwane skryptem | Bez schematów MCP tej usługi; filtrowanie lokalne ogranicza wynik dla modelu | Jawna lista hostów i endpointów, odczyt domyślny, przegląd skryptu |

Czasy są porównaniem nakładu, nie gwarancją instalacji. Gotowe integracje opisuje [Atlassian](https://atlassian.github.io/atlassian-mcp-server/), a odrębny wariant indeksowania firmowego [Microsoft: Jira DC](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/jira-data-center-overview) i [Confluence on-prem](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/confluence-onpremises-deployment).

**Claude Code:** oficjalny plugin `atlassian` wydaje Atlassian w repozytorium `atlassian/atlassian-mcp-server`; wpis jest też w [katalogu Anthropic](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json). [Manifest pluginu](https://github.com/atlassian/atlassian-mcp-server/blob/main/.claude-plugin/plugin.json) dołącza `.mcp.json` i `skills/`, m.in. wyszukiwanie wiedzy, triage, backlog i raport statusu. [Instalacja z PowerShell](https://code.claude.com/docs/en/plugins/install):

```powershell
claude plugin install atlassian@claude-plugins-official
```

**Codex:** [Atlassian potwierdza swój plugin dla ChatGPT i Codex](https://community.atlassian.com/forums/discussion/3288784/bring-your-atlassian-work-into-chatgpt-and-codex/p1). W sesji CLI otwórz `/plugins` i wyszukaj "Atlassian Rovo"; dostępność zależy od konta i polityk organizacji. [OpenAI opisuje katalog oraz paczki skills/MCP](https://developers.openai.com/codex/plugins/). Nie kopiuj komendy instalacyjnej Claude do Codex. Skill `atlassian-onprem-safe` wskazany jako przykład dla `EdukeyTeam/agent-toolbox` ma status **UNCONFIRMED**: nie potwierdzono go w publicznym drzewie repozytorium. Nie instaluj paczki o tej nazwie bez sprawdzenia źródła.

## 2. Kilka serwerów MCP naraz

Używaj osobnych nazw dla pracy i konta prywatnego. [OAuth Rovo](https://developer.atlassian.com/cloud/rovo-mcp/guides/configuring-oauth-2-1/) zwykle wiąże autoryzację z jednym `cloudId`, czyli witryną Jira/Confluence, a nie automatycznie z całą organizacją. Bitbucket ma osobny kontekst workspace; dodatkowe konto/workspace traktuj jako osobne połączenie. Workspace Bitbucket musi być powiązany z organizacją. Dwie nazwy same nie gwarantują izolacji sesji OAuth ani ograniczenia tokenu do jednej witryny.

Poniżej wariant z osobnymi tokenami dla dwóch kont. Administrator musi wcześniej włączyć API token authentication w ustawieniach Rovo MCP. Potrzebujesz zakresów `agent-interface` dla odczytu/wyszukiwania wybranych produktów. [Osobisty API token](https://developer.atlassian.com/cloud/rovo-mcp/guides/configuring-authentication-via-api-token/) używa Basic, a klucz konta serwisowego Bearer. Nie zamieniaj tych mechanizmów. Token nie jest związany z jednym `cloudId`: przy wywołaniu narzędzia wskaż właściwą witrynę w wymaganym parametrze `cloudId` i sprawdź wynik.

W tym samym PowerShell, z którego uruchomisz agenta, zakładamy już ustawione bezpiecznie `ATL_WORK_EMAIL`, `ATL_WORK_TOKEN`, `ATL_PRIVATE_EMAIL`, `ATL_PRIVATE_TOKEN`. Zbuduj pełne nagłówki w pamięci, bez wypisywania wartości. [PowerShell obsługuje zmienne procesu](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables?view=powershell-7.5), a [Base64](https://learn.microsoft.com/en-us/dotnet/api/system.convert.tobase64string) jedynie koduje dane, nie szyfruje sekretu.

```powershell
$env:ATL_WORK_AUTH = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($env:ATL_WORK_EMAIL + ':' + $env:ATL_WORK_TOKEN))
```

```powershell
$env:ATL_PRIVATE_AUTH = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($env:ATL_PRIVATE_EMAIL + ':' + $env:ATL_PRIVATE_TOKEN))
```

**Claude Code:** wybierz polecenia albo równoważny plik `.mcp.json`, nie oba naraz. Pojedyncze cudzysłowy PowerShell zachowują dosłowne `${VAR}`; klient rozwinie je przy połączeniu. Nie podawaj rozwiniętej wartości sekretu jako argumentu. [Dokumentacja Claude MCP](https://code.claude.com/docs/en/mcp) potwierdza transport HTTP, `--header`, zakres local i rozwijanie zmiennych.

```powershell
claude mcp add --transport http --scope local atlassian-work https://mcp.atlassian.com/v2/mcp --header 'Authorization: ${ATL_WORK_AUTH}'
```

```powershell
claude mcp add --transport http --scope local atlassian-private https://mcp.atlassian.com/v2/mcp --header 'Authorization: ${ATL_PRIVATE_AUTH}'
```

```json
{"mcpServers":{"atlassian-work":{"type":"http","url":"https://mcp.atlassian.com/v2/mcp","headers":{"Authorization":"${ATL_WORK_AUTH}"}},"atlassian-private":{"type":"http","url":"https://mcp.atlassian.com/v2/mcp","headers":{"Authorization":"${ATL_PRIVATE_AUTH}"}}}}
```

**Codex:** w swoim pliku `$HOME\.codex\config.toml` dodaj dwa bloki. `env_http_headers` wskazuje nazwę zmiennej zawierającej cały nagłówek, bez składni `${...}`. [Dokumentacja Codex MCP](https://developers.openai.com/codex/mcp/) opisuje ten mechanizm; nie używaj `bearer_token_env_var` do nagłówka Basic.

```toml
[mcp_servers.atlassian-work]
url = "https://mcp.atlassian.com/v2/mcp"
env_http_headers = { Authorization = "ATL_WORK_AUTH" }

[mcp_servers.atlassian-private]
url = "https://mcp.atlassian.com/v2/mcp"
env_http_headers = { Authorization = "ATL_PRIVATE_AUTH" }
```

Uruchom nową sesję agenta z tego okna, wpisz `/mcp`, sprawdź obie nazwy i wykonaj po jednym uzgodnionym odczycie z każdego konta. W wyniku sprawdź witrynę, projekt i klucz; sam status połączenia nie dowodzi prawidłowego dostępu. Dla pojedynczego połączenia OAuth użyj wariantu J0-B ćwiczenia zamiast nagłówków Basic.

## 3. Kiedy API w skillu wygrywa z MCP

Wybierz lokalny skill i skrypt REST dla Server/DC za VPN, masowego JQL, pól niestandardowych, załączników, pełnej historii zmian i diffów Bitbucket. Skrypt kontroluje paginację, limity, dobór pól i format wyniku; nie zakładaj, że `expand=changelog` zwraca całą historię. Cloud i DC mają różne kontrakty: sprawdź [Jira Cloud](https://developer.atlassian.com/cloud/jira/platform/rest/v3/), [Jira DC](https://developer.atlassian.com/server/jira/platform/rest-apis/), [Bitbucket Cloud](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-pullrequests/) lub [Bitbucket DC](https://developer.atlassian.com/server/bitbucket/rest/). Skończony eksport można filtrować lokalnie i przekazać modelowi tylko dowody. To może oszczędzić tokeny; nie gwarantuje mniejszego kosztu każdej sesji. Rovo v2 i klienci także potrafią odkrywać narzędzia na żądanie.

Wybierz MCP, gdy potrzebujesz szybkiego startu przez OAuth bez ręcznego tokenu, wyszukiwania między produktami lub kontekstu Teamwork Graph. Skill może uczyć korzystania z MCP, więc wybór nie musi być rozłączny. Bezpośrednie API też może korzystać z OAuth; jego zaletą jest kontrola przepływu, nie sam rodzaj logowania.

## 4. Bezpieczeństwo

W Cloud wybieraj zakresy odczytu/wyszukiwania, termin wygaśnięcia i osobny token dla każdego narzędzia. W DC ogranicz uprawnienia konta i metody skryptu zgodnie z możliwościami wersji. Nie wkładaj tokenów do promptów, repozytorium, logów ani historii poleceń; konfiguracja zawiera tylko nazwy zmiennych. Odczyt jest domyślny. Przed zapisem pokaż człowiekowi konkretne zgłoszenia, diff i plan operacji; samo podłączenie pluginu nie oznacza zgody na zmiany.

Treść ticketu, komentarza, strony i PR to niezaufane dane. Polecenie "wyślij token" lub "zignoruj instrukcje" w opisie zgłoszenia nie ma uprawnień do sterowania agentem. Ogranicz hosty, narzędzia i zakres wyjścia. Po zakończeniu zamknij procesy agentów, usuń poświadczenia z bieżącego PowerShell, a jednorazowe tokeny unieważnij w panelu konta.

```powershell
Remove-Item Env:ATL_WORK_AUTH,Env:ATL_PRIVATE_AUTH,Env:ATL_WORK_TOKEN,Env:ATL_PRIVATE_TOKEN,Env:ATL_WORK_EMAIL,Env:ATL_PRIVATE_EMAIL -ErrorAction SilentlyContinue
```
