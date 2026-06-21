from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from include.swpc.classifier import classify_g, normalize_payload

JsonObject = Mapping[str, Any]
RawPayload = JsonObject | Sequence[Any]
ForecastRecord = dict[str, Any]

FORECAST_RECORD_COLUMNS = (
    "record_hash",
    "endpoint",
    "product_type",
    "valid_start",
    "valid_end",
    "issued_at",
    "observed",
    "severity",
    "value",
    "units",
    "record",
    "raw_payload_id",
    "source",
    "fetched_at",
)

NOAA_SCALE_FAMILIES = ("G", "S", "R")
NOAA_SCALE_LABELS = {
    "G": {
        0: "None",
        1: "G1 Minor",
        2: "G2 Moderate",
        3: "G3 Strong",
        4: "G4 Severe",
        5: "G5 Extreme",
    },
    "S": {
        0: "None",
        1: "S1 Minor",
        2: "S2 Moderate",
        3: "S3 Strong",
        4: "S4 Severe",
        5: "S5 Extreme",
    },
    "R": {
        0: "None",
        1: "R1 Minor",
        2: "R2 Moderate",
        3: "R3 Strong",
        4: "R4 Severe",
        5: "R5 Extreme",
    },
}


def normalize_forecast_records(
    endpoint: str,
    payload: RawPayload,
    fetched_at: Any,
    *,
    raw_payload_id: Any | None = None,
    source: str | None = None,
) -> list[ForecastRecord]:
    """Normalize forecast-like SWPC products for ``swpc_forecast_records``.

    The normalizer is conservative: it emits official scale rows, alert rows,
    Kp history/forecast windows, and selected solar-wind measurement metrics
    whose product type can be consumed by event-window logic.
    """

    fetched_at_text = _normalize_datetime(fetched_at)
    rows = normalize_payload(payload, endpoint=endpoint)
    endpoint_key = endpoint.lower()

    if _is_noaa_scales_endpoint(endpoint_key):
        records = _normalize_noaa_scale_rows(rows)
    elif _is_alerts_endpoint(endpoint_key):
        records = _normalize_alert_rows(rows)
    elif _is_kp_endpoint(endpoint_key):
        records = _normalize_kp_rows(endpoint_key, rows)
    elif _is_solar_wind_endpoint(endpoint_key):
        records = _normalize_solar_wind_rows(endpoint_key, rows)
    else:
        records = []

    return [
        _forecast_record(
            endpoint=endpoint,
            raw_payload_id=raw_payload_id,
            source=source,
            fetched_at=fetched_at_text,
            **record,
        )
        for record in records
    ]


