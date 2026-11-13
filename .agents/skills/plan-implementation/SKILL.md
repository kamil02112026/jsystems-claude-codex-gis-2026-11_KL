---
name: plan-implementation
description: Create a reviewable implementation plan with one dependency matrix (tasks, PRD/ADR links, owners/models, editable files, verification) from an approved PRD and ADRs, then stop for human review. Use when the user asks to plan an implementation, a vertical slice, a feature or an MVP from PRD/ADR documents, or to prepare work for subagents or CLI agents (Claude Code, Codex, OpenCode). Do not use for small single-file changes or when no PRD/ADR exists yet (write those first).
---

# Implementation plan with a dependency matrix

Produce a plan that a human can review and agents can execute task by task. Planning never authorizes execution, new agents, paid API calls, pushes or merges.

## Inputs (ask only for what is missing or ambiguous)
- Approved PRD and ADRs of THIS application (paths). Course/teaching examples are not requirements.
- The repository's AGENTS.md / CLAUDE.md (TDD, mock and commit rules).
- A data or environment profile if the app depends on data (e.g. `reports/<app>/profile.md`).
- Destination: default `docs/plans/<feature>-implementation-plan.md`.

## Steps
1. **Baseline, verified.** Inspect the real checkout: source tree, build descriptors, entry points, tests, `git status`, tracker. Run the existing test command once. Report what exists and any baseline failure; never assume a framework or command.
2. **Read sources fully** (delegate to a read-only Plan subagent when they are long; you keep the conclusions). Find the exact MVP/slice scope in the PRD and follow it over any summary.
3. **Draft the plan** with the sections below. Link PRD criteria, ADR sections and test IDs; do not copy their content. Missing architecture → "proposed ADR", not an invented assumption.
4. **Verify the draft before saving** — this step is mandatory:
   - every cited test/decision/criterion ID exists in the sources (script a grep over all IDs);
   - scope matches the PRD slice exactly (nothing from later increments);
   - CLI flags/commands match the ADR interface;
   - every data fact quoted in the plan is re-checked with a read-only query;
   - relative links resolve.
   Add a short "Draft verification" table to the plan with the results.
5. **Save as DRAFT**, list unresolved decisions (U1..Un) with a proposed default each, name the first bounded task and the review gate. Stop.

## Plan sections
1. Header: status (DRAFT — awaiting owner review), date, path, branch, source links, "planning does not authorize execution".
2. Verified baseline (table: element, state, evidence/command).
3. Slice scope, explicit out-of-scope, milestones (first milestone must run offline/without paid calls if possible), criteria → tasks mapping.
4. Phases (small, each ends green + commit).
5. **One authoritative matrix**, exactly these columns plus a Status column used as the tracker:
   `| Task | Observable outcome | PRD/ADR links | Prerequisites | Owner/model | Editable files | Verification and handoff | Status |`
   Each row: bounded deliverable, a failing behavioral test first (Red), named test IDs, real commands, one commit boundary.
6. Owners and models: strong orchestrator (architecture, shared contracts, lockfiles, integration, briefs, acceptance, the ONLY committer). Prefer cheap small workers for bounded implementation and test-writing:
   - **Claude Code subagents — Haiku 5.5** for most bounded work (Agent tool, ad hoc brief);
   - **Codex — Sol 6.1** for complicated tasks and code review, **Luna 6** for simple tasks and research;
   - **OpenCode — MiMo-V2.6-Flash** (Xiaomi Token Plan) for simple, well-specified rows.
   Record per row: agent, model, rounds budget, escalation rule. Verify the harness and model ids before the first dispatch; otherwise run the matrix sequentially with one agent.
