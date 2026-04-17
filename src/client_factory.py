"""
数据源工厂
根据 config.yaml 中的 data_source 字段返回对应的 API 客户端。
JZLClient 和 TikHubClient 接口对齐，调用方无需感知差异。
"""

import logging
from src.config import load_config

logger = logging.getLogger(__name__)


def get_client():
    """返回当前配置的 API 客户端实例。"""
    cfg = load_config()
    source = cfg.get("data_source", "jzl")

    if source == "tikhub":
        from src.tikhub_api import TikHubClient
        logger.info("数据源: TikHub")
        return TikHubClient()
    else:
        from src.jzl_api import JZLClient
        logger.info("数据源: JZL")
        return JZLClient()
