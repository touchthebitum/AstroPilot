"""Validate a compiled upgrade snapshot with production readers, without manual extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-directory', type=Path, required=True)
    parser.add_argument('--fixture-directory', type=Path, required=True)
    args = parser.parse_args()
    case, fixture = args.case_directory, args.fixture_directory
    proof = json.loads((case / 'proof.json').read_text(encoding='utf-8'))
    expected = json.loads((fixture / 'fixture.json').read_text(encoding='utf-8'))
    assert expected['synthetic_only'] is True and proof['synthetic_only'] is True
    assert proof['success'] and proof['parent_lease_held'] and proof['backup_factory_mocked'] is False
    relative = Path(proof['snapshot_relative_path'])
    assert not relative.is_absolute() and '..' not in relative.parts
    backup = case / relative
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == proof['snapshot_sha256']
    from astropilot.profile_backup import inspect_backup, snapshot
    files, summary = inspect_backup(backup.read_bytes())
    counts = {key: summary[key] for key in ('projects', 'sessions', 'observations', 'comparisons')}
    assert all(counts[key] == expected['summary'][key] == 1 for key in counts)
    assert files == snapshot(fixture / 'data') == snapshot(case / 'stable/profil')
    assert {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()} == expected['domain_sha256']
    proof.update(production_archive_validation=True, archive_documents_identical=len(files), archive_summary=counts)
    (case / 'proof.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
