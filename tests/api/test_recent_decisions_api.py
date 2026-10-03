from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from astropilot.app import create_app
from astropilot.recent_decision_reader import (
    FileRecentDecisionReader, RecentDecisionsInvalidFilter,
    RecentDecisionsDatasetChanged, RecentDecisionsUnavailable,
)
from decision.weather.decision_forecast_evidence import DecisionForecastEvidence
from decision.weather.decision_forecast_evidence_persistence import serialize_decision_forecast_evidence
from decision.weather.provider_reliability import WeatherForecastPoint, WeatherLocation, WeatherValue, WeatherVariable

AT = datetime(2026, 10, 3, 18, tzinfo=timezone.utc)
FILTERS = dict(latitude=46.9, longitude=6.5, retrieved_from='2026-10-02T00:00:00Z', retrieved_to='2026-10-04T00:00:00Z')


def point(**overrides):
    params = dict(provider_id='open_meteo', retrieved_at_utc=AT,
                  forecast_for_utc=AT + timedelta(hours=2),
                  requested_location=WeatherLocation(46.9, 6.5),
                  grid_location=WeatherLocation(46.9, 6.5),
                  values=(WeatherValue(WeatherVariable.TEMPERATURE_C, 8.0, '°C'),))
    params.update(overrides)
    return WeatherForecastPoint(**params)


def write(root, identity, points=None):
    directory = root / 'decision_forecast_evidence'
    directory.mkdir(exist_ok=True)
    evidence = DecisionForecastEvidence((point(),) if points is None else points)
    (directory / f'{identity}.json').write_text(serialize_decision_forecast_evidence(decision_id=identity, evidence=evidence))


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_read_catalogue_exact_site_unknown_metadata_and_no_writes(tmp_path):
    write(tmp_path, 'decision-a')
    write(tmp_path, 'decision-b')
    write(tmp_path, 'near-site', (point(requested_location=WeatherLocation(46.90001, 6.5)),))
    write(tmp_path, 'other-time', (point(retrieved_at_utc=AT - timedelta(days=4)),))
    before = snapshot(tmp_path)
    result = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32).list_recent(**FILTERS)
    assert [i['decision_id'] for i in result['items']] == ['decision-b', 'decision-a']
    item = result['items'][0]
    assert item['decision_created_at_utc'] is None
    assert item['site']['timezone'] is None and item['site']['name'] is None
    assert item['decision_status'] is None and item['superseded'] is None
    assert result['time_basis'] == 'forecast_retrieved_at_utc'
    assert result['comparability_guaranteed'] is False
    assert snapshot(tmp_path) == before


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_pagination_cursor_query_and_dataset_changes(tmp_path):
    write(tmp_path, 'a')
    write(tmp_path, 'b')
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32)
    first = reader.list_recent(**FILTERS, limit=1)
    cursor = first['next_cursor']
    assert reader.list_recent(**FILTERS, limit=1, cursor=cursor)['items'][0]['decision_id'] == 'a'
    with pytest.raises(RecentDecisionsInvalidFilter):
        reader.list_recent(**{**FILTERS, 'latitude': 46.8}, limit=1, cursor=cursor)
    write(tmp_path, 'c')
    with pytest.raises(RecentDecisionsDatasetChanged):
        reader.list_recent(**FILTERS, limit=1, cursor=cursor)


@pytest.mark.parametrize('override', [dict(limit=0), dict(limit=51), dict(latitude=float('nan')),
    dict(longitude=181), dict(retrieved_from='2026-10-02T00:00:00'),
    dict(retrieved_to='2026-09-01T00:00:00Z'), dict(retrieved_to='2026-12-01T00:00:00Z'),
    dict(cursor='invalid'), dict(cursor='x' * 513)])
