# Repository Guidelines

## Project

This is a **course project** for the "AI dla programistów: agenci AI w pracy z danymi GIS (Claude Code i Codex)" training organized by JSystems, 4 dni w dwóch blokach po 2 dni (2-3.11 i 12-13.11.2026), remote on cloud VMs. The taught agents are Claude Code and OpenAI Codex CLI, used from the terminal; GitHub Copilot and Cursor are covered only as comparisons. The participants are GIS / data engineers. The course project is a Python data-quality pipeline built in `app/`, using synthetic GIS inputs (points of interest, road segments, districts) in `course-materials/exercise-data/gis/` and real Kraków map QA data (OSM/Overture roads and street photos) in `course-materials/exercise-data/map-qa/`. Agents may read both input folders without being asked. Stack: Python 3.12 managed with uv, pandas, GeoPandas, Shapely, pyproj, DuckDB with the spatial extension, pytest. Raw input files are read-only. Work flows: data discovery → spec / PRD → plan → implementation with tests → review.

This is only the **base starting repository** for the course; concrete decisions are made live with the group.

Chat in Polish unless the user asks for another language. Course PRD/ADR exercises and participant-facing project documentation use Polish. Keep filenames and code identifiers in English. The optional teaching library retains its source languages. This is a greenfield scaffold, not an agreed product specification. For a legacy-led course, keep materials separate and work in the original application clone; adapt these instructions to its actual stack and verification commands.

**Key docs** (created during the course — load only when in doubt):
- `docs/PRD.md` — product requirements and acceptance criteria
- `docs/ADR/` — Architecture Decision Records
- `docs/design-guidelines.md` — design system and tokens

---

## Repository Layout

```
app/                 Application built during the course (start: empty scaffold)
assets/              Design tokens, logo, favicon
docs/                PRD, ADR, design system
course-materials/    Notes, scripts, examples, research
```

