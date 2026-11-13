# Template A — orchestrator + in-session subagents only

Use when one agent session (Claude Code or Codex) runs the whole plan and delegates bounded rows to its own subagents. No extra CLI logins, no external processes. Best for: courses, small teams, plans with many shared files.

## Execution model
- **Orchestrator** (strong model, the session itself): shared contracts, lockfiles, integration, briefs, acceptance, the ONLY committer.
- **Workers**: in-session subagents with a self-contained brief.
  - Claude Code: `Agent` tool, `subagent_type: general-purpose` with `model: haiku` for bounded implementation/test-writing; `Plan`/`Explore` (read-only) for research and review.
  - Codex: its built-in subagent/spawn mechanism if enabled in this version (check `codex --help` / `/help`); otherwise run rows sequentially.
- Subagents edit only the files listed in their row and return a short report; they do not commit, push or install.

## Plan sections specific to this template
Add to the generic sections from SKILL.md:

```markdown
## Właściciele i modele (Template A — subagenci)
| Rola | Narzędzie | Model | Zakres | Budżet rund | Eskalacja |
|---|---|---|---|---|---|
| Orkiestrator | Claude Code (ta sesja) | <strong model id> | kontrakty, integracja, akceptacja, commity | — | właściciel |
| Wykonawca | Agent tool, general-purpose | haiku | wiersze T.. o ograniczonym zakresie | 2 | po 2 nieudanych rundach wiersz wraca do orkiestratora |
| Recenzent | Agent tool, Plan (read-only) | <strong model id> | review fazy przed commitem | 1 | ustalenia → nowe wiersze |

## Fale równoległe
| Fala | Wiersze | Rozłączne pliki? | Warunek startu |
|---|---|---|---|
| W1 | T03, T04, T05 | tak | T02 (kontrakt) zielony i zacommitowany |
```

## Rules
- At most ~3 subagents in parallel, one checkout; worktree only for same-file parallel edits (ask first; repo convention `../<repo>-worktrees/<branch>`).
- Subagent brief = row + exact editable files + current contract signatures + Red→Green steps + commands + escalation conditions. Workers do not see the conversation — the brief is everything.
- The orchestrator re-runs the row's tests, reads the diff, then commits (`Area: summary (Txx)`).
- Fork for parallel *thinking*, fresh subagent for an independent *review*.
