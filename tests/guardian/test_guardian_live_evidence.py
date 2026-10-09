from datetime import datetime, timezone, timedelta
import ast
from pathlib import Path
import pytest
from astropilot.guardian_live_evidence import ProductionGuardianWeatherAdapter, GuardianAcquisitionError
from decision.services.guardian_service import assess_guardian

NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)

def payload():
    return {'current': {'time': NOW.timestamp(), 'interval': 900, 'rain': 0, 'showers': 0,
        'wind_speed_10m': 4, 'wind_gusts_10m': 8, 'relative_humidity_2m': 50,
        'temperature_2m': 15, 'dew_point_2m': 5},
        'current_units': {'time': 'unixtime', 'interval': 'seconds', 'rain': 'mm', 'showers': 'mm',
        'wind_speed_10m': 'km/h', 'wind_gusts_10m': 'km/h',
        'relative_humidity_2m': '%', 'temperature_2m': '°C', 'dew_point_2m': '°C'}}

def acquire(doc):
    calls = []
    adapter = ProductionGuardianWeatherAdapter(46, 7, timeout_seconds=2,
        transport=lambda **kw: calls.append(kw) or doc)
    result = adapter(NOW)
    assert len(calls) == 1
    assert calls[0]['timeout_seconds'] == 2
    return result

def test_complete_available_channels():
    result = acquire(payload())
    for name in ('rain_active', 'wind_kmh', 'gust_kmh', 'humidity_percent', 'dew_spread_c'):
        evidence = getattr(result, name)
        assert evidence.timestamp == NOW
        assert evidence.provenance == 'FORECAST'
        assert 'open-meteo' in evidence.source
    assert result.dew_spread_c.value == 10
    assert result.rain_eta_minutes is None
    assert assess_guardian(result, now=NOW).risk_level.name == 'UNKNOWN'

@pytest.mark.parametrize('field,channel', [('rain','rain_active'), ('wind_gusts_10m','gust_kmh'),
    ('relative_humidity_2m','humidity_percent'), ('dew_point_2m','dew_spread_c')])
def test_missing(field, channel):
    doc = payload(); del doc['current'][field]
    assert getattr(acquire(doc), channel) is None

@pytest.mark.parametrize('value', [None, True, '2', float('nan'), float('inf'), -1, 501])
def test_invalid_wind(value):
    doc = payload(); doc['current']['wind_speed_10m'] = value
    assert acquire(doc).wind_kmh is None

def test_rain_and_stale():
    doc = payload(); doc['current']['rain'] = 1
    assert acquire(doc).rain_active.value is True
    doc['current']['time'] -= 3600
    result = acquire(doc)
    assert result.rain_active.timestamp == NOW - timedelta(hours=1)
    assert assess_guardian(result, now=NOW).risk_level.name == 'UNKNOWN'

def test_timeout_no_retry():
    calls = []
    def fail(**kw):
        calls.append(kw); raise TimeoutError('secret')
    adapter = ProductionGuardianWeatherAdapter(46, 7, transport=fail)
    with pytest.raises(GuardianAcquisitionError, match='acquisition_failed') as exc:
        adapter(NOW)
    assert 'secret' not in str(exc.value)
    assert len(calls) == 1

@pytest.mark.parametrize('field,value', [('time',None), ('time',True), ('interval',0)])
def test_invalid_envelope(field,value):
    doc = payload(); doc['current'][field] = value
    with pytest.raises(GuardianAcquisitionError): acquire(doc)

def test_architecture():
    tree = ast.parse(Path('astropilot/guardian_live_evidence.py').read_text())
    imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(any(b in name for b in ('tonight','opportunity','field_lab','thread','subprocess')) for name in imports)

def test_real_deadline_restores_handler():
    import signal
    from astropilot.guardian_live_evidence import _deadline
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(TimeoutError):
        with _deadline(.01):
            signal.pause()
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)