def test_invalid_filters(tmp_path, override):
    with pytest.raises(RecentDecisionsInvalidFilter):
        FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32).list_recent(**{**FILTERS, **override})


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_missing_directory_is_empty_without_creation(tmp_path):
    assert FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32).list_recent(**FILTERS)['items'] == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_invalid_empty_and_inconsistent_evidence_are_not_candidates(tmp_path):
    write(tmp_path, 'empty', ())
    write(tmp_path, 'mixed-site', (point(), point(requested_location=WeatherLocation(46.8, 6.5))))
    write(tmp_path, 'mixed-time', (point(), point(retrieved_at_utc=AT - timedelta(hours=1))))
    (tmp_path / 'decision_forecast_evidence' / 'broken.json').write_text('{')
    result = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32).list_recent(**FILTERS)
    assert result['items'] == [] and result['complete'] is False
    assert len(result['diagnostics']) == 4


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_scan_and_byte_budgets_fail_closed(tmp_path, monkeypatch):
    write(tmp_path, 'a')
    write(tmp_path, 'b')
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32)
    monkeypatch.setattr(reader, 'MAX_DOCUMENTS', 1)
    with pytest.raises(RecentDecisionsUnavailable, match='scan_limit'):
        reader.list_recent(**FILTERS)
    monkeypatch.setattr(reader, 'MAX_DOCUMENTS', 512)
    monkeypatch.setattr(reader, 'MAX_TOTAL_BYTES', 1)
    with pytest.raises(RecentDecisionsUnavailable, match='scan_limit'):
        reader.list_recent(**FILTERS)


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_symlink_document_is_not_followed(tmp_path):
    write(tmp_path, 'a')
    (tmp_path / 'decision_forecast_evidence' / 'b.json').symlink_to(tmp_path / 'decision_forecast_evidence' / 'a.json')
    with pytest.raises(RecentDecisionsUnavailable):
        FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32).list_recent(**FILTERS)


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_inventory_change_during_read_is_rejected(tmp_path, monkeypatch):
    write(tmp_path, 'a')
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32)
    original = reader._files._read_bytes
    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        write(tmp_path, 'b')
        return result
    monkeypatch.setattr(reader._files, '_read_bytes', read)
    with pytest.raises(RecentDecisionsDatasetChanged):
        reader.list_recent(**FILTERS)


def test_capability_rejection_without_filesystem_access(tmp_path, monkeypatch):
    import astropilot.recent_decision_reader as module
    def reject():
        from astropilot.outcome_history_reader import OutcomeHistoryUnavailable
        raise OutcomeHistoryUnavailable('unsupported')
    monkeypatch.setattr(module, '_require_secure_fs_capabilities', reject)
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32)
    monkeypatch.setattr(reader, '_snapshot', lambda: pytest.fail('filesystem read'))
    with pytest.raises(RecentDecisionsUnavailable):
        reader.list_recent(**FILTERS)


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_api_real_reader_does_not_evaluate_or_write(tmp_path):
    write(tmp_path, 'old-decision')
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32)
    service = SimpleNamespace(read_recent_decisions=reader.list_recent,
                              evaluate=lambda **kw: pytest.fail('Tonight evaluated'))
    before = snapshot(tmp_path)
    with TestClient(create_app(service_factory=lambda: service)) as client:
        response = client.get('/v1/decisions/recent', params=FILTERS)
        assert response.status_code == 200
        assert response.json()['items'][0]['decision_id'] == 'old-decision'
        assert client.get('/v1/decisions/recent', params={**FILTERS, 'limit': 51}).status_code == 422
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('error, status, code', [
    (RecentDecisionsDatasetChanged('internal'), 409, 'recent_decisions_dataset_changed'),
    (RecentDecisionsUnavailable('/private/path'), 503, 'recent_decisions_unavailable'),
    (RecentDecisionsUnavailable('recent_decisions_scan_limit'), 503, 'recent_decisions_scan_limit'),
])
def test_api_errors_are_explicit_and_redacted(error, status, code):
    def read(**filters):
        raise error
    with TestClient(create_app(service_factory=lambda: SimpleNamespace(read_recent_decisions=read))) as client:
        response = client.get('/v1/decisions/recent', params=FILTERS)
    assert response.status_code == status
    assert response.json() == {'detail': {'code': code}}


@pytest.mark.skipif(os.name != "posix", reason="Secure catalogue requires POSIX descriptors")
def test_cursor_tampering_is_rejected(tmp_path):
    write(tmp_path, 'a')
    write(tmp_path, 'b')
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32)
    cursor = reader.list_recent(**FILTERS, limit=1)['next_cursor']
    altered = ('A' if cursor[0] != 'A' else 'B') + cursor[1:]
    with pytest.raises(RecentDecisionsInvalidFilter):
        reader.list_recent(**FILTERS, limit=1, cursor=altered)


def test_durable_service_read_boundary_and_unconfigured_reader(tmp_path):
    from decision.services.durable_tonight_application_service import DurableTonightApplicationService
    calls = []
    def read(**filters):
        calls.append(filters)
        return {"items": []}
    service = DurableTonightApplicationService(application_service=None, evidence_store=None,
        decision_id_factory=lambda: pytest.fail("allocated decision ID"),
        recent_decision_reader=SimpleNamespace(list_recent=read))
    assert service.read_recent_decisions(**FILTERS) == {"items": []}
    assert calls == [FILTERS]
    service.recent_decision_reader = None
    with pytest.raises(RecentDecisionsUnavailable):
        service.read_recent_decisions(**FILTERS)


