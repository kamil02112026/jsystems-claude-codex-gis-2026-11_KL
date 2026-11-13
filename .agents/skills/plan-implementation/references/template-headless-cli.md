# Template B — orchestrator + headless CLI agents

Use when rows go to other CLI agents (Codex, OpenCode, another `claude -p`) as separate processes, e.g. to use cheaper models or to compare agents. Requires each CLI to be installed and logged in — verify before the first dispatch.

## Execution model
- **Orchestrator**: one interactive session; writes briefs, dispatches, integrates, the ONLY committer.
- **Workers**: headless processes started from the repo root; input = a brief file in `.agent-briefs/<task>.md` (git-ignored); output = a diff in the working tree + a result file. No git writes.
- Model ids differ per tool and account: confirm once (`opencode models`, Codex `/model` or config, `claude --help`) and write the exact ids into the plan.

Suggested defaults (confirm with the owner):
- Codex — Sol 6.1 for complicated rows and code review, Luna 6 for simple rows and research;
- OpenCode — MiMo-V2.6-Flash (Xiaomi Token Plan) for simple, well-specified rows;
- Claude Code headless — Haiku for bounded rows.

## Command table (verified with `--help`: Codex 0.167.2, OpenCode 2.2.5, Claude Code 2.1.x, Windows/PowerShell, 2026-11-13 — re-check after updates)

| Worker | Command (PowerShell) | Notes |
|---|---|---|
| Codex (implementation) | `Get-Content .agent-briefs\T08.md -Raw \| codex exec -C . -m <id> -s workspace-write --json -o .agent-briefs\T08.result.md -` | prompt from stdin (`-`); `-s workspace-write` limits writes to the repo; `--json` = JSONL events; `-o` = final message; `--ephemeral` skips session files |
| Codex (review) | `codex exec review` or `codex exec -m <id> -s read-only "Review main...HEAD against docs/PRD.md and docs/ADR/ ..."` | read-only sandbox |
| OpenCode | `opencode run -m xiaomi-token-plan-ams/mimo-v2.6-flash --title T09 --format json -f .agent-briefs\T09.md "Execute the attached brief."` | `--auto` ONLY with a project `opencode.jsonc` that denies push/force/main |
| Claude Code | `claude -p (Get-Content .agent-briefs\T10.md -Raw) --model haiku --output-format json --permission-mode acceptEdits --allowedTools "Read,Edit,Write,Bash(uv run *)"` | narrow `--allowedTools`; no `--dangerously-skip-permissions` |

## Plan sections specific to this template

```markdown
## Delegowanie headless
| Wiersz | Narzędzie | Model (dokładne id) | Brief | Plik wyniku | Sandbox / uprawnienia | Budżet rund |
|---|---|---|---|---|---|---|
| T08 | codex exec | <id> | .agent-briefs/T08.md | .agent-briefs/T08.result.md | workspace-write | 2 |
```

## Rules
- One worker per row, disjoint editable files, at most ~3 in parallel; wait for all result files before integrating.
- Never put secrets in prompts or briefs; workers read env vars by NAME only.
- No auto-approve flags (`--auto`, `--dangerously-skip-permissions`, `danger-full-access`) without deny rules for push/main/secrets.
- Integration: re-run the row's tests, read the diff, check the spec; discard failed or out-of-scope diffs with `git checkout -- <worker's files>` only.
- A failed CLI (not installed, not logged in, unknown model id) → the row falls back to Template A or runs sequentially in the orchestrator; record it in Status.
