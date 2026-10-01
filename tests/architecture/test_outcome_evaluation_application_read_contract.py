from types import SimpleNamespace
from pathlib import Path
import ast
import pytest

from decision.services.durable_tonight_application_service import DurableTonightApplicationService
from decision.services.outcome_evaluation_orchestration import OutcomeEvaluationOrchestrationError


def service(items):
    return DurableTonightApplicationService(
        application_service=None, evidence_store=None, decision_id_factory=lambda: pytest.fail("ID allocated"),
        outcome_evaluation_store=SimpleNamespace(list_by_observation=lambda **kw: items),
        outcome_evaluation_clock=lambda: pytest.fail("clock read"),
    )


def test_read_filters_version_and_never_resolves_lineage_or_evaluates():
    v1 = SimpleNamespace(evaluation_algorithm_version="outcome_evaluation.v1")
    v2 = SimpleNamespace(evaluation_algorithm_version="outcome_evaluation.v2")
    app = service([v2, v1])
    app._outcome_evaluation_orchestration_service = lambda: pytest.fail("orchestration used")
    assert app.load_outcome_evaluation_by_observation("historical") is v1
    assert service([v2]).load_outcome_evaluation_by_observation("absent") is None
    with pytest.raises(OutcomeEvaluationOrchestrationError, match="outcome_evaluation_conflict"):
        service([v1, v1]).load_outcome_evaluation_by_observation("ambiguous")
    with pytest.raises(RuntimeError, match="outcome_evaluation_persistence_unavailable"):
        app.outcome_evaluation_store = None
        app.load_outcome_evaluation_by_observation("x")


def test_http_handlers_use_only_application_boundary():
    tree = ast.parse(Path("astropilot/app.py").read_text())
    handlers = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                and node.name in {"evaluate_field_observation_outcome", "read_field_observation_outcome"}]
    assert len(handlers) == 2
    for node in handlers:
        calls = {n.func.attr for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert not calls & {"save", "list_by_observation", "evaluate", "resolve", "now"}
        assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(node))
