"""LLM-based semantic review for hot Xiaohongshu candidates."""

from __future__ import annotations

import json
import logging
from pathlib import Path
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_scorecard(llm_cfg: dict) -> str:
    scorecard_path = llm_cfg.get("scorecard_path") or "docs/topic_scorecard_v1.md"
    path = _repo_root() / scorecard_path
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("无法读取选题打分卡: %s", exc)
        return ""


def _fallback_decision(reason: str, should_push: bool = True) -> dict:
    return {
        "is_relevant": should_push,
        "should_push": should_push,
        "defer": not should_push,
        "matched_topic": "未进行 LLM 审核",
        "category": "未分类",
        "quality_score": 60 if should_push else 0,
        "score_breakdown": {},
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
        logger.warning("LLM API key 未配置，跳过 LLM 语义清洗")
        return _fallback_decision(
            "LLM API key 未配置，按点赞阈值通过" if fail_open else "LLM API key 未配置",
            should_push=fail_open,
        )

    max_content_chars = int(llm_cfg.get("max_content_chars", 900))
    scorecard = _load_scorecard(llm_cfg)
    push_score_threshold = int(llm_cfg.get("push_score_threshold", 35))
    strong_score_threshold = int(llm_cfg.get("strong_score_threshold", 50))
    model = llm_cfg.get("model") or "gpt-4o-mini"
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是小红书爆款笔记监控系统的选题评估器。"
                    "基础字段、时间、点赞数、链接已经由程序处理，你只做语义清洗和选题潜力评分。"
                    "请严格依据给定《选题评估打分卡 v1》给 0-100 分，并过滤广告、抽奖、纯带货、低信息量、"
                    "与监控来源明显无关的内容。必须只返回 JSON。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "选题评估打分卡": scorecard,
                    "要求": {
                        "输出 JSON 字段": {
                            "is_relevant": "布尔值，是否和监控来源相关",
                            "should_push": "布尔值，是否值得推送给用户",
                            "matched_topic": "命中的主题或关键词",
                            "category": "A栏选题品类",
                            "quality_score": "0 到 100 的整数总分",
                            "score_breakdown": {
                                "category_score": "A 选题品类分",
                                "information_gap_score": "B 信息差分",
                                "viral_signal_score": "C 爆款信号分",
                                "audience_emotion_adjustment": "D 受众与情绪修正",
                                "accessibility_bonus": "E 可触达感修正",
                                "persona_bonus": "人设匹配加成",
                            },
                            "reason": "用一句话解释通过或拒绝原因",
                        },
                        "推送阈值": f"相关且总分 >= {push_score_threshold} 才 should_push=true；>= {strong_score_threshold} 视为强推荐",
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
        logger.info("LLM 语义清洗请求: note_id=%s model=%s", note.get("note_id"), model)
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/mi6886/xhs-monitor",
                "X-Title": "xhs-monitor",
            },
            json=payload,
            timeout=timeout,
        )
        if not resp.ok:
            logger.error(
                "LLM API 返回错误: note_id=%s status=%s body=%s",
                note.get("note_id"),
                resp.status_code,
                resp.text[:500],
            )
            resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        decision = _parse_json_object(content)
    except Exception as exc:
        logger.error("LLM 语义清洗失败: note_id=%s error=%s", note.get("note_id"), exc)
        return _fallback_decision(
            "LLM 语义清洗失败，按点赞阈值通过" if fail_open else "LLM 语义清洗失败",
            should_push=fail_open,
        )

    should_push = bool(decision.get("should_push"))
    quality_score = decision.get("quality_score", 0)
    try:
        quality_score = max(0, min(100, int(quality_score)))
    except (TypeError, ValueError):
        quality_score = 0
    should_push = should_push and quality_score >= push_score_threshold

    return {
        "is_relevant": bool(decision.get("is_relevant", should_push)),
        "should_push": should_push,
        "matched_topic": str(decision.get("matched_topic") or "未知")[:80],
        "category": str(decision.get("category") or "未分类")[:80],
        "quality_score": quality_score,
        "score_breakdown": decision.get("score_breakdown") if isinstance(decision.get("score_breakdown"), dict) else {},
        "reason": str(decision.get("reason") or "无理由")[:240],
    }


def _parse_json_object(content: str) -> dict:
    """Parse strict JSON, with a small fallback for fenced JSON replies."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start:end + 1])
        raise


def review_and_promote(note: dict, cfg: dict) -> bool | None:
    """Run semantic review before moving a hot candidate to selected."""
    note_id = note.get("note_id")
    decision = review_note(note, cfg)

    if note_id:
        save_llm_review(note_id, decision)

    if decision.get("defer"):
        logger.warning(
            "LLM 未完成，保留候选等待下次重试: %s reason=%s",
            note_id,
            decision.get("reason"),
        )
        return None

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
