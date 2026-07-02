from datetime import date
from pathlib import Path
import json
import tempfile

import pandas as pd

from src.transform import to_bronze, to_silver, to_gold


def _fake_raw(tmp: Path) -> Path:
    payload = {
        'Tunis': {
            '__meta__': {'city': 'Tunis', 'country': 'TN', 'fetched_at': '2026-05-01'},
            'daily': {
                'time': ['2026-04-25', '2026-04-26'],
                'temperature_2m_max': [25.0, 26.0],
                'temperature_2m_min': [15.0, 14.0],
                'precipitation_sum':  [0.0,  3.4],
                'wind_speed_10m_max': [12.0, 35.0],
            },
        },
    }
    p = tmp / 'open-meteo-2026-05-01.json'
    p.write_text(json.dumps(payload))
    return p


def test_full_pipeline_smoke():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        raw = _fake_raw(tmp)
        bronze = to_bronze(raw, tmp / 'bronze')
        silver = to_silver(bronze, tmp / 'silver')
        gold   = to_gold(silver, tmp / 'gold')

        b = pd.read_parquet(bronze)
        s = pd.read_parquet(silver)
        g = pd.read_parquet(gold)

        assert len(b) == 2
        assert {'temp_avg', 'windy_day', 'rainy_day'} <= set(s.columns)
        assert g.iloc[0]['windy_days'] == 1
        assert g.iloc[0]['rainy_days'] == 1
        assert g.iloc[0]['days'] == 2


def _bad_raw(tmp: Path) -> Path:
    """Two rows: one valid, one where temp_min > temp_max (schema violation)."""
    payload = {
        'Tunis': {
            '__meta__': {'city': 'Tunis', 'country': 'TN', 'fetched_at': '2026-05-01'},
            'daily': {
                'time': ['2026-04-25', '2026-04-26'],
                'temperature_2m_max': [25.0, 15.0],   # 2nd row: max < min
                'temperature_2m_min': [15.0, 20.0],
                'precipitation_sum':  [0.0,  0.0],
                'wind_speed_10m_max': [12.0, 10.0],
            },
        },
    }
    p = tmp / 'open-meteo-2026-05-01.json'
    p.write_text(json.dumps(payload))
    return p


def test_bad_row_rejected_at_bronze():
    """A row that violates the Pydantic schema is skipped, not silently kept."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        raw = _bad_raw(tmp)
        bronze = to_bronze(raw, tmp / 'bronze')

        b = pd.read_parquet(bronze)
        # only the valid row survives; the temp_min > temp_max row is dropped
        assert len(b) == 1
        assert b.iloc[0]['day'] == date(2026, 4, 25)
