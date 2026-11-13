"""Seeder behavior against explicit synthetic transport scenarios; no network."""

import copy
import json
from pathlib import Path

import httpx
import pytest

import seed_jira as seed
from test_jira_read import ENV


DATA = Path(__file__).resolve().parents[2] / "exercise-data/jira-jobs/tickets.json"


@pytest.fixture
def tickets():
    return json.loads(DATA.read_text(encoding="utf-8"))["issues"]


def test_payload_keeps_adf_labels_and_original_date(tickets):
    original = copy.deepcopy(tickets[0])
    payload = seed.issue_payload(tickets[0], "MAPJOB", "Task")
    fields = payload["fields"]
    assert fields["project"] == {"key": "MAPJOB"} and fields["issuetype"] == {"name": "Task"}
    assert fields["description"]["version"] == 1
    assert fields["description"]["content"][:len(original["fields"]["description"]["content"])] == original["fields"]["description"]["content"]
    assert "course-seed" in fields["labels"]
    assert set(original["fields"]["labels"]) <= set(fields["labels"])
    assert original["fields"]["created"] in json.dumps(fields["description"])
    assert "created" not in fields and tickets[0] == original


def test_key_mapping_and_link_direction(tickets):
    mapping = {t["key"]: f"MAPJOB-{n}" for n, t in enumerate(tickets, 1)}
    links = seed.link_payloads(tickets, mapping)
    assert len(links) == 12
    assert {link['type']['name'] for link in links} == {'Duplicate', 'Relates', 'Blocks'}
    for ticket in tickets:
        for link in ticket['fields']['issuelinks']:
            if 'outwardIssue' in link:
                assert {'type': {'name': link['type']['name']}, 'inwardIssue': {'key': mapping[ticket['key']]}, 'outwardIssue': {'key': mapping[link['outwardIssue']['key']]}} in links


def test_idempotency_does_not_collapse_equal_summaries(tickets):
    same = copy.deepcopy(tickets[:2])
    same[1]["fields"]["summary"] = same[0]["fields"]["summary"]
    existing = [{"key": f"MAPJOB-{n}", "fields": seed.issue_payload(t, "MAPJOB", "Task")["fields"]} for n, t in enumerate(same, 1)]
    assert seed.existing_key(same[0], existing) == "MAPJOB-1"
    assert seed.existing_key(same[1], existing) == "MAPJOB-2"
    assert seed.existing_key(same[0], []) is None


def test_ambiguous_summary_stops(tickets):
    fields = {"summary": tickets[0]["fields"]["summary"], "labels": ["course-seed"]}
    with pytest.raises(ValueError, match="Ambiguous"):
        seed.existing_key(tickets[0], [{"key": "MAPJOB-1", "fields": fields}, {"key": "MAPJOB-2", "fields": fields}])


def test_dry_run_never_touches_network_or_map(tmp_path, capsys, tickets):
    def forbidden(request):
        pytest.fail("Dry-run must be offline")
    target = tmp_path / "seed-map.json"
    assert seed.main([], env=ENV, transport=httpx.MockTransport(forbidden), map_path=target) == 0
    assert not target.exists()
    output = capsys.readouterr().out
    assert "40" in output and "TEST-1" in output and "course-seed" in output
    assert "synthetic-token" not in output


def test_missing_environment_even_in_dry_run(capsys):
    assert seed.main([], env={}) == 1
    error = capsys.readouterr().err
    assert all(name in error for name in ENV)


