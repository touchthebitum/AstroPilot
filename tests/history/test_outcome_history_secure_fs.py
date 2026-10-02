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


@pytest.mark.skipif(reader_module.os.name != 'posix', reason='secure POSIX reader')
@pytest.mark.parametrize('size', (0, 32, 33))
def test_document_read_budget(monkeypatch, tmp_path, size):
    import hashlib
    monkeypatch.setattr(reader_module, '_MAX_DOCUMENT_BYTES', 32)
    directory = tmp_path / 'field_observations'
    directory.mkdir()
    (directory / 'safe-id.json').write_bytes(b'x' * size)
    reader = reader_module.FileOutcomeHistoryReader(tmp_path)
    if size > 32:
        with pytest.raises(reader_module.OutcomeHistoryDocumentTooLarge):
            reader._read_bytes('field_observations', 'safe-id.json')
        assert reader._digest('field_observations', 'safe-id.json').startswith('too_large:')
    else:
        assert reader._read_bytes('field_observations', 'safe-id.json') == b'x' * size
        assert reader._digest('field_observations', 'safe-id.json') == hashlib.sha256(b'x' * size).hexdigest()


@pytest.mark.skipif(reader_module.os.name != 'posix', reason='secure POSIX reader')
def test_sparse_oversize_never_opens_stream(monkeypatch, tmp_path):
    directory = tmp_path / 'field_observations'
    directory.mkdir()
    with (directory / 'safe-id.json').open('wb') as stream:
        stream.truncate(1024 ** 3)
    reader = reader_module.FileOutcomeHistoryReader(tmp_path)
    monkeypatch.setattr(reader_module.os, 'fdopen', Mock(side_effect=AssertionError('content read')))
    with pytest.raises(reader_module.OutcomeHistoryDocumentTooLarge):
        reader._read_bytes('field_observations', 'safe-id.json')


@pytest.mark.skipif(reader_module.os.name != 'posix', reason='secure POSIX reader')
@pytest.mark.parametrize('size', (32, 33))
def test_short_reads_eintr_and_misleading_size(monkeypatch, tmp_path, size):
    from contextlib import contextmanager
    directory = tmp_path / 'field_observations'
    directory.mkdir()
    (directory / 'safe-id.json').write_bytes(b'x' * size)
    monkeypatch.setattr(reader_module, '_MAX_DOCUMENT_BYTES', 32)
    native_fstat = reader_module.os.fstat
    native_fdopen = reader_module.os.fdopen
    calls = []
    def misleading(fd):
        info = native_fstat(fd)
        return SimpleNamespace(**{name: (0 if name == 'st_size' else getattr(info, name))
            for name in ('st_size', 'st_mode', 'st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns')})
    @contextmanager
    def short_stream(*args, **kwargs):
        with native_fdopen(*args, **kwargs) as stream:
            class Short:
                def read(self, budget):
                    calls.append(budget)
                    if len(calls) == 1:
                        raise InterruptedError()
                    return stream.read(min(3, budget))
            yield Short()
    monkeypatch.setattr(reader_module.os, 'fstat', misleading)
    monkeypatch.setattr(reader_module.os, 'fdopen', short_stream)
    reader = reader_module.FileOutcomeHistoryReader(tmp_path)
    if size == 32:
        assert reader._read_bytes('field_observations', 'safe-id.json') == b'x' * size
    else:
        with pytest.raises(reader_module.OutcomeHistoryDocumentTooLarge):
            reader._read_bytes('field_observations', 'safe-id.json')
    assert all(0 < budget <= 33 for budget in calls)


@pytest.mark.skipif(reader_module.os.name != 'posix', reason='secure POSIX reader')
@pytest.mark.parametrize('mutation', ('grow', 'shrink', 'error'))
def test_mutation_during_bounded_read_and_descriptor_cleanup(monkeypatch, tmp_path, mutation):
    from contextlib import contextmanager
    directory = tmp_path / 'field_observations'
    directory.mkdir()
    path = directory / 'safe-id.json'
    path.write_bytes(b'x' * 16)
    monkeypatch.setattr(reader_module, '_MAX_DOCUMENT_BYTES', 32)
    monkeypatch.setattr(reader_module, '_READ_CHUNK_BYTES', 4)
    native_fdopen = reader_module.os.fdopen
    native_close = reader_module.os.close
    descriptors = []
    returned = []
    @contextmanager
    def changing_stream(fd, *args, **kwargs):
        descriptors.append(fd)
        assert kwargs['buffering'] == 0
        with native_fdopen(fd, *args, **kwargs) as stream:
            class Changing:
                def read(self, budget):
                    chunk = stream.read(budget)
                    returned.append(len(chunk))
                    if len(returned) == 1:
                        if mutation == 'error':
                            raise OSError('read failed')
                        with path.open('r+b') as writer:
                            writer.truncate(40 if mutation == 'grow' else 4)
                    return chunk
            yield Changing()
    closes = []
    def close(fd):
        closes.append(fd)
        native_close(fd)
    monkeypatch.setattr(reader_module.os, 'fdopen', changing_stream)
    monkeypatch.setattr(reader_module.os, 'close', close)
    reader = reader_module.FileOutcomeHistoryReader(tmp_path)
    if mutation == 'grow':
        with pytest.raises(reader_module.OutcomeHistoryDocumentTooLarge):
            reader._read_bytes('field_observations', 'safe-id.json')
        assert sum(returned) == 33
    elif mutation == 'shrink':
        assert reader._read_bytes('field_observations', 'safe-id.json') == b'x' * 4
    else:
        with pytest.raises(OSError):
            reader._read_bytes('field_observations', 'safe-id.json')
    assert descriptors and all(fd in closes for fd in descriptors)
