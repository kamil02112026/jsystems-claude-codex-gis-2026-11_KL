"""Sanitization and Markdown/ADF regression tests using invented identities."""
import copy
import json

import pytest

import sanitize_export as sanitizer


def test_bitbucket_identities_are_stable_in_text_urls_and_commit_raw():
    user = {'type': 'user', 'uuid': '{private-uuid}', 'account_id': 'private-account',
            'display_name': 'Invented Person', 'nickname': 'private-handle',
            'links': {'avatar': {'href': 'https://avatar.invalid/private'}}}
    raw = {'workspace': 'devpowers', 'repo': 'map-data-jobs-pipelines',
           'author': user, 'reviewer': copy.deepcopy(user),
           'commit': {'author': {'raw': 'Invented Person <fake@example.invalid>', 'user': user}},
           'description': 'Invented Person private-account {private-uuid} private-handle',
           'url': 'https://bitbucket.org/devpowers/map-data-jobs-pipelines/pull-requests/1',
           'jira': 'https://edukey.atlassian.net/browse/TEST-12'}
    original = copy.deepcopy(raw)
    clean = sanitizer.sanitize_prs(raw)
    text = json.dumps(clean).casefold()
    assert all(s not in text for s in ('devpowers', 'edukey', 'invented person', 'private-', 'fake@example.invalid'))
    assert clean['workspace'] == 'course-workspace'
    assert clean['repo'] == raw['repo']
    assert clean['author'] == clean['reviewer'] == clean['commit']['author']['user']
    assert 'bitbucket.org/course-workspace/' in text and 'course-site.atlassian.net' in text
    assert clean['author']['links']['avatar']['href'] == sanitizer.AVATAR
    assert raw == original
    assert sanitizer.sanitize_prs(clean) == clean


def test_sparse_bitbucket_user_uuid_is_scrubbed_without_type_or_display_name():
    raw = {'author': {'uuid': '{invented-user-id}'}, 'body': 'User {invented-user-id}'}
    clean = sanitizer.sanitize_prs(raw)
    assert 'invented-user-id' not in json.dumps(clean)
    assert clean['author']['uuid'] in clean['body']
    assert sanitizer.sanitize_prs(clean) == clean


