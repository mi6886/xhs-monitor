"""
JZL (极致了/云端点) API 最小封装
Base URL: https://api.yddm.com
Auth: X-API-Key header

MVP 只封装 3 个端点:
  1. search_note_app  — 关键词搜索笔记 (App v58)
  2. user_post2       — 用户笔记列表 (App v58)
  3. note_detail2     — 笔记详情 (App vx56)
"""

import time
import logging
import requests

from src.config import load_config

logger = logging.getLogger(__name__)


class JZLClient:
    """JZL API 客户端。"""

    def __init__(self):
        cfg = load_config()
        jzl_cfg = cfg.get("jzl", {})
        self.base_url = jzl_cfg.get("base_url", "https://api.yddm.com")
        self.api_key = jzl_cfg.get("api_key", "")
        self.interval = jzl_cfg.get("request_interval", 2)

        if not self.api_key:
            logger.warning("JZL API Key 未配置，API 调用将失败")

    def _request(self, path: str, body: dict) -> dict:
        """统一请求方法。返回完整响应 dict 或抛异常。"""
        url = f"{self.base_url}{path}"
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

        logger.debug(f"JZL 请求: POST {path} body={body}")

        try:
            resp = requests.post(url, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            logger.error(f"JZL 请求超时: {path}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"JZL 请求失败: {path} error={e}")
            raise

        code = data.get("code")
        if code != 0:
            msg = data.get("msg", "unknown")
            logger.error(f"JZL 业务错误: {path} code={code} msg={msg}")
            raise JZLAPIError(code, msg)

        # 记录积分消耗
        inner = data.get("data", {})
        cost = inner.get("cost", 0)
        balance = inner.get("balance", 0)
        if cost:
            logger.info(f"JZL 积分消耗: {cost}, 余额: {balance}")

        # 请求间隔
        time.sleep(self.interval)

        return data

    # ─── 1. 关键词搜索笔记 (App v58) ───

    def search_notes(self, keyword: str, page: int = 1,
                     sort: str = "", note_type: str = "",
                     note_time: str = "") -> dict:
        """
        搜索笔记。

        Args:
            keyword: 搜索关键词
            page: 页码，从 1 开始
            sort: 排序方式（空字符串=综合）
            note_type: 笔记类型筛选
            note_time: 时间筛选

        Returns:
            完整响应 dict，笔记在 data.items[].note 中
        """
        return self._request("/xhs/search_note_app", {
            "keyword": keyword,
            "page": page,
            "sort": sort,
            "note_type": note_type,
            "note_time": note_time,
        })

    # ─── 2. 用户笔记列表 (App v58) ───

    def get_user_notes(self, user_id: str, page: int = 1,
                       cursor: str = "") -> dict:
        """
        获取用户笔记列表。

        Args:
            user_id: 小红书用户 ID
            page: 页码
            cursor: 分页游标（首页传空）

        Returns:
            完整响应 dict，笔记在 data.notes[] 中
        """
        return self._request("/xhs/user_post2", {
            "user_id": user_id,
            "page": page,
            "cursor": cursor,
        })

    # ─── 3. 笔记详情 (App vx56) — 10 积分/次 ───

    def get_note_detail(self, note_id: str) -> dict:
        """
        获取笔记详情。

        Args:
            note_id: 笔记 ID

        Returns:
            完整响应 dict，详情在 data.note_list[0] 中
        """
        return self._request("/xhs/note_detail2", {
            "note_id": note_id,
        })


class JZLAPIError(Exception):
    """JZL API 业务错误。"""
    def __init__(self, code: int, msg: str):
        self.code = code
        self.msg = msg
        super().__init__(f"JZL API Error: code={code} msg={msg}")
