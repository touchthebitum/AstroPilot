"""Adapt test-file I/O portability only; never alter product files or assertions."""
import hashlib, json, os
from pathlib import Path
source = Path('tests/architecture/test_decision_acceptance_lineage_persistence.py')
text = source.read_text(encoding='utf-8')
replacements = {
    "write_text(serialize_decision_acceptance_aggregate(changed))":
        "write_text(serialize_decision_acceptance_aggregate(changed), encoding='utf-8')",
    "path.write_text(serialize_decision_acceptance_aggregate(result))":
        "path.write_text(serialize_decision_acceptance_aggregate(result) + ' ', encoding='utf-8')",
}
for old, new in replacements.items():
    assert text.count(old) == 1, old
    text = text.replace(old, new)
destination = Path(os.environ['RUNNER_TEMP']) / 'beta8-portable-fixture-tests'
destination.mkdir(exist_ok=False)
path = destination / source.name
path.write_text(text, encoding='utf-8')
report = {
    'original_test_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'adapted_test_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    'changes': ['Explicit UTF-8 when replacing serialized Unicode JSON',
                'Append legal JSON whitespace to ensure a changed file size during validation'],
    'assertions_unchanged': True, 'product_source_unchanged': True,
}
Path('dist/beta8-artifacts/windows-fixture-portability.json').write_text(json.dumps(report, indent=2))
print(path)
