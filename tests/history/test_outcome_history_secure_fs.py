"""Capability tests run on POSIX and Windows without document filesystem probes."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from astropilot.app import create_app
from astropilot import outcome_history_reader as reader_module
from decision.services.outcome_history import OutcomeHistoryService

FAMILIES = ('outcome_evaluations', 'field_observations',
            'decision_forecast_evidence', 'execution_lineage', 'decision_lineage')
FAILURES = ('windows', 'O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK',
            'open_dir_fd', 'stat_dir_fd', 'scandir_fd',
            'missing_supports_dir_fd', 'missing_supports_fd',
            'null_supports_dir_fd', 'null_supports_fd',
            'integer_supports_dir_fd', 'integer_supports_fd',
            'list_supports_dir_fd', 'list_supports_fd')


def capabilities(monkeypatch, failure=None):
    # A local os proxy keeps test-runner/API filesystem activity independent.
    proxy = SimpleNamespace(**vars(reader_module.os))
    proxy.name = 'posix'
    for flag in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'):
        setattr(proxy, flag, getattr(proxy, flag, 1))
    proxy.supports_dir_fd = set(reader_module._DIR_FD_OPERATIONS)
    proxy.supports_fd = {reader_module._SCANDIR_OPERATION}
    if failure == 'windows':
        proxy.name = 'nt'
    elif failure in ('O_DIRECTORY', 'O_NOFOLLOW', 'O_NONBLOCK'):
        delattr(proxy, failure)
    elif failure in ('open_dir_fd', 'stat_dir_fd'):
        proxy.supports_dir_fd.remove(reader_module._DIR_FD_OPERATIONS[failure == 'stat_dir_fd'])
    elif failure == 'scandir_fd':
        proxy.supports_fd.clear()
    elif failure and failure.startswith(('null_', 'integer_', 'list_')):
        kind, attribute = failure.split('_', 1)
        value = {'null': None, 'integer': 42, 'list': list(getattr(proxy, attribute))}[kind]
        setattr(proxy, attribute, value)
    elif failure:
        delattr(proxy, failure.removeprefix('missing_'))
    for operation in ('open', 'stat', 'scandir', 'fstat', 'fdopen', 'close'):
        setattr(proxy, operation, Mock(side_effect=AssertionError('filesystem access before capability rejection')))
    monkeypatch.setattr(reader_module, 'os', proxy)
    return proxy


def assert_no_fs(proxy):
    for operation in ('open', 'stat', 'scandir', 'fstat', 'fdopen', 'close'):
        getattr(proxy, operation).assert_not_called()


@pytest.mark.parametrize('failure', FAILURES)
@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('entry', ('read', '_directory_fd', '_inventory', '_read_bytes', '_digest', '_metadata'))
def test_capability_rejection_precedes_document_fs(monkeypatch, tmp_path, failure, family, entry):
    reader = reader_module.FileOutcomeHistoryReader(tmp_path / 'missing-root')
    proxy = capabilities(monkeypatch, failure)
    arguments = {'read': (), '_directory_fd': (family,), '_inventory': (family,),
                 '_read_bytes': (family, 'safe-id.json'), '_digest': (family, 'safe-id.json'),
                 '_metadata': ({family: ['safe-id.json']},)}
    with pytest.raises(reader_module.OutcomeHistoryUnavailable, match='^outcome_history_unavailable$'):
        getattr(reader, entry)(*arguments[entry])
    assert_no_fs(proxy)


@pytest.mark.parametrize('failure', FAILURES)
def test_api_capability_rejection_is_503(monkeypatch, tmp_path, failure):
    reader = reader_module.FileOutcomeHistoryReader(tmp_path / 'missing-root')
    service = OutcomeHistoryService(reader, cursor_key=b'0123456789abcdef0123456789abcdef')
    app = create_app(service_factory=lambda: SimpleNamespace(read_outcome_history=service.history))
    with TestClient(app) as client:
        proxy = capabilities(monkeypatch, failure)
        response = client.get('/v1/outcome-evaluations/history', params={'cursor': 'invalid'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'outcome_history_unavailable'
    assert_no_fs(proxy)


@pytest.mark.parametrize('container', (set, frozenset))
def test_declared_posix_capabilities_require_no_probe(monkeypatch, container):
    proxy = capabilities(monkeypatch)
    proxy.supports_dir_fd = container(proxy.supports_dir_fd)
    proxy.supports_fd = container(proxy.supports_fd)
    reader_module._require_secure_fs_capabilities()
    assert_no_fs(proxy)


def test_native_platform_contract():
    if reader_module.os.name == 'nt':
        with pytest.raises(reader_module.OutcomeHistoryUnavailable, match='^outcome_history_unavailable$'):
            reader_module._require_secure_fs_capabilities()
    else:
        reader_module._require_secure_fs_capabilities()


def test_native_platform_get_contract(monkeypatch, tmp_path):
    # Use the real platform declarations; never reconstruct POSIX capabilities.
    if reader_module.os.name != 'nt':
        reader_module._require_secure_fs_capabilities()
        return
    reader = reader_module.FileOutcomeHistoryReader(tmp_path / 'missing-root')
    service = OutcomeHistoryService(reader, cursor_key=b'0123456789abcdef0123456789abcdef')
    app = create_app(service_factory=lambda: SimpleNamespace(read_outcome_history=service.history))
    with TestClient(app) as client:
        with monkeypatch.context() as patch:
            # Copy native declarations unchanged; instrument only the reader.
            proxy = SimpleNamespace(**vars(reader_module.os))
            patch.setattr(reader_module, 'os', proxy)
            operations = []
            for name in ('open', 'stat', 'scandir', 'fstat', 'fdopen', 'close'):
                operation = Mock(side_effect=AssertionError('native Windows document filesystem access'))
                patch.setattr(proxy, name, operation)
                operations.append(operation)
            response = client.get('/v1/outcome-evaluations/history')
            assert response.status_code == 503
            assert response.json()['detail']['code'] == 'outcome_history_unavailable'
            for operation in operations:
                operation.assert_not_called()
