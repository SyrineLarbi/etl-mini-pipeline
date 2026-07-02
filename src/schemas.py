"""
Pydantic v2 models for the bronze layer.

These models are the single source of truth for the bronze-row shape.
The transform step parses raw JSON through these models; rows that don't
fit raise ValidationError, surface in logs, and aren't silently dropped.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class DailyForecast(BaseModel):
    """One row per (city, day)."""
    model_config = {'frozen': True, 'extra': 'forbid'}

    city: str = Field(..., min_length=2, max_length=80)
    country: str = Field(..., min_length=2, max_length=2)
    day: date

    temp_max:        float = Field(..., ge=-90, le=70, description='°C')
    temp_min:        float = Field(..., ge=-90, le=70, description='°C')
    precipitation_mm: float = Field(..., ge=0,    le=600)
    wind_max_kmh:    float = Field(..., ge=0,    le=400)

    fetched_at: date

    @field_validator('country')
    @classmethod
    def country_upper(cls, v: str) -> str:
        return v.upper()

    @field_validator('temp_min')
    @classmethod
    def min_le_max(cls, v: float, info):
        # Ensure consistency. If parsing in any order, info.data has prior fields.
        max_v = info.data.get('temp_max')
        if max_v is not None and v > max_v:
            raise ValueError(f'temp_min ({v}) > temp_max ({max_v})')
        return v


class ExtractMeta(BaseModel):
    """Slim metadata we attach during extract."""
    model_config = {'frozen': True}

    city: str
    country: str
    fetched_at: date
