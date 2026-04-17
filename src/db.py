"""
SQLite 数据库模块
- 建库建表
- 4 张表的基本 CRUD
"""

import os
import sqlite3
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_conn = None


def get_db_path() -> str:
    from src.config import load_config
    cfg = load_config()
    db_rel = cfg.get("database", {}).get("path", "data/monitor.db")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, db_rel)


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    logger.info(f"连接数据库: {db_path}")
    _conn = sqlite3.connect(db_path)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA foreign_keys=ON")
    return _conn


def init_tables():
    """建表。幂等操作，可重复调用。"""
    conn = get_conn()
    conn.executescript("""
    -- 1. watch_targets: 监控账号和关键词
    CREATE TABLE IF NOT EXISTS watch_targets (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        type        TEXT NOT NULL CHECK(type IN ('keyword', 'account')),
        value       TEXT NOT NULL,               -- 关键词文本 或 账号昵称
        user_id     TEXT,                        -- 账号的小红书 user_id（关键词为 NULL）
        priority    TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('high', 'normal')),
        enabled     INTEGER NOT NULL DEFAULT 1,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(type, value)
    );

    -- 2. notes: 主表（候选 + 最终结果）
    CREATE TABLE IF NOT EXISTS notes (
        note_id         TEXT PRIMARY KEY,
        title           TEXT,
        content         TEXT,                    -- 正文/desc
        author          TEXT,
        author_id       TEXT,
        cover_image     TEXT,
        url             TEXT,
        note_type       TEXT,                    -- video / normal
        topics          TEXT,                    -- JSON 数组
        published_at    TEXT,                    -- ISO 格式
        likes           INTEGER DEFAULT 0,
        collects        INTEGER DEFAULT 0,
        comments        INTEGER DEFAULT 0,
        shares          INTEGER DEFAULT 0,
        source_type     TEXT,                    -- keyword / account
        source_value    TEXT,                    -- 命中的关键词或账号昵称
        status          TEXT NOT NULL DEFAULT 'candidate'
                        CHECK(status IN ('candidate', 'selected', 'expired')),
        first_seen_at   TEXT NOT NULL DEFAULT (datetime('now')),
        last_checked_at TEXT,
        check_count     INTEGER NOT NULL DEFAULT 0
    );

    -- 3. note_checks: 每次快照
    CREATE TABLE IF NOT EXISTS note_checks (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id     TEXT NOT NULL REFERENCES notes(note_id),
        likes       INTEGER DEFAULT 0,
        collects    INTEGER DEFAULT 0,
        comments    INTEGER DEFAULT 0,
        shares      INTEGER DEFAULT 0,
        checked_at  TEXT NOT NULL DEFAULT (datetime('now')),
        raw_data    TEXT                         -- 原始 JSON（test 模式保留）
    );
    CREATE INDEX IF NOT EXISTS idx_note_checks_note_id ON note_checks(note_id);

    -- 4. push_records: Telegram 推送记录
    CREATE TABLE IF NOT EXISTS push_records (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        note_id     TEXT NOT NULL REFERENCES notes(note_id),
        channel     TEXT NOT NULL DEFAULT 'telegram',
        status      TEXT NOT NULL CHECK(status IN ('success', 'failed')),
        pushed_at   TEXT NOT NULL DEFAULT (datetime('now')),
        error_msg   TEXT,
        UNIQUE(note_id, channel)
    );
    """)
    conn.commit()
    logger.info("数据库表初始化完成")


# ─── watch_targets CRUD ───

