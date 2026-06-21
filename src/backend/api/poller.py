from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

logger = logging.getLogger("soteria.poller")

EVENT_WINDOW_COLUMNS = (
    "id,event_key,event_type,source_product,source_endpoint,window_start,"
    "peak_time,window_end,peak_value,peak_severity,threshold_value,units,"
    "confidence,status,evidence,updated_at"
)


class EventWindowReactionMessage(BaseModel):
    """Compact message emitted when an event window should trigger agent work."""

    model_config = ConfigDict(extra="forbid")

    event_window_id: str
    event_key: str
    event_type: str
    source_product: str
    status: str
    confidence: str
    priority: str
    peak_severity: int | None = None
    window_start: dt.datetime
    window_end: dt.datetime
    updated_at: dt.datetime
    detected_at: dt.datetime
    trigger_source: str = "space_weather_event_windows"


class EventWindowReactionBatch(BaseModel):
    """Batch of event-window changes emitted from one poll cycle."""

    model_config = ConfigDict(extra="forbid")

    trigger_type: str = "event_windows_changed"
    trigger_source: str = "space_weather_event_windows"
    priority: str
    event_window_ids: list[str]
    event_windows: list[EventWindowReactionMessage]
    detected_at: dt.datetime


class EventWindowPollerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval_seconds: float = Field(default=5.0, gt=0)
    initial_lookback_minutes: int = Field(default=5, ge=0)
    max_rows_per_poll: int = Field(default=100, ge=1, le=1000)
    min_peak_severity: int = Field(default=1, ge=0, le=5)
    include_ended_windows: bool = False
    redis_seen_key_prefix: str = "soteria:event-window-seen:"


class ReactionDispatcher(Protocol):
    async def dispatch(self, batch: EventWindowReactionBatch) -> None:
        """Send a reaction message to the downstream report/runbook service."""


class SeenCache(Protocol):
    async def claim(self, fingerprint: str) -> bool:
        """Return True when this fingerprint has not been seen before."""

    async def release(self, fingerprint: str) -> None:
        """Release a claimed fingerprint after a failed dispatch."""

    async def close(self) -> None:
        """Close any held resources."""


class MemorySeenCache:
    def __init__(self) -> None:
        self._seen_fingerprints: set[str] = set()

    async def claim(self, fingerprint: str) -> bool:
        if fingerprint in self._seen_fingerprints:
            logger.debug("memory dedupe hit fingerprint=%s", fingerprint)
            return False
        self._seen_fingerprints.add(fingerprint)
        logger.debug("memory dedupe claimed fingerprint=%s", fingerprint)
        return True

    async def release(self, fingerprint: str) -> None:
        self._seen_fingerprints.discard(fingerprint)
        logger.debug("memory dedupe released fingerprint=%s", fingerprint)

    async def close(self) -> None:
        return None


class RedisSeenCache:
    def __init__(
        self,
        url: str,
        *,
        key_prefix: str,
    ) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=True)
        self.key_prefix = key_prefix
        logger.info("redis seen-cache configured key_prefix=%s", key_prefix)

    async def claim(self, fingerprint: str) -> bool:
        claimed = bool(
            await self._redis.set(
                self._key(fingerprint),
                "1",
                nx=True,
            )
        )
        if claimed:
            logger.debug("redis dedupe claimed fingerprint=%s", fingerprint)
        else:
            logger.debug("redis dedupe hit fingerprint=%s", fingerprint)
        return claimed

    async def release(self, fingerprint: str) -> None:
        await self._redis.delete(self._key(fingerprint))
        logger.debug("redis dedupe released fingerprint=%s", fingerprint)

    async def close(self) -> None:
        await self._redis.aclose()

    def _key(self, fingerprint: str) -> str:
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
        return f"{self.key_prefix}{digest}"


class LoggingReactionDispatcher:
    async def dispatch(self, batch: EventWindowReactionBatch) -> None:
        logger.info(
            "reaction batch event_window_count=%s priority=%s event_window_ids=%s",
            len(batch.event_windows),
            batch.priority,
            batch.event_window_ids,
        )
        logger.debug("reaction payload=%s", batch.model_dump_json())


