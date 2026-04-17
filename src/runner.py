"""
主调度入口
串联: 发现 → 复查 → 推送

用法:
    python -m src.runner              # 完整流程
    python -m src.runner discover     # 只运行发现
    python -m src.runner recheck      # 只运行复查
    python -m src.runner push         # 只运行推送
"""

import sys
import time
import logging

from src.config import load_config, get_mode, setup_logging
from src.db import init_tables, get_conn
from src.discover import run_discover
from src.recheck import run_recheck
from src.push import run_push

logger = logging.getLogger(__name__)


def print_stats():
    """打印当前数据库状态摘要。"""
    conn = get_conn()
    stats = {}
    for table in ["watch_targets", "notes", "note_checks", "push_records"]:
        row = conn.execute(f"SELECT COUNT(*) as c FROM {table}").fetchone()
        stats[table] = row["c"]

    # notes 各状态计数
    status_rows = conn.execute(
        "SELECT status, COUNT(*) as c FROM notes GROUP BY status"
    ).fetchall()
    status_map = {r["status"]: r["c"] for r in status_rows}

    logger.info("--- 数据库状态 ---")
    logger.info(f"  监控目标: {stats['watch_targets']}")
    logger.info(f"  笔记总数: {stats['notes']} "
                f"(candidate={status_map.get('candidate', 0)}, "
                f"selected={status_map.get('selected', 0)}, "
                f"expired={status_map.get('expired', 0)})")
    logger.info(f"  快照记录: {stats['note_checks']}")
    logger.info(f"  推送记录: {stats['push_records']}")


def run_all():
    """完整流程: 发现 → 复查 → 推送。"""
    start = time.time()

    logger.info("=" * 60)
    logger.info(f"监控系统启动 mode={get_mode()}")
    logger.info("=" * 60)

    # 1. 发现
    try:
        run_discover()
    except Exception as e:
        logger.error(f"发现任务异常: {e}", exc_info=True)

    # 2. 复查
    try:
        run_recheck()
    except Exception as e:
        logger.error(f"复查任务异常: {e}", exc_info=True)

    # 3. 推送
    try:
        run_push()
    except Exception as e:
        logger.error(f"推送任务异常: {e}", exc_info=True)

    elapsed = time.time() - start
    logger.info(f"本次运行耗时: {elapsed:.1f} 秒")
    print_stats()


def main():
    setup_logging()
    load_config()
    init_tables()

    # 解析子命令
    command = sys.argv[1] if len(sys.argv) > 1 else "all"

    if command == "discover":
        run_discover()
    elif command == "recheck":
        run_recheck()
    elif command == "push":
        run_push()
    elif command == "stats":
        print_stats()
    elif command == "all":
        run_all()
    else:
        print(f"未知命令: {command}")
        print("可用命令: all, discover, recheck, push, stats")
        sys.exit(1)


if __name__ == "__main__":
    main()
