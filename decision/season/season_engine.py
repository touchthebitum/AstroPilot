from datetime import datetime
from zoneinfo import ZoneInfo
from decision.season.season_data import SEASON_WINDOWS, TIMEZONE


class SeasonEngine:

    @staticmethod
    def remaining_good_nights(target):
        days = SeasonEngine.remaining_days(target)

        if days is None:
            return 10

        return max(1, int(days / 3))
    
    @staticmethod
    def remaining_days(target):
        return SeasonEngine.season_days_remaining(target)
    
    @staticmethod
    def season_days_remaining(obj):
        today = datetime.now(ZoneInfo(TIMEZONE)).date()
        current_month = today.month

        if isinstance(obj, str):
            name = obj
        else:
            name = obj.get("catalog_key") or obj.get("name")

        season=SEASON_WINDOWS.get(name)

        if not season:
            return None

        months = season.get("best_months", []) + season.get("ok_months", [])

        if not months:
            return None

        if current_month not in months:
            return 0

        future_months = [m for m in months if m >= current_month]

        if future_months:
            last_month = max(future_months)
        else:
            last_month = max(months)

        year = today.year

        if last_month < current_month:
            year += 1

        if last_month == 12:
            season_end = datetime(year + 1, 1, 1).date()
        else:
            season_end = datetime(year, last_month + 1, 1).date()

        return max(0, (season_end - today).days)