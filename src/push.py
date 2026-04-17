"""
Telegram 推送模块
- 推送已入选(selected)且未推送过的笔记
- 推送失败记录保留，下次补推
"""

import json
import logging
import requests

from src.config import load_config
from src.db import get_unpushed_selected, insert_push_record

logger = logging.getLogger(__name__)


def _format_message(note: dict) -> str:
    """格式化 Telegram 推送消息。"""
    title = note.get("title", "无标题")
    author = note.get("author", "未知")
    source = note.get("source_value", "")
    source_type = note.get("source_type", "")
    url = note.get("url", "")
    published = note.get("published_at", "")[:16] if note.get("published_at") else ""

    likes = note.get("likes", 0)
    collects = note.get("collects", 0)
    comments = note.get("comments", 0)
    shares = note.get("shares", 0)

    # 话题
    topics_str = ""
    if note.get("topics"):
        try:
            topics = json.loads(note["topics"])
            if topics:
                topics_str = " ".join(f"#{t}" for t in topics[:5])
        except (json.JSONDecodeError, TypeError):
            pass

    source_label = "关键词" if source_type == "keyword" else "账号"

    lines = [
        f"🔥 小红书爆款笔记",
        f"",
        f"📌 {title}",
        f"✍️ {author}",
    ]
    if topics_str:
        lines.append(f"🏷 {topics_str}")
    if published:
        lines.append(f"📅 {published}")
    lines.append(f"🔍 命中{source_label}: {source}")
    lines.append(f"")
    lines.append(f"❤️ {likes}  ⭐ {collects}  💬 {comments}  🔄 {shares}")
    lines.append(f"")
    lines.append(f"👉 查看原文: {url}")

    return "\n".join(lines)


def _send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """发送 Telegram 消息。返回是否成功。"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": False,
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

    logger.info(f"开始推送: {len(notes)} 条待推送")

    success = 0
    failed = 0

    for note in notes:
        note_id = note["note_id"]
        msg = _format_message(note)

        ok = _send_telegram(bot_token, chat_id, msg)
        if ok:
            insert_push_record(note_id, "success")
            success += 1
            logger.info(f"推送成功: {note_id} 「{note.get('title', '')[:30]}」")
        else:
            insert_push_record(note_id, "failed", error_msg="send failed")
            failed += 1
            logger.error(f"推送失败: {note_id}")

    logger.info(f"推送完成: 成功={success}, 失败={failed}")
