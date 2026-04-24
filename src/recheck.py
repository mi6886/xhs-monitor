"""
复查任务
- 对 candidate 状态的笔记进行二次复查
- 调用 note_detail2（10积分/次）获取最新互动数据
- 快照落库
- 爆款判定: 任一快照点赞 >= 阈值 → 晋升
- 淘汰判定: 首次发现超过 24 小时窗口仍未过阈值 → 淘汰
"""

import json
import logging
from datetime import datetime, timedelta

from src.config import load_config, get_mode, get_mode_value
from src.client_factory import get_client
from src.jzl_api import JZLAPIError
from src.tikhub_api import TikHubAPIError
from src.normalize import normalize_note_detail2
from src.llm_cleaner import review_and_promote
from src.db import (
    get_candidates,
    insert_check,
    expire_note,
    get_max_likes,
    get_conn,
)

logger = logging.getLogger(__name__)


def run_recheck():
    """执行复查任务。"""
    cfg = load_config()
    client = get_client()
    rules = cfg.get("rules", {})
    likes_threshold = rules.get("likes_threshold", 1000)
    window_hours = rules.get("watch_window_hours", 24)
    max_per_run = get_mode_value(cfg.get("recheck", {}).get("max_per_run", 50))

    candidates = get_candidates()
    if not candidates:
        logger.info("无需复查的候选笔记")
        return

    logger.info("=" * 60)
    logger.info(f"复查任务开始: {len(candidates)} 条候选, 本次最多复查 {max_per_run} 条")
    logger.info("=" * 60)

    now = datetime.now()
    checked = 0
    promoted = 0
    expired = 0

    for note in candidates:
        if checked >= max_per_run:
            logger.info(f"达到本次复查上限 {max_per_run}，剩余下次处理")
            break

        note_id = note["note_id"]
        first_seen = note["first_seen_at"]

        # 判断是否超出观察窗口
        try:
            first_seen_dt = datetime.fromisoformat(first_seen)
        except (ValueError, TypeError):
            first_seen_dt = now  # 容错

        window_deadline = first_seen_dt + timedelta(hours=window_hours)

        if now > window_deadline:
            # 窗口已关闭，检查历史最高点赞
            max_likes = get_max_likes(note_id)
            if max_likes >= likes_threshold:
                note_for_review = dict(note)
                note_for_review["likes"] = max_likes
                if review_and_promote(note_for_review, cfg):
                    promoted += 1
                    logger.info(f"窗口关闭时晋升: {note_id} max_likes={max_likes}")
                else:
                    expired += 1
            else:
                expire_note(note_id)
                expired += 1
                logger.info(f"淘汰: {note_id} max_likes={max_likes} < {likes_threshold}")
            continue

        # 窗口内：调 API 复查
        try:
            resp = client.get_note_detail(note_id)
        except (JZLAPIError, TikHubAPIError) as e:
            logger.error(f"复查失败: {note_id} error={e}")
            checked += 1
            continue
        except Exception as e:
            logger.error(f"复查异常: {note_id} error={e}")
            checked += 1
            continue

        normalized = normalize_note_detail2(resp)
        if not normalized:
            logger.warning(f"复查返回空数据: {note_id}")
            checked += 1
            continue

        likes = normalized.get("likes", 0)
        collects = normalized.get("collects", 0)
        comments = normalized.get("comments", 0)
        shares = normalized.get("shares", 0)

        # 快照落库
        save_raw = json.dumps(resp, ensure_ascii=False) if get_mode() == "test" else None
        insert_check(note_id, likes, collects, comments, shares, raw_data=save_raw)

        # 更新 notes 表互动数据
        conn = get_conn()
        conn.execute("""
            UPDATE notes SET likes=?, collects=?, comments=?, shares=?,
                last_checked_at=datetime('now'), check_count=check_count+1
            WHERE note_id=?
        """, (likes, collects, comments, shares, note_id))
        conn.commit()

        logger.info(f"复查完成: {note_id} 「{note.get('title', '')[:30]}」 likes={likes}")

        # 爆款判定
        if likes >= likes_threshold:
            note_for_review = dict(note)
            note_for_review.update({
                "likes": likes,
                "collects": collects,
                "comments": comments,
                "shares": shares,
            })
            if review_and_promote(note_for_review, cfg):
                promoted += 1
            else:
                expired += 1

        checked += 1

    logger.info(f"复查任务完成: 检查={checked}, 晋升={promoted}, 淘汰={expired}")
