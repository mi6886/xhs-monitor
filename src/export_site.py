"""Export Xiaohongshu digest data for the static GitHub Pages site."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.db import get_conn

logger = logging.getLogger(__name__)

PERIOD_SLUGS = {
    "Morning": "morning",
    "Afternoon": "afternoon",
    "Evening": "evening",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_topics(topics: str | None) -> list[str]:
    if not topics:
        return []
    try:
        value = json.loads(topics)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _clean_note(note: dict) -> dict:
    return {
        "note_id": note.get("note_id", ""),
        "title": note.get("title") or "无标题",
        "content": note.get("content") or "",
        "author": note.get("author") or "未知作者",
        "author_id": note.get("author_id") or "",
        "cover_image": note.get("cover_image") or "",
        "url": note.get("url") or "",
        "note_type": note.get("note_type") or "normal",
        "topics": _parse_topics(note.get("topics")),
        "published_at": note.get("published_at") or "",
        "likes": int(note.get("likes") or 0),
        "collects": int(note.get("collects") or 0),
        "comments": int(note.get("comments") or 0),
        "shares": int(note.get("shares") or 0),
        "source_type": note.get("source_type") or "",
        "source_value": note.get("source_value") or "未知",
        "source_types": note.get("source_types") or [],
        "source_values": note.get("source_values") or [],
        "merged_note_ids": note.get("merged_note_ids") or [note.get("note_id", "")],
        "llm_score": note.get("llm_score"),
        "llm_topic": note.get("llm_topic") or "",
        "llm_reason": note.get("llm_reason") or "",
        "llm_category": note.get("llm_category") or "",
        "first_seen_at": note.get("first_seen_at") or "",
        "last_checked_at": note.get("last_checked_at") or "",
    }


def _status_counts() -> dict[str, int]:
    conn = get_conn()
    rows = conn.execute("SELECT status, COUNT(*) AS count FROM notes GROUP BY status").fetchall()
    counts = {row["status"]: row["count"] for row in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "candidate": counts.get("candidate", 0),
        "selected": counts.get("selected", 0),
        "expired": counts.get("expired", 0),
    }


def export_digest(notes: list[dict], period: str, delivery_status: str = "success") -> Path:
    """Write the digest notes to site/data for GitHub Pages."""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    period_slug = PERIOD_SLUGS.get(period, period.lower())
    sorted_notes = sorted(notes, key=lambda n: int(n.get("likes") or 0), reverse=True)
    cleaned_notes = [_clean_note(note) for note in sorted_notes]

    data = {
        "source": "xhs",
        "title": "小红书爆款笔记",
        "date": f"{now:%Y-%m-%d}",
        "period": period_slug,
        "period_label": period,
        "generated_at": now.isoformat(),
        "delivery_status": delivery_status,
        "count": len(cleaned_notes),
        "stats": _status_counts(),
        "notes": cleaned_notes,
    }

    data_dir = _repo_root() / "site" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    output_path = data_dir / f"final-{data['date']}-{period_slug}.json"
    latest_path = data_dir / f"latest-{period_slug}.json"
    all_latest_path = data_dir / "latest.json"

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    output_path.write_text(payload + "\n", encoding="utf-8")
    latest_path.write_text(payload + "\n", encoding="utf-8")
    all_latest_path.write_text(payload + "\n", encoding="utf-8")

    logger.info("已导出网页数据: %s notes=%s", output_path, len(cleaned_notes))
    return output_path
