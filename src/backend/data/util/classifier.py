from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any


JsonObject = Mapping[str, Any]
NormalizedRow = dict[str, Any]
RawPayload = JsonObject | Sequence[Any]

TIME_FIELDS = (
    "time_tag",
    "issue_datetime",
    "observed_date",
    "fetched_at",
    "published_at",
)
TIME_FIELD_SET = set(TIME_FIELDS)

SCALE_LABELS = {
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

NOAA_SCALE_FIELDS = ("G", "S", "R")


@dataclass(frozen=True)
class ScaleClassification:
    """NOAA G/S/R scale classification for one endpoint measurement."""

    endpoint: str
    scale_family: str
    scale: str | None
    level: int
    label: str
    time_tag: str | None
    source_field: str
    source_value: Any
    derived: bool
    record: NormalizedRow

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EndpointClassification:
    """Normalized NOAA payload rows plus the latest scale states they imply."""

    endpoint: str
    normalized_rows: list[NormalizedRow]
    classifications: list[ScaleClassification]

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "normalized_rows": self.normalized_rows,
            "classifications": [
                classification.to_dict() for classification in self.classifications
            ],
        }


@dataclass(frozen=True)
class EndpointScaleSpec:
    scale_family: str
    source_fields: tuple[str, ...]
    classifier: Callable[[Any], str | None]
    row_filter: Callable[[JsonObject], bool] = lambda _row: True


def normalize_payload(payload: RawPayload, endpoint: str | None = None) -> list[NormalizedRow]:
    """Normalize SWPC JSON payloads into row dictionaries.

    NOAA uses several shapes: arrays of records, single objects, objects keyed
    by day/offset, and chart-ready arrays where the first row is a header. This
    function maps those shapes to rows and keeps the endpoint on each row when
    supplied.
    """

    rows = _payload_rows(payload)
    normalized = [_normalize_row(row, endpoint=endpoint) for row in rows]
    return sorted(normalized, key=_row_sort_key)


def classify_endpoint(endpoint: str, payload: RawPayload) -> EndpointClassification:
    """Normalize raw SWPC endpoint data and classify the latest NOAA scale state."""

    normalized_rows = normalize_payload(payload, endpoint=endpoint)

    if _is_noaa_scales_endpoint(endpoint):
        classifications = _classify_official_noaa_scales(endpoint, normalized_rows)
    else:
        specs = _specs_for_endpoint(endpoint, normalized_rows)
        classifications = [
            classification
            for spec in specs
            if (
                classification := _classify_latest_row(
                    endpoint,
                    normalized_rows,
                    spec,
                )
            )
            is not None
        ]

    return EndpointClassification(
        endpoint=endpoint,
        normalized_rows=normalized_rows,
        classifications=classifications,
    )


def classify_rows(endpoint: str, payload: RawPayload) -> list[NormalizedRow]:
    """Return normalized rows with per-row derived scale fields when available."""

    rows = normalize_payload(payload, endpoint=endpoint)
    if _is_noaa_scales_endpoint(endpoint):
        return rows

    specs = _specs_for_endpoint(endpoint, rows)
    classified_rows: list[NormalizedRow] = []
    for row in rows:
        classified = dict(row)
        for spec in specs:
            if not spec.row_filter(row):
                continue
            field, value = _first_present(row, spec.source_fields)
            if field is None:
                continue
            scale = spec.classifier(value)
            level = _scale_level(scale)
            family = spec.scale_family.lower()
            classified[f"{family}_scale"] = scale
            classified[f"{family}_scale_level"] = level
            classified[f"{family}_scale_label"] = _scale_label(spec.scale_family, level)
            classified[f"{family}_scale_source_field"] = field
        classified_rows.append(classified)
    return classified_rows


def classify_g(kp: Any) -> str | None:
    """Classify geomagnetic storms from Kp using NOAA G-scale thresholds."""

    kp_value = _parse_kp(kp)
    if kp_value is None:
        return None
    if kp_value >= 9:
        return "G5"
    if kp_value >= 8:
        return "G4"
    if kp_value >= 7:
        return "G3"
    if kp_value >= 6:
        return "G2"
    if kp_value >= 5:
        return "G1"
    return None


def classify_s(proton_flux_pfu: Any) -> str | None:
    """Classify solar radiation storms from >=10 MeV proton flux in pfu."""

    flux = _to_float(proton_flux_pfu)
    if flux is None:
        return None
    if flux >= 100000:
        return "S5"
    if flux >= 10000:
        return "S4"
    if flux >= 1000:
        return "S3"
    if flux >= 100:
        return "S2"
    if flux >= 10:
        return "S1"
    return None


