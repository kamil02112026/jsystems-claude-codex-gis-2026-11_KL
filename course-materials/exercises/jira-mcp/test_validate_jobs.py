"""Cross-field checks that JSON Schema cannot express directly."""
import pytest
from test_job_schema import candidate
import validate_jobs


def test_accepted_candidate():
    assert validate_jobs.validate_job(candidate()) == []


@pytest.mark.parametrize('changes,message', [({'bbox': [20.8, 52.1, 20.7, 52.2]}, 'bbox'), ({'start_step': 'ingest'}, 'start_step'), ({'steps': ['validation', 'publish', 'export']}, 'steps')])
def test_rejects_invalid_cross_field_values(changes, message):
    job = candidate(); job.update(changes)
    assert any(message in error for error in validate_jobs.validate_job(job))
