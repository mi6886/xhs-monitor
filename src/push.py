"""
Telegram 推送模块
- 推送已入选(selected)且未推送过的笔记
- 推送失败记录保留，下次补推
"""

import logging
import html
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

from src.config import load_config
from src.db import get_unpushed_selected, insert_push_record

logger = logging.getLogger(__name__)


def _get_period(now: datetime) -> str:
    """Return the Beijing-time period label for this run."""
    explicit = os.environ.get("XHS_RUN_PERIOD", "").strip()
    if explicit in {"Morning", "Afternoon", "Evening"}:
        return explicit

    hour = now.hour
    if hour < 12:
        return "Morning"
    if hour < 18:
        return "Afternoon"
    return "Evening"


def _format_header(notes: list[dict]) -> str:
    """Format the digest header required by the scheduled Telegram push."""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    period = _get_period(now)
    return f"🔥 小红书爆款笔记 | {now:%Y-%m-%d} {period} | {len(notes)}条"


def _format_item(index: int, note: dict) -> str:
    """Format one note as a compact digest item."""
    title = html.escape(note.get("title") or "无标题")
    author = html.escape(note.get("author") or "未知作者")
    published = html.escape((note.get("published_at") or "")[:16] or "未知")
    source = html.escape(note.get("source_value") or "未知")
    url = html.escape(note.get("url") or "")
    likes = int(note.get("likes") or 0)
    collects = int(note.get("collects") or 0)
    comments = int(note.get("comments") or 0)
    shares = int(note.get("shares") or 0)

    lines = [
        f"{index}. {title}",
        author,
        published,
        f"🩷 {likes}  ⭐️ {collects}  💬 {comments}  🔄 {shares}",
        f"🔍 命中关键词: {source}",
    ]
    if url:
        lines.append(f'<a href="{url}">笔记链接</a>')
    else:
        lines.append("无链接")
    return "\n".join(lines)


def _format_plain_item(index: int, note: dict) -> str:
    """Format one note without Telegram HTML markup."""
    title = note.get("title") or "无标题"
    author = note.get("author") or "未知作者"
    published = (note.get("published_at") or "")[:16] or "未知"
    source = note.get("source_value") or "未知"
    likes = int(note.get("likes") or 0)
    collects = int(note.get("collects") or 0)
    comments = int(note.get("comments") or 0)
    shares = int(note.get("shares") or 0)
    url = note.get("url") or "无链接"

    return "\n".join([
        f"{index}. {title}",
        author,
        published,
        f"🩷 {likes}  ⭐️ {collects}  💬 {comments}  🔄 {shares}",
        f"🔍 命中关键词: {source}",
        url,
    ])


def format_plain_digest(notes: list[dict]) -> str:
    """Format selected notes in the exact plain-text style requested by the user."""
    sorted_notes = sorted(notes, key=lambda n: int(n.get("likes") or 0), reverse=True)
    return "\n\n".join(
        _format_plain_item(index, note)
        for index, note in enumerate(sorted_notes, 1)
    )


def _format_digest_messages(notes: list[dict]) -> list[str]:
    """Format selected notes into one or more Telegram-safe digest messages."""
    sorted_notes = sorted(notes, key=lambda n: int(n.get("likes") or 0), reverse=True)
    header = _format_header(sorted_notes)
    messages: list[str] = []
    current = header

    for index, note in enumerate(sorted_notes, 1):
        item = _format_item(index, note)
        next_text = f"{current}\n\n{item}"

        # Telegram messages max out at 4096 chars. Keep a little headroom.
        if len(next_text) > 3800 and current != header:
            messages.append(current)
            current = f"{header}\n\n{item}"
        else:
            current = next_text

    messages.append(current)
    return messages


def _send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """发送 Telegram 消息。返回是否成功。"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        data = resp.json()
        if data.get("ok"):
            return True
        else:
            logger.error(f"Telegram 发送失败: {data.get('description', 'unknown')}")
            return False
    except Exception as e:
        logger.error(f"Telegram 请求异常: {e}")
        return False


def run_push():
    """推送所有未推送的已入选笔记。"""
    cfg = load_config()
    tg_cfg = cfg.get("telegram", {})
    bot_token = tg_cfg.get("bot_token", "")
    chat_id = tg_cfg.get("chat_id", "")

    if not bot_token or not chat_id:
        logger.warning("Telegram 未配置，跳过推送")
        return

    notes = get_unpushed_selected()
    if not notes:
        logger.info("无需推送的笔记")
        return

    logger.info(f"开始汇总推送: {len(notes)} 条待推送")

    messages = _format_digest_messages(notes)
    sent_all = True

    for idx, msg in enumerate(messages, 1):
        ok = _send_telegram(bot_token, chat_id, msg)
        if ok:
            logger.info(f"汇总消息推送成功: part={idx}/{len(messages)}")
        else:
            sent_all = False
            logger.error(f"汇总消息推送失败: part={idx}/{len(messages)}")
            break

    status = "success" if sent_all else "failed"
    error_msg = None if sent_all else "batch send failed"
    for note in notes:
        insert_push_record(note["note_id"], status, error_msg=error_msg)

    if sent_all:
        logger.info(f"推送完成: 成功={len(notes)}, 消息数={len(messages)}")
    else:
        logger.info(f"推送完成: 成功=0, 失败={len(notes)}")