def classify_r(xray_flux_wm2: Any) -> str | None:
    """Classify radio blackouts from GOES 0.1-0.8 nm X-ray flux in W/m^2."""

    flux = _to_float(xray_flux_wm2)
    if flux is None:
        return None
    if flux >= 2e-3:
        return "R5"
    if flux >= 1e-3:
        return "R4"
    if flux >= 1e-4:
        return "R3"
    if flux >= 5e-5:
        return "R2"
    if flux >= 1e-5:
        return "R1"
    return None


def _payload_rows(payload: RawPayload) -> list[JsonObject]:
    if isinstance(payload, Mapping):
        return _mapping_payload_rows(payload)

    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes):
        raise TypeError("payload must be a mapping or sequence")

    if not payload:
        return []

    first = payload[0]
    if _is_header_row(first):
        headers = [str(header) for header in first]
        return [
            _row_from_header(headers, row)
            for row in payload[1:]
            if isinstance(row, Sequence) and not isinstance(row, str | bytes)
        ]

    if all(isinstance(row, Mapping) for row in payload):
        return [row for row in payload if isinstance(row, Mapping)]

    raise ValueError("sequence payloads must be record arrays or header-row arrays")


def _mapping_payload_rows(payload: JsonObject) -> list[JsonObject]:
    if payload and all(isinstance(value, Mapping) for value in payload.values()):
        rows: list[JsonObject] = []
        for key, value in payload.items():
            row = dict(value)
            row.setdefault("window_offset", key)
            rows.append(row)
        return rows
    return [payload]


def _is_header_row(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str | bytes)
        and bool(value)
        and all(isinstance(item, str) for item in value)
    )


def _row_from_header(headers: Sequence[str], values: Sequence[Any]) -> NormalizedRow:
    row = {
        header: values[index] if index < len(values) else None
        for index, header in enumerate(headers)
    }
    if len(values) > len(headers):
        row["_extra_values"] = list(values[len(headers) :])
    return row


def _normalize_row(row: JsonObject, endpoint: str | None) -> NormalizedRow:
    normalized: NormalizedRow = {}
    if endpoint is not None:
        normalized["endpoint"] = endpoint

    for key, value in row.items():
        key_string = str(key)
        if key_string in TIME_FIELD_SET:
            normalized[key_string] = _normalize_timestamp(value)
        else:
            normalized[key_string] = _normalize_value(value)

    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "" or stripped.lower() in {"null", "none", "nan"}:
            return None
        number = _to_float(stripped)
        return number if number is not None else stripped
    return value


