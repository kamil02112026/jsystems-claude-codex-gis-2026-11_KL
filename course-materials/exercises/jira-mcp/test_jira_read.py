"""Offline transport simulations, not recordings of a live Jira contract."""

import json

import httpx
import pytest

import jira_read as reader


ENV = {"JIRA_BASE_URL": "https://example.atlassian.net", "JIRA_EMAIL": "test@example.invalid", "JIRA_API_TOKEN": "synthetic-token"}


def client(handler, env=None):
    settings = reader.Settings.from_env(ENV if env is None else env)
    return reader.JiraReader(settings, transport=httpx.MockTransport(handler))


def test_environment_validation_names_only():
    with pytest.raises(ValueError) as error:
        reader.Settings.from_env({"JIRA_EMAIL": "private-value"})
    assert "JIRA_BASE_URL" in str(error.value) and "JIRA_API_TOKEN" in str(error.value)
    assert "private-value" not in str(error.value)


def test_scoped_base_and_basic_auth():
    def handle(request):
        assert str(request.url).startswith("https://api.atlassian.com/ex/jira/cloud-123/rest/api/3/")
        assert request.headers["Authorization"].startswith("Basic ")
        return httpx.Response(200, json={"key": "MAPJOB-1", "fields": {}})
    with client(handle, {**ENV, "JIRA_CLOUD_ID": "cloud-123"}) as api:
        assert api.get_issue("MAPJOB-1")["key"] == "MAPJOB-1"


@pytest.mark.parametrize("base", ["http://example.atlassian.net", "https://other.invalid", "https://user:password@example.atlassian.net", "https://example.atlassian.net/?token=bad"])
def test_reject_unsafe_base(base):
    with pytest.raises(ValueError, match="JIRA_BASE_URL"):
        reader.Settings.from_env({**ENV, "JIRA_BASE_URL": base})


@pytest.mark.parametrize("method,path", [("POST", "/rest/api/3/search/jql"), ("DELETE", "/rest/api/3/issue/MAPJOB-1"), ("GET", "https://other.invalid"), ("GET", "/rest/api/3/myself")])
def test_read_only_allowlist(method, path):
    def forbidden(request):
        pytest.fail("Rejected requests must not reach transport")
    with client(forbidden) as api, pytest.raises(ValueError):
        api.request(method, path)


def test_search_paginates_enhanced_endpoint():
    calls = []
    def handle(request):
        assert request.method == "GET" and request.url.path == "/rest/api/3/search/jql"
        assert request.url.params["jql"] == "project = MAPJOB"
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"issues": [{"key": "MAPJOB-1"}], "nextPageToken": "page-2", "isLast": False})
        assert request.url.params["nextPageToken"] == "page-2"
        return httpx.Response(200, json={"issues": [{"key": "MAPJOB-2"}], "isLast": True})
    with client(handle) as api:
        assert [i["key"] for i in api.search("project = MAPJOB")] == ["MAPJOB-1", "MAPJOB-2"]


def test_comments_paginate_and_keep_chronology():
    def handle(request):
        start = int(request.url.params["startAt"])
        assert request.url.params["orderBy"] == "created"
        return httpx.Response(200, json={"startAt": start, "total": 2, "comments": [{"id": str(start + 1), "created": f"2026-11-0{start + 1}"}]})
    with client(handle) as api:
        assert [c["id"] for c in api.comments("MAPJOB-1")] == ["1", "2"]


def test_repeated_pagination_token_is_error():
    with client(lambda r: httpx.Response(200, json={"issues": [], "nextPageToken": "same"})) as api:
        with pytest.raises(ValueError, match="pagination"):
            api.search("project = MAPJOB")


def test_http_error_never_echoes_body_or_token():
    with client(lambda r: httpx.Response(403, text="synthetic-token private-value")) as api:
        with pytest.raises(ValueError) as error:
            api.get_issue("MAPJOB-1")
    assert "403" in str(error.value)
    assert "synthetic-token" not in str(error.value) and "private-value" not in str(error.value)


def test_adf_preserves_paragraphs_cards_and_links():
    adf = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Link", "marks": [{"type": "link", "attrs": {"href": "https://example.invalid"}}]}, {"type": "hardBreak"}, {"type": "inlineCard", "attrs": {"url": "https://card.invalid"}}]}]}
    text = reader.flatten_adf(adf)
    assert "Link" in text and "https://example.invalid" in text and "\nhttps://card.invalid" in text
    assert reader.flatten_adf(None) == ""


def test_cli_outputs_plain_text(capsys):
    issue = {"key": "MAPJOB-1", "fields": {"summary": "Próba", "description": {"type": "doc", "content": [{"type": "text", "text": "Opis"}]}, "status": {"name": "To Do"}, "issuelinks": []}}
    assert reader.main(["get", "MAPJOB-1"], env=ENV, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=issue))) == 0
    result = capsys.readouterr().out
    assert "MAPJOB-1" in result and "Opis" in result and '"type"' not in result


def test_cli_missing_env(capsys):
    assert reader.main(["search", "project = MAPJOB"], env={}) == 1
    assert "JIRA_API_TOKEN" in capsys.readouterr().err


def test_invalid_port_does_not_echo_environment_value(capsys):
    assert reader.main(["get", "MAPJOB-1"], env={**ENV, "JIRA_BASE_URL": "https://example.atlassian.net:private-value"}) == 1
    error = capsys.readouterr().err
    assert "JIRA_BASE_URL" in error and "private-value" not in error
