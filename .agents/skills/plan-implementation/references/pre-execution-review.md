# Pre-execution review (before the first task runs)

Run this after the owner reviewed the DRAFT and before any task is executed (also before `/goal`). Planning and review never authorize execution.

## Who reviews
A fresh context that did not write the plan:
- Claude Code: a read-only `Plan` or `Explore` subagent, or `/code-review` on the plan diff;
- Codex: `codex exec -s read-only -m <review-model> "<prompt below>"` (or `codex exec review`);
- give it the file paths, not your conclusions.

Prompt skeleton: "Review `<plan>` against `AGENTS.md`, `docs/PRD.md`, `docs/ADR/*.md`. Report only concrete findings with file:line, severity (blocker/major/minor) and a proposed fix. Do not edit files."

## Checklist

### AGENTS.md / CLAUDE.md
- [ ] TDD order, mock-from-capture rule, Manual QA and commit format appear as rules in the plan.
- [ ] Branch rule (no commits to `main`), push/PR rules, worktree convention match the plan.
- [ ] Documentation language and verification commands match.

### PRD
- [ ] The plan's slice equals the PRD's MVP/increment exactly — nothing from later increments, nothing missing.
- [ ] Every acceptance criterion in scope maps to at least one task and one test.
- [ ] PRD contradictions found are listed as U-items (not silently resolved).

### ADR
- [ ] Every cited decision/section ID exists; CLI flags, contracts, versions and file paths match the ADRs.
- [ ] Missing architecture is a "proposed ADR" task, not an assumption inside a row.
- [ ] Decisions with status `Proposed` are not treated as `Accepted`.

### Plan file
- [ ] Exactly one authoritative matrix; Status column present; every row has a Red test, editable files, a real command and one commit boundary.
- [ ] Parallel waves have disjoint editable files; shared contracts/lockfiles serialized.
- [ ] Every paid call, install, network download, remote change, push, PR and merge sits behind a named gate.
- [ ] Data facts re-checked with a read-only query; external facts name source + version.
- [ ] Relative links resolve (script it); every cited ID exists (grep).
- [ ] Each item is labelled agreed / proposed / assumption.

## Output
Add a "Pre-execution review" table to the plan (`# | finding | severity | file:line | resolution`), fix blockers in the plan (or in PRD/ADR with the owner's consent), and set status to `APPROVED <date>` only after the owner says so.
