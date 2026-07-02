"""
Streamlit dashboard over the gold-layer weather warehouse.

Run it:
    streamlit run src/dashboard.py

Reads db/warehouse.duckdb (populated by `python -m src.pipeline run`) and
renders the latest per-city snapshot plus any accumulated history.
"""
from __future__ import annotations

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "db" / "warehouse.duckdb"

# ── temperature palette (cool → warm → hot), matches the ETL theme ──────
TEMP_SCALE = alt.Scale(
    domain=[16, 28, 41],
    range=["#4f9fe0", "#f0a63c", "#e14b3a"],
)

st.set_page_config(page_title="Weather ETL · Gold", page_icon="🌡️", layout="wide")


@st.cache_data(ttl=30)
def load_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read summary + history from DuckDB (read-only)."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        summary = con.execute(
            "SELECT * FROM gold.weather_summary ORDER BY temp_avg DESC"
        ).df()
        history = con.execute(
            "SELECT * FROM gold.weather_history ORDER BY loaded_at, city"
        ).df()
    finally:
        con.close()
    return summary, history


# ── guard: warehouse must exist ─────────────────────────────────────────
if not DB_PATH.exists():
    st.error("No warehouse yet. Run `python -m src.pipeline run` first.")
    st.stop()

summary, history = load_tables()

st.title("🌡️ Weather ETL — Gold Layer")
st.caption(
    "Analytics-ready output of `gold.weather_summary`, aggregated over a 7-day "
    "window per city. Source: Open-Meteo → bronze → silver → gold → DuckDB."
)

if summary.empty:
    st.warning("The gold table is empty. Run the pipeline to populate it.")
    st.stop()

# ── summary metrics ─────────────────────────────────────────────────────
hottest = summary.loc[summary["temp_max"].idxmax()]
wettest = summary.loc[summary["precip_total"].idxmax()]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Cities tracked", int(summary["city"].nunique()))
c2.metric("Peak temperature", f"{hottest['temp_max']:.1f} °C", help=f"{hottest['city']}")
c3.metric("Wettest city", f"{wettest['precip_total']:.1f} mm", help=f"{wettest['city']} · {int(wettest['rainy_days'])} rainy days")
c4.metric("Mean of city averages", f"{summary['temp_avg'].mean():.1f} °C")

st.divider()

# ── city comparison ─────────────────────────────────────────────────────
st.subheader("City comparison")
metric = st.radio(
    "Metric",
    ["Temperature", "Precipitation"],
    horizontal=True,
    label_visibility="collapsed",
)

if metric == "Temperature":
    # min → max range bar with an average tick, colored by average temp
    base = alt.Chart(summary).encode(
        y=alt.Y("city:N", sort="-x", title=None),
    )
    rng = base.mark_bar(height=10, cornerRadius=5).encode(
        x=alt.X("temp_min:Q", title="°C", scale=alt.Scale(zero=False)),
        x2="temp_max:Q",
        color=alt.Color("temp_avg:Q", scale=TEMP_SCALE, title="avg °C"),
        tooltip=[
            "city", "country",
            alt.Tooltip("temp_min:Q", title="min °C"),
            alt.Tooltip("temp_avg:Q", title="avg °C"),
            alt.Tooltip("temp_max:Q", title="max °C"),
        ],
    )
    avg_tick = base.mark_tick(thickness=2, size=18, color="#e7ecf3").encode(
        x="temp_avg:Q"
    )
    st.altair_chart((rng + avg_tick).properties(height=280), use_container_width=True)
else:
    chart = (
        alt.Chart(summary)
        .mark_bar(cornerRadius=4, color="#33c2bd")
        .encode(
            y=alt.Y("city:N", sort="-x", title=None),
            x=alt.X("precip_total:Q", title="mm (7-day total)"),
            tooltip=[
                "city", "country",
                alt.Tooltip("precip_total:Q", title="precip mm"),
                alt.Tooltip("rainy_days:Q", title="rainy days"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(chart, use_container_width=True)

# ── raw snapshot ────────────────────────────────────────────────────────
st.subheader("Station readouts")
st.dataframe(
    summary,
    hide_index=True,
    use_container_width=True,
    column_config={
        "temp_avg": st.column_config.NumberColumn("avg °C", format="%.1f"),
        "temp_min": st.column_config.NumberColumn("min °C", format="%.1f"),
        "temp_max": st.column_config.NumberColumn("max °C", format="%.1f"),
        "precip_total": st.column_config.NumberColumn("precip mm", format="%.1f"),
    },
)

# ── history / time-travel (only meaningful after multiple loads) ────────
n_loads = history["loaded_at"].nunique() if not history.empty else 0
if n_loads > 1:
    st.subheader("History")
    st.caption(f"{n_loads} loads recorded in `gold.weather_history`.")
    line = (
        alt.Chart(history)
        .mark_line(point=True)
        .encode(
            x=alt.X("loaded_at:T", title="loaded at"),
            y=alt.Y("temp_avg:Q", title="avg °C", scale=alt.Scale(zero=False)),
            color=alt.Color("city:N", title="city"),
            tooltip=["city", "loaded_at:T", alt.Tooltip("temp_avg:Q", format=".1f")],
        )
        .properties(height=300)
    )
    st.altair_chart(line, use_container_width=True)
else:
    st.info(
        "Run the pipeline again to accumulate history — the time-travel chart "
        "appears once there's more than one load."
    )
