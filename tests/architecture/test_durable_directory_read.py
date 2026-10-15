"""An unreadable durable directory must never be treated as empty history."""
import errno
import os

import pytest

from astropilot.execution_lineage_store import FileExecutionLineageStore
from astropilot.decision_acceptance_lineage_store import FileDecisionAcceptanceLineageStore


@pytest.mark.parametrize('store', ['execution', 'acceptance', 'snapshot', 'observation', 'evaluation'])
@pytest.mark.parametrize('number', [errno.EACCES, errno.EIO])
def test_failed_enumeration_is_not_empty_state(tmp_path, monkeypatch, store, number):
    directory = tmp_path/'store'
    directory.mkdir()
    original = os.scandir
    def fail(path):
        if os.fspath(path) == os.fspath(directory):
            raise OSError(number, 'SECRET')
        return original(path)
    execution = FileExecutionLineageStore(directory)
    acceptance = FileDecisionAcceptanceLineageStore(directory)
    from astropilot.field_observation_store import FileFieldObservationStore
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    operation = {'observation': FileFieldObservationStore(directory)._load_all,
                 'evaluation': FileOutcomeEvaluationStore(directory)._load_all,
                 'execution': execution.list_sessions,
                 'acceptance': acceptance._load_all,
                 'snapshot': acceptance.session_read_snapshot}[store]
    with monkeypatch.context() as patch:
        patch.setattr(os, 'scandir', fail)
        with pytest.raises(OSError) as result:
            operation()
        assert result.value.errno == number
    # A fresh instance can enumerate again after access is restored.
    if store == 'execution':
        assert FileExecutionLineageStore(directory).list_sessions() == []
    elif store == 'acceptance':
        assert FileDecisionAcceptanceLineageStore(directory)._load_all() == []
    elif store == 'snapshot':
        assert FileDecisionAcceptanceLineageStore(directory).session_read_snapshot() is not None


def test_absent_optional_histories_remain_empty(tmp_path):
    from astropilot.field_observation_store import FileFieldObservationStore
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    assert FileFieldObservationStore(tmp_path/'absent')._load_all() == []
    assert FileOutcomeEvaluationStore(tmp_path/'absent')._load_all() == []


def test_json_enumeration_preserves_native_glob_names(tmp_path):
    from astropilot.durable_read import json_document_paths
    names = ['.json', 'normal.json', '.hidden.json', 'mixed.JSON',
             'notjson', 'trailing.json.tmp', 'almostjson']
    for name in names:
        (tmp_path/name).write_text('{}', encoding='utf-8')
    # Native matching is case-sensitive on POSIX, case-insensitive on Windows.
    assert json_document_paths(tmp_path) == sorted(tmp_path.glob('*.json'))
    assert tmp_path/'.json' in json_document_paths(tmp_path)


@pytest.mark.parametrize('store', ['execution', 'acceptance', 'snapshot', 'observation', 'evaluation'])
def test_dot_json_corruption_is_refused_without_mutation(tmp_path, store):
    from astropilot.field_observation_store import FileFieldObservationStore
    from astropilot.outcome_evaluation_store import FileOutcomeEvaluationStore
    from decision.execution_lineage_persistence import ExecutionLineageCorruptionError
    from decision.acceptance_lineage_persistence import AcceptanceLineageCorruptionError
    from decision.field_observation_persistence import FieldObservationPersistenceError
    from decision.outcome_evaluation_persistence import OutcomeEvaluationPersistenceError
    path = tmp_path/'.json'
    path.write_bytes(b'{')
    acceptance = FileDecisionAcceptanceLineageStore(tmp_path)
    operations = {
        'execution': (FileExecutionLineageStore(tmp_path)._load_all, ExecutionLineageCorruptionError),
        'acceptance': (acceptance._load_all, AcceptanceLineageCorruptionError),
        'snapshot': (acceptance.session_read_snapshot, AcceptanceLineageCorruptionError),
        'observation': (FileFieldObservationStore(tmp_path)._load_all, FieldObservationPersistenceError),
        'evaluation': (FileOutcomeEvaluationStore(tmp_path)._load_all, OutcomeEvaluationPersistenceError),
    }
    operation, error = operations[store]
    with pytest.raises(error):
        operation()
    assert path.read_bytes() == b'{'
