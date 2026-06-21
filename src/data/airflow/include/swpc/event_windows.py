from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


TimeseriesRecord = Mapping[str, Any]
EventWindow = dict[str, Any]

EVENT_WINDOW_PRODUCT_TYPES = (
    "kp_forecast",
    "kp_history",
    "noaa_scale_g",
    "noaa_scale_s",
    "noaa_scale_r",
    "solar_wind_mag_bz_gsm",
    "solar_wind_mag_bt",
    "solar_wind_plasma_speed",
    "solar_wind_plasma_density",
)


@dataclass(frozen=True)
class RiskInterval:
    event_type: str
    source_product: str
    source_endpoint: str | None
    start: dt.datetime
    end: dt.datetime
    peak_time: dt.datetime
    value: float | None
    severity: int
    threshold_value: float | None
    units: str | None
    observed: bool | None
    fetched_at: dt.datetime | None
    record_id: str | None
    product_type: str
    evidence: dict[str, Any]


def derive_space_weather_event_windows(
    records: Sequence[TimeseriesRecord],
    *,
    now: Any | None = None,
    merge_gap: dt.timedelta = dt.timedelta(minutes=5),
    stale_after: dt.timedelta = dt.timedelta(hours=6),
) -> list[EventWindow]:
    """Build operational event windows from normalized SWPC time-series rows."""

    now_timestamp = _parse_datetime(now) or dt.datetime.now(dt.UTC)
    intervals = [
        *(_index_risk_interval(record) for record in records),
        *_solar_wind_coupling_intervals(records),
    ]
    usable = [interval for interval in intervals if interval is not None]

    windows: list[EventWindow] = []
    for group_key, group_intervals in _group_intervals(usable).items():
        event_type, source_product = group_key
        ordered = sorted(group_intervals, key=lambda item: item.start)
        if not ordered:
            continue

        current: list[RiskInterval] = []
        current_end: dt.datetime | None = None
        for interval in ordered:
            if current and current_end is not None and interval.start > current_end + merge_gap:
                windows.append(_event_window(current, now_timestamp, stale_after))
                current = []
                current_end = None
            current.append(interval)
            current_end = max(current_end or interval.end, interval.end)

        if current:
            windows.append(_event_window(current, now_timestamp, stale_after))

    return sorted(windows, key=lambda row: (row["window_start"], row["event_type"]))


def summarize_event_windows(rows: Sequence[EventWindow]) -> dict[str, Any]:
    return {
        "event_window_count": len(rows),
        "event_types": sorted({str(row["event_type"]) for row in rows}),
        "active_count": sum(1 for row in rows if row.get("status") == "active"),
        "future_count": sum(1 for row in rows if row.get("status") == "future"),
        "ended_count": sum(1 for row in rows if row.get("status") == "ended"),
    }


def _index_risk_interval(record: TimeseriesRecord) -> RiskInterval | None:
    product_type = str(record.get("product_type") or "")
    severity = _to_int(record.get("severity"))
    if severity is None or severity < 1:
        return None

    if product_type in {"kp_forecast", "kp_history", "noaa_scale_g"}:
        event_type = "geomagnetic_storm_risk"
        source_product = "geomagnetic_index"
        threshold = 1.0
    elif product_type == "noaa_scale_s":
        event_type = "radiation_storm_risk"
        source_product = "noaa_scale_s"
        threshold = 1.0
    elif product_type == "noaa_scale_r":
        event_type = "radio_blackout_risk"
        source_product = "noaa_scale_r"
        threshold = 1.0
    else:
        return None

    start = _parse_datetime(record.get("valid_start"))
    if start is None:
        return None
    end = _parse_datetime(record.get("valid_end")) or start + dt.timedelta(hours=3)
    if end <= start:
        end = start + dt.timedelta(minutes=1)

    return RiskInterval(
        event_type=event_type,
        source_product=source_product,
        source_endpoint=_text_or_none(record.get("endpoint")),
        start=start,
        end=end,
        peak_time=start,
        value=_to_float(record.get("value")),
        severity=severity,
        threshold_value=threshold,
        units=_text_or_none(record.get("units")),
        observed=_to_bool_or_none(record.get("observed")),
        fetched_at=_parse_datetime(record.get("fetched_at")),
        record_id=_text_or_none(record.get("id")),
        product_type=product_type,
        evidence=_compact_record(record),
    )


