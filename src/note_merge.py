"""Utilities for merging duplicate notes before display."""

from __future__ import annotations

import re


_SPACE_RE = re.compile(r"\s+")


def _norm_text(value: object) -> str:
    """Normalize text enough to identify the same note across search targets."""
    return _SPACE_RE.sub("", str(value or "")).strip().lower()


def _duplicate_key(note: dict) -> tuple[str, str, str] | None:
    """Return a conservative key for display-time de-duplication."""
    title = _norm_text(note.get("title"))
    author = _norm_text(note.get("author"))
    published_day = str(note.get("published_at") or "")[:10]

    if not title or title == _norm_text("无标题") or not author or not published_day:
        return None
    return title, author, published_day


def _iter_sources(note: dict) -> list[dict[str, str]]:
    source_values = note.get("source_values")
    source_types = note.get("source_types")

    if isinstance(source_values, list):
        values = [str(value).strip() for value in source_values if str(value).strip()]
        if isinstance(source_types, list):
            types = [str(value).strip() or "keyword" for value in source_types]
        else:
            types = [str(note.get("source_type") or "keyword")] * len(values)
        return [
            {"type": types[index] if index < len(types) else "keyword", "value": value}
            for index, value in enumerate(values)
        ]

    value = str(note.get("source_value") or "").strip()
    if not value:
        return []
    return [{"type": str(note.get("source_type") or "keyword"), "value": value}]


def _merge_sources(target: dict, note: dict) -> None:
    seen = {
        (str(source.get("type") or ""), str(source.get("value") or ""))
        for source in target["_sources"]
    }
    for source in _iter_sources(note):
        key = (source["type"], source["value"])
        if key not in seen:
            target["_sources"].append(source)
            seen.add(key)


def _note_ids(note: dict) -> list[str]:
    ids = note.get("merged_note_ids")
    if isinstance(ids, list):
        values = [str(value).strip() for value in ids if str(value).strip()]
    else:
        values = []

    note_id = str(note.get("note_id") or "").strip()
    if note_id and note_id not in values:
        values.append(note_id)
    return values


def _finish_note(note: dict) -> dict:
    sources = note.pop("_sources", [])
    source_types = [source["type"] for source in sources if source.get("value")]
    source_values = [source["value"] for source in sources if source.get("value")]

    if source_values:
        note["source_types"] = source_types
        note["source_values"] = source_values
        if len(set(source_types)) == 1:
            note["source_type"] = source_types[0]
        else:
            note["source_type"] = "mixed"
        note["source_value"] = "、".join(source_values)

    return note


def merge_duplicate_notes(notes: list[dict]) -> list[dict]:
    """Merge display duplicates while preserving the original source records."""
    groups: dict[tuple[str, str, str], dict] = {}
    merged: list[dict] = []

    for note in notes:
        key = _duplicate_key(note)
        if key is None:
            item = dict(note)
            item["_sources"] = []
            item["merged_note_ids"] = _note_ids(note)
            _merge_sources(item, note)
            merged.append(item)
            continue

        existing = groups.get(key)
        if existing is None:
            item = dict(note)
            item["_sources"] = []
            item["merged_note_ids"] = _note_ids(note)
            _merge_sources(item, note)
            groups[key] = item
            merged.append(item)
            continue

        existing_ids = existing.setdefault("merged_note_ids", [])
        for note_id in _note_ids(note):
            if note_id and note_id not in existing_ids:
                existing_ids.append(note_id)

        note_likes = int(note.get("likes") or 0)
        existing_likes = int(existing.get("likes") or 0)
        if note_likes > existing_likes:
            for field in (
                "note_id",
                "url",
                "cover_image",
                "content",
                "topics",
                "note_type",
                "published_at",
                "last_checked_at",
            ):
                if note.get(field):
                    existing[field] = note.get(field)

        for metric in ("likes", "collects", "comments", "shares"):
            existing[metric] = max(int(existing.get(metric) or 0), int(note.get(metric) or 0))

        _merge_sources(existing, note)

    return [_finish_note(note) for note in merged]
