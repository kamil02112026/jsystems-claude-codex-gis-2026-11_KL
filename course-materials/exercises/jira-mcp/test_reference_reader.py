"""Read references from the actual offline snapshot; no API response mocks."""
import pytest

import jira_read as reader


def test_bitbucket_reader_preserves_captured_evidence_and_repo_identity():
    api = reader.OfflineReader()
    bundles = api.list_prs(source='bitbucket')
    assert len(bundles) == 10
    assert len(api.list_prs()) == 10  # GitHub remains the default.
    pr = api.get_pr(1, source='bitbucket')
    assert pr['pr']['data']['id'] == 1
    text = reader.format_pr(pr, source='bitbucket')
    assert 'TEST-12' in text and 'bitbucket.org/course-workspace/map-data-jobs-pipelines/' in text
    assert 'hash' in pr['commits']['data']['values'][0]
    for query, number in [('TEST-21', 4), ('TSET-9', 5), ('TEST-24', 8), ('TEST-99', 7)]:
        assert number in [b['pr']['data']['id'] for b in api.list_prs(query, source='bitbucket')]
    unrelated = api.get_pr(1, source='bitbucket', repo='ai-php-course-08-2026')
    assert 'ai-php-course-08-2026' in reader.format_pr(unrelated, source='bitbucket')
    assert unrelated != pr
    assert len(api.list_prs(source='bitbucket', repo='map-data-jobs-pipelines')) == 9
    with pytest.raises(ValueError):
        api.list_prs(source='../../tickets')
    with pytest.raises(ValueError):
        api.get_pr(99, source='bitbucket')


def test_remote_links_keep_correct_and_wrong_ticket_without_repair():
    api = reader.OfflineReader()
    for key, number in [('TEST-12', 1), ('TEST-17', 2), ('TEST-15', 3), ('TEST-13', 9)]:
        links = api.get_remote_links(key)
        assert len(links) == 1
        assert links[0]['object']['url'].endswith(f'/pull-requests/{number}')
        assert '/ex/jira/00000000-0000-0000-0000-000000000000/' in links[0]['self']
    assert api.get_remote_links('TEST-1') == []
    with pytest.raises(ValueError):
        api.get_remote_links('TEST-999')


def test_bitbucket_and_remotelinks_cli(capsys):
    assert reader.main(['--offline', 'prs', '--source', 'bitbucket'], env={}) == 0
    assert 'Liczba PR: 10' in capsys.readouterr().out
    assert reader.main(['--offline', 'pr', '8', '--source', 'bitbucket'], env={}) == 0
    text = capsys.readouterr().out
    assert 'TEST-24' in text and 'Sprawdźcie wersję wydania w YAML' in text
    assert 'brak osobnego zasobu diff' in text
    assert reader.main(['--offline', 'pr', '1', '--source', 'bitbucket', '--repo', 'ai-php-course-08-2026'], env={}) == 0
    assert 'ai-php-course-08-2026' in capsys.readouterr().out
    assert reader.main(['--offline', 'remotelinks', 'TEST-13'], env={}) == 0
    assert '/pull-requests/9' in capsys.readouterr().out
    assert reader.main(['remotelinks', 'TEST-13'], env={}) == 1
    assert 'offline' in capsys.readouterr().err


def test_list_search_and_get_confluence_pages():
    with reader.OfflineReader() as api:
        assert len(api.search_pages('')) == 5
        hits = api.search_pages('KONWENCJE parametrów')
        assert '220135425' in [p['id'] for p in hits]
        assert api.search_pages('brak-nieistniejącej-frazy') == []
        page = api.get_page('220135425')
        assert page['parentId'] == '220102657'
        assert page['body']['storage']['value']
        assert api.search_pages('TEST-99')
        page['title'] = 'changed'
        assert api.get_page('220135425')['title'] != 'changed'


@pytest.mark.parametrize('page_id', ['999999', '../../tickets.json', 'https://example.invalid'])
def test_invalid_or_missing_page_id(page_id):
    with reader.OfflineReader() as api, pytest.raises(ValueError):
        api.get_page(page_id)


def test_reference_cli_offline_and_env(capsys):
    assert reader.main(['--offline', 'pages', 'konwencje'], env={}) == 0
    assert '220135425' in capsys.readouterr().out
    assert reader.main(['page', '220135425'], env={'JIRA_OFFLINE': '1'}) == 0
    text = capsys.readouterr().out
    assert 'Konwencje parametrów' in text and 'TEST-1' in text
    assert 'course-site.atlassian.net' in text
    assert reader.main(['--offline', 'page', '999999'], env={}) == 1
    assert 'Nie znaleziono strony' in capsys.readouterr().err


def test_reference_cli_rejects_live_without_request_or_credentials(capsys):
    for args in [['pages'], ['page','220135425'], ['prs'], ['pr','1']]:
        assert reader.main(args, env={}) == 1
        assert 'offline' in capsys.readouterr().err


def test_ticket_metadata_visible_for_calendar_conflicts(capsys):
    assert reader.main(['--offline', 'get', 'TEST-6'], env={}) == 0
    text = capsys.readouterr().out
    assert 'Medium' in text and '2026-11-19' in text and '2026-11-17' in text


def test_pr_reader_keeps_rest_resources_and_searches_all_evidence():
    with reader.OfflineReader() as api:
        prs = api.list_prs()
        assert len(prs) == 10
        pr = api.get_pr(1)
        assert isinstance(pr['pr']['commits'], int)
        assert isinstance(pr['commits'], list) and pr['commits'][0]['commit']['message']
        assert isinstance(pr['pr']['comments'], int)
        assert pr['review_comments'][0]['id'] == 4559055426
        for query, number in [('test-12-osm-wk46', 3), ('TEST-18', 4), ('TSET-15', 5), ('zasłoniętego TEST-29', 1), ('2026.10 sl-461.yaml', 10)]:
            assert number in [item['pr']['number'] for item in api.list_prs(query)]
        assert api.list_prs('nieistniejąca-fraza-xyz') == []
        pr['pr']['title'] = 'changed'
        assert api.get_pr(1)['pr']['title'] != 'changed'


@pytest.mark.parametrize('number', ['9999', '../../tickets.json', '0', '-1', '1.0'])
def test_invalid_or_missing_pr(number):
    with reader.OfflineReader() as api, pytest.raises(ValueError):
        api.get_pr(number)


def test_pr_cli_exposes_commits_review_comments_and_diff(capsys):
    assert reader.main(['--offline', 'prs'], env={}) == 0
    assert 'Liczba PR: 10' in capsys.readouterr().out
    assert reader.main(['--offline', 'pr', '10'], env={}) == 0
    text = capsys.readouterr().out
    assert '2026.10' in text and 'jobs/sl-461.yaml' in text and '4559055746' in text
    assert '1f2f109e' in text
    assert reader.main(['--offline', 'pr', '9999'], env={}) == 1
    assert 'Nie znaleziono PR' in capsys.readouterr().err