def _normalize_noaa_scale_rows(rows: Sequence[JsonObject]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        valid_start = _timestamp_from_date_parts(row.get("DateStamp"), row.get("TimeStamp"))
        valid_end = _add_time(valid_start, days=1)
        window_offset = _to_float(row.get("window_offset"))

        for family in NOAA_SCALE_FAMILIES:
            value = row.get(family)
            severity = _official_scale_level(value)
            record = {
                **dict(row),
                "scale_family": family,
                "scale": f"{family}{severity}" if severity > 0 else None,
                "scale_level": severity,
                "scale_label": NOAA_SCALE_LABELS[family][severity],
            }
            records.append(
                {
                    "product_type": f"noaa_scale_{family.lower()}",
                    "valid_start": valid_start,
                    "valid_end": valid_end,
                    "issued_at": None,
                    "observed": window_offset <= 0 if window_offset is not None else None,
                    "severity": severity,
                    "value": severity,
                    "units": f"NOAA {family} scale",
                    "record": record,
                }
            )
    return records


def _normalize_alert_rows(rows: Sequence[JsonObject]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        issued_at = _first_datetime(row, ("issue_datetime", "issued_at", "time_tag"))
        severity = _message_severity(row)
        records.append(
            {
                "product_type": "alert",
                "valid_start": issued_at,
                "valid_end": None,
                "issued_at": issued_at,
                "observed": None,
                "severity": severity,
                "value": None,
                "units": None,
                "record": dict(row),
            }
        )
    return records


def _normalize_kp_rows(endpoint_key: str, rows: Sequence[JsonObject]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    forecast_product = "forecast" in endpoint_key
    product_type = "kp_forecast" if forecast_product else "kp_history"

    for row in rows:
        valid_start = _first_datetime(row, ("time_tag", "valid_start", "start_time"))
        valid_end = _first_datetime(row, ("valid_end", "end_time"))
        if valid_end is None:
            valid_end = _add_time(valid_start, hours=3)

        value = _first_number(row, ("kp", "Kp", "kp_index", "estimated_kp"))
        scale = _scale_from_record(row, value)
        severity = _scale_level(scale)
        record = {
            **dict(row),
            "derived_noaa_scale": scale,
            "derived_scale_level": severity,
        }

        records.append(
            {
                "product_type": product_type,
                "valid_start": valid_start,
                "valid_end": valid_end,
                "issued_at": _first_datetime(row, ("issue_datetime", "issued_at")),
                "observed": _observed_value(row, default=not forecast_product),
                "severity": severity,
                "value": value,
                "units": "Kp",
                "record": record,
            }
        )
    return records


def _normalize_solar_wind_rows(
    endpoint_key: str,
    rows: Sequence[JsonObject],
) -> list[dict[str, Any]]:
    metric_specs: tuple[tuple[str, str, str], ...]
    if "mag" in endpoint_key:
        metric_specs = (
            ("bz_gsm", "solar_wind_mag_bz_gsm", "nT"),
            ("bt", "solar_wind_mag_bt", "nT"),
        )
    elif "wind" in endpoint_key or "plasma" in endpoint_key:
        metric_specs = (
            ("proton_speed", "solar_wind_plasma_speed", "km/s"),
            ("speed", "solar_wind_plasma_speed", "km/s"),
            ("proton_density", "solar_wind_plasma_density", "p/cm^3"),
            ("density", "solar_wind_plasma_density", "p/cm^3"),
            ("proton_temperature", "solar_wind_plasma_temperature", "K"),
            ("temperature", "solar_wind_plasma_temperature", "K"),
        )
    else:
        return []

    records: list[dict[str, Any]] = []
    for row in rows:
        valid_start = _first_datetime(row, ("time_tag", "valid_start"))
        for field, product_type, units in metric_specs:
            value = _to_float(row.get(field))
            if value is None:
                continue
            records.append(
                {
                    "product_type": product_type,
                    "valid_start": valid_start,
                    "valid_end": None,
                    "issued_at": None,
                    "observed": True,
                    "severity": None,
                    "value": value,
                    "units": units,
                    "record": {**dict(row), "metric": field},
                }
            )
    return records


def _forecast_record(
    *,
    endpoint: str,
    product_type: str,
    valid_start: str | None,
    valid_end: str | None,
    issued_at: str | None,
    observed: bool | None,
    severity: int | None,
    value: float | int | None,
    units: str | None,
    record: JsonObject,
    raw_payload_id: Any | None,
    source: str | None,
    fetched_at: str | None,
) -> ForecastRecord:
    row = {
        "endpoint": endpoint,
        "product_type": product_type,
        "valid_start": valid_start,
        "valid_end": valid_end,
        "issued_at": issued_at,
        "observed": observed,
        "severity": severity,
        "value": value,
        "units": units,
        "record": _json_safe(record),
    }
    row["record_hash"] = _record_hash(row)
    row["raw_payload_id"] = raw_payload_id
    row["source"] = source
    row["fetched_at"] = fetched_at
    return {column: row[column] for column in FORECAST_RECORD_COLUMNS}


def _record_hash(row: JsonObject) -> str:
    stable = {
        key: row[key]
        for key in (
            "endpoint",
            "product_type",
            "valid_start",
            "valid_end",
            "issued_at",
            "observed",
            "severity",
            "value",
            "units",
            "record",
        )
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_noaa_scales_endpoint(endpoint_key: str) -> bool:
    return endpoint_key.rstrip("/").endswith("/products/noaa-scales.json")


def _is_alerts_endpoint(endpoint_key: str) -> bool:
    return endpoint_key.rstrip("/").endswith("/products/alerts.json")


def _is_kp_endpoint(endpoint_key: str) -> bool:
    return (
        "planetary_k_index" in endpoint_key
        or "planetary-k-index" in endpoint_key
    )


def _is_solar_wind_endpoint(endpoint_key: str) -> bool:
    return (
        "rtsw_mag" in endpoint_key
        or "rtsw_wind" in endpoint_key
        or "/solar-wind/mag" in endpoint_key
        or "/solar-wind/plasma" in endpoint_key
    )


def _timestamp_from_date_parts(date_value: Any, time_value: Any) -> str | None:
    if date_value is None:
        return None
    if time_value is None:
        return _normalize_datetime(date_value)
    return _normalize_datetime(f"{date_value} {time_value}")


def _first_datetime(row: JsonObject, fields: Sequence[str]) -> str | None:
    for field in fields:
        if field in row and row[field] is not None:
            parsed = _normalize_datetime(row[field])
            if parsed is not None:
                return parsed
    return None


def _normalize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        timestamp = value
    elif isinstance(value, dt.date):
        timestamp = dt.datetime.combine(value, dt.time.min, tzinfo=dt.UTC)
    elif isinstance(value, str):
        timestamp = _parse_datetime(value)
        if timestamp is None:
            return value.strip() or None
    else:
        return None

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.UTC)
    return timestamp.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: str) -> dt.datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T")
    try:
        return dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _add_time(
    value: str | None,
    *,
    hours: int = 0,
    days: int = 0,
) -> str | None:
    if value is None:
        return None
    timestamp = _parse_datetime(value)
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.UTC)
    timestamp += dt.timedelta(hours=hours, days=days)
    return timestamp.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _first_number(row: JsonObject, fields: Sequence[str]) -> float | None:
    for field in fields:
        value = _to_float(row.get(field))
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    if not isinstance(value, str):
        return None

    stripped = value.strip().replace(",", "")
    match = re.fullmatch(r"(\d)([+\-oO])", stripped)
    if match:
        base = float(match.group(1))
        suffix = match.group(2).lower()
        if suffix == "+":
            return base + (1 / 3)
        if suffix == "-":
            return base - (1 / 3)
        return base

    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", stripped):
        return None
    number = float(stripped)
    return number if math.isfinite(number) else None


def _official_scale_level(value: Any) -> int:
    if isinstance(value, Mapping):
        for key in ("Scale", "scale", "value", "Value"):
            if key in value:
                return _official_scale_level(value[key])
        return 0

    number = _to_float(value)
    if number is None:
        return 0
    return min(max(int(number), 0), 5)


def _scale_from_record(row: JsonObject, kp_value: Any) -> str | None:
    for field in ("noaa_scale", "scale", "g_scale"):
        value = row.get(field)
        if isinstance(value, str):
            match = re.search(r"G[1-5]", value.upper())
            if match:
                return match.group(0)
        level = _official_scale_level(value)
        if level > 0:
            return f"G{level}"
    return classify_g(kp_value)


def _scale_level(scale: str | None) -> int:
    if scale is None:
        return 0
    match = re.fullmatch(r"[GSR](\d)", scale)
    return int(match.group(1)) if match else 0


def _message_severity(row: JsonObject) -> int | None:
    text = " ".join(str(value) for value in row.values() if value is not None)
    levels = [int(match.group(1)) for match in re.finditer(r"\b[GSR]([1-5])\b", text)]
    return max(levels) if levels else None


def _observed_value(row: JsonObject, *, default: bool) -> bool:
    if "observed" not in row or row["observed"] is None:
        return default
    value = row["observed"]
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "yes", "y", "1", "observed"}:
        return True
    if normalized in {"false", "f", "no", "n", "0", "forecast"}:
        return False
    return default


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dt.datetime | dt.date):
        return _normalize_datetime(value)
    return value


__all__ = [
    "FORECAST_RECORD_COLUMNS",
    "ForecastRecord",
    "normalize_forecast_records",
]
