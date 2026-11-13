"""Validate proposed reference CSVs; never writes to Jira or another service."""
import argparse
import csv
import json
from pathlib import Path

from jira_read import DATA_PATH

COLUMNS = ['source', 'source_id', 'mention_text', 'jira_key', 'confidence', 'action', 'evidence']
ALLOWED = {
    'source': {'pr', 'page', 'comment'},
    'confidence': {'high', 'medium', 'low'},
    'action': {'link', 'flag_for_human', 'ignore'},
}


def validate_file(path):
    known_keys = {i['key'] for i in json.loads(DATA_PATH.read_text(encoding='utf-8'))['issues']}
    errors, count = [], 0
    with path.open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source, strict=True)
        if reader.fieldnames != COLUMNS:
            return 0, ['Nagłówek musi zawierać dokładnie: ' + ','.join(COLUMNS)]
        for count, row in enumerate(reader, 1):
            prefix = f'Wiersz {reader.line_num}: '
            if None in row or any(value is None for value in row.values()):
                errors.append(prefix + 'Nieprawidłowa liczba komórek')
                continue
            for name, allowed in ALLOWED.items():
                if row[name] not in allowed:
                    errors.append(prefix + f'{name}: dozwolone ' + ', '.join(sorted(allowed)))
            for name in ('source_id', 'mention_text', 'evidence'):
                if not row[name].strip():
                    errors.append(prefix + f'{name}: wymagane')
            key = row['jira_key']
            if key and key not in known_keys:
                errors.append(prefix + 'jira_key: rozwiązany klucz musi istnieć w snapshocie')
            if row['action'] == 'link' and not key:
                errors.append(prefix + 'link wymaga rozwiązanego jira_key')
    if not count:
        errors.append('Brak wierszy danych')
    return count, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, nargs='?', default=Path('reports/jira-jobs/links.csv'))
    args = parser.parse_args(argv)
    try:
        count, errors = validate_file(args.csv)
    except (OSError, ValueError, KeyError, csv.Error):
        print('Nie można odczytać poprawnego pliku CSV lub snapshotu.')
        return 1
    for error in errors:
        print(error)
    print(f'Sprawdzono {count} wierszy. ' + ('Są błędy.' if errors else 'Kontrakt CSV poprawny; trafność powiązań wymaga oceny.'))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
