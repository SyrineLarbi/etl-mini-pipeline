"""
Three-stage transform: bronze → silver → gold.

bronze: schema-validated rows (one per city/day).
silver: cleaned, with derived columns (temp_avg).
gold:   aggregated per city across the bronze window.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd
from pydantic import ValidationError

from .schemas import DailyForecast


# ─────────────────────────────────────────────────────────────────────
# bronze
# ─────────────────────────────────────────────────────────────────────
def to_bronze(raw_path: Path, bronze_dir: Path) -> Path:
    """Parse raw JSON, validate every row through Pydantic, write parquet."""
    bronze_dir = Path(bronze_dir)
    bronze_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(Path(raw_path).read_text())

    rows: list[DailyForecast] = []
    skipped: list[tuple[str, str, str]] = []

    for city, data in payload.items():
        meta = data.get('__meta__', {})
        country = meta.get('country', '??')
        fetched_at = meta.get('fetched_at')
        d = data.get('daily', {})
        for i, day in enumerate(d.get('time', [])):
            try:
                rows.append(DailyForecast(
                    city=city, country=country, day=day,
                    temp_max=         d['temperature_2m_max'][i],
                    temp_min=         d['temperature_2m_min'][i],
                    precipitation_mm= d['precipitation_sum'][i],
                    wind_max_kmh=     d['wind_speed_10m_max'][i],
                    fetched_at=fetched_at,
                ))
            except (ValidationError, TypeError, IndexError) as e:
                skipped.append((city, day, str(e)))

    if skipped:
        print(f'  ⚠ skipped {len(skipped)} row(s):')
        for city, day, msg in skipped[:5]:
            print(f'     {city} {day} → {msg.splitlines()[0]}')

    df = pd.DataFrame(r.model_dump() for r in rows)
    out = bronze_dir / (Path(raw_path).stem + '.parquet')
    df.to_parquet(out, index=False)
    return out


# ─────────────────────────────────────────────────────────────────────
# silver
# ─────────────────────────────────────────────────────────────────────
def to_silver(bronze_path: Path, silver_dir: Path) -> Path:
    silver_dir = Path(silver_dir)
    silver_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(bronze_path).dropna()
    df['temp_avg']      = (df['temp_max'] + df['temp_min']) / 2
    df['windy_day']     = df['wind_max_kmh'] > 30
    df['rainy_day']     = df['precipitation_mm'] > 1.0
    df['day']           = pd.to_datetime(df['day']).dt.date

    out = silver_dir / Path(bronze_path).name
    df.to_parquet(out, index=False)
    return out


# ─────────────────────────────────────────────────────────────────────
# gold
# ─────────────────────────────────────────────────────────────────────
def to_gold(silver_path: Path, gold_dir: Path) -> Path:
    gold_dir = Path(gold_dir)
    gold_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(silver_path)
    agg = (df.groupby(['city', 'country'], as_index=False)
             .agg(temp_avg=('temp_avg',         'mean'),
                  temp_min=('temp_min',         'min'),
                  temp_max=('temp_max',         'max'),
                  precip_total=('precipitation_mm', 'sum'),
                  windy_days=('windy_day',      'sum'),
                  rainy_days=('rainy_day',      'sum'),
                  days=('day',                  'nunique'))
          )
    agg['precip_total']  = agg['precip_total'].round(1)
    agg['temp_avg']      = agg['temp_avg'].round(1)

    out = gold_dir / Path(silver_path).name
    agg.to_parquet(out, index=False)
    return out


# ─────────────────────────────────────────────────────────────────────
# helper for the CLI
# ─────────────────────────────────────────────────────────────────────
def transform_all(raw_path: Path, bronze_dir: Path, silver_dir: Path, gold_dir: Path) -> Path:
    bronze = to_bronze(raw_path, bronze_dir)
    silver = to_silver(bronze, silver_dir)
    gold   = to_gold(silver, gold_dir)
    return gold
