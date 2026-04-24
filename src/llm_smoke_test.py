"""Smoke test for the configured LLM semantic filter."""

from __future__ import annotations

import json
import logging

from src.config import load_config, setup_logging
from src.llm_cleaner import review_note

logger = logging.getLogger(__name__)


def main() -> int:
    setup_logging()
    cfg = load_config()
    note = {
        "note_id": "llm-smoke-test",
        "title": "GPT-Image-2 刚刚发布，AI 生图进入新阶段",
        "content": "OpenAI 发布 GPT-Image-2，图像生成质量、文字渲染和编辑能力明显提升，适合做产品速报和技术叙事。",
        "author": "系统测试",
        "source_type": "keyword",
        "source_value": "GPT-Image-2",
        "published_at": "2026-04-24T14:40:00",
        "likes": 2500,
        "collects": 900,
        "comments": 120,
        "shares": 300,
    }

    decision = review_note(note, cfg)
    print(json.dumps(decision, ensure_ascii=False, indent=2))

    if decision.get("defer"):
        logger.error("LLM smoke test deferred: %s", decision.get("reason"))
        return 1
    if decision.get("matched_topic") == "未进行 LLM 审核":
        logger.error("LLM smoke test did not receive a real model decision")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
