import ast
from pathlib import Path


ROOT = Path(__file__).parents[2]
TARGETS = (
    ROOT / "decision" / "field_observation.py",
    ROOT / "decision" / "services" / "field_observation_context.py",
    ROOT / "decision" / "services" / "field_observation_recording_service.py",
)
FORBIDDEN_PARTS = ("scoring", "learning", "calibration")
FORBIDDEN_PREFIXES = ("decision.rules", "astropilot.scoring")


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def test_field_observation_boundary_cannot_import_scoring_learning_or_calibration():
    violations = []
    for path in TARGETS:
        for module in imported_modules(path):
            if module.startswith(FORBIDDEN_PREFIXES) or any(
                part in module.split(".") for part in FORBIDDEN_PARTS
            ):
                violations.append((path.relative_to(ROOT), module))
    assert violations == []