def test_api_requires_explicit_site_and_time_range():
    def read(**filters):
        pytest.fail("missing filters reached reader")
    with TestClient(create_app(service_factory=lambda: SimpleNamespace(read_recent_decisions=read))) as client:
        assert client.get('/v1/decisions/recent').status_code == 422


def test_platform_rejection_is_redacted_api_503(tmp_path, monkeypatch):
    import astropilot.recent_decision_reader as module
    from astropilot.outcome_history_reader import OutcomeHistoryUnavailable
    def reject():
        raise OutcomeHistoryUnavailable('platform details')
    monkeypatch.setattr(module, '_require_secure_fs_capabilities', reject)
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b"k" * 32)
    monkeypatch.setattr(reader, '_snapshot', lambda: pytest.fail("document access"))
    with TestClient(create_app(service_factory=lambda: SimpleNamespace(read_recent_decisions=reader.list_recent))) as client:
        response = client.get('/v1/decisions/recent', params=FILTERS)
    assert response.status_code == 503
    assert response.json() == {'detail': {'code': 'recent_decisions_unavailable'}}


@pytest.mark.parametrize('corruption', ['deep', 'time', 'number'])
def test_api_isolated_decode_overflow_preserves_valid_candidate(tmp_path, corruption):
    write(tmp_path, 'valid')
    write(tmp_path, 'broken')
    path = tmp_path / 'decision_forecast_evidence' / 'broken.json'
    raw = path.read_text()
    if corruption == 'deep':
        raw = '[' * 20000 + '0' + ']' * 20000
    elif corruption == 'time':
        raw = raw.replace(AT.isoformat(), '0001-01-01T00:00:00+01:00')
    else:
        raw = raw.replace('46.9', '1' + '0' * 400)
    path.write_text(raw)
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b'k' * 32)
    before = snapshot(tmp_path)
    service = SimpleNamespace(read_recent_decisions=reader.list_recent,
                              evaluate=lambda **kw: pytest.fail('recompute'))
    with TestClient(create_app(service_factory=lambda: service)) as client:
        response = client.get('/v1/decisions/recent', params=FILTERS)
    assert response.status_code == 200
    result = response.json()
    assert [item['decision_id'] for item in result['items']] == ['valid']
    assert result['complete'] is False
    assert result['diagnostics'] == [{'decision_id': 'broken', 'code': 'decision_evidence_invalid'}]
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('case', ['three', 'exact', 'extra', 'growth'])
def test_actual_read_budget(tmp_path, monkeypatch, case):
    import astropilot.outcome_history_reader as module
    size = 16 * 1024 * 1024
    directory = tmp_path / 'decision_forecast_evidence'
    directory.mkdir()
    sizes = [size, size] if case == 'exact' else [size, size, 1 if case in ('extra', 'growth') else size]
    for index, length in enumerate(sizes):
        (directory / f'{index}.json').write_bytes(b' ' * length)
    original = module.os.fdopen
    reads = []
    def instrument(fd, *args, **kwargs):
        stream = original(fd, *args, **kwargs)
        counts = []
        reads.append(counts)
        class Meter:
            def __enter__(self):
                if case == 'growth' and len(reads) == 3:
                    with (directory / '2.json').open('ab') as writer:
                        writer.write(b' ' * size)
                return self
            def __exit__(self, *exc):
                stream.close()
            def read(self, amount):
                chunk = stream.read(amount)
                counts.append(len(chunk))
                return chunk
        return Meter()
    monkeypatch.setattr(module.os, 'fdopen', instrument)
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b'k' * 32)
    with TestClient(create_app(service_factory=lambda: SimpleNamespace(read_recent_decisions=reader.list_recent))) as client:
        response = client.get('/v1/decisions/recent', params=FILTERS)
    if case == 'exact':
        assert response.status_code == 200
        assert sum(map(sum, reads)) == 32 * 1024 * 1024
    else:
        assert response.status_code == 503
        assert response.json()['detail']['code'] == 'recent_decisions_scan_limit'
        assert list(map(sum, reads)) == [size, size, 1]


