"""
发现任务
- 遍历所有启用的关键词和账号
- 调用 JZL API 搜索/拉取笔记
- 筛选 24 小时内发布的笔记
- 候选入库 + 快照落库
- 如点赞已超过阈值，直接晋升
"""

import json
import logging
from datetime import datetime, timedelta

from src.config import load_config, get_mode, get_mode_value
from src.client_factory import get_client
from src.jzl_api import JZLAPIError
from src.tikhub_api import TikHubAPIError
from src.normalize import normalize_search_app, normalize_user_post2
from src.llm_cleaner import review_and_promote
from src.db import (
    get_enabled_targets,
    upsert_note,
    insert_check,
)

logger = logging.getLogger(__name__)


def _is_within_window(published_at: str, hours: int) -> bool:
    """判断发布时间是否在 N 小时内。"""
    if not published_at:
        return False
    try:
        pub_dt = datetime.fromisoformat(published_at)
        cutoff = datetime.now() - timedelta(hours=hours)
        return pub_dt >= cutoff
    except ValueError:
        logger.warning(f"无法解析发布时间: {published_at}")
        return False


def _process_note(note: dict, cfg: dict, raw_json: str = None):
    """
    处理单条标准化后的笔记:
    1. 检查发布时间
    2. 候选入库
    3. 快照落库
    4. 判定是否爆款
    """
    rules = cfg.get("rules", {})
    publish_hours = rules.get("publish_within_hours", 24)
    likes_threshold = rules.get("likes_threshold", 1000)

    note_id = note.get("note_id")
    if not note_id:
        return

    # 24h 窗口检查（关键词和账号统一过滤）
    if not _is_within_window(note.get("published_at"), publish_hours):
        logger.debug(f"跳过(非窗口内): {note_id} published={note.get('published_at')}")
        return

    # 候选入库
    result = upsert_note(note)
    likes = note.get("likes", 0)
    logger.info(f"笔记 {result}: {note_id} 「{note.get('title', '')[:30]}」 likes={likes}")

    # 快照落库
    save_raw = raw_json if get_mode() == "test" else None
    insert_check(
        note_id=note_id,
        likes=likes,
        collects=note.get("collects", 0),
        comments=note.get("comments", 0),
        shares=note.get("shares", 0),
        raw_data=save_raw,
    )

    # 爆款判定: 当前点赞 >= 阈值，直接晋升
    if likes >= likes_threshold:
        review_and_promote(note, cfg)


def discover_by_keywords(client, cfg: dict):
    """关键词发现任务。"""
    targets = get_enabled_targets("keyword")
    if not targets:
        logger.info("无启用的关键词目标")
        return

    pages = get_mode_value(cfg.get("discover", {}).get("keyword_pages", 1))
    batch_interval = get_mode_value(cfg.get("discover", {}).get("batch_interval", 2))

    logger.info(f"开始关键词发现: {len(targets)} 个关键词, 每个 {pages} 页")

    for target in targets:
        keyword = target["value"]
        logger.info(f"搜索关键词: {keyword}")

        all_outside_window = False
        for page in range(1, pages + 1):
            try:
                # TikHub 同时使用“一天内”筛选和热度排序，优先拿到 24h 内点赞最高的笔记。
                resp = client.search_notes(keyword, page=page,
                                           sort="popularity_descending")
            except (JZLAPIError, TikHubAPIError) as e:
                logger.error(f"关键词搜索失败: {keyword} page={page} error={e}")
                break
            except Exception as e:
                logger.error(f"关键词搜索异常: {keyword} page={page} error={e}")
                break

            # 解析: data.items[].note
            items = resp.get("data", {}).get("items", [])
            if not items:
                logger.debug(f"关键词 {keyword} 第 {page} 页无结果")
                break

            page_has_valid = False
            for item in items:
                note_raw = item.get("note", item)  # 兼容不同层级
                normalized = normalize_search_app(note_raw, source_value=keyword)
                if not _is_within_window(normalized.get("published_at"),
                                         cfg.get("rules", {}).get("publish_within_hours", 24)):
                    continue
                page_has_valid = True
                raw_json = json.dumps(item, ensure_ascii=False)
                _process_note(normalized, cfg, raw_json=raw_json)

            # TikHub 已按“一天内”过滤；这里仅作为 API 返回异常或时间解析异常时的保护。
            if not page_has_valid:
                logger.debug(f"关键词 {keyword} 第 {page} 页无窗口内笔记，停止翻页")
                break


def discover_by_accounts(client, cfg: dict):
    """账号发现任务。"""
    targets = get_enabled_targets("account")
    if not targets:
        logger.info("无启用的账号目标")
        return

    pages = get_mode_value(cfg.get("discover", {}).get("account_pages", 1))

    logger.info(f"开始账号发现: {len(targets)} 个账号, 每个 {pages} 页")

    for target in targets:
        name = target["value"]
        user_id = target.get("user_id")

        if not user_id:
            logger.warning(f"账号 {name} 缺少 user_id，跳过（需先补全）")
            continue

        logger.info(f"拉取账号笔记: {name} (uid={user_id})")

        cursor = ""
        for page in range(1, pages + 1):
            try:
                resp = client.get_user_notes(user_id, page=page, cursor=cursor)
            except (JZLAPIError, TikHubAPIError) as e:
                logger.error(f"账号拉取失败: {name} page={page} error={e}")
                break
            except Exception as e:
                logger.error(f"账号拉取异常: {name} page={page} error={e}")
                break

            # 解析: data.notes[]
            notes = resp.get("data", {}).get("notes", [])
            if not notes:
                logger.debug(f"账号 {name} 第 {page} 页无结果")
                break

            for note_raw in notes:
                normalized = normalize_user_post2(note_raw, source_value=name)
                raw_json = json.dumps(note_raw, ensure_ascii=False)
                _process_note(normalized, cfg, raw_json=raw_json)

            # 更新 cursor
            if notes:
                cursor = notes[-1].get("cursor", "")


def run_discover():
    """执行完整发现任务。"""
    cfg = load_config()
    client = get_client()

    logger.info("=" * 60)
    logger.info(f"发现任务开始 mode={get_mode()}")
    logger.info("=" * 60)

    discover_by_keywords(client, cfg)
    discover_by_accounts(client, cfg)

    logger.info("发现任务完成")
