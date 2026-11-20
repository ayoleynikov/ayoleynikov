"""Parse YouTube Data API v3 JSON into NormalizedMention objects."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pulse.connectors.types import (
    ConnectorError,
    ConnectorErrorKind,
    NormalizedMention,
    canonicalize_url,
)


def parse_search_items(
    payload: dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
) -> tuple[list[NormalizedMention], str | None]:
    """Parse search.list response. Returns (mentions, next_page_token)."""
    _require_dict(payload, "search.list")
    if "error" in payload:
        raise parse_api_error(payload["error"])
    items = payload.get("items")
    if not isinstance(items, list):
        raise ConnectorError(
            "YouTube search response missing items list",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
            details={"keys": list(payload.keys())},
        )
    mentions: list[NormalizedMention] = []
    for item in items:
        if not isinstance(item, dict):
            raise ConnectorError(
                "YouTube search item must be an object",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            )
        kind = (item.get("id") or {}).get("kind") if isinstance(item.get("id"), dict) else None
        video_id = None
        if isinstance(item.get("id"), dict):
            video_id = item["id"].get("videoId")
        if not video_id:
            # Skip non-video results (channels/playlists) without inventing data.
            continue
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        mentions.append(
            _video_mention(
                video_id=str(video_id),
                snippet=snippet,
                collected_at=collected_at,
                source_version=source_version,
                extras={"result_kind": kind, "from": "search.list"},
            )
        )
    next_token = payload.get("nextPageToken")
    return mentions, next_token if isinstance(next_token, str) else None


def parse_video_items(
    payload: dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
) -> list[NormalizedMention]:
    _require_dict(payload, "videos.list")
    if "error" in payload:
        raise parse_api_error(payload["error"])
    items = payload.get("items")
    if not isinstance(items, list):
        raise ConnectorError(
            "YouTube videos response missing items list",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )
    mentions: list[NormalizedMention] = []
    for item in items:
        if not isinstance(item, dict):
            raise ConnectorError(
                "YouTube video item must be an object",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            )
        video_id = item.get("id")
        if not isinstance(video_id, str) or not video_id.strip():
            raise ConnectorError(
                "YouTube video missing id",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            )
        snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        stats = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
        engagement: dict[str, Any] = {}
        for key, dest in (
            ("viewCount", "views"),
            ("likeCount", "likes"),
            ("commentCount", "comments"),
        ):
            raw = stats.get(key)
            if isinstance(raw, str) and raw.isdigit():
                engagement[dest] = int(raw)
            elif isinstance(raw, int):
                engagement[dest] = raw
        mention = _video_mention(
            video_id=video_id,
            snippet=snippet,
            collected_at=collected_at,
            source_version=source_version,
            extras={"from": "videos.list"},
        )
        mention = mention.model_copy(update={"engagement": {**mention.engagement, **engagement}})
        mentions.append(mention.ensure_hashes())
    return mentions


def parse_comment_threads(
    payload: dict[str, Any],
    *,
    collected_at: datetime,
    source_version: str,
    video_id: str,
) -> tuple[list[NormalizedMention], str | None]:
    _require_dict(payload, "commentThreads.list")
    if "error" in payload:
        err = payload["error"]
        # Comments disabled → permanent, not silent invent.
        reason = ""
        if isinstance(err, dict):
            errors = err.get("errors") or []
            if errors and isinstance(errors[0], dict):
                reason = str(errors[0].get("reason") or "")
        if reason in {"commentsDisabled", "forbidden"}:
            raise ConnectorError(
                f"YouTube comments not permitted for video {video_id}: {reason}",
                kind=ConnectorErrorKind.PERMANENT,
                retryable=False,
                details={"video_id": video_id, "reason": reason},
            )
        raise parse_api_error(err)

    items = payload.get("items")
    if not isinstance(items, list):
        raise ConnectorError(
            "YouTube commentThreads response missing items list",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )
    mentions: list[NormalizedMention] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        snippet_wrap = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
        top = snippet_wrap.get("topLevelComment")
        if not isinstance(top, dict):
            continue
        top_snippet = top.get("snippet") if isinstance(top.get("snippet"), dict) else {}
        comment_id = top.get("id") or item.get("id")
        if not comment_id:
            raise ConnectorError(
                "YouTube comment missing id",
                kind=ConnectorErrorKind.PARSE,
                retryable=False,
            )
        text = top_snippet.get("textDisplay") or top_snippet.get("textOriginal")
        author = top_snippet.get("authorDisplayName")
        author_channel = top_snippet.get("authorChannelId")
        if isinstance(author_channel, dict):
            author_id = author_channel.get("value")
        else:
            author_id = None
        published = _parse_ts(top_snippet.get("publishedAt"))
        url = f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"
        mentions.append(
            NormalizedMention(
                source="youtube",
                external_id=f"comment:{comment_id}",
                source_url=url,
                author_id=str(author_id) if author_id else None,
                author_name=str(author) if author else None,
                content=str(text) if text is not None else None,
                title=None,
                language=None,
                published_at=published,
                collected_at=collected_at,
                engagement=(
                    {"likes": int(top_snippet["likeCount"])}
                    if isinstance(top_snippet.get("likeCount"), int)
                    else {}
                ),
                metadata={
                    "video_id": video_id,
                    "kind": "youtube#comment",
                    "from": "commentThreads.list",
                },
                canonical_url=canonicalize_url(url),
                source_version=source_version,
            ).ensure_hashes()
        )
    next_token = payload.get("nextPageToken")
    return mentions, next_token if isinstance(next_token, str) else None


def _video_mention(
    *,
    video_id: str,
    snippet: dict[str, Any],
    collected_at: datetime,
    source_version: str,
    extras: dict[str, Any],
) -> NormalizedMention:
    url = f"https://www.youtube.com/watch?v={video_id}"
    title = snippet.get("title")
    description = snippet.get("description")
    channel_id = snippet.get("channelId")
    channel_title = snippet.get("channelTitle")
    published = _parse_ts(snippet.get("publishedAt"))
    return NormalizedMention(
        source="youtube",
        external_id=f"video:{video_id}",
        source_url=url,
        author_id=str(channel_id) if channel_id else None,
        author_name=str(channel_title) if channel_title else None,
        content=str(description) if description is not None else None,
        title=str(title) if title is not None else None,
        language=None,
        published_at=published,
        collected_at=collected_at,
        engagement={},
        metadata={"video_id": video_id, **extras},
        canonical_url=canonicalize_url(url),
        source_version=source_version,
    ).ensure_hashes()


def _require_dict(payload: Any, label: str) -> None:
    if not isinstance(payload, dict):
        raise ConnectorError(
            f"YouTube {label} response must be an object",
            kind=ConnectorErrorKind.PARSE,
            retryable=False,
        )


def parse_api_error(error: Any) -> ConnectorError:
    message = "YouTube API error"
    code = None
    if isinstance(error, dict):
        message = str(error.get("message") or message)
        code = error.get("code")
    kind = ConnectorErrorKind.PERMANENT
    retryable = False
    if code == 403 and "quota" in message.lower():
        kind = ConnectorErrorKind.RATE_LIMIT
        retryable = True
    elif code in {500, 503}:
        kind = ConnectorErrorKind.TRANSIENT
        retryable = True
    return ConnectorError(
        message,
        kind=kind,
        retryable=retryable,
        status_code=int(code) if isinstance(code, int) else None,
        details=error if isinstance(error, dict) else {"error": error},
    )


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