@pytest.mark.parametrize('remaining,length,accepted,read_count', [
    (0, 0, True, 0), (0, 1, False, 1), (7, 7, True, 7), (7, 8, False, 8),
    (32 * 1024 * 1024, 16 * 1024 * 1024 + 1, False, 16 * 1024 * 1024 + 1),
])
def test_secure_reader_remaining_budget_and_growth(tmp_path, monkeypatch, remaining, length, accepted, read_count):
    import astropilot.outcome_history_reader as module
    directory = tmp_path / 'decision_forecast_evidence'
    directory.mkdir()
    path = directory / 'a.json'
    path.write_bytes(b'')
    original = module.os.fdopen
    counts = []
    def instrument(fd, *args, **kwargs):
        stream = original(fd, *args, **kwargs)
        class Meter:
            def __enter__(self):
                path.write_bytes(b'x' * length)
                return self
            def __exit__(self, *exc):
                stream.close()
            def read(self, amount):
                raw = stream.read(amount)
                counts.append(len(raw))
                return raw
        return Meter()
    monkeypatch.setattr(module.os, 'fdopen', instrument)
    reader = module.FileOutcomeHistoryReader(tmp_path)
    if accepted:
        assert len(reader._read_bytes('decision_forecast_evidence', 'a.json', remaining_total_budget=remaining)) == length
    else:
        with pytest.raises(module.OutcomeHistoryDocumentTooLarge):
            reader._read_bytes('decision_forecast_evidence', 'a.json', remaining_total_budget=remaining)
    assert sum(counts) == read_count


@pytest.mark.parametrize('change', ['bool', 'duplicate', 'nonhex', 'extra', 'uppercase'])
def test_signed_cursor_strict_schema(tmp_path, change):
    import base64
    import hashlib
    import hmac
    import json
    write(tmp_path, 'a')
    write(tmp_path, 'b')
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b'k' * 32)
    cursor = reader.list_recent(**FILTERS, limit=1)['next_cursor']
    value = json.loads(base64.urlsafe_b64decode(cursor.split('.')[0]))
    if change == 'bool':
        value['version'] = True
    elif change in ('nonhex', 'uppercase'):
        value['fingerprint'] = ('g' if change == 'nonhex' else 'A') * 64
    elif change == 'extra':
        value['extra'] = 1
    raw = json.dumps(value)
    if change == 'duplicate':
        raw = raw[:-1] + ', "version": 1}'
    encoded = base64.urlsafe_b64encode(raw.encode()).decode()
    signed = encoded + '.' + hmac.new(b'k' * 32, b'recent-decisions-v1\0' + encoded.encode(), hashlib.sha256).hexdigest()
    with TestClient(create_app(service_factory=lambda: SimpleNamespace(read_recent_decisions=reader.list_recent))) as client:
        assert client.get('/v1/decisions/recent', params={**FILTERS, 'limit': 1, 'cursor': signed}).status_code == 422


def test_zero_coordinate_continuation(tmp_path):
    for identity in ('a', 'b'):
        write(tmp_path, identity, (point(requested_location=WeatherLocation(0.0, 0.0)),))
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b'k' * 32)
    filters = {**FILTERS, 'latitude': -0.0, 'longitude': -0.0, 'limit': 1}
    first = reader.list_recent(**filters)
    assert reader.list_recent(**{**filters, 'latitude': 0.0, 'longitude': 0.0}, cursor=first['next_cursor'])['items'][0]['decision_id'] == 'a'


def test_api_real_reader_continuation_and_unavailable_storage(tmp_path):
    write(tmp_path, 'a')
    write(tmp_path, 'b')
    reader = FileRecentDecisionReader(tmp_path, cursor_key=b'k' * 32)
    service = SimpleNamespace(read_recent_decisions=reader.list_recent)
    with TestClient(create_app(service_factory=lambda: service)) as client:
        params = {**FILTERS, 'limit': 1}
        cursor = client.get('/v1/decisions/recent', params=params).json()['next_cursor']
        assert client.get('/v1/decisions/recent', params={**params, 'cursor': cursor + 'x'}).status_code == 422
        write(tmp_path, 'c')
        assert client.get('/v1/decisions/recent', params={**params, 'cursor': cursor}).status_code == 409
        (tmp_path / 'decision_forecast_evidence' / 'unsafe.json').symlink_to(tmp_path / 'absent')
        assert client.get('/v1/decisions/recent', params=params).status_code == 503


def test_unexpected_decoder_error_is_not_swallowed(tmp_path, monkeypatch):
    import astropilot.recent_decision_reader as module
    write(tmp_path, 'a')
    def fail(*args, **kwargs):
        raise RuntimeError('unexpected internal failure')
    monkeypatch.setattr(module, 'deserialize_decision_forecast_evidence', fail)
    with pytest.raises(RuntimeError, match='unexpected internal failure'):
        FileRecentDecisionReader(tmp_path, cursor_key=b'k' * 32).list_recent(**FILTERS)