class HttpReactionDispatcher:
    """Dispatch messages to another service over HTTP.

    The receiving service should fetch satellites, build evidence bundles, call
    the agents, validate outputs, and persist reports/runbooks.
    """

    def __init__(self, url: str, *, timeout_seconds: float = 10.0) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds
        logger.info("http reaction dispatcher configured url=%s", url)

    async def dispatch(self, batch: EventWindowReactionBatch) -> None:
        await asyncio.to_thread(self._post, batch)

    def _post(self, batch: EventWindowReactionBatch) -> None:
        body = batch.model_dump_json().encode("utf-8")
        request = Request(
            self.url,
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read()
                summary = _reaction_response_summary(response_body)
                _log_reaction_response(
                    response.status,
                    len(batch.event_windows),
                    summary,
                )
                _raise_for_reaction_response_errors(response.status, summary)
        except HTTPError as exc:
            response_body = exc.read()
            summary = _reaction_response_summary(response_body)
            _log_reaction_response(
                exc.code,
                len(batch.event_windows),
                summary,
                is_error=True,
            )
            detail = _reaction_response_error_detail(summary, response_body)
            raise RuntimeError(
                f"reaction service returned HTTP {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"failed to dispatch reaction message: {exc}") from exc


def _reaction_response_summary(response_body: bytes) -> dict[str, Any]:
    if not response_body:
        return {}
    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"non_json_body": response_body[:500].decode("utf-8", errors="replace")}
    if not isinstance(payload, dict):
        return {"non_object_body": True}
    return {
        "status": payload.get("status"),
        "requested_event_window_ids": payload.get("requested_event_window_ids") or [],
        "reports_count": len(payload.get("reports") or []),
        "failures_count": len(payload.get("failures") or []),
        "persisted_rows_count": payload.get("persisted_rows_count"),
        "persistence_errors": payload.get("persistence_errors") or [],
        "runbooks_generated_count": payload.get("runbooks_generated_count"),
        "runbooks_persisted_count": payload.get("runbooks_persisted_count"),
        "runbook_errors": payload.get("runbook_errors") or [],
        "validation_errors": payload.get("validation_errors") or [],
    }


def _log_reaction_response(
    http_status: int,
    event_window_count: int,
    summary: dict[str, Any],
    *,
    is_error: bool = False,
) -> None:
    log = logger.error if is_error or _reaction_summary_has_errors(summary) else logger.info
    log(
        "http reaction response event_window_count=%s http_status=%s "
        "pipeline_status=%s reports=%s failures=%s persisted_reports=%s "
        "runbooks_generated=%s runbooks_persisted=%s persistence_errors=%s "
        "runbook_errors=%s validation_errors=%s event_window_ids=%s",
        event_window_count,
        http_status,
        summary.get("status"),
        summary.get("reports_count"),
        summary.get("failures_count"),
        summary.get("persisted_rows_count"),
        summary.get("runbooks_generated_count"),
        summary.get("runbooks_persisted_count"),
        _summarize_errors(summary.get("persistence_errors")),
        _summarize_errors(summary.get("runbook_errors")),
        _summarize_errors(summary.get("validation_errors")),
        summary.get("requested_event_window_ids"),
    )


def _raise_for_reaction_response_errors(
    http_status: int,
    summary: dict[str, Any],
) -> None:
    if http_status >= 400:
        raise RuntimeError(
            f"reaction service returned HTTP {http_status}: "
            f"{_reaction_response_error_detail(summary)}"
        )
    if _reaction_summary_has_errors(summary):
        raise RuntimeError(
            "reaction service completed with pipeline errors: "
            f"{_reaction_response_error_detail(summary)}"
        )


def _reaction_summary_has_errors(summary: dict[str, Any]) -> bool:
    if not summary:
        return False
    if summary.get("status") == "failed":
        return True
    for field_name in ("persistence_errors", "runbook_errors"):
        if summary.get(field_name):
            return True
    generated = summary.get("runbooks_generated_count")
    persisted = summary.get("runbooks_persisted_count")
    if generated is not None and persisted is not None and generated != persisted:
        return True
    return False


def _reaction_response_error_detail(
    summary: dict[str, Any],
    response_body: bytes | None = None,
) -> str:
    details: list[str] = []
    for field_name in ("status", "persistence_errors", "runbook_errors"):
        value = summary.get(field_name)
        if value:
            details.append(f"{field_name}={_summarize_errors(value)}")
    generated = summary.get("runbooks_generated_count")
    persisted = summary.get("runbooks_persisted_count")
    if generated is not None and persisted is not None and generated != persisted:
        details.append(f"runbook_count_mismatch={persisted}/{generated}")
    if details:
        return "; ".join(details)
    if response_body:
        return response_body[:500].decode("utf-8", errors="replace")
    return "no response summary"


def _summarize_errors(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return [str(item)[:300] for item in value[:5]]


class SupabaseReactionJobDispatcher:
    """Dispatch messages by inserting durable reaction jobs into Supabase."""

    def __init__(
        self,
        client: Any,
        *,
        table: str = "agent_reaction_jobs",
    ) -> None:
        self.client = client
        self.table = table
        logger.info("supabase reaction-job dispatcher configured table=%s", table)

    async def dispatch(self, batch: EventWindowReactionBatch) -> None:
        await asyncio.to_thread(self._insert_job, batch)

    def _insert_job(self, batch: EventWindowReactionBatch) -> None:
        payload = batch.model_dump(mode="json")
        self.client.table(self.table).insert(
            {
                "trigger_type": batch.trigger_type,
                "trigger_source": batch.trigger_source,
                "source_ids": batch.event_window_ids,
                "event_window_ids": batch.event_window_ids,
                "priority": batch.priority,
                "status": "queued",
                "payload": payload,
            }
        ).execute()
        logger.info(
            "supabase reaction job queued event_window_count=%s priority=%s table=%s",
            len(batch.event_windows),
            batch.priority,
            self.table,
        )


class EventWindowPoller:
    """Poll event windows and emit reaction messages for new/updated rows."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        dispatcher: ReactionDispatcher | None = None,
        seen_cache: SeenCache | None = None,
        settings: EventWindowPollerSettings | None = None,
    ) -> None:
        self.client = client or _get_supabase_client()
        self.settings = settings or EventWindowPollerSettings()
        self.dispatcher = dispatcher or build_dispatcher(self.client)
        self.seen_cache = seen_cache or build_seen_cache(self.settings)
        self._watermark = dt.datetime.now(dt.UTC) - dt.timedelta(
            minutes=self.settings.initial_lookback_minutes
        )
        logger.info(
            "event-window poller initialized interval=%ss lookback=%sm limit=%s "
            "min_severity=%s include_ended=%s watermark=%s",
            self.settings.poll_interval_seconds,
            self.settings.initial_lookback_minutes,
            self.settings.max_rows_per_poll,
            self.settings.min_peak_severity,
            self.settings.include_ended_windows,
            _iso_z(self._watermark),
        )

    async def run_forever(self) -> None:
        logger.info("event-window poller started")
        try:
            while True:
                try:
                    messages = await self.poll_once()
                    logger.info(
                        "poll complete dispatched=%s next_poll_in=%ss watermark=%s",
                        len(messages),
                        self.settings.poll_interval_seconds,
                        _iso_z(self._watermark),
                    )
                except Exception as exc:
                    logger.exception("event-window poll failed: %s", exc)
                await asyncio.sleep(self.settings.poll_interval_seconds)
        finally:
            await self.close()

    async def close(self) -> None:
        await self.seen_cache.close()
        logger.info("event-window poller stopped")

    async def poll_once(self) -> list[EventWindowReactionMessage]:
        logger.debug("querying event windows updated_since=%s", _iso_z(self._watermark))
        rows = await asyncio.to_thread(self._query_changed_event_windows)
        logger.info(
            "queried event windows rows=%s updated_since=%s",
            len(rows),
            _iso_z(self._watermark),
        )
        messages: list[EventWindowReactionMessage] = []
        claimed_fingerprints: list[str] = []
        max_updated_at = self._watermark

        for row in rows:
            updated_at = _parse_datetime(row.get("updated_at"))
            if updated_at is None:
                logger.warning(
                    "skipping event window with missing updated_at id=%s",
                    row.get("id"),
                )
                continue
            max_updated_at = max(max_updated_at, updated_at)

            message = _reaction_message(row)
            if message is None:
                continue
            should_dispatch, reason = self._dispatch_decision(message)
            if not should_dispatch:
                logger.debug(
                    "skipping event window id=%s reason=%s status=%s severity=%s "
                    "window_end=%s",
                    message.event_window_id,
                    reason,
                    message.status,
                    message.peak_severity,
                    _iso_z(message.window_end),
                )
                continue

            fingerprint = _fingerprint(message)
            if not await self.seen_cache.claim(fingerprint):
                logger.debug(
                    "skipping seen event window id=%s updated_at=%s",
                    message.event_window_id,
                    _iso_z(message.updated_at),
                )
                continue

            claimed_fingerprints.append(fingerprint)
            messages.append(message)
            logger.debug(
                "queued event window for batch id=%s event_type=%s priority=%s severity=%s",
                message.event_window_id,
                message.event_type,
                message.priority,
                message.peak_severity,
            )

        if messages:
            batch = _reaction_batch(messages)
            try:
                await self.dispatcher.dispatch(batch)
            except Exception:
                for fingerprint in claimed_fingerprints:
                    await self.seen_cache.release(fingerprint)
                raise
            logger.info(
                "dispatched event-window batch count=%s priority=%s event_window_ids=%s",
                len(messages),
                batch.priority,
                batch.event_window_ids,
            )
        else:
            logger.debug("no eligible unseen event windows to dispatch")

        self._watermark = max_updated_at
        return messages

    def _query_changed_event_windows(self) -> list[dict[str, Any]]:
        response = (
            self.client.table("space_weather_event_windows")
            .select(EVENT_WINDOW_COLUMNS)
            .gte("updated_at", _iso_z(self._watermark))
            .order("updated_at")
            .limit(self.settings.max_rows_per_poll)
            .execute()
        )
        return [dict(row) for row in response.data or []]

    def _dispatch_decision(self, message: EventWindowReactionMessage) -> tuple[bool, str]:
        if (
            not self.settings.include_ended_windows
            and message.status.lower() == "ended"
        ):
            return False, "ended_window"
        if message.window_end <= dt.datetime.now(dt.UTC):
            return False, "expired_window"
        severity = message.peak_severity or 0
        if severity < self.settings.min_peak_severity:
            return False, "severity_below_threshold"
        return True, "eligible"


def build_dispatcher(client: Any) -> ReactionDispatcher:
    reaction_url = os.getenv("SOTERIA_REACTION_SERVICE_URL")
    if reaction_url:
        return HttpReactionDispatcher(
            reaction_url,
            timeout_seconds=float(
                os.getenv("SOTERIA_REACTION_SERVICE_TIMEOUT_SECONDS", "10")
            ),
        )

    if _env_bool("SOTERIA_USE_REACTION_JOBS"):
        table = os.getenv("SOTERIA_REACTION_JOBS_TABLE", "agent_reaction_jobs")
        return SupabaseReactionJobDispatcher(client, table=table)

    return LoggingReactionDispatcher()


def build_seen_cache(settings: EventWindowPollerSettings) -> SeenCache:
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.warning("REDIS_URL is not set; using in-memory seen-cache")
        return MemorySeenCache()

    return RedisSeenCache(
        redis_url,
        key_prefix=settings.redis_seen_key_prefix,
    )


def _reaction_message(row: dict[str, Any]) -> EventWindowReactionMessage | None:
    try:
        severity = _optional_int(row.get("peak_severity"))
        return EventWindowReactionMessage(
            event_window_id=str(row["id"]),
            event_key=str(row["event_key"]),
            event_type=str(row["event_type"]),
            source_product=str(row["source_product"]),
            status=str(row["status"]),
            confidence=str(row["confidence"]),
            priority=_priority(severity),
            peak_severity=severity,
            window_start=_require_datetime(row.get("window_start"), "window_start"),
            window_end=_require_datetime(row.get("window_end"), "window_end"),
            updated_at=_require_datetime(row.get("updated_at"), "updated_at"),
            detected_at=dt.datetime.now(dt.UTC),
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("skipping invalid event window row: %s", exc)
        return None


def _reaction_batch(
    messages: list[EventWindowReactionMessage],
) -> EventWindowReactionBatch:
    return EventWindowReactionBatch(
        priority=_batch_priority(messages),
        event_window_ids=[message.event_window_id for message in messages],
        event_windows=messages,
        detected_at=dt.datetime.now(dt.UTC),
    )


def _batch_priority(messages: list[EventWindowReactionMessage]) -> str:
    priorities = {message.priority for message in messages}
    if "critical" in priorities:
        return "critical"
    if "high" in priorities:
        return "high"
    return "normal"


def _priority(severity: int | None) -> str:
    if severity is not None and severity >= 4:
        return "critical"
    if severity is not None and severity >= 3:
        return "high"
    return "normal"


def _fingerprint(message: EventWindowReactionMessage) -> str:
    stable = {
        "event_window_id": message.event_window_id,
        "event_key": message.event_key,
        "status": message.status,
        "peak_severity": message.peak_severity,
        "updated_at": _iso_z(message.updated_at),
    }
    return json.dumps(stable, sort_keys=True)


def _get_supabase_client() -> Any:
    url = os.getenv("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured.")

    from supabase import create_client

    return create_client(url, key)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _require_datetime(value: Any, field_name: str) -> dt.datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be an ISO-8601 datetime")
    return parsed


def _parse_datetime(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _env_bool(key: str) -> bool:
    return os.getenv(key, "").strip().lower() in {"1", "true", "yes", "on"}


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.debug("logging configured level=%s", logging.getLevelName(level))


async def main() -> None:
    configure_logging()
    await EventWindowPoller().run_forever()


if __name__ == "__main__":
    asyncio.run(main())
