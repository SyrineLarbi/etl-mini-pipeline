"""
Load the gold parquet into DuckDB.

Strategy: drop-and-replace the snapshot table. Cheap (5 rows), idempotent,
and gives a clean `loaded_at` per run.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / 'db' / 'warehouse.duckdb'

CREATE_SQL = """
CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.weather_summary (
    city          VARCHAR PRIMARY KEY,
    country       VARCHAR NOT NULL,
    temp_avg      DOUBLE,
    temp_min      DOUBLE,
    temp_max      DOUBLE,
    precip_total  DOUBLE,
    windy_days    BIGINT,
    rainy_days    BIGINT,
    days          BIGINT,
    loaded_at     TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold.weather_history (
    city          VARCHAR,
    country       VARCHAR,
    temp_avg      DOUBLE,
    temp_min      DOUBLE,
    temp_max      DOUBLE,
    precip_total  DOUBLE,
    windy_days    BIGINT,
    rainy_days    BIGINT,
    days          BIGINT,
    loaded_at     TIMESTAMP
);
"""


def load_gold(parquet_path: Path) -> dict:
    """
    Insert the latest gold snapshot.

    - `gold.weather_summary` keeps only the latest row per city (drop-and-replace).
    - `gold.weather_history` accumulates every run for time-travel queries.
    """
    parquet_path = Path(parquet_path)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(CREATE_SQL)
        loaded_at = datetime.utcnow()

        con.execute('DELETE FROM gold.weather_summary')
        con.execute(
            f"""
            INSERT INTO gold.weather_summary
            SELECT *, ? AS loaded_at FROM read_parquet('{parquet_path}')
            """,
            [loaded_at],
        )

        con.execute(
            f"""
            INSERT INTO gold.weather_history
            SELECT *, ? AS loaded_at FROM read_parquet('{parquet_path}')
            """,
            [loaded_at],
        )

        n_summary = con.execute('SELECT COUNT(*) FROM gold.weather_summary').fetchone()[0]
        n_history = con.execute('SELECT COUNT(*) FROM gold.weather_history').fetchone()[0]
    finally:
        con.close()

    return {
        'summary_rows': n_summary,
        'history_rows': n_history,
        'loaded_at':    loaded_at.isoformat(),
        'db_path':      str(DB_PATH),
    }
