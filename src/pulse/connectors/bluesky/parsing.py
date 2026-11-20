"""Parse Jetstream v1/v2 frames into mentions or delete actions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pulse.connectors.types import (
    ConnectorError,
    ConnectorErrorKind,
    NormalizedMention,
    canonicalize_url,
)

POST_COLLECTION = "app.bsky.feed.post"


@dataclass(frozen=True, slots=True)
class JetstreamCursor:
    """Resume position after durable processing of an event."""

    time_us: int | None = None
    seq: int | None = None

    def as_token(self) -> str:
        """Prefer portable timestamp cursor when available; else seq."""
        if self.time_us is not None:
            return str(self.time_us)
        if self.seq is not None:
            return str(self.seq)
        msg = "cursor requires time_us or seq"
        raise ConnectorError(msg, kind=ConnectorErrorKind.PARSE)


@dataclass(frozen=True, slots=True)
class StreamPostEvent:
    mention: NormalizedMention
    cursor: JetstreamCursor
    raw: dict[str, Any]
    kind: Literal["post"] = "post"


@dataclass(frozen=True, slots=True)
class StreamDeleteEvent:
    source: str
    external_id: str
    cursor: JetstreamCursor
    raw: dict[str, Any]
    kind: Literal["delete"] = "delete"


@dataclass(frozen=True, slots=True)
class StreamInfoEvent:
    name: str
    message: str
    raw: dict[str, Any]
    kind: Literal["info"] = "info"


@dataclass(frozen=True, slots=True)
class StreamSkipEvent:
    """Non-post commit / identity / account — acknowledged but not stored as mentions."""

    reason: str
    cursor: JetstreamCursor | None
    raw: dict[str, Any]
    kind: Literal["skip"] = "skip"


StreamEvent = StreamPostEvent | StreamDeleteEvent | StreamInfoEvent | StreamSkipEvent


def parse_frame(
    raw: str | bytes | dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
    wanted_collections: list[str] | None = None,
) -> StreamEvent | None:
    """Parse one WebSocket frame into a stream event.

    Returns ``None`` only for empty keepalives. Malformed JSON raises ``ConnectorError``.
    """
    if isinstance(raw, dict):
        payload = raw
    else:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not text or not text.strip():
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConnectorError(
                f"invalid jetstream JSON: {exc}",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            ) from exc

    if not isinstance(payload, dict):
        raise ConnectorError(
            "jetstream frame must be a JSON object",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )

    # Terminal error frames (v2).
    if payload.get("$type") == "error" or (
        "error" in payload and payload.get("$type") is None and "did" not in payload
    ):
        err = payload.get("error") or payload.get("message") or "jetstream error"
        raise ConnectorError(
            f"jetstream error frame: {err}",
            kind=ConnectorErrorKind.TRANSIENT,
            retryable=True,
            details=payload,
        )

    # Unwrap v2 message envelope: {"$type":"message","payload":{...}}
    if payload.get("$type") == "message" and isinstance(payload.get("payload"), dict):
        return _parse_v2_payload(
            payload["payload"],
            collected_at=collected_at,
            source_version=source_version,
            wanted_collections=wanted_collections,
            envelope=payload,
        )

    # Bare v2 lexicon object (some clients/tests omit the message wrapper).
    type_name = str(payload.get("$type") or "")
    if type_name.startswith("network.bsky.jetstream.subscribeEvents#"):
        return _parse_v2_payload(
            payload,
            collected_at=collected_at,
            source_version=source_version,
            wanted_collections=wanted_collections,
            envelope=payload,
        )

    # Legacy Jetstream /subscribe JSON.
    return _parse_legacy_payload(
        payload,
        collected_at=collected_at,
        source_version=source_version,
        wanted_collections=wanted_collections,
    )


def _parse_v2_payload(
    payload: dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
    wanted_collections: list[str] | None,
    envelope: dict[str, Any],
) -> StreamEvent:
    type_name = str(payload.get("$type") or "")
    fragment = type_name.rsplit("#", 1)[-1] if "#" in type_name else type_name

    if fragment == "info":
        return StreamInfoEvent(
            name=str(payload.get("name") or payload.get("info") or "info"),
            message=str(payload.get("message") or ""),
            raw=envelope,
        )

    cursor = JetstreamCursor(
        time_us=_datetime_to_us(payload.get("witnessedAt"))
        or _datetime_to_us(payload.get("time"))
        or _as_int(payload.get("time_us")),
        seq=_as_int(payload.get("seq")),
    )

    if fragment != "commit":
        return StreamSkipEvent(reason=f"v2:{fragment}", cursor=cursor, raw=envelope)

    return _commit_to_event(
        did=str(payload.get("did") or ""),
        operation=str(payload.get("operation") or ""),
        collection=str(payload.get("collection") or ""),
        rkey=str(payload.get("rkey") or ""),
        record=payload.get("record") if isinstance(payload.get("record"), dict) else None,
        cid=payload.get("cid"),
        cursor=cursor,
        collected_at=collected_at,
        source_version=source_version,
        wanted_collections=wanted_collections,
        raw=envelope,
    )


def _parse_legacy_payload(
    payload: dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
    wanted_collections: list[str] | None,
) -> StreamEvent:
    kind = str(payload.get("kind") or "")
    cursor = JetstreamCursor(
        time_us=_as_int(payload.get("time_us")),
        seq=_as_int(payload.get("cursor")),
    )

    if kind != "commit":
        return StreamSkipEvent(reason=f"legacy:{kind or 'unknown'}", cursor=cursor, raw=payload)

    commit = payload.get("commit")
    if not isinstance(commit, dict):
        raise ConnectorError(
            "legacy commit event missing commit object",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
            details={"payload_keys": list(payload.keys())},
        )

    return _commit_to_event(
        did=str(payload.get("did") or ""),
        operation=str(commit.get("operation") or ""),
        collection=str(commit.get("collection") or ""),
        rkey=str(commit.get("rkey") or ""),
        record=commit.get("record") if isinstance(commit.get("record"), dict) else None,
        cid=commit.get("cid"),
        cursor=cursor,
        collected_at=collected_at,
        source_version=source_version,
        wanted_collections=wanted_collections,
        raw=payload,
    )


def _commit_to_event(
    *,
    did: str,
    operation: str,
    collection: str,
    rkey: str,
    record: dict[str, Any] | None,
    cid: Any,
    cursor: JetstreamCursor,
    collected_at: datetime,
    source_version: str,
    wanted_collections: list[str] | None,
    raw: dict[str, Any],
) -> StreamEvent:
    if not did or not rkey or not collection:
        raise ConnectorError(
            "commit missing did/collection/rkey",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )

    wanted = wanted_collections or [POST_COLLECTION]
    if collection not in wanted:
        return StreamSkipEvent(
            reason=f"collection:{collection}",
            cursor=cursor,
            raw=raw,
        )

    external_id = f"at://{did}/{collection}/{rkey}"
    if operation == "delete":
        return StreamDeleteEvent(
            source="bluesky",
            external_id=external_id,
            cursor=cursor,
            raw=raw,
        )

    if operation not in {"create", "update"}:
        return StreamSkipEvent(reason=f"operation:{operation}", cursor=cursor, raw=raw)

    if record is None:
        raise ConnectorError(
            f"commit {operation} missing record for {external_id}",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )

    text = record.get("text")
    if text is not None and not isinstance(text, str):
        text = str(text)

    created_at = _parse_created_at(record.get("createdAt"))
    source_url = f"https://bsky.app/profile/{did}/post/{rkey}"
    try:
        canonical = canonicalize_url(source_url)
    except ConnectorError:
        canonical = source_url

    langs = record.get("langs")
    language = None
    if isinstance(langs, list) and langs:
        language = str(langs[0])

    mention = NormalizedMention(
        source="bluesky",
        external_id=external_id,
        source_url=source_url,
        author_id=did,
        author_name=None,  # never invent handles
        content=text,
        title=None,
        language=language,
        published_at=created_at,
        collected_at=collected_at,
        engagement={},
        metadata={
            "collection": collection,
            "rkey": rkey,
            "cid": cid,
            "operation": operation,
            "record_type": record.get("$type"),
        },
        canonical_url=canonical,
        source_version=source_version,
    ).ensure_hashes()

    return StreamPostEvent(mention=mention, cursor=cursor, raw=raw)


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _datetime_to_us(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1_000_000)


def _parse_created_at(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
