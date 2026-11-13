"""Digest a Claude Code or Codex CLI session transcript by session ID.

Prints what matters for lessons learned: user messages (corrections),
interruptions, rejected/denied tool calls, tool errors, compaction summaries,
files written, commits/pushes, and subagent transcripts. Read-only.

Usage (from the repository root):
    python -I .agents/skills/plan-implementation/scripts/session_history.py <session-id> [--max 600] [--all-text]

Search roots: $CLAUDE_CONFIG_DIR or ~/.claude (projects/*/<id>.jsonl + subagents/),
$CODEX_HOME or ~/.codex (sessions/**/rollout-*<id>.jsonl). Override with --root.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

DENY_MARKERS = ("doesn't want to proceed", "has been denied", "denied by the Claude Code auto mode", "Permission for this action")
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "apply_patch"}


def roots(extra: list[str]) -> list[Path]:
    out = [Path(p) for p in extra]
    for env, default in (("CLAUDE_CONFIG_DIR", "~/.claude"), ("CODEX_HOME", "~/.codex")):
        out.append(Path(os.environ.get(env) or default).expanduser())
        out.append(Path(default).expanduser())
    seen, uniq = set(), []
    for r in out:
        if r.exists() and r.resolve() not in seen:
            seen.add(r.resolve())
            uniq.append(r)
    return uniq


def find(session_id: str, search: list[Path]) -> list[Path]:
    hits: list[Path] = []
    for r in search:
        hits += list(r.glob(f"projects/*/{session_id}.jsonl"))
        hits += sorted(r.glob(f"projects/*/{session_id}/subagents/*.jsonl"))
        hits += list(r.glob(f"sessions/**/*{session_id}*.jsonl"))
    return hits


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(x.get("text", "")) for x in content if isinstance(x, dict) and x.get("type") in ("text", "input_text", "output_text"))
    return ""


def short(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 3] + "..."


def digest(path: Path, n: int, all_text: bool) -> None:
    print(f"\n######## {path}  ({path.stat().st_size // 1024} KiB)")
    writes: dict[str, int] = {}
    errors = 0
    for raw in path.open(encoding="utf-8", errors="replace"):
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ts = str(d.get("timestamp", ""))[5:16]
        # --- Claude Code format
        if d.get("type") in ("user", "assistant") and isinstance(d.get("message"), dict):
            content = d["message"].get("content")
            if d["type"] == "user":
                t = text_of(content).strip()
                if t and not t.startswith(("<system-reminder", "<local-command", "Base directory for this skill")):
                    tag = "SUMMARY" if "continued from a previous conversation" in t else "USER"
                    print(f"[{ts}] {tag}: {short(t, n * (4 if tag == 'SUMMARY' else 1))}")
                for x in content if isinstance(content, list) else []:
                    if isinstance(x, dict) and x.get("type") == "tool_result" and x.get("is_error"):
                        errors += 1
                        body = short(text_of(x.get("content")) or json.dumps(x.get("content")), 300)
                        kind = "DENIED" if any(m in body for m in DENY_MARKERS) else "TOOL_ERROR"
                        print(f"[{ts}] {kind}: {body}")
            else:
                for x in content if isinstance(content, list) else []:
                    if not isinstance(x, dict):
                        continue
                    if x.get("type") == "tool_use":
                        name, inp = x.get("name"), x.get("input", {})
                        if name in WRITE_TOOLS:
                            fp = inp.get("file_path", "?")
                            writes[fp] = writes.get(fp, 0) + 1
                        elif name == "Bash" and any(k in inp.get("command", "") for k in ("git commit", "git push", "gh pr", "git reset", "git remote")):
                            print(f"[{ts}] GIT: {short(inp['command'], 200)}")
                        elif name in ("AskUserQuestion", "Agent", "Skill", "ExitPlanMode"):
                            print(f"[{ts}] {name}: {short(json.dumps(inp, ensure_ascii=False), 260)}")
                    elif all_text and x.get("type") == "text":
                        print(f"[{ts}] ASSISTANT: {short(x.get('text', ''), n)}")
            continue
        # --- Codex CLI format
        p = d.get("payload") or {}
        if d.get("type") == "response_item" and p.get("type") == "message":
            t = text_of(p.get("content")).strip()
            if p.get("role") == "user" and t and not t.startswith(("<environment_context", "# AGENTS.md", "<permissions", "<user_instructions")):
                print(f"[{ts}] USER: {short(t, n)}")
            elif p.get("role") == "assistant" and all_text and t:
                print(f"[{ts}] ASSISTANT: {short(t, n)}")
        elif d.get("type") == "response_item" and p.get("type") in ("function_call", "custom_tool_call"):
            args = str(p.get("arguments") or p.get("input") or "")
            if any(k in args for k in ("git commit", "git push", "gh pr", "apply_patch")):
                print(f"[{ts}] CALL: {short(args, 200)}")
        elif d.get("type") == "response_item" and p.get("type") in ("function_call_output", "custom_tool_call_output"):
            out = str(p.get("output", ""))
            if re.search(r'exit_code\\*"?:\s*[1-9]|Exit code: [1-9]|rejected by (the )?user|denied', out):
                errors += 1
                print(f"[{ts}] TOOL_ERROR: {short(out, 300)}")
    if writes:
        print("FILES WRITTEN: " + "; ".join(f"{k} x{v}" for k, v in sorted(writes.items(), key=lambda kv: -kv[1])))
    print(f"ERRORS/DENIALS: {errors}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session_id")
    ap.add_argument("--root", action="append", default=[], help="extra search root (repeatable)")
    ap.add_argument("--max", type=int, default=600, help="max chars per message")
    ap.add_argument("--all-text", action="store_true", help="also print assistant text")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    search = roots(a.root)
    files = find(a.session_id, search)
    if not files:
        print(f"Session {a.session_id} not found under: " + ", ".join(map(str, search)), file=sys.stderr)
        return 1
    for f in files:
        digest(f, a.max, a.all_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