def _solar_wind_coupling_intervals(
    records: Sequence[TimeseriesRecord],
) -> list[RiskInterval]:
    by_timestamp: dict[dt.datetime, dict[str, TimeseriesRecord]] = defaultdict(dict)
    for record in records:
        product_type = str(record.get("product_type") or "")
        if product_type not in {
            "solar_wind_mag_bz_gsm",
            "solar_wind_mag_bt",
            "solar_wind_plasma_speed",
            "solar_wind_plasma_density",
        }:
            continue
        timestamp = _parse_datetime(record.get("valid_start"))
        if timestamp is None:
            continue
        by_timestamp[timestamp][product_type] = record

    intervals: list[RiskInterval] = []
    for timestamp, metrics in by_timestamp.items():
        bz = _to_float(metrics.get("solar_wind_mag_bz_gsm", {}).get("value"))
        bt = _to_float(metrics.get("solar_wind_mag_bt", {}).get("value"))
        speed = _to_float(metrics.get("solar_wind_plasma_speed", {}).get("value"))
        density = _to_float(metrics.get("solar_wind_plasma_density", {}).get("value"))

        severity = 0
        if bz is not None and bz <= -5:
            severity += 1
        if bz is not None and bz <= -10:
            severity += 1
        if bt is not None and bt >= 15:
            severity += 1
        if speed is not None and speed >= 500:
            severity += 1
        if density is not None and density >= 10:
            severity += 1
        severity = min(severity, 5)
        if severity < 1:
            continue

        representative = (
            metrics.get("solar_wind_mag_bz_gsm")
            or metrics.get("solar_wind_mag_bt")
            or next(iter(metrics.values()))
        )
        intervals.append(
            RiskInterval(
                event_type="solar_wind_coupling_risk",
                source_product="solar_wind_observed",
                source_endpoint=_text_or_none(representative.get("endpoint")),
                start=timestamp,
                end=timestamp + dt.timedelta(minutes=1),
                peak_time=timestamp,
                value=bz,
                severity=severity,
                threshold_value=-5.0,
                units="nT",
                observed=True,
                fetched_at=_parse_datetime(representative.get("fetched_at")),
                record_id=_text_or_none(representative.get("id")),
                product_type="solar_wind_coupling",
                evidence={
                    "bz_gsm": bz,
                    "bt": bt,
                    "proton_speed": speed,
                    "proton_density": density,
                    "source_records": [
                        _compact_record(metric)
                        for metric in metrics.values()
                    ],
                },
            )
        )
    return intervals


def _group_intervals(
    intervals: Sequence[RiskInterval],
) -> dict[tuple[str, str], list[RiskInterval]]:
    grouped: dict[tuple[str, str], list[RiskInterval]] = defaultdict(list)
    for interval in intervals:
        grouped[(interval.event_type, interval.source_product)].append(interval)
    return grouped


