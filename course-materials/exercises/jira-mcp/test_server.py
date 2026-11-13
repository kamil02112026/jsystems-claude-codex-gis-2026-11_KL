"""Testy kontraktu narzędzi na zanonimizowanym snapshocie Jira."""

import importlib.util
import json
from pathlib import Path

import pytest


def test_bitbucket_and_remote_link_tools(server):
    assert len(server.list_prs(source='bitbucket').splitlines()) == 10
    assert 'TEST-21' in server.get_pr(4, source='bitbucket')
    assert 'ai-php-course-08-2026' in server.get_pr(1, source='bitbucket', repo='ai-php-course-08-2026')
    assert '/pull-requests/9' in server.get_remote_links('TEST-13')
    assert server.get_remote_links('TEST-1') == 'Brak linków zewnętrznych.'
    with pytest.raises(ValueError):
        server.list_prs(source='gitlab')


@pytest.fixture(scope="module")
def server():
    path = Path(__file__).with_name("server.py")
    spec = importlib.util.spec_from_file_location("jira_jobs_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discovery_is_complete(server):
    lines = server.search_tickets("").splitlines()
    assert len(lines) == 40
    assert lines[0].startswith("TEST-1 |")
    assert lines[-1].startswith("TEST-40 |")


@pytest.mark.parametrize("query,key", [
    ("ZMIANA ODBIORCY TEST-1", "TEST-1"),
    ("ZATWIERDZONEGO OUTPUT_PATH TEST-30", "TEST-30"),
])
def test_search_matches_comments_and_all_words_case_insensitively(server, query, key):
    result = server.search_tickets(query)
    assert result.startswith(f"{key} |")
    assert len(result.splitlines()) == 1


def test_status_filter_is_exact_and_case_insensitive(server):
    result = server.search_tickets("", status="in progress")
    assert result
    assert all(" | In Progress | " in line for line in result.splitlines())
    assert server.search_tickets("", status="progress") == "Brak zgłoszeń."


def test_search_unknown_returns_explicit_message(server):
    assert server.search_tickets("nieistniejący-fioletowy-tunel") == "Brak zgłoszeń."


def test_get_ticket_preserves_raw_values_and_metadata(server):
    text = server.get_ticket("test-1")
    for value in ("TEST-1", "regoin", "PL-MZ", "26.11", "2026-11-13", "job-order"):
        assert value in text
    assert '"type": "doc"' not in text


def test_adf_rich_content_keeps_boundaries_and_link_text(server):
    adf = {"type": "doc", "content": [
        {"type": "heading", "content": [{"type": "text", "text": "Obszar"}]},
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                {"type": "paragraph", "content": [
                    {"type": "text", "text": "PL"}, {"type": "hardBreak"},
                    {"type": "text", "text": "drogi"}]}]}]},
        {"type": "paragraph", "content": [
            {"type": "inlineCard", "attrs": {"url": "https://example.invalid/spec"}}]},
    ]}
    assert server.flatten_adf(adf).strip() == "Obszar\nPL\ndrogi\nhttps://example.invalid/spec"
    assert server.flatten_adf(None) == ""


def test_get_ticket_exposes_explicit_links(server):
    assert "TEST-10" in server.get_ticket("TEST-9")


def test_comments_preserve_override_and_chronology(server):
    text = server.list_comments("TEST-1")
    assert text.index("conflation jest gotowe") < text.index("zmiana odbiorcy")
    assert "listopad 2026" in text and "parquet" in text
    assert "Analityk (kurs)" in text
    assert "2026-11-19" in text


def test_empty_comments(server):
    assert server.list_comments("TEST-2") == "Brak komentarzy."


@pytest.mark.parametrize("tool", ["get_ticket", "list_comments"])
@pytest.mark.parametrize("key", ["TEST-999", "../../tickets.json"])
def test_unknown_ticket_is_not_a_path(server, tool, key):
    with pytest.raises(ValueError, match="Nie znaleziono zgłoszenia|Invalid issue key"):
        getattr(server, tool)(key)


def test_data_shape_and_adf():
    path = Path(__file__).resolve().parents[2] / "exercise-data/jira-jobs/tickets.json"
    response = json.loads(path.read_text(encoding="utf-8"))
    assert len(response["issues"]) == 40
    assert len({issue["key"] for issue in response["issues"]}) == 40
    for issue in response["issues"]:
        fields = issue["fields"]
        assert issue["key"].startswith("TEST-")
        assert fields["description"]["type"] == "doc"
        assert fields["description"]["version"] == 1
        assert fields["summary"] and fields["status"]["name"]
        assert isinstance(fields["labels"], list)
        assert fields["created"]
        assert isinstance(fields["issuelinks"], list)
        comments = fields["comment"]
        assert comments["total"] == len(comments["comments"])
        assert all(c["body"]["type"] == "doc" for c in comments["comments"])


def test_confluence_and_github_tools(server):
    assert len(server.search_pages('').splitlines()) == 5
    assert '220135425' in server.search_pages('konwencje parametrów')
    assert 'course-site.atlassian.net' in server.get_page('220135425')
    assert len(server.list_prs('').splitlines()) == 10
    assert server.list_prs('test-12-osm-wk46').startswith('3 |')
    assert '2026.10' in server.get_pr(10) and '4559055746' in server.get_pr(10)
    assert server.search_pages('brak-nieistniejącej-frazy') == 'Brak stron.'
    assert server.list_prs('brak-nieistniejącej-frazy') == 'Brak PR.'
    with pytest.raises(ValueError):
        server.get_page('../tickets.json')
    with pytest.raises(ValueError):
        server.get_pr(9999)
