# Lessons learned (mistakes a plan must prevent)

Each lesson names its source. Copy the ones relevant to the current plan into its "Rules" section as concrete rules, not as history. Append new lessons after each session analysis (keep: lesson → rule for the plan → source).

## Planning and specification

| Lesson | Rule to put into the plan | Source |
|---|---|---|
| Decisions depending on data were made while the data profile was missing. | Data-dependent decisions are `conditional` until the profile exists; the profile refresh is task 0. | Claude `bdff53af` (ADR session, 2026-11-03) |
| The agent's own recommendations were treated as accepted after "do all 3 steps". | Mark every item as **agreed** (owner said so), **proposed** (default awaiting approval) or **assumption**. Only "agreed" items drive tasks without a gate. | `bdff53af` |
| A docs-only review found 7 contradictions in the PRD after the ADRs were written. | Run the pre-execution review (`pre-execution-review.md`) on PRD + ADR + AGENTS.md + plan before the first task; unresolved conflicts become U-items. | `bdff53af` |
| Skill defaults (English) conflicted with the repo language rule. | Write the plan in the repository's documentation language from AGENTS.md; identifiers and filenames in English. | `bdff53af` ("Pisz po polsku (zasada AGENTS.md)") |
| Mermaid diagrams were only checked for closed fences, not rendered. | If the plan contains diagrams, render or lint them, or state that they were not rendered. | `bdff53af` |
| Docs summarised from memory were wrong (image size limits, BYOK cost fields); model pages returned 404. | Every external fact in the plan names its source and version (`--help`, Context7 id, URL + date); unknowns stay "unknown", never invented. | `bdff53af`, MVP execution 2026-11-12 |

## Git, GitHub and permissions

| Lesson | Rule to put into the plan | Source |
|---|---|---|
| First commit landed on `main`, then had to be moved with `reset --soft`. | Header names the feature branch; task 0 creates/checks it before the first commit. | `bdff53af` |
| `gh` on a fork defaulted to the upstream repo; `/code-review` reviewed the wrong PR. | Use full PR URLs or `--repo owner/name`; run `gh repo set-default <fork>` once; name the target repo in the header. | `bdff53af` |
| Chained `git remote add && git push` was denied; the same push alone passed. | Give gated commands as single commands, one per line; put long PR bodies in a file (`--body-file`). | `bdff53af` |
| Auto-mode classifier blocked "Remote Repoint" and "Merge Without Review". | Remote changes, push, PR creation and merge are human gates; the plan lists the exact command for the owner (`! <command>`). | `bdff53af` |
| GitHub/environment setup crowded out the real work. | Environment and publishing are separate phases (P0 setup, last phase publish), never mixed into implementation rows. | `bdff53af` |

## Execution (from the MVP/v1 runs)

| Lesson | Rule to put into the plan | Source |
|---|---|---|
| `/goal` or "implement the plan" was read as consent to spend money or push. | Consent is per gate and per run; an owner pre-authorization block (max USD per run and total, max requests, pushes, branch) at the top; `/goal` stops at any gate not pre-authorized. | MVP/v1 plan execution, 2026-11-12/13 |
| "Run the same command again" re-spent money instead of reading the cache. | Cache checks use a flag that guarantees 0 requests (`--cache-only`, `--max-images 0`). | MVP execution |
| Mocks from documentation had the wrong shape. | Real capture first (dry-run, request/USD cap, no retries, secrets redacted); mocks derived only from captures. | MVP execution |
| Worker output was accepted on its own report. | Orchestrator re-runs the row's tests and reads the diff; workers never commit or accept their own work. | MVP execution |
| E2E passed in the agent shell but failed for a real user process (UTF-8 env vars, closed stdin, Windows NUL). | E2E runs a real process in a clean env (strip `PYTHONUTF8`/`PYTHONIOENCODING`, closed stdin). | MVP execution |
| Some rows could not run in the session (Databricks access). | A row that cannot run gets `blocked:<reason>` in Status and the run continues with independent rows. | v1 execution (`e272621`) |