def _event_window(
    intervals: Sequence[RiskInterval],
    now: dt.datetime,
    stale_after: dt.timedelta,
) -> EventWindow:
    start = min(interval.start for interval in intervals)
    end = max(interval.end for interval in intervals)
    peak = max(
        intervals,
        key=lambda interval: (
            interval.severity,
            abs(interval.value) if interval.value is not None else -1,
        ),
    )
    event_type = intervals[0].event_type
    source_product = intervals[0].source_product
    confidence = _confidence(intervals, now, stale_after)
    status = _status(start, end, now)
    source_endpoints = sorted(
        {
            interval.source_endpoint
            for interval in intervals
            if interval.source_endpoint is not None
        }
    )
    source_products = sorted({interval.product_type for interval in intervals})
    evidence = {
        "record_count": len(intervals),
        "source_products": source_products,
        "source_endpoints": source_endpoints,
        "observed_count": sum(1 for interval in intervals if interval.observed is True),
        "forecast_count": sum(1 for interval in intervals if interval.observed is False),
        "threshold_value": peak.threshold_value,
        "sample": [interval.evidence for interval in intervals[:25]],
    }

    row = {
        "event_key": _event_key(event_type, source_product, start),
        "event_type": event_type,
        "source_product": source_product,
        "source_endpoint": ",".join(source_endpoints) if source_endpoints else None,
        "window_start": _format_datetime(start),
        "peak_time": _format_datetime(peak.peak_time),
        "window_end": _format_datetime(end),
        "peak_value": peak.value,
        "peak_severity": peak.severity,
        "threshold_value": peak.threshold_value,
        "units": peak.units,
        "confidence": confidence,
        "status": status,
        "evidence": evidence,
    }
    return row


def _confidence(
    intervals: Sequence[RiskInterval],
    now: dt.datetime,
    stale_after: dt.timedelta,
) -> str:
    now = _ensure_utc(now)
    fetched_times = [
        _ensure_utc(interval.fetched_at)
        for interval in intervals
        if interval.fetched_at is not None
    ]
    if fetched_times and max(fetched_times) < now - stale_after:
        return "stale"
    observed_count = sum(1 for interval in intervals if interval.observed is True)
    forecast_count = sum(1 for interval in intervals if interval.observed is False)
    if observed_count and not forecast_count:
        return "observed"
    if forecast_count and not observed_count:
        return "forecast"
    if observed_count and forecast_count:
        return "uncertain"
    return "uncertain"


def _status(start: dt.datetime, end: dt.datetime, now: dt.datetime) -> str:
    if now < start:
        return "future"
    if now >= end:
        return "ended"
    return "active"


def _event_key(event_type: str, source_product: str, start: dt.datetime) -> str:
    stable = {
        "event_type": event_type,
        "source_product": source_product,
        "window_start": _format_datetime(start),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _compact_record(record: TimeseriesRecord) -> dict[str, Any]:
    return {
        "id": _text_or_none(record.get("id")),
        "endpoint": _text_or_none(record.get("endpoint")),
        "product_type": _text_or_none(record.get("product_type")),
        "valid_start": _text_or_none(record.get("valid_start")),
        "valid_end": _text_or_none(record.get("valid_end")),
        "observed": _to_bool_or_none(record.get("observed")),
        "severity": _to_int(record.get("severity")),
        "value": _to_float(record.get("value")),
        "units": _text_or_none(record.get("units")),
    }


def _parse_datetime(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        timestamp = value
    elif isinstance(value, dt.date):
        timestamp = dt.datetime.combine(value, dt.time.min, tzinfo=dt.UTC)
    elif isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        if " " in normalized and "T" not in normalized:
            normalized = normalized.replace(" ", "T")
        try:
            timestamp = dt.datetime.fromisoformat(normalized)
        except ValueError:
            return None
    else:
        return None

    return _ensure_utc(timestamp)


def _format_datetime(value: dt.datetime) -> str:
    return _ensure_utc(value).isoformat().replace("+00:00", "Z")


def _ensure_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        normalized = value.replace(tzinfo=dt.UTC)
    else:
        normalized = value.astimezone(dt.UTC)
    return dt.datetime(
        normalized.year,
        normalized.month,
        normalized.day,
        normalized.hour,
        normalized.minute,
        normalized.second,
        normalized.microsecond,
        tzinfo=dt.UTC,
    )


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _to_bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "t", "yes", "y", "1", "observed"}:
        return True
    if normalized in {"false", "f", "no", "n", "0", "forecast"}:
        return False
    return None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


__all__ = [
    "EVENT_WINDOW_PRODUCT_TYPES",
    "EventWindow",
    "derive_space_weather_event_windows",
    "summarize_event_windows",
]
