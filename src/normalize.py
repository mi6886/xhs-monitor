"""
标准化函数
将 3 个不同 JZL 接口的返回数据统一为 notes 表结构。

三个接口返回结构差异很大:
  - search_note_app:  data.items[].note     (App 搜索)
  - user_post2:       data.notes[]          (App 用户笔记列表)
  - note_detail2:     data.note_list[0]     (App 笔记详情)
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _unix_to_iso(ts) -> str:
    """将 Unix 时间戳转为 ISO 格式。支持秒和毫秒。"""
    if not ts:
        return None
    ts = int(ts)
    if ts > 1e12:  # 毫秒
        ts = ts / 1000
    try:
        return datetime.fromtimestamp(ts).isoformat()
    except (ValueError, OSError):
        logger.warning(f"无法解析时间戳: {ts}")
        return None


def _extract_cover(images_list: list) -> str:
    """从图片列表中提取第一张封面图 URL。"""
    if not images_list:
        return None
    first = images_list[0]
    # 不同接口的图片 URL 字段名不同
    return (first.get("url") or first.get("url_size_large")
            or first.get("url_default") or first.get("original") or None)


def _extract_topics_from_hashtag(hash_tags: list) -> str:
    """从 hash_tag 数组提取话题名，返回 JSON 字符串。"""
    if not hash_tags:
        return None
    names = [t.get("name", "") for t in hash_tags if t.get("name")]
    return json.dumps(names, ensure_ascii=False) if names else None


def _extract_topics_from_tag_list(tag_list: list) -> str:
    """从 tag_list 数组提取话题名，返回 JSON 字符串。"""
    if not tag_list:
        return None
    names = [t.get("name", "") for t in tag_list
             if t.get("type") == "topic" and t.get("name")]
    return json.dumps(names, ensure_ascii=False) if names else None


def _build_note_url(note_id: str, xsec_token: str = None) -> str:
    """构建小红书笔记链接。带 xsec_token 才能正常打开。"""
    base = f"https://www.xiaohongshu.com/explore/{note_id}"
    if xsec_token:
        return f"{base}?xsec_token={xsec_token}&xsec_source=pc_search"
    return base


# ─── 1. search_note_app (App v58) ───

def normalize_search_app(raw_item: dict, source_value: str) -> dict:
    """
    标准化搜索接口(App v58)返回的单条数据。

    raw_item 是 data.items[i].note
    """
    note = raw_item  # 已经是 note 对象

    user = note.get("user", {})
    images_list = note.get("images_list", [])

    note_id = note.get("id") or note.get("note_id", "")
    xsec_token = note.get("xsec_token", "")

    return {
        "note_id": note_id,
        "title": note.get("title", ""),
        "content": note.get("desc", ""),
        "author": user.get("nickname", ""),
        "author_id": user.get("userid", "") or user.get("user_id", ""),
        "cover_image": _extract_cover(images_list),
        "url": _build_note_url(note_id, xsec_token),
        "note_type": note.get("type", ""),
        "topics": _extract_topics_from_hashtag(note.get("hash_tag", [])),
        "published_at": _unix_to_iso(note.get("timestamp")),
        "likes": int(note.get("liked_count", 0) or 0),
        "collects": int(note.get("collected_count", 0) or 0),
        "comments": int(note.get("comments_count", 0) or 0),
        "shares": int(note.get("shared_count", 0) or 0),
        "source_type": "keyword",
        "source_value": source_value,
    }


# ─── 2. user_post2 (App v58) ───

def normalize_user_post2(raw_item: dict, source_value: str) -> dict:
    """
    标准化用户笔记列表(App v58)返回的单条数据。

    raw_item 是 data.notes[i]
    """
    user = raw_item.get("user", {})
    images_list = raw_item.get("images_list", [])

    return {
        "note_id": raw_item.get("note_id") or raw_item.get("id", ""),
        "title": raw_item.get("display_title", "") or raw_item.get("title", ""),
        "content": raw_item.get("desc", ""),
        "author": user.get("nickname", ""),
        "author_id": user.get("user_id", ""),
        "cover_image": _extract_cover(images_list),
        "url": _build_note_url(raw_item.get("note_id") or raw_item.get("id", "")),
        "note_type": raw_item.get("type", ""),
        "topics": None,  # user_post2 不返回话题
        "published_at": _unix_to_iso(raw_item.get("create_time")),
        "likes": int(raw_item.get("likes", 0) or 0),
        "collects": int(raw_item.get("collected_count", 0) or 0),
        "comments": int(raw_item.get("comments_count", 0) or 0),
        "shares": int(raw_item.get("shared_count", 0) or 0),
        "source_type": "account",
        "source_value": source_value,
    }


# ─── 3. note_detail2 (App vx56) ───

def normalize_note_detail2(raw_data: dict) -> dict:
    """
    标准化笔记详情(App vx56)返回的数据。

    raw_data 是完整的 API 响应。
    笔记在 data.note_list[0] 中。
    """
    data = raw_data.get("data", {})
    note_list = data.get("note_list", [])
    if not note_list:
        return None

    note = note_list[0]
    user = data.get("user", {}) or note.get("user", {})
    images_list = note.get("images_list", [])

    note_id = note.get("id", "")
    # 详情接口的链接从 share_info.link 取（带完整 token）
    share_link = note.get("share_info", {}).get("link", "")
    if not share_link:
        xsec_token = note.get("xsec_token", "") or data.get("xsec_token", "")
        share_link = _build_note_url(note_id, xsec_token)

    return {
        "note_id": note_id,
        "title": note.get("title", "") or data.get("note_card", {}).get("title", ""),
        "content": note.get("desc", ""),
        "author": user.get("nickname", "") or user.get("name", ""),
        "author_id": user.get("userid", "") or user.get("id", ""),
        "cover_image": _extract_cover(images_list),
        "url": share_link,
        "note_type": note.get("type", ""),
        "topics": _extract_topics_from_hashtag(note.get("hash_tag", [])),
        "published_at": _unix_to_iso(note.get("time")),
        "likes": int(note.get("liked_count", 0) or 0),
        "collects": int(note.get("collected_count", 0) or 0),
        "comments": int(note.get("comments_count", 0) or 0),
        "shares": int(note.get("shared_count", 0) or 0),
    }


# ─── 4. note_detail4 (App v9) — 备选 ───

def normalize_note_detail4(raw_data: dict) -> dict:
    """
    标准化笔记详情4(App v9)。备选接口。

    raw_data 是完整 API 响应。
    笔记在 data.note_card 中。
    """
    data = raw_data.get("data", {})
    card = data.get("note_card", {})
    if not card:
        return None

    user = card.get("user", {})
    interact = card.get("interact_info", {})
    image_list = card.get("image_list", [])

    def _safe_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    cover = None
    if image_list:
        first = image_list[0]
        cover = first.get("url_pre") or first.get("url_default") or first.get("url")

    return {
        "note_id": card.get("note_id", ""),
        "title": card.get("title", ""),
        "content": card.get("desc", ""),
        "author": user.get("nickname", ""),
        "author_id": user.get("user_id", ""),
        "cover_image": cover,
        "url": _build_note_url(card.get("note_id", "")),
        "note_type": card.get("type", ""),
        "topics": _extract_topics_from_tag_list(card.get("tag_list", [])),
        "published_at": _unix_to_iso(card.get("time")),
        "likes": _safe_int(interact.get("liked_count", 0)),
        "collects": _safe_int(interact.get("collected_count", 0)),
        "comments": _safe_int(interact.get("comment_count", 0)),
        "shares": _safe_int(interact.get("share_count", 0)),
    }