def _normalize_timestamp(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        timestamp = value
    elif isinstance(value, dt.date):
        timestamp = dt.datetime.combine(value, dt.time.min, tzinfo=dt.UTC)
    elif isinstance(value, str):
        timestamp = _parse_datetime(value)
        if timestamp is None:
            return value.strip()
    else:
        return value

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


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        stripped = value.strip().replace(",", "")
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", stripped):
            return None
        number = float(stripped)
        return number if math.isfinite(number) else None
    return None


def _parse_kp(value: Any) -> float | None:
    number = _to_float(value)
    if number is not None:
        return number
    if not isinstance(value, str):
        return None

    match = re.fullmatch(r"\s*(\d)([+\-oO])\s*", value)
    if not match:
        return None

    base = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "+":
        return base + (1 / 3)
    if suffix == "-":
        return base - (1 / 3)
    return base


def _is_noaa_scales_endpoint(endpoint: str) -> bool:
    return endpoint.rstrip("/").endswith("/products/noaa-scales.json") or endpoint.rstrip("/") == "products/noaa-scales.json"


def _specs_for_endpoint(endpoint: str, rows: Sequence[NormalizedRow]) -> list[EndpointScaleSpec]:
    endpoint_key = endpoint.lower()
    specs: list[EndpointScaleSpec] = []

    if "planetary_k_index" in endpoint_key or "planetary-k-index" in endpoint_key:
        specs.append(
            EndpointScaleSpec(
                scale_family="G",
                source_fields=("estimated_kp", "kp", "kp_index", "Kp"),
                classifier=classify_g,
            )
        )

    if "integral-protons" in endpoint_key:
        specs.append(
            EndpointScaleSpec(
                scale_family="S",
                source_fields=("flux",),
                classifier=classify_s,
                row_filter=_is_10mev_proton_row,
            )
        )

    if "xrays" in endpoint_key:
        specs.append(
            EndpointScaleSpec(
                scale_family="R",
                source_fields=("flux", "observed_flux"),
                classifier=classify_r,
                row_filter=_is_long_xray_row,
            )
        )

    if not specs:
        specs.extend(_infer_specs_from_rows(rows))

    return specs


def _infer_specs_from_rows(rows: Sequence[NormalizedRow]) -> list[EndpointScaleSpec]:
    fields = {field for row in rows for field in row}
    specs: list[EndpointScaleSpec] = []
    if {"estimated_kp", "kp", "kp_index", "Kp"} & fields:
        specs.append(
            EndpointScaleSpec(
                scale_family="G",
                source_fields=("estimated_kp", "kp", "kp_index", "Kp"),
                classifier=classify_g,
            )
        )
    if "flux" in fields and any(_is_10mev_proton_row(row) for row in rows):
        specs.append(
            EndpointScaleSpec(
                scale_family="S",
                source_fields=("flux",),
                classifier=classify_s,
                row_filter=_is_10mev_proton_row,
            )
        )
    if {"flux", "observed_flux"} & fields and any(_is_long_xray_row(row) for row in rows):
        specs.append(
            EndpointScaleSpec(
                scale_family="R",
                source_fields=("flux", "observed_flux"),
                classifier=classify_r,
                row_filter=_is_long_xray_row,
            )
        )
    return specs


def _classify_latest_row(
    endpoint: str,
    rows: Sequence[NormalizedRow],
    spec: EndpointScaleSpec,
) -> ScaleClassification | None:
    for row in reversed(rows):
        if not spec.row_filter(row):
            continue
        source_field, source_value = _first_present(row, spec.source_fields)
        if source_field is None:
            continue

        scale = spec.classifier(source_value)
        level = _scale_level(scale)
        return ScaleClassification(
            endpoint=endpoint,
            scale_family=spec.scale_family,
            scale=scale,
            level=level,
            label=_scale_label(spec.scale_family, level),
            time_tag=_time_tag(row),
            source_field=source_field,
            source_value=source_value,
            derived=True,
            record=dict(row),
        )
    return None


def _classify_official_noaa_scales(
    endpoint: str,
    rows: Sequence[NormalizedRow],
) -> list[ScaleClassification]:
    current_row = _current_noaa_scale_row(rows)
    if current_row is None:
        return []

    classifications: list[ScaleClassification] = []
    for family in NOAA_SCALE_FIELDS:
        raw_value = current_row.get(family)
        scale = _official_scale_value(family, raw_value)
        level = _scale_level(scale)
        classifications.append(
            ScaleClassification(
                endpoint=endpoint,
                scale_family=family,
                scale=scale,
                level=level,
                label=_scale_label(family, level),
                time_tag=_time_tag(current_row),
                source_field=family,
                source_value=raw_value,
                derived=False,
                record=dict(current_row),
            )
        )
    return classifications


def _current_noaa_scale_row(rows: Sequence[NormalizedRow]) -> NormalizedRow | None:
    if not rows:
        return None
    for row in rows:
        if str(row.get("window_offset")) == "0":
            return row
    return rows[-1]


def _official_scale_value(family: str, value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("Scale", "scale", "value", "Value"):
            if key in value:
                return _official_scale_value(family, value[key])
        return None

    level = _to_int(value)
    if level is None or level <= 0:
        return None
    return f"{family}{min(level, 5)}"


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _first_present(row: JsonObject, fields: Sequence[str]) -> tuple[str | None, Any]:
    for field in fields:
        value = row.get(field)
        if value is not None:
            return field, value
    return None, None


def _is_10mev_proton_row(row: JsonObject) -> bool:
    return _clean_energy(row.get("energy")) in {">=10mev", ">10mev"}


def _is_long_xray_row(row: JsonObject) -> bool:
    return _clean_energy(row.get("energy")) in {"0.1-0.8nm", "0.1-0.8"}


def _clean_energy(value: Any) -> str:
    if value is None:
        return ""
    return str(value).lower().replace(" ", "")


def _scale_level(scale: str | None) -> int:
    if not scale:
        return 0
    match = re.fullmatch(r"[GSR](\d)", scale)
    if not match:
        return 0
    return int(match.group(1))


def _scale_label(family: str, level: int) -> str:
    return SCALE_LABELS[family][level]


def _time_tag(row: JsonObject) -> str | None:
    for field in TIME_FIELDS:
        value = row.get(field)
        if value is not None:
            return str(value)
    return None


def _row_sort_key(row: JsonObject) -> tuple[int, str]:
    time_tag = _time_tag(row)
    if time_tag is None:
        return 1, ""
    return 0, time_tag


__all__ = [
    "EndpointClassification",
    "ScaleClassification",
    "classify_endpoint",
    "classify_g",
    "classify_r",
    "classify_rows",
    "classify_s",
    "normalize_payload",
]