@pytest.mark.parametrize('field', ['rain', 'wind_speed_10m', 'relative_humidity_2m', 'temperature_2m'])
def test_wrong_units(field):
    doc = payload(); doc['current_units'][field] = 'wrong'
    result = acquire(doc)
    channel = {'rain':'rain_active', 'wind_speed_10m':'wind_kmh',
               'relative_humidity_2m':'humidity_percent', 'temperature_2m':'dew_spread_c'}[field]
    assert getattr(result, channel) is None

def test_periodic_failure_is_error():
    from decision.runners.guardian_periodic_runner import GuardianPeriodicRunner
    from decision.runners.guardian_runner import GuardianRunner
    def fail(**kw): raise TimeoutError()
    runner = GuardianPeriodicRunner(evidence_provider=ProductionGuardianWeatherAdapter(46,7,transport=fail),
        session_context_provider=lambda _: None, guardian_runner=GuardianRunner())
    result = runner.run_cycle(logical_time=NOW)
    assert result.status.value == 'ERROR'
    assert result.errors == ('evidence_provider_error',)


def test_transport_deadline_covers_blocked_connect(monkeypatch):
    import signal
    from astropilot import guardian_live_evidence as live
    calls = []
    class BlockedConnection:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args):
            calls.append('request'); signal.pause()
        def close(self): calls.append('close')
    monkeypatch.setattr(live, 'HTTPSConnection', BlockedConnection)
    with pytest.raises(GuardianAcquisitionError):
        live.ProductionGuardianWeatherAdapter(46,7,timeout_seconds=.01)(NOW)
    assert calls == ['request', 'close']


def test_no_workers_created():
    import threading
    import multiprocessing
    before = threading.enumerate(), multiprocessing.active_children()
    acquire(payload())
    assert (threading.enumerate(), multiprocessing.active_children()) == before


@pytest.mark.parametrize('channel,field,bad', [('humidity_percent','relative_humidity_2m',101),
    ('rain_active','rain',-1), ('dew_spread_c','dew_point_2m',71), ('gust_kmh','wind_gusts_10m',-1)])
def test_out_of_range(channel,field,bad):
    doc=payload(); doc['current'][field]=bad
    assert getattr(acquire(doc),channel) is None


def test_showers_and_partial_rain():
    doc = payload(); doc['current']['showers'] = 1
    assert acquire(doc).rain_active.value is True
    del doc['current']['rain']
    assert acquire(doc).rain_active.value is True
    doc['current']['showers'] = 0
    assert acquire(doc).rain_active is None


def test_forecast_probability_never_substituted():
    doc = payload(); del doc['current']['rain']; del doc['current']['showers']
    doc['current']['precipitation_probability'] = 0
    doc['current']['precipitation'] = 0
    assert acquire(doc).rain_active is None
    assert acquire(doc).rain_eta_minutes is None


def test_transport_one_request_no_redirect(monkeypatch):
    from astropilot import guardian_live_evidence as live
    import json
    calls = []
    class Socket:
        def settimeout(self, value): assert 0 < value <= 2
    class Response:
        status = 200
        def __init__(self): self.body = [json.dumps(payload()).encode(), b'']
        def read1(self, size): return self.body.pop(0)
    class Connection:
        sock = Socket()
        def __init__(self, host, timeout): assert host == 'api.open-meteo.com'; assert timeout == 2
        def request(self, method, path): calls.append((method,path))
        def getresponse(self): return Response()
        def close(self): calls.append('close')
    monkeypatch.setattr(live, 'HTTPSConnection', Connection)
    assert live.ProductionGuardianWeatherAdapter(46,7,timeout_seconds=2)(NOW).wind_kmh.value == 4
    assert len(calls) == 2
    assert calls[0][0] == 'GET'
    assert 'current=rain%2Cshowers' in calls[0][1]
    assert calls[1] == 'close'


def test_alarm_unavailable_fails_closed(monkeypatch):
    from astropilot import guardian_live_evidence as live
    monkeypatch.delattr(live.signal, 'setitimer')
    with pytest.raises(GuardianAcquisitionError):
        live.ProductionGuardianWeatherAdapter(46,7)(NOW)
