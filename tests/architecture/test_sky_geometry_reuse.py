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
