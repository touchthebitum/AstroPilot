from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from astral import Observer
import pytest
from astropilot.engines.sky_engine import SkyEngine

class UncachedSky(SkyEngine):
    def hour_geometry(self, *args):
        self._hour_geometry_cache.clear()
        return super().hour_geometry(*args)

def test_reuse_preserves_windows_and_weather_recalculation():
    observer = Observer(46.88, 6.54)
    target = {'ra': 10.6847, 'dec': 41.269, 'type':'galaxy', 'size_arcmin':190}
    start = datetime(2026, 10, 12, 22, tzinfo=ZoneInfo('Europe/Zurich'))
    hours = [{'time':start+timedelta(hours=i), 'cloud_cover':0,
        'cloud_cover_low':0, 'cloud_cover_mid':0, 'cloud_cover_high':0,
        'relative_humidity_2m':50, 'wind_speed_10m':5, 'visibility':30000,
        'precipitation':0, 'temperature_2m':10} for i in range(3)]
    cached, uncached = SkyEngine(), UncachedSky()
    def windows(engine):
        return engine.best_windows(hours, 5, observer, 46.88, 6.54,
            target_obj=target, min_altitude_deg=0)
    initial = windows(cached)
    assert initial
    assert initial == windows(uncached)
    hours[0]['cloud_cover_high'] = 100
    updated = windows(cached)
    assert updated == windows(uncached)
    assert updated != initial

def test_geometry_keys_keep_target_site_and_dst_fold_distinct():
    engine = SkyEngine();observer = Observer(46.88, 6.54)
    target = {'ra':10.6847, 'dec':41.269}
    wall = datetime(2026,10,25,2,tzinfo=ZoneInfo('Europe/Zurich'))
    first = engine.hour_geometry({'time':wall},observer,target,46.88,6.54)
    first['target_altitude'] = -999
    assert engine.hour_geometry({'time':wall},observer,target,46.88,6.54)['target_altitude'] != -999
    for time, site, obj in [(wall.replace(fold=1),observer,target),
            (wall,Observer(40.4,-3.7),target),
            (wall,observer,{'ra':83.82,'dec':-5.39})]:
        actual=engine.hour_geometry({'time':time},site,obj,site.latitude,site.longitude)
        expected=SkyEngine().hour_geometry({'time':time},site,obj,site.latitude,site.longitude)
        assert actual == pytest.approx(expected)
        assert actual['target_altitude'] != engine.hour_geometry({'time':wall},observer,target,46.88,6.54)['target_altitude']


def test_moon_reuse_matches_direct_astropy_across_targets_sites_and_dst(monkeypatch):
    import astropy.units as u
    from astropy.coordinates import SkyCoord, EarthLocation
    from astropy.time import Time
    import astropilot.engines.sky_engine as module
    direct_get_body = module.get_body
    calls = []
    def counted(*args, **kwargs):
        calls.append(1)
        return direct_get_body(*args, **kwargs)
    monkeypatch.setattr(module, 'get_body', counted)
    engine = SkyEngine()
    fold = datetime(2026, 10, 25, 2, 15, tzinfo=ZoneInfo('Europe/Zurich'))
    samples = [
        (10.6847, 41.269, fold, 46.88, 6.54),
        (83.82, -5.39, fold, 46.88, 6.54),
        (10.6847, 41.269, fold.replace(fold=1), 46.88, 6.54),
        (10.6847, 41.269, fold, 40.4, -3.7),
        (10.6847, 41.269, Time(fold), 46.88, 6.54),
    ]
    for ra, dec, instant, lat, lon in samples:
        expected = SkyCoord(ra=ra*u.deg, dec=dec*u.deg).separation(
            direct_get_body('moon', Time(instant), location=EarthLocation(lat=lat*u.deg, lon=lon*u.deg))
        ).deg
        assert engine.moon_target_separation(ra, dec, instant, lat, lon) == expected
    assert len(calls) == 3, 'same place and instant must share the exact Moon position across targets'
    SkyEngine().moon_target_separation(*samples[0])
    assert len(calls) == 4, 'independent engines must not share cached request data'
