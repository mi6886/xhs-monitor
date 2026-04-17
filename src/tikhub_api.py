"""
TikHub API 封装
Base URL: https://api.tikhub.io
Auth: Authorization: Bearer <token>

MVP 只封装 3 个端点 (web_v3):
  1. fetch_search_notes  — 搜索笔记
  2. fetch_user_notes    — 用户笔记列表
  3. fetch_note_detail   — 笔记详情
"""

import time
import logging
import requests

from src.config import load_config

logger = logging.getLogger(__name__)


class TikHubClient:
    """TikHub API 客户端。接口与 JZLClient 对齐。"""

    def __init__(self):
        cfg = load_config()
        th_cfg = cfg.get("tikhub", {})
        self.base_url = th_cfg.get("base_url", "https://api.tikhub.io")
        self.api_key = th_cfg.get("api_key", "")
        self.interval = cfg.get("jzl", {}).get("request_interval", 2)

        if not self.api_key:
            logger.warning("TikHub API Key 未配置，API 调用将失败")

    def _request(self, path: str, params: dict) -> dict:
        """统一 GET 请求。TikHub 全部是 GET + query params。"""
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        logger.debug(f"TikHub 请求: GET {path} params={params}")

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            data = resp.json()
        except requests.exceptions.Timeout:
            logger.error(f"TikHub 请求超时: {path}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"TikHub 请求失败: {path} error={e}")
            raise

        # TikHub 错误码检查: HTTP 4xx 或 detail.code
        if resp.status_code >= 400:
            detail = data.get("detail", {})
            msg = detail.get("message_zh", detail.get("message", f"HTTP {resp.status_code}"))
            logger.error(f"TikHub HTTP 错误: {path} status={resp.status_code} msg={msg}")
            raise TikHubAPIError(resp.status_code, msg)

        code = data.get("code")
        if code is not None and code != 200 and code != 0:
            msg = data.get("message", data.get("msg", "unknown"))
            logger.error(f"TikHub 业务错误: {path} code={code} msg={msg}")
            raise TikHubAPIError(code, msg)

        time.sleep(self.interval)
        return data

    # ─── 1. 搜索笔记 ───

    def search_notes(self, keyword: str, page: int = 1,
                     sort: str = "", note_type: str = "",
                     note_time: str = "") -> dict:
        """
        搜索笔记 (app v1)。

        TikHub app/search_notes 参数名与 JZL 不同:
          JZL: sort, note_time
          TikHub: sort_type, filter_note_time

        返回格式与 JZL search_note_app 一致:
          data.data.items[].note.{id, title, liked_count, desc, timestamp, ...}

        Args:
            keyword: 搜索关键词
            page: 页码
            sort: 排序 (time_descending / popularity_descending)
            note_type: 笔记类型
            note_time: 时间筛选（JZL 不生效，TikHub 映射为中文）

        Returns:
            重组后的响应 dict，格式对齐 JZL
        """
        # 映射 sort 参数名
        params = {
            "keyword": keyword,
            "page": page,
            "sort_type": sort if sort else "general",
            "filter_note_time": "一天内",  # 固定筛选一天内，减少浪费
        }
        if note_type:
            params["filter_note_type"] = note_type

        resp = self._request("/api/v1/xiaohongshu/app/search_notes", params)
        # TikHub 嵌套多一层: data.data.items → 拍平为 data.items
        inner_data = resp.get("data", {}).get("data", {})
        items = inner_data.get("items", [])
        resp["data"]["items"] = items
        return resp

    # ─── 2. 用户笔记列表 ───

    def get_user_notes(self, user_id: str, page: int = 1,
                       cursor: str = "") -> dict:
        """
        获取用户笔记列表 (web_v2)。

        Args:
            user_id: 用户 ID
            cursor: 分页游标
            page: 页码（TikHub 用 cursor 分页，page 忽略）

        Returns:
            完整响应 dict
        """
        return self._request("/api/v1/xiaohongshu/web_v2/fetch_home_notes", {
            "user_id": user_id,
            "cursor": cursor,
            "num": 30,
        })

    # ─── 3. 笔记详情 ───

    def get_note_detail(self, note_id: str) -> dict:
        """
        获取笔记详情 (web_v2 feed_notes_v2)。

        返回格式与 JZL note_detail2 一致:
          data.note_list[0] + data.user

        Args:
            note_id: 笔记 ID

        Returns:
            完整响应 dict
        """
        return self._request("/api/v1/xiaohongshu/web_v2/fetch_feed_notes_v2", {
            "note_id": note_id,
        })


class TikHubAPIError(Exception):
    """TikHub API 业务错误。"""
    def __init__(self, code, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"TikHub API Error: code={code} msg={msg}")
