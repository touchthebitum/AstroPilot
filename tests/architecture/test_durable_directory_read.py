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
