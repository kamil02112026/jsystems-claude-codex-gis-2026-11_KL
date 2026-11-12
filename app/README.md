# mapqa — Map Attribute QA Copilot (PoC)

CLI w Pythonie 3.12 (uv), które wskazuje kandydatów do ręcznej weryfikacji atrybutów dróg na podstawie OSM i zdjęć ulic. Specyfikacja: [PRD](../docs/PRD.md), [ADR](../docs/ADR/), plan: [docs/plans/map-qa-mvp-implementation-plan.md](../docs/plans/map-qa-mvp-implementation-plan.md).

Polecenia uruchamiaj z **katalogu głównego repozytorium** (ścieżki w konfiguracji są względne do katalogu roboczego):

```powershell
uv sync --project app
uv run --project app mapqa --help
uv run --project app pytest app/tests -q          # unit/contract/integration (bez e2e i paid)
uv run --project app pytest app/tests -m e2e -q   # prawdziwe CLI na plikach kursu, offline
```

Testy oznaczone `paid` wysyłają prawdziwe zapytania do OpenRouter i uruchamia się je wyłącznie świadomie, za zgodą właściciela.
