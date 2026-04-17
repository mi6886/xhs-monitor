#!/usr/bin/env python3
"""
导入监控目标脚本
从 seed_accounts.txt 和 seed_keywords.txt 导入到 watch_targets 表。
可重复运行，已存在的目标会跳过。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config, setup_logging
from src.db import init_tables, upsert_watch_target

import logging
logger = logging.getLogger(__name__)


def load_seed_file(filepath: str) -> list[str]:
    """读取种子文件，返回非空非注释行列表。"""
    if not os.path.exists(filepath):
        logger.warning(f"种子文件不存在: {filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    result = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            result.append(line)
    return result


def main():
    setup_logging()
    cfg = load_config()
    init_tables()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    seeds_cfg = cfg.get("seeds", {})

    # 导入账号
    accounts_file = os.path.join(root, seeds_cfg.get("accounts", "seed_accounts.txt"))
    accounts = load_seed_file(accounts_file)
    acc_count = 0
    for name in accounts:
        upsert_watch_target("account", name)
        acc_count += 1
    logger.info(f"导入账号: {acc_count} 条")

    # 导入关键词
    keywords_file = os.path.join(root, seeds_cfg.get("keywords", "seed_keywords.txt"))
    keywords = load_seed_file(keywords_file)
    kw_count = 0
    for kw in keywords:
        upsert_watch_target("keyword", kw)
        kw_count += 1
    logger.info(f"导入关键词: {kw_count} 条")

    print(f"\n导入完成: {acc_count} 个账号, {kw_count} 个关键词")


if __name__ == "__main__":
    main()
