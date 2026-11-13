"""Validate CSV artifacts without calling a model or changing Jira."""
import csv
import pytest
import validate_links as validator

COLUMNS = ['source', 'source_id', 'mention_text', 'jira_key', 'confidence', 'action', 'evidence']


def write_csv(tmp_path, rows, columns=COLUMNS):
    path = tmp_path / 'links.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def row(**changes):
    return dict(source='pr', source_id='pr:1:title', mention_text='TEST-1', jira_key='TEST-1', confidence='high', action='link', evidence='Tytuł PR, klucz istnieje') | changes


def test_accepts_link_flag_and_ignore_with_utf8_bom(tmp_path, capsys):
    path = write_csv(tmp_path, [row(), row(source='page', jira_key='', confidence='low', action='flag_for_human'), row(source='comment', jira_key='', confidence='medium', action='ignore')])
    assert validator.main([str(path)]) == 0
    assert '3' in capsys.readouterr().out


@pytest.mark.parametrize('changes', [dict(source='commit'), dict(confidence='certain'), dict(action='write'), dict(jira_key='TEST-99'), dict(jira_key='test-1'), dict(source_id=''), dict(evidence=''), dict(jira_key='')])
def test_rejects_invalid_rows(tmp_path, changes):
    assert validator.main([str(write_csv(tmp_path, [row(**changes)]))]) == 1


def test_requires_exact_columns_and_nonempty_report(tmp_path):
    assert validator.main([str(write_csv(tmp_path, [], COLUMNS[:-1]))]) == 1
    assert validator.main([str(write_csv(tmp_path, []))]) == 1
    assert validator.main([str(tmp_path / 'missing.csv')]) == 1


def test_rejects_truncated_or_extra_cells(tmp_path):
    path = tmp_path / 'links.csv'
    path.write_text(','.join(COLUMNS) + '\npr,1,TEST-1,TEST-1,high,link\n', encoding='utf-8')
    assert validator.main([str(path)]) == 1
    path.write_text(','.join(COLUMNS) + '\npr,1,TEST-1,TEST-1,high,link,proof,extra\n', encoding='utf-8')
    assert validator.main([str(path)]) == 1
