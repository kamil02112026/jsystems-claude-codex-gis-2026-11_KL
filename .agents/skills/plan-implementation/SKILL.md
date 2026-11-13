---
name: plan-implementation
description: Create a reviewable implementation plan with one dependency matrix (tasks, PRD/ADR links, owners/models, editable files, verification) from an approved PRD and ADRs, using lessons from earlier Claude/Codex sessions (by session ID), then run a pre-execution review of AGENTS.md, PRD, ADRs and the plan and stop for the owner. Two execution templates - in-session subagents only, or headless CLI agents (Codex, OpenCode, claude -p). Use when the user asks to plan an implementation, a vertical slice, a feature or an MVP, to prepare work for subagents or CLI agents, or to review a plan before running it. Do not use for single-file changes or when no PRD/ADR exists yet (write those first).
---

# Implementation plan with a dependency matrix

Produce a plan a human can review and agents can execute row by row. **Planning never authorizes execution**, new agents, paid API calls, installs, pushes or merges.

## Inputs — ask when missing (question mode)
Required: PRD and ADR paths of THIS application; AGENTS.md/CLAUDE.md; target slice (MVP / increment / feature); execution template (A or B); branch; destination (default `docs/plans/<feature>-implementation-plan.md`). Optional: session IDs with history; data profile (e.g. `reports/<app>/profile.md`); budget limits.

- Read what you can find first; ask only about what is still missing or contradictory.
- Ask in one batch, max 4 questions, each with a recommended default (Claude Code: `AskUserQuestion`; Codex: a numbered list in chat). Typical: slice scope, template A/B, session IDs to learn from, budget/gates.
- **Blocking** gaps (no PRD/ADR, unknown slice) → stop and ask. **Non-blocking** gaps → U1..Un with a proposed default; never act on them as if agreed.
- Label every decision in the plan: **agreed** (owner said so) / **proposed** / **assumption**. Your own recommendation is never "agreed".

## Steps
1. **Learn from history** (when the user gives session IDs or asks to avoid earlier mistakes):
   `python -I .agents/skills/plan-implementation/scripts/session_history.py <session-id>` (Claude Code and Codex transcripts; `--all-text` adds assistant text). Read user corrections, interruptions, denials and errors. Report briefly what the session actually produced — it may not be the one where a plan was written; say so instead of guessing. The session may still be running: treat its tail as incomplete. Then read `references/lessons-learned.md`, append new lessons there (lesson → rule → source ID), and copy the relevant rules into the plan.
2. **Baseline, verified.** Inspect the real checkout: tree, build descriptors, entry points, tests, `git status`, current branch, remotes (`gh repo set-default` for forks). Run the existing test command once. Report baseline failures; never assume a framework or command.
3. **Read sources fully** (PRD, all ADRs, AGENTS.md, data profile; delegate long reads to a read-only subagent and keep the conclusions). Follow the exact slice in the PRD over any summary. Missing architecture → "proposed ADR" task. Data-dependent decisions without a profile → `conditional`.
4. **Choose the template** (ask if not given):
   - **A — subagents only** → `references/template-subagents.md`
   - **B — headless CLI agents** → `references/template-headless-cli.md`
   Without a working harness/model ids, fall back to sequential execution by one agent.
5. **Draft the plan** (sections below), in the repository's documentation language from AGENTS.md. Link PRD criteria, ADR sections and test IDs; do not copy their content.
6. **Verify the draft** (mandatory): every cited ID exists (script a grep); scope equals the PRD slice; CLI flags/commands match ADRs and `--help`; data facts re-checked read-only; relative links resolve. Add a "Draft verification" table.
7. **Save as DRAFT and stop.** Output the path, verification table, U-items with defaults, the first bounded task and the review gate.
8. **Pre-execution review** — before the first task runs (also before `/goal`), on the owner's go: follow `references/pre-execution-review.md` (fresh-context reviewer over AGENTS.md, PRD, ADRs and the plan). Fix blockers, add the review table, set `APPROVED <date>` only when the owner says so.

## Plan sections
0. Owner pre-authorization (max USD per run and total, max requests, allowed pushes, branch; empty = no consent).
1. Header: status (DRAFT — awaiting owner review), date, path, branch, target repo, source links, "planning does not authorize execution", precedence (PRD business, ADR technical).
2. Verified baseline (element | state | evidence/command).
3. Scope, explicit out-of-scope, milestones (first one offline / no paid calls if possible), criteria → tasks map.
4. Phases: P0 setup/environment, …, last phase publish (push/PR). Each phase ends green + committed.
5. **One authoritative matrix** — exactly these columns:
   `| Task | Observable outcome | PRD/ADR links | Prerequisites | Owner/model | Editable files | Verification and handoff | Status |`
   Each row: bounded deliverable, a failing behavioral test first (Red), test IDs, real commands, one commit boundary. Status values: `todo`, `in-progress`, `done <sha>`, `blocked:<reason>`.
6. Owners, models and parallel waves — from the chosen template.
7. Critical path, shared-file hotspots, failure/rollback (`git revert`, never force-push), smaller fallback.
8. Briefs: compiled just before dispatch into `.agent-briefs/<task>.md` (git-ignored) — source excerpts, contract signatures, exact editable files, concurrent tasks, Red→Green→Refactor steps, test inputs/expected results, commands, escalation conditions.
9. Rules: the relevant lessons from `references/lessons-learned.md` as concrete rules.
10. Human gates: plan approval, installs/network, every paid call (max requests, max USD), remote changes, push, PR, merge — each with the exact single command for the owner.
11. Unresolved decisions (U1..Un, proposed default each), draft verification, pre-execution review (filled in step 8), first bounded task, review gate.

## `/goal` over the whole plan
Order: contracts/scaffolding → offline core → integrations behind captures → paid/real runs → reporting/UI → hardening and review. Scope a goal "up to gate Gx"; it may pass only gates pre-authorized in section 0. Every phase ends committed, so a stopped goal resumes from the Status column.
