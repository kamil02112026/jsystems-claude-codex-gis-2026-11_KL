"""The schema accepts review candidates and rejects silent missing parameters."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import pytest

SCHEMA_PATH = Path(__file__).resolve().parents[2] / 'exercise-data/jira-jobs/job-params.schema.json'


def candidate():
    return {'job_id': 'TEST-1', 'region': 'PL-14', 'area_name': 'Nowa Wieś', 'bbox': [20.78, 52.1, 20.835, 52.135], 'layers': ['roads', 'speed_limits'], 'data_release': '2026.11', 'start_step': 'validation', 'steps': ['validation', 'export', 'publish'], 'output_format': 'parquet', 'output_path': 'dbfs:/map-jobs/sl-461/final/', 'deadline': '2026-11-19', 'requester_team': 'Map Requests', 'notes': [], 'unknown_reasons': {}}


def errors(job):
    schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(job))


def test_valid_candidate_and_missing_target():
    job = candidate()
    assert not errors(job)
    job['output_path'] = None
    assert errors(job)
    job['unknown_reasons']['output_path'] = 'Brak zaakceptowanego celu, job zablokowany.'
    assert not errors(job)


@pytest.mark.parametrize('field,value', [('data_release', '26.11'), ('deadline', '2026-02-30'), ('layers', ['speed limts']), ('bbox', [200, 52, 201, 53]), ('unknown_reasons', {'nonexistent': 'unknown'}), ('notes', 'untyped string')])
def test_rejects_invalid_candidate(field, value):
    job = candidate(); job[field] = value
    assert errors(job)


def test_explicit_no_bbox_requires_explanation():
    job = candidate(); job['bbox'] = None
    assert errors(job)
    job['unknown_reasons']['bbox'] = 'Jawnie cały region, brak dodatkowego wycinka.'
    assert not errors(job)
