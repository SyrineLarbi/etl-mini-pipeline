"""
Extract daily weather aggregates from Open-Meteo for a fixed list of cities.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

API = 'https://api.open-meteo.com/v1/forecast'

# (city, latitude, longitude, country_iso2)
CITIES: list[tuple[str, float, float, str]] = [
    ('Tunis',  36.8065, 10.1815, 'TN'),
    ('Lisbon', 38.7223, -9.1393, 'PT'),
    ('Paris',  48.8566,  2.3522, 'FR'),
    ('Cairo',  30.0444, 31.2357, 'EG'),
    ('Lagos',   6.5244,  3.3792, 'NG'),
]

DAILY_VARS = ','.join([
    'temperature_2m_max',
    'temperature_2m_min',
    'precipitation_sum',
    'wind_speed_10m_max',
])


def extract(out_dir: Path | str) -> Path:
    """
    Hit Open-Meteo for every city, write {city: response} to one JSON file
    named after today's date. Return the path written.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    out_path = out_dir / f'open-meteo-{today}.json'

    payload: dict[str, dict] = {}
    with httpx.Client(timeout=30) as client:
        for city, lat, lon, country in CITIES:
            r = client.get(API, params={
                'latitude':       lat,
                'longitude':      lon,
                'daily':          DAILY_VARS,
                'timezone':       'auto',
                'past_days':      7,
                'forecast_days':  0,
            })
            r.raise_for_status()
            data = r.json()
            data['__meta__'] = {'city': city, 'country': country, 'fetched_at': today}
            payload[city] = data

    out_path.write_text(json.dumps(payload, indent=2))
    return out_path


if __name__ == '__main__':
    path = extract('data/raw')
    print(f'Wrote {path}  ({path.stat().st_size // 1024} KB)')