def test_scrubs_nested_identities_and_embedded_values_without_mutating_input():
    cloud = '12345678-1234-1234-1234-123456789abc'
    user = {'accountId': 'private-id-123', 'displayName': 'Private Person', 'emailAddress': 'person@example.invalid', 'avatarUrls': {'48x48': 'https://avatar.invalid/private'}, 'timeZone': 'Europe/Warsaw'}
    raw = {'issues': [{'key': 'TEST-1', 'self': f'https://edukey.atlassian.net/rest/api/3/issue/1', 'fields': {'creator': user, 'reporter': copy.deepcopy(user), 'description': 'Contact Private Person private-id-123 person@example.invalid', 'comment': {'comments': [{'body': {'type': 'doc', 'version': 1, 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': r'\[1, 2\]'}]}]}}]}, 'project': {'key': 'TEST', 'name': 'Edukey Internal'}, 'customfield_10000': f'https://api.atlassian.com/ex/jira/{cloud}/rest/api/3/issue/1', 'created': '2026-11-13T08:00:00.000+0000'}}], 'isLast': True}
    original = copy.deepcopy(raw)
    clean = sanitizer.sanitize(raw)
    text = json.dumps(clean)
    for value in ('Private Person', 'private-id-123', 'person@example.invalid', cloud, 'edukey'):
        assert value not in text.lower()
    assert raw == original and clean['isLast'] is True
    fields = clean['issues'][0]['fields']
    assert fields['creator']['accountId'] == fields['reporter']['accountId'] == '712020:course-user-1'
    assert fields['creator']['displayName'] == 'Analityk (kurs)'
    assert fields['creator']['timeZone'] == 'Europe/Warsaw'
    assert 'emailAddress' not in fields['creator']
    assert set(fields['creator']['avatarUrls'].values()) == {'https://example.invalid/avatar.png'}
    assert fields['comment']['comments'][0]['body']['content'][0]['content'][0]['text'] == '[1, 2]'
    assert fields['created'] == original['issues'][0]['fields']['created']


def walk(node):
    yield node
    for child in node.get('content', []):
        yield from walk(child)


def test_markdown_to_adf_preserves_tables_code_lists_and_inline_marks():
    md = '# Zakres\n\n| Parametr | Wartość |\n| --- | --- |\n| bbox | [1, 2, 3, 4] |\n\n- **roads** i *poi* oraz `delta`\n- drugi\n\n1. validation\n2. export\n\n```yaml\nrelease: 2026.11\n```'
    adf = sanitizer.markdown_to_adf(md)
    assert adf['type'] == 'doc' and adf['version'] == 1
    nodes = list(walk(adf))
    assert {'heading', 'table', 'tableHeader', 'tableCell', 'bulletList', 'orderedList', 'codeBlock'} <= {n['type'] for n in nodes}
    assert next(n for n in nodes if n['type'] == 'codeBlock')['attrs']['language'] == 'yaml'
    assert {'strong', 'em', 'code'} <= {m['type'] for n in nodes for m in n.get('marks', [])}
    assert '[1, 2, 3, 4]' in json.dumps(adf)
    assert sanitizer.markdown_to_adf(md.replace('\n', r'\n')) == adf


def test_already_adf_is_preserved_and_sanitization_is_idempotent():
    raw = {'issues': [{'fields': {'description': {'type': 'doc', 'version': 1, 'content': [{'type': 'paragraph', 'content': [{'type': 'text', 'text': 'unchanged'}]}]}}}]}
    assert sanitizer.sanitize(raw) == raw
    assert sanitizer.sanitize(sanitizer.sanitize(raw)) == raw


def test_connector_markdown_comments_are_rest_v3_adf():
    raw = {'issues': [{'fields': {'comment': {'comments': [{'id': '1', 'body': r'**Analyst:** bbox \[1, 2, 3, 4\]'}]}}}]}
    clean = sanitizer.sanitize(raw)
    body = clean['issues'][0]['fields']['comment']['comments'][0]['body']
    assert body['type'] == 'doc' and body['version'] == 1
    assert any(n.get('text') == 'Analyst:' and n.get('marks') == [{'type': 'strong'}] for n in walk(body))
    assert r'\[' not in json.dumps(body)


def test_underscores_inside_identifiers_are_not_emphasis():
    adf = sanitizer.markdown_to_adf('speed_limits and output_path, *review* and _approved_.')
    texts = ''.join(n.get('text', '') for n in walk(adf))
    assert 'speed_limits and output_path' in texts
    assert sum(m['type'] == 'em' for n in walk(adf) for m in n.get('marks', [])) == 2


def test_sanitizes_personal_space_and_github_owner_in_text_and_urls():
    raw = {'spaceKey': '~557058:invented-id', 'url': 'https://edukey.atlassian.net/wiki/spaces/\\~557058%3Ainvented-id/pages/220135425', 'repo': {'full_name': 'LucasMatuszewski/map-data-jobs-sim', 'owner': {'login': 'LucasMatuszewski', 'avatar_url': 'https://avatars.githubusercontent.com/u/123'}}, 'commit': {'author': {'name': 'Invented Person', 'email': 'invented@example.invalid'}}, 'body': 'LucasMatuszewski / Invented Person / invented@example.invalid'}
    clean = sanitizer.sanitize(raw)
    text = json.dumps(clean).lower()
    assert all(value not in text for value in ['edukey', '557058', 'lucas', 'invented person', 'invented@example.invalid'])
    assert clean['spaceKey'] == '~course-user'
    assert 'course-org/map-data-jobs-sim' in text and '220135425' in text
    assert clean['repo']['owner']['avatar_url'] == sanitizer.AVATAR
    assert sanitizer.sanitize(clean) == clean


def test_confluence_rest_v2_shape_preserves_html_and_metadata():
    raw = {'pages': [{'id': '22', 'title': 'Konwencje', 'parentId': '21', 'spaceId': '20', 'spaceKey': '~557058:invented-id', 'version': {'number': 2}, 'body_format': 'storage', 'body': '<p>TEST-1 <a href="https://edukey.atlassian.net/browse/TEST-2">zadanie</a></p>', '_links': {'webui': '/wiki/spaces/~557058:invented-id/pages/22'}}]}
    clean = sanitizer.sanitize_pages(raw)
    page = clean['results'][0]
    assert page['id'] == '22' and page['parentId'] == '21' and page['spaceId'] == '20'
    assert page['version']['number'] == 2
    assert page['body']['storage']['representation'] == 'storage'
    assert '<p>TEST-1' in page['body']['storage']['value']
    assert 'course-site.atlassian.net/browse/TEST-2' in page['body']['storage']['value']
    assert sanitizer.sanitize_pages(clean) == clean


def test_github_bundle_preserves_rest_counters_and_separate_resources():
    raw = {'repo': 'LucasMatuszewski/map-data-jobs-sim', 'pull_requests': [{'pr': {'number': 1, 'comments': 2, 'commits': 1, 'user': {'login': 'LucasMatuszewski'}}, 'commits': [{'sha': 'abc', 'commit': {'author': {'name': 'Invented Author', 'email': 'invented@example.invalid'}, 'message': 'TEST-18: zmiana'}}], 'comments': [{'id': 10, 'body': 'TEST-15'}], 'review_comments': [], 'files': [{'filename': 'jobs/job.yaml', 'patch': '+data_release: 2026.10'}]}]}
    clean = sanitizer.sanitize_prs(raw)
    item = clean['pull_requests'][0]
    assert clean['repo'] == 'course-org/map-data-jobs-sim'
    assert item['pr']['commits'] == 1 and item['pr']['comments'] == 2
    assert item['commits'][0]['commit']['message'] == 'TEST-18: zmiana'
    assert item['comments'][0]['id'] == 10
    assert item['files'][0]['patch'] == '+data_release: 2026.10'
    assert 'invented' not in json.dumps(clean).lower()
    assert sanitizer.sanitize_prs(clean) == clean


def test_regeneration_cli_all_four_outputs_and_path_protection(tmp_path):
    from pathlib import Path
    data = Path(__file__).resolve().parents[2] / 'exercise-data/jira-jobs'
    args = [str(data/'tickets.json'), str(tmp_path/'tickets.json'), '--example', str(tmp_path/'issue-example.json'), '--pages-raw', str(data/'confluence-pages.json'), '--pages', str(tmp_path/'confluence-pages.json'), '--prs-raw', str(data/'github-prs.json'), '--prs', str(tmp_path/'github-prs.json')]
    assert sanitizer.main(args) is None
    for name in ['tickets.json', 'issue-example.json', 'confluence-pages.json', 'github-prs.json']:
        assert json.loads((tmp_path/name).read_text()) == json.loads((data/name).read_text())
    with pytest.raises(SystemExit):
        sanitizer.main([str(data/'tickets.json'), str(data/'tickets.json'), '--example', str(tmp_path/'issue-example.json')])
    with pytest.raises(SystemExit):
        sanitizer.main([*args, '--pages', str(data/'confluence-pages.json')])
    with pytest.raises(SystemExit):
        sanitizer.main(args[:-2])


def test_snapshot_identity_audit():
    from pathlib import Path
    import re
    data = Path(__file__).resolve().parents[2] / 'exercise-data/jira-jobs'
    for name in ['tickets.json', 'issue-example.json', 'confluence-pages.json', 'github-prs.json', 'bitbucket-prs.json', 'remote-links.json']:
        text = (data/name).read_text()
        assert not re.search(r'devpowers|edukey|557058|lucas|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', text, re.I), name


def test_bitbucket_regeneration_cli_and_remote_link_extraction(tmp_path):
    from pathlib import Path
    data = Path(__file__).resolve().parents[2] / 'exercise-data/jira-jobs'
    output, links = tmp_path / 'prs.json', tmp_path / 'links.json'
    args = ['bitbucket', str(data / 'bitbucket-prs.json'), str(output), '--remote-links', str(links)]
    sanitizer.main(args)
    assert json.loads(output.read_text()) == json.loads((data / 'bitbucket-prs.json').read_text())
    assert json.loads(links.read_text()) == json.loads((data / 'remote-links.json').read_text())
    with pytest.raises(SystemExit):
        sanitizer.main(['bitbucket', str(output), str(output), '--remote-links', str(links)])


def test_personal_space_alias_stays_distinct_from_account_alias():
    raw = {'author': {'accountId': '557058:invented-id', 'displayName': 'Invented Person'}, 'spaceKey': '~557058:invented-id', 'url': '/spaces/\\~557058%3Ainvented-id/pages/22'}
    clean = sanitizer.sanitize(raw)
    assert clean['spaceKey'] == '~course-user'
    assert clean['url'] == '/spaces/~course-user/pages/22'
    assert clean['author']['accountId'] == '712020:course-user-1'


def test_github_account_ids_are_scrubbed_without_changing_pr_or_comment_ids():
    raw = {'pr': {'id': 321, 'user': {'login': 'LucasMatuszewski', 'id': 987, 'node_id': 'invented-user-node'}}, 'comments': [{'id': 654, 'user': {'login': 'review-bot', 'id': 876, 'node_id': 'invented-bot-node'}}]}
    clean = sanitizer.sanitize(raw)
    assert clean['pr']['id'] == 321 and clean['comments'][0]['id'] == 654
    assert clean['pr']['user']['id'] != 987
    assert clean['comments'][0]['user']['id'] != 876
    assert clean['pr']['user']['node_id'] != 'invented-user-node'
    assert sanitizer.sanitize(clean) == clean
