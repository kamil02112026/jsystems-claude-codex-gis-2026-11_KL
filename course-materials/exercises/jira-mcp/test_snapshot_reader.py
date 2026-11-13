"""Exercise offline CLI against the real sanitized snapshot; no transport mocks."""
import json
from pathlib import Path

import pytest

import jira_read as reader


def test_offline_search_project_parent_epics_and_comments():
    with reader.OfflineReader() as api:
        assert len(api.search('project = TEST ORDER BY key')) == 40
        assert len(api.search('project = TEST AND issuetype = Epic')) == 7
        assert len(api.search('parent = TEST-1')) == 3
        assert [i['key'] for i in api.search('parent = TEST-8')] == ['TEST-33']
        assert any(i['key'] == 'TEST-1' for i in api.search('text ~ "zmiana odbiorcy"'))
        assert api.search('project = OTHER') == []
        assert api.search('project = TEST AND labels = "job-order" AND status = "To Do"')


def test_offline_rejects_unsupported_jql_instead_of_returning_all():
    with reader.OfflineReader() as api, pytest.raises(ValueError, match='JQL'):
        api.search('project = TEST OR status = Done')


def test_get_exposes_parent_children_links_and_code_blocks(capsys):
    assert reader.main(['--offline', 'get', 'TEST-1'], env={}) == 0
    text = capsys.readouterr().out
    assert all(key in text for key in ['TEST-8', 'TEST-9', 'TEST-10'])
    assert 'regoin' in text and 'PL-MZ' in text
    assert reader.main(['get', 'TEST-33'], env={'JIRA_OFFLINE': '1'}) == 0
    assert 'TEST-8' in capsys.readouterr().out


def test_no_credentials_or_network_for_offline(capsys):
    assert reader.main(['--offline', 'search', 'project = TEST'], env={}) == 0
    assert 'Liczba zgłoszeń: 40' in capsys.readouterr().out
    assert reader.main(['--offline', 'comments', 'TEST-1'], env={}) == 0
    text = capsys.readouterr().out
    assert 'parquet' in text and '2026-11-19' in text
    assert reader.main(['--offline', 'get', 'TEST-999'], env={}) == 1
    assert 'Nie znaleziono zgłoszenia' in capsys.readouterr().err


def test_adf_table_cells_and_code_have_boundaries():
    adf = {'type': 'doc', 'content': [{'type': 'table', 'content': [{'type': 'tableRow', 'content': [{'type': 'tableCell', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'region'}]}]}, {'type': 'tableCell', 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'PL-14'}]}]}]}]}, {'type': 'codeBlock', 'content': [{'type': 'text', 'text': 'start_step: validation'}]}, {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Po kodzie'}]}]}
    text = reader.flatten_adf(adf)
    assert 'region' in text and 'PL-14' in text
    assert 'validation\nPo kodzie' in text


def test_offline_module_does_not_need_httpx(monkeypatch):
    import runpy
    import sys
    monkeypatch.setitem(sys.modules, 'httpx', None)
    module = runpy.run_path(str(Path(reader.__file__)))
    with module['OfflineReader']() as api:
        assert len(api.search('project = TEST')) == 40