7. Parallel waves: only rows with independent inputs AND disjoint editable files; max ~3 workers; serialize shared contracts, lockfiles, migrations, integration. One checkout by default; worktree only for same-file parallel edits (follow the repo's worktree convention and ask first).
8. Critical path, shared-file hotspots, failure/rollback (`git revert`, never force-push), smaller fallback.
9. Briefs: compiled just before dispatch in `.agent-briefs/<task>.md` (git-ignored): source excerpts, current contract signatures, exact editable files, concurrent tasks, Red→Green→Refactor steps, test inputs/expected results, commands, escalation conditions. Workers return diffs; no git writes; they cannot accept their own work.
10. Human gates: plan approval, installs/network, every PAID call (state max requests and max USD), push, PR, merge.
11. Unresolved decisions, first bounded task, review gate.

## Headless delegation (include this section in every plan that uses CLI workers)
Run from the repository root; the brief is a file, the worker returns a diff and a short report, never commits. Flags verified with `--help` (Codex 0.167.2, OpenCode 2.2.5, Claude Code 2.1.x on Windows/PowerShell); re-check `--help` after updates.

| Worker | Command (PowerShell) | Notes |
|---|---|---|
| Codex (implementation) | `Get-Content .agent-briefs\T08.md -Raw \| codex exec -C . -m <sol-or-luna-id> -s workspace-write --json -o .agent-briefs\T08.result.md -` | prompt from stdin (`-`); `-s workspace-write` limits writes to the repo; `--json` = JSONL events; `-o` = final message file; `--ephemeral` to skip session files |
| Codex (code review) | `codex exec review` (inside the repo) or `codex exec -m <sol-id> -s read-only "Review the diff main...HEAD against docs/PRD.md and docs/ADR/ ..."` | read-only sandbox for reviews |
| OpenCode | `opencode run -m xiaomi-token-plan-ams/mimo-v2.6-flash --title T09 --format json -f .agent-briefs\T09.md "Execute the attached brief."` | `-f` attaches the brief; use `--auto` ONLY with a project `opencode.jsonc` that denies push/force/main (see course `agent-configs/opencode`) |
| Claude Code | `claude -p (Get-Content .agent-briefs\T10.md -Raw) --model haiku --output-format json --permission-mode acceptEdits --allowedTools "Read,Edit,Write,Bash(uv run *)"` | or the Agent tool from the orchestrator session (preferred: shared context, no extra login) |

Rules for headless runs:
- Model ids differ per tool and account: confirm them once (`opencode models`, Codex `/model` or config) and write the exact ids into the plan.
- One worker per row, disjoint editable files, at most ~3 in parallel; the orchestrator waits for all JSON results before integrating.
- Never pass secrets in prompts or briefs; workers read env vars by NAME only.
- No auto-approve flags (`--auto`, `--dangerously-skip-permissions`, `danger-full-access`) without deny rules for push/main/secrets.
- The orchestrator re-runs the row's tests and reads the diff before committing; failed or out-of-scope diffs are discarded (`git checkout -- <files>` only for the worker's files).

## One-flow execution (`/goal` over the whole plan)
- Order phases by dependency and risk: contracts and scaffolding → offline core → integrations behind captures → paid/real runs → reporting/UI → hardening and review.
- Put an **owner pre-authorization block** at the top of the plan (max USD per run and total, max requests, allowed pushes, branch name). `/goal` may pass a gate only if it is pre-authorized there; anything else stops and asks.
- Every phase ends green and committed, so a stopped goal can resume from the Status column.

## Execution lessons (put the relevant ones into the plan's rules)
- **Consent is per gate and per run.** `/goal` or "implement the plan" is not consent to spend money or push. For a cache check use a flag that guarantees 0 requests (e.g. `--cache-only` / `--max-images 0`) — never "the same command again".
- **Real API before mocks.** Capture real responses (dry-run first, hard request/USD cap, no retries, secrets redacted); derive every HTTP mock from captures. Docs were wrong in practice (image size limits, BYOK cost fields).
- **Verify worker output yourself**: re-run tests, read the diff, check the spec. Workers find spec bugs — fix the spec (ADR) with the code.
- **E2E in a clean environment**: strip `PYTHONUTF8`/`PYTHONIOENCODING`-style overrides and test a real process with closed stdin; Windows pipes and the NUL device behave differently from your session.
- **Independent review in a fresh context** before calling it done; fix confirmed findings with regression tests.
- **Fork hygiene**: pass full PR URLs or set `gh repo set-default <fork>`; block pushes to the upstream remote you must not change.
- **Do not set `/goal` past a human gate** — scope it to "up to gate Gx".

## Output
The saved plan path, the draft-verification table, unresolved decisions with defaults, the first bounded task and the review gate. Then wait for the owner.
