"""Read-only locality lookup. No coordinates are saved or chosen automatically."""
import math
import requests

def find_locations(name):
    from astropilot.real_weather_context import current
    if current() is not None:
        from astropilot.weather_relay import fetch_locations_from_relay
        payload = fetch_locations_from_relay(name)
        return clean_locations(payload)
    try:
        response = requests.get("https://geocoding-api.open-meteo.com/v1/search",
            params={"name": name.strip(), "count": 8, "language": "fr", "format": "json"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
        return clean_locations(payload)
    except requests.RequestException as exc:
        raise OSError("location_provider_unavailable") from exc


def clean_locations(payload):
    if not isinstance(payload, dict) or payload.get("error"):
        raise ValueError("invalid_location_response")
    results = payload.get("results", [])
    if not isinstance(results, list):
        raise ValueError("invalid_location_results")
    clean = []
    for item in results[:8]:
        if not isinstance(item, dict):
            continue
        lat, lon = item.get("latitude"), item.get("longitude")
        if (isinstance(lat, bool) or isinstance(lon, bool) or
            not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or
            not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180):
            continue
        label = " — ".join(str(item[k])[:120] for k in ("name", "admin1", "country") if item.get(k))
        if label:
            clean.append({"label": label, "latitude": lat, "longitude": lon})
    return clean
