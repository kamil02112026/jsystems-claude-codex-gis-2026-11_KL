"""Validate review YAML configs; a passing result never authorizes execution."""
import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = Path(__file__).resolve().parents[2] / 'exercise-data/jira-jobs/job-params.schema.json'
STEP_ORDER = ['ingest', 'conflation', 'validation', 'export', 'publish']


def validate_job(job):
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    errors = [f'{".".join(str(p) for p in error.absolute_path) or "job"}: {error.message}' for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(job)]
    if errors:
        return errors
    bbox = job['bbox']
    if bbox is not None and not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        errors.append('bbox: expected west < east and south < north')
    steps = job['steps']
    if steps and job['start_step'] is not None and steps[0] != job['start_step']:
        errors.append('start_step: must match the first steps entry')
    if steps and steps != sorted(steps, key=STEP_ORDER.index):
        errors.append('steps: expected pipeline order ingest, conflation, validation, export, publish')
    return errors


def main(argv=None):
    import yaml  # Only the YAML command needs PyYAML, not the reader or MCP.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, nargs='?', default=Path('reports/jira-jobs/jobs'))
    args = parser.parse_args(argv)
    files = sorted(args.directory.glob('*.yaml'))
    if not files:
        print('Brak plików YAML.'); return 1
    failed, seen = False, set()
    for path in files:
        try:
            job = yaml.safe_load(path.read_text(encoding='utf-8'))
            errors = validate_job(job)
            if not errors:
                if path.stem != job['job_id'] or job['job_id'] in seen:
                    errors.append('job_id: duplicate or different from filename')
                seen.add(job['job_id'])
            for error in errors:
                print(f'{path.name}: {error}')
            failed |= bool(errors)
        except (ValueError, OSError, yaml.YAMLError) as error:
            print(f'{path.name}: {error}'); failed = True
    print(f'Sprawdzono {len(files)} plików. ' + ('Są błędy.' if failed else 'Schemat i reguły między polami poprawne.'))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