**Do not read `course-materials/` on your own** (exceptions: `course-materials/exercise-data/gis/` and `course-materials/exercise-data/map-qa/`, the project's input data). It holds teaching examples from this and earlier courses: sample PRDs, ADRs, prompts and agent instructions. They are not requirements or conventions for this app. Do not browse, search or index it during normal work; open a file there only when the user names it or asks for course material.

---

**`README.md` is the participant entry page.** Do not add an update-notes section, changelog or "what's new" list to its top before the course has started. During the course the trainer adds update notes there; add them only when the trainer asks.

---

## Agent Workflow

### Documentation lookup (libraries, APIs, CLIs)
Do not rely on training data for library or API details. Look them up in this order:
1. **CLI tools:** run `<tool> --help` (and `<tool> <subcommand> --help`) on this machine first; the installed version is the source of truth.
2. **Context7:** MCP (`resolve-library-id`, then `query-docs`) when configured; otherwise the Context7 CLI (`npx ctx7@latest`). Query the pinned version.
3. **Web search:** when Context7 is unavailable or has no or outdated results; prefer official documentation, changelogs and PyPI pages.

Name the source and version you relied on in ADRs and task summaries.

### When implementing new or refactoring functionality
1. Read the relevant PRD and ADR files for the affected area.
2. Define the expected behavior from the specification before writing or changing any code.
3. Confirm the actual application checkout and inspect source, build descriptors, call sites and dependencies before proposing commands or APIs. Identify build, test and startup commands from that project, using its wrapper when available; do not assume a framework, build tool or runtime version.
4. Establish missing or ambiguous requirements with the user and record agreed application scope in its PRD before implementation. Routine course-document changes do not need an application PRD or ADR.

### TDD Rules
For every feature and bug fix:
1. Start from the specification, not the existing implementation.
2. Write or extend tests **before** production code.
3. Run the new tests and confirm they fail for the expected reason.
4. Implement the minimum code needed to make them pass.
5. Run the full verification suite for the changed scope.
6. Refactor only while tests stay green.
7. **Manually validate the running application** (see Manual QA below). Automated tests — especially E2E — can produce false passes; a task is not done until the real app has been exercised by hand.

If the area has no suitable test infrastructure yet, add it as part of the task — do not silently skip tests.

Before creating or refreshing a unit/integration mock of an endpoint or database, make a fresh real request/query in an authorized local/test environment using synthetic data. Save the complete response verbatim (HTTP status, headers and body, or database result rows and type/schema information) and derive the mock from that capture, not from documentation that may be stale. Use a response containing no secrets; record its date, target, request/query and relevant service version without credentials. If a safe capture cannot be obtained, report the missing prerequisite instead of inventing a response shape.

For behavior-preserving legacy refactoring, write characterization tests against the original code and get them green before changing it. Assert observable inputs, outputs, state changes and errors rather than private methods or the current class layout. Demonstrate that critical assertions detect a controlled behavioral mutation, then revert that mutation. Existing tests may protect a pure refactor; a new behavior or bug fix still requires Red -> Green -> Refactor.

Investigate production code and fixtures before changing a failing assertion. Do not weaken, disable or delete tests to conceal a defect. Change expected behavior only when the specification supports it, and explain why.

### Manual QA (required after every task that affects the running app)

Use the application's actual runtime and verified commands. The browser flow below applies to web applications; desktop applications need their real UI, and command-line tools need observable CLI checks.

For CLI work, run the actual CLI and inspect its output. For web UI work, use **the Playwright CLI** to drive the real running app like a human tester:

1. Start the app with its verified project command and open it in the browser. Record successful startup separately from compilation and test execution.
2. Take a screenshot of every screen you touched.
3. Exercise the changed GIS flow end-to-end, such as importing a file, querying POIs, selecting a map filter or exporting a report. Test only actual features agreed in the PRD.
4. Verify the flow actually works: correct navigation, correct data displayed, no console errors, Polish UI text.
5. For UI changes, **compare screenshots against the agreed design reference** (`assets/design-tokens.json` and `docs/design-guidelines.md` once created during the design exercise). Verify colors, typography, spacing and controls; ask for the visual decision if no reference has been agreed.
6. Report what you validated (steps + screenshots) in your task summary. If anything looks or behaves wrong, fix it before committing.

### Verification (required before every commit)

Verify only the scope relevant to your change. If the change affects runtime behavior, confirm the app starts correctly.

**Test Strategy:**
| Type | Mocks | Who |
|---|---|---|
| Unit | All deps | be/fe-dev |
| Integration | Only external LLM API | be-dev |
| E2E | NOTHING (real stack) | qa-engineer |

**Verification:** For runtime changes, start the real application and finish with Manual QA. Record compilation/build, test execution and startup as separate checks, including discovery counts and skips. A successful build or E2E run alone does not establish that the app works. Documentation-only changes use diff, link and consistency checks and do not require application startup. Fix errors and warnings introduced by the change; report pre-existing failures without hiding them.

**Env Vars:** No model API key is required for the synthetic GIS starter, PRD or normal Claude Code/Codex CLI use on the provided accounts. `.env.example` contains optional settings for an explicitly selected API exercise; `OPENROUTER_API_KEY` is needed only when that exercise actually calls OpenRouter.

### Map QA data profile
- Refresh the input data profile with `uv run course-materials/exercise-data/map-qa/profile_data.py` (read-only DuckDB queries from `profile.sql`, ~1 min) instead of writing ad-hoc profiling queries.
- The curated summary lives in `reports/map-qa/profile.md` (committed); other files under `reports/` are generated and git-ignored. Update the profile when input data or `profile.sql` changes, and check PRD/ADR assumptions against it.

### Commit Rules
- Never commit directly to `main`; work on a feature branch and open a PR. If the current branch is `main`, create a feature branch before the first commit.
- Commit only after verification passes and the changed scope is in a working state.
- Keep commits focused: one logical change per commit.
- Format: `Area: short summary` (e.g. `Backend:`, `Frontend:`, `Docs:`)
- Do **not** push to remote unless the user explicitly asks.

### Git Worktrees
- Use this checkout by default. Create a worktree only when requested or needed for parallel agent work; ask first when not explicitly requested.
- Remove worktrees with `git worktree remove <path>` and run `git worktree prune` when done.

### Completion Criteria
A task is complete only when:
- Implementation matches the relevant PRD, ADR, and design guidance
- Tests were written first and pass honestly
- Verification for the changed scope passed with no errors or warnings
- Runtime changes passed Manual QA on the actual UI, CLI or API, with screenshots or command/request evidence and the application's own visual reference where applicable; documentation-only work passed its scoped checks
- The commit message is focused and the repository is in a consistent, reviewable state
