from astral import LocationInfo
from astral.moon import moonrise, moonset
from datetime import date
from zoneinfo import ZoneInfo

city = LocationInfo(
    "Sion",
    "Switzerland",
    "Europe/Zurich",
    46.2333,
    7.3667
)

today = date.today()

print(
    "Lever lune :",
    moonrise(city.observer, today, tzinfo=ZoneInfo("Europe/Zurich"))
)

print(
    "Coucher lune :",
    moonset(city.observer, today, tzinfo=ZoneInfo("Europe/Zurich"))
)