def test_apply_resumes_comments_and_links_without_duplicates(tmp_path, tickets):
    records, comments, links, mutations = {}, {}, [], []
    def handle(request):
        path = request.url.path
        if request.method == "GET" and path.endswith("search/jql"):
            return httpx.Response(200, json={"issues": list(records.values()), "isLast": True})
        if request.method == "GET" and path.endswith("issueLinkType"):
            return httpx.Response(200, json={"issueLinkTypes": [{"name": "Relates", "inward": "relates to", "outward": "relates to"}, {"name": "Blocks", "inward": "is blocked by", "outward": "blocks"}, {"name": "Duplicate", "inward": "is duplicated by", "outward": "duplicates"}]})
        if request.method == "POST":
            payload = json.loads(request.content)
            mutations.append(path)
            if path.endswith("/issue"):
                key = f"MAPJOB-{len(records)+1}"
                records[key] = {"key": key, "fields": {**payload["fields"], "issuelinks": []}}
                return httpx.Response(201, json={"key": key})
            if path.endswith("/comment"):
                key = path.split("/")[-2]
                comments.setdefault(key, []).append({"id": str(len(comments.get(key, []))+1), "created": "2026-11-13", **payload})
                return httpx.Response(201, json={"id": "new-comment"})
            if path.endswith("/issueLink"):
                links.append(payload)
                source, target = payload["inwardIssue"]["key"], payload["outwardIssue"]["key"]
                records[source]["fields"]["issuelinks"].append({"type": payload["type"], "outwardIssue": {"key": target}})
                return httpx.Response(201)
        if request.method == "GET" and "/issue/" in path:
            key = path.split("/issue/")[1].split("/")[0]
            if path.endswith("/comment"):
                items = comments.get(key, [])
                return httpx.Response(200, json={"comments": items, "total": len(items), "startAt": 0})
            return httpx.Response(200, json=records[key])
        pytest.fail(f"Unexpected request: {request.method} {path}")
    settings = seed.Settings.from_env(ENV)
    target = tmp_path / "seed-map.json"
    with seed.SeedClient(settings, transport=httpx.MockTransport(handle)) as api:
        first = seed.apply_seed(api, tickets, "MAPJOB", "Task", target)
        count = len(mutations)
        second = seed.apply_seed(api, tickets, "MAPJOB", "Task", target)
    assert first == second == json.loads(target.read_text())
    assert len(records) == 40 and len(links) == 12
    assert sum(map(len, comments.values())) == sum(len(t["fields"]["comment"]["comments"]) for t in tickets)
    assert len(mutations) == count


def test_checkpoint_handles_search_index_lag_and_comment_failure(tmp_path, tickets):
    ticket = copy.deepcopy(next(t for t in tickets if t["fields"]["comment"]["comments"]))
    ticket["fields"]["issuelinks"] = []  # Isolate checkpoint recovery from the separately tested link graph.
    records, posted, fail = {}, [], [True]
    def handle(request):
        path = request.url.path
        if path.endswith("search/jql"):
            return httpx.Response(200, json={"issues": [], "isLast": True})
        if path.endswith("issueLinkType"):
            return httpx.Response(200, json={"issueLinkTypes": []})
        if request.method == "POST" and path.endswith("/issue"):
            key = f"MAPJOB-{len(records)+1}"
            records[key] = {"key": key, **json.loads(request.content)}
            return httpx.Response(201, json={"key": key})
        if path.endswith("/comment"):
            if request.method == "GET":
                return httpx.Response(200, json={"comments": [{"id": str(n), "created": "2026-11-13", **p} for n, p in enumerate(posted)], "total": len(posted)})
            if fail[0]:
                fail[0] = False
                return httpx.Response(503)
            posted.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "new"})
        return httpx.Response(200, json=records[path.rsplit("/", 1)[-1]])
    path = tmp_path / "seed-map.json"
    with seed.SeedClient(seed.Settings.from_env(ENV), transport=httpx.MockTransport(handle)) as api:
        with pytest.raises(ValueError, match="503"):
            seed.apply_seed(api, [ticket], "MAPJOB", "Task", path)
        assert path.exists()
        mapping = seed.apply_seed(api, [ticket], "MAPJOB", "Task", path)
    assert len(records) == 1 and mapping[ticket["key"]] == "MAPJOB-1"
    assert len(posted) == len(ticket["fields"]["comment"]["comments"])


def test_seed_client_refuses_delete_and_arbitrary_post():
    with seed.SeedClient(seed.Settings.from_env(ENV), transport=httpx.MockTransport(lambda r: pytest.fail("Unexpected request"))) as api:
        for method, path in [("DELETE", "/rest/api/3/issue/MAPJOB-1"), ("POST", "/rest/api/3/project")]:
            with pytest.raises(ValueError):
                api.request(method, path)
