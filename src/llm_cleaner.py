"""LLM-based semantic review for hot Xiaohongshu candidates."""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from src.db import expire_note, promote_note, save_llm_review

logger = logging.getLogger(__name__)


def _is_enabled(cfg: dict) -> bool:
    return bool(cfg.get("llm_cleaning", {}).get("enabled", False))


def _source_label(note: dict) -> str:
    if note.get("source_type") == "account":
        return f"来源账号: {note.get('source_value') or '未知'}"
    return f"命中关键词: {note.get('source_value') or '未知'}"


def _trim(text: Any, max_chars: int) -> str:
    value = str(text or "").strip()
    return value[:max_chars]


def _fallback_decision(reason: str, should_push: bool = True) -> dict:
    return {
        "is_relevant": should_push,
        "should_push": should_push,
        "matched_topic": "未进行 LLM 审核",
        "quality_score": 6 if should_push else 0,
        "reason": reason,
    }


def review_note(note: dict, cfg: dict) -> dict:
    """Ask the LLM whether an already-hot note should be pushed."""
    llm_cfg = cfg.get("llm_cleaning", {})
    if not _is_enabled(cfg):
        return _fallback_decision("LLM 语义清洗未开启")

    api_key = llm_cfg.get("api_key", "")
    fail_open = bool(llm_cfg.get("fail_open", True))
    if not api_key:
        logger.warning("OPENAI_API_KEY 未配置，跳过 LLM 语义清洗")
        return _fallback_decision(
            "OPENAI_API_KEY 未配置，按点赞阈值通过" if fail_open else "OPENAI_API_KEY 未配置",
            should_push=fail_open,
        )

    max_content_chars = int(llm_cfg.get("max_content_chars", 900))
    payload = {
        "model": llm_cfg.get("model") or "gpt-4o-mini",
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是小红书爆款笔记监控系统的语义清洗器。"
                    "只判断一条已经满足时间和点赞门槛的笔记是否值得推送。"
                    "请过滤广告、抽奖、纯带货、低信息量、与监控来源明显无关的内容。"
                    "必须只返回 JSON。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "要求": {
                        "返回字段": [
                            "is_relevant",
                            "should_push",
                            "matched_topic",
                            "quality_score",
                            "reason",
                        ],
                        "quality_score": "0 到 10 的整数",
                        "should_push": "只有内容和监控来源相关且有信息价值时才为 true",
                    },
                    "笔记": {
                        "标题": note.get("title") or "",
                        "正文": _trim(note.get("content"), max_content_chars),
                        "作者": note.get("author") or "",
                        "来源": _source_label(note),
                        "发布时间": note.get("published_at") or "",
                        "点赞": int(note.get("likes") or 0),
                        "收藏": int(note.get("collects") or 0),
                        "评论": int(note.get("comments") or 0),
                        "转发": int(note.get("shares") or 0),
                    },
                }, ensure_ascii=False),
            },
        ],
    }

    base_url = (llm_cfg.get("base_url") or "https://api.openai.com/v1").rstrip("/")
    timeout = int(llm_cfg.get("timeout_seconds", 20))

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        decision = json.loads(content)
    except Exception as exc:
        logger.error("LLM 语义清洗失败: note_id=%s error=%s", note.get("note_id"), exc)
        return _fallback_decision(
            "LLM 语义清洗失败，按点赞阈值通过" if fail_open else "LLM 语义清洗失败",
            should_push=fail_open,
        )

    should_push = bool(decision.get("should_push"))
    quality_score = decision.get("quality_score", 0)
    try:
        quality_score = max(0, min(10, int(quality_score)))
    except (TypeError, ValueError):
        quality_score = 0

    return {
        "is_relevant": bool(decision.get("is_relevant", should_push)),
        "should_push": should_push,
        "matched_topic": str(decision.get("matched_topic") or "未知")[:80],
        "quality_score": quality_score,
        "reason": str(decision.get("reason") or "无理由")[:240],
    }


def review_and_promote(note: dict, cfg: dict) -> bool:
    """Run semantic review before moving a hot candidate to selected."""
    note_id = note.get("note_id")
    decision = review_note(note, cfg)

    if note_id:
        save_llm_review(note_id, decision)

    if decision.get("should_push"):
        promote_note(note_id)
        logger.info(
            "LLM 通过并晋升: %s score=%s topic=%s reason=%s",
            note_id,
            decision.get("quality_score"),
            decision.get("matched_topic"),
            decision.get("reason"),
        )
        return True

    expire_note(note_id)
    logger.info(
        "LLM 拒绝并淘汰: %s score=%s topic=%s reason=%s",
        note_id,
        decision.get("quality_score"),
        decision.get("matched_topic"),
        decision.get("reason"),
    )
    return False
