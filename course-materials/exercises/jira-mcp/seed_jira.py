"""LEGACY trainer-only flat-ticket seeder, not a v2 seed-spec.json importer.

Does not recreate epics, parents, subtasks or v2 workflow. Do not use it to
regenerate the current snapshot. Dry-run is offline; writes require --apply.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

from jira_read import JiraReader, Settings


DATA = Path(__file__).resolve().parents[2] / "exercise-data/jira-jobs/tickets.json"
MAP_PATH = DATA.with_name("seed-map.json")


def paragraph(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def source_label(ticket):
    return "course-source-" + ticket["key"].lower()


def issue_payload(ticket, project, issue_type):
    fields = ticket["fields"]
    description = deepcopy(fields["description"])
    description["content"].append(paragraph(f'Źródło kursowe: {ticket["key"]}; utworzono pierwotnie: {fields["created"]}; status źródłowy: {fields["status"]["name"]}. Klucze MAPJOB w oryginalnym tekście odnoszą się do zbioru źródłowego; bieżące klucze wskazuje seed-map.json.'))
    return {"fields": {"project": {"key": project}, "issuetype": {"name": issue_type}, "summary": fields["summary"], "description": description, "labels": list(dict.fromkeys(fields["labels"] + ["course-seed", source_label(ticket)]))}}


def comment_payload(comment):
    body = deepcopy(comment["body"])
    body["content"].append(paragraph(f'Źródło komentarza: {comment["id"]}; {comment["created"]}; {comment["author"]["displayName"]}.'))
    return {"body": body}


def existing_key(ticket, issues):
    candidates = [i for i in issues if i["fields"]["summary"] == ticket["fields"]["summary"] and "course-seed" in i["fields"].get("labels", [])]
    exact = [i for i in candidates if source_label(ticket) in i["fields"].get("labels", [])]
    legacy = [i for i in candidates if not any(label.startswith("course-source-") for label in i["fields"].get("labels", []))]
    matches = exact or legacy
    if len(matches) > 1:
        raise ValueError(f'Ambiguous seeded summary for {ticket["key"]}; inspect Jira manually')
    return matches[0]["key"] if matches else None


def link_payloads(tickets, mapping):
    result, seen = [], set()
    for ticket in tickets:
        for link in ticket["fields"]["issuelinks"]:
            outward = "outwardIssue" in link
            other = link["outwardIssue" if outward else "inwardIssue"]["key"]
            source, target = (ticket["key"], other) if outward else (other, ticket["key"])
            identity = (link["type"]["name"], source, target)
            if identity not in seen:
                result.append({"type": {"name": identity[0]}, "inwardIssue": {"key": mapping[source]}, "outwardIssue": {"key": mapping[target]}})
                seen.add(identity)
    return result


class SeedClient(JiraReader):
    """Explicit separate write client, never used by participant CLI."""

    def request(self, method, path, **kwargs):
        write = method == "POST" and re.fullmatch(r"/rest/api/3/(issue|issue/[A-Z][A-Z0-9_]*-[0-9]+/comment|issueLink)", path)
        if write or (method == "GET" and path == "/rest/api/3/issueLinkType"):
            return self._send(method, path, **kwargs)
        return super().request(method, path, **kwargs)


def save_mapping(path, mapping):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def apply_seed(api, tickets, project, issue_type, map_path):
    existing = api.search(f'project = "{project}" AND labels = "course-seed"', fields="summary,labels")
    # Resolve every identity before creating anything; equal titles must not collapse.
    mapping = {t["key"]: existing_key(t, existing) for t in tickets}
    selected = [key for key in mapping.values() if key]
    if len(selected) != len(set(selected)):
        raise ValueError("Ambiguous source mapping; equal summaries need course-source labels")
    checkpoint = json.loads(map_path.read_text(encoding="utf-8")) if map_path.exists() else {}
    for ticket in tickets:
        old = ticket["key"]
        if not mapping[old] and old in checkpoint:
            # Search indexing can lag behind a successful create. Verify the checkpoint directly.
            candidate = api.get_issue(checkpoint[old])
            if existing_key(ticket, [candidate]) == checkpoint[old] and candidate["fields"].get("project", {}).get("key", project) == project:
                mapping[old] = checkpoint[old]
            else:
                raise ValueError(f"Checkpoint mismatch for {old}; inspect seed-map.json")
        if not mapping[old]:
            mapping[old] = api.request("POST", "/rest/api/3/issue", json=issue_payload(ticket, project, issue_type))["key"]
        # Persist each successful create before comments or links, to support resuming.
        save_mapping(map_path, {**checkpoint, **{k: v for k, v in mapping.items() if v}})
        expected = sorted(ticket["fields"]["comment"]["comments"], key=lambda c: (c["created"], c["id"]))
        if expected:
            bodies = [c["body"] for c in api.comments(mapping[old])]
            for comment in expected:
                payload = comment_payload(comment)
                if payload["body"] not in bodies:
                    api.request("POST", f'/rest/api/3/issue/{mapping[old]}/comment', json=payload)
                    bodies.append(payload["body"])
    available = api.request("GET", "/rest/api/3/issueLinkType")["issueLinkTypes"]
    source_types = {link["type"]["name"]: link["type"] for t in tickets for link in t["fields"]["issuelinks"]}
    for payload in link_payloads(tickets, mapping):
        original_type = source_types[payload["type"]["name"]]
        matches = [t for t in available if t["name"] == original_type["name"] or (t.get("inward"), t.get("outward")) == (original_type["inward"], original_type["outward"])]
        if len(matches) != 1:
            raise ValueError("Required issue link type unavailable or ambiguous; configure it in Jira")
        payload["type"] = {"name": matches[0]["name"]}
        source, target = payload["inwardIssue"]["key"], payload["outwardIssue"]["key"]
        present = api.get_issue(source)["fields"].get("issuelinks", [])
        if not any(link["type"]["name"] == payload["type"]["name"] and link.get("outwardIssue", {}).get("key") == target for link in present):
            api.request("POST", "/rest/api/3/issueLink", json=payload)
    return mapping


def main(argv=None, *, env=None, transport=None, map_path=MAP_PATH):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="MAPJOB")
    parser.add_argument("--issue-type", default="Task")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env(env)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", args.project):
            raise ValueError("Invalid --project key")
        tickets = json.loads(DATA.read_text(encoding="utf-8"))["issues"]
        if args.apply:
            with SeedClient(settings, transport=transport) as api:
                mapping = apply_seed(api, tickets, args.project, args.issue_type, map_path)
        else:
            print(f"DRY RUN (offline): {len(tickets)} issues, {sum(len(t['fields']['comment']['comments']) for t in tickets)} comments; labels include course-seed.")
            print("Existing Jira summaries, source markers and checkpoint will be checked only with --apply.")
            for ticket in tickets:
                fields = issue_payload(ticket, args.project, args.issue_type)["fields"]
                print(f'{ticket["key"]}: {fields["summary"]} | {args.issue_type} | ADF + source footer | {len(fields["labels"])} labels')
            mapping = {t["key"]: "(assigned on --apply)" for t in tickets}
            print(f"Planned structural links: {len(link_payloads(tickets, mapping))}")
        print("old key -> new key")
        for old, new in mapping.items():
            print(f"{old} -> {new}")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error) if isinstance(error, ValueError) else "Seed failed; inspect local input/checkpoint and Jira configuration", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
