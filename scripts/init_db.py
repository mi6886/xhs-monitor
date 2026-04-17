#!/usr/bin/env python3
"""建库建表脚本。可重复运行，幂等。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config, setup_logging
from src.db import init_tables, get_conn

if __name__ == "__main__":
    setup_logging()
    load_config()
    init_tables()

    # 打印表信息验证
    conn = get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    print(f"\n数据库表 ({len(tables)}):")
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) as c FROM [{t['name']}]").fetchone()["c"]
        print(f"  - {t['name']}: {count} 行")