def upsert_watch_target(type_: str, value: str, user_id: str = None,
                        priority: str = "normal") -> int:
    """插入或忽略监控目标，返回 rowcount。"""
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO watch_targets (type, value, user_id, priority)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(type, value) DO UPDATE SET
            user_id = COALESCE(excluded.user_id, watch_targets.user_id),
            priority = excluded.priority
    """, (type_, value.strip(), user_id, priority))
    conn.commit()
    return cur.rowcount


def get_enabled_targets(type_: str = None) -> list:
    """获取所有启用的监控目标。type_ 为 None 则返回全部。"""
    conn = get_conn()
    if type_:
        rows = conn.execute(
            "SELECT * FROM watch_targets WHERE enabled=1 AND type=? ORDER BY priority DESC, id",
            (type_,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM watch_targets WHERE enabled=1 ORDER BY type, priority DESC, id"
        ).fetchall()
    return [dict(r) for r in rows]


def update_target_user_id(target_id: int, user_id: str):
    """补全账号的 user_id。"""
    conn = get_conn()
    conn.execute("UPDATE watch_targets SET user_id=? WHERE id=?", (user_id, target_id))
    conn.commit()


# ─── notes CRUD ───

def upsert_note(note: dict) -> str:
    """插入或更新笔记。返回 'inserted' 或 'updated'。"""
    conn = get_conn()
    existing = conn.execute("SELECT note_id, status FROM notes WHERE note_id=?",
                            (note["note_id"],)).fetchone()
    if existing:
        # 已存在：更新互动数据，不覆盖 status=selected
        if existing["status"] == "selected":
            # 已入选的不降级，只更新互动数据
            conn.execute("""
                UPDATE notes SET likes=?, collects=?, comments=?, shares=?,
                    last_checked_at=datetime('now'), check_count=check_count+1
                WHERE note_id=?
            """, (note.get("likes", 0), note.get("collects", 0),
                  note.get("comments", 0), note.get("shares", 0),
                  note["note_id"]))
        else:
            conn.execute("""
                UPDATE notes SET
                    title=COALESCE(?, title),
                    content=COALESCE(?, content),
                    author=COALESCE(?, author),
                    author_id=COALESCE(?, author_id),
                    cover_image=COALESCE(?, cover_image),
                    url=COALESCE(?, url),
                    note_type=COALESCE(?, note_type),
                    topics=COALESCE(?, topics),
                    published_at=COALESCE(?, published_at),
                    likes=?, collects=?, comments=?, shares=?,
                    last_checked_at=datetime('now'),
                    check_count=check_count+1
                WHERE note_id=?
            """, (
                note.get("title"), note.get("content"),
                note.get("author"), note.get("author_id"),
                note.get("cover_image"), note.get("url"),
                note.get("note_type"), note.get("topics"),
                note.get("published_at"),
                note.get("likes", 0), note.get("collects", 0),
                note.get("comments", 0), note.get("shares", 0),
                note["note_id"],
            ))
        conn.commit()
        return "updated"
    else:
        conn.execute("""
            INSERT INTO notes (note_id, title, content, author, author_id,
                cover_image, url, note_type, topics, published_at,
                likes, collects, comments, shares,
                source_type, source_value, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'candidate')
        """, (
            note["note_id"], note.get("title"), note.get("content"),
            note.get("author"), note.get("author_id"),
            note.get("cover_image"), note.get("url"),
            note.get("note_type"), note.get("topics"),
            note.get("published_at"),
            note.get("likes", 0), note.get("collects", 0),
            note.get("comments", 0), note.get("shares", 0),
            note.get("source_type"), note.get("source_value"),
        ))
        conn.commit()
        return "inserted"


def promote_note(note_id: str):
    """将笔记标记为 selected（爆款）。"""
    conn = get_conn()
    conn.execute("UPDATE notes SET status='selected' WHERE note_id=?", (note_id,))
    conn.commit()
    logger.info(f"笔记晋升为爆款: {note_id}")


def expire_note(note_id: str):
    """将笔记标记为 expired（淘汰）。"""
    conn = get_conn()
    conn.execute("UPDATE notes SET status='expired' WHERE note_id=?", (note_id,))
    conn.commit()


def get_candidates() -> list:
    """获取所有 candidate 状态的笔记。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM notes WHERE status='candidate' ORDER BY first_seen_at"
    ).fetchall()
    return [dict(r) for r in rows]


def get_unpushed_selected() -> list:
    """获取已入选但未推送的笔记。"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT n.* FROM notes n
        WHERE n.status='selected'
          AND n.note_id NOT IN (
              SELECT note_id FROM push_records WHERE status='success'
          )
        ORDER BY n.first_seen_at
    """).fetchall()
    return [dict(r) for r in rows]


# ─── note_checks CRUD ───

def insert_check(note_id: str, likes: int, collects: int, comments: int,
                 shares: int, raw_data: str = None):
    """插入一条快照记录。"""
    conn = get_conn()
    conn.execute("""
        INSERT INTO note_checks (note_id, likes, collects, comments, shares, raw_data)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (note_id, likes, collects, comments, shares, raw_data))
    conn.commit()


def get_max_likes(note_id: str) -> int:
    """获取某笔记历史最高点赞数。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT MAX(likes) as max_likes FROM note_checks WHERE note_id=?",
        (note_id,)
    ).fetchone()
    return row["max_likes"] or 0


# ─── push_records CRUD ───

def insert_push_record(note_id: str, status: str, error_msg: str = None):
    """插入推送记录。"""
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO push_records (note_id, channel, status, pushed_at, error_msg)
        VALUES (?, 'telegram', ?, datetime('now'), ?)
    """, (note_id, status, error_msg))
    conn.commit()
