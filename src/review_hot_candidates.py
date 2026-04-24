"""Review hot candidates with the configured LLM without changing state."""

from __future__ import annotations

import argparse
import json
import logging

from src.config import load_config, setup_logging
from src.db import get_conn, init_tables
from src.llm_cleaner import review_note

logger = logging.getLogger(__name__)


FAILED_FALLBACK_REASONS = (
    "LLM 语义清洗失败，按点赞阈值通过",
    "LLM API key 未配置，按点赞阈值通过",
)


def _load_notes(min_likes: int, failed_fallback_only: bool) -> list[dict]:
    conn = get_conn()
    params: list[object] = [min_likes]
    where = ["likes >= ?"]

    if failed_fallback_only:
        placeholders = ",".join("?" for _ in FAILED_FALLBACK_REASONS)
        where.append(f"llm_reason IN ({placeholders})")
        params.extend(FAILED_FALLBACK_REASONS)

    rows = conn.execute(f"""
        SELECT * FROM notes
        WHERE {' AND '.join(where)}
        ORDER BY likes DESC, first_seen_at DESC
    """, params).fetchall()
    return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-likes", type=int, default=1000)
    parser.add_argument("--failed-fallback-only", action="store_true")
    args = parser.parse_args()

    setup_logging()
    cfg = load_config()
    init_tables()

    notes = _load_notes(args.min_likes, args.failed_fallback_only)
    print(f"Reviewing {len(notes)} notes with likes >= {args.min_likes}")

    results = []
    for note in notes:
        decision = review_note(note, cfg)
        results.append({
            "note_id": note.get("note_id"),
            "title": note.get("title") or "无标题",
            "likes": int(note.get("likes") or 0),
            "source": note.get("source_value") or "未知",
            "should_push": bool(decision.get("should_push")),
            "defer": bool(decision.get("defer")),
            "score": decision.get("quality_score"),
            "category": decision.get("category"),
            "topic": decision.get("matched_topic"),
            "reason": decision.get("reason"),
            "url": note.get("url") or "",
        })

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("\n| # | 推送 | 分数 | 点赞 | 来源 | 标题 | 原因 |")
    print("|---:|---|---:|---:|---|---|---|")
    for index, item in enumerate(results, 1):
        flag = "YES" if item["should_push"] else ("DEFER" if item["defer"] else "NO")
        title = str(item["title"]).replace("|", "/")
        reason = str(item["reason"]).replace("|", "/")
        source = str(item["source"]).replace("|", "/")
        print(
            f"| {index} | {flag} | {item['score']} | {item['likes']} | "
            f"{source} | {title} | {reason} |"
        )

    if any(item["defer"] for item in results):
        logger.error("At least one note could not be reviewed by the LLM")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
