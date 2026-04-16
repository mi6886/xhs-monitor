import Database from "better-sqlite3";
import fs from "fs";
import path from "path";

const DB_PATH = process.env.DB_PATH || "./data/monitor.db";
const SEED_PATH = path.resolve("data/seed-rules.json");

function main() {
  const dbPath = path.resolve(DB_PATH);

  const dir = path.dirname(dbPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  const db = new Database(dbPath);
  db.pragma("journal_mode = WAL");

  db.exec(`
    CREATE TABLE IF NOT EXISTS rules (
      id TEXT PRIMARY KEY,
      type TEXT NOT NULL CHECK(type IN ('keyword', 'account')),
      value TEXT NOT NULL,
      user_id TEXT,
      priority TEXT NOT NULL DEFAULT 'normal',
      enabled INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS candidates (
      note_id TEXT PRIMARY KEY,
      rule_id TEXT NOT NULL,
      title TEXT NOT NULL DEFAULT '',
      content TEXT NOT NULL DEFAULT '',
      author TEXT NOT NULL DEFAULT '',
      author_id TEXT NOT NULL DEFAULT '',
      cover_image TEXT NOT NULL DEFAULT '',
      url TEXT NOT NULL DEFAULT '',
      note_type TEXT NOT NULL DEFAULT 'normal',
      topics TEXT NOT NULL DEFAULT '[]',
      published_at TEXT NOT NULL,
      likes INTEGER NOT NULL DEFAULT 0,
      comments INTEGER NOT NULL DEFAULT 0,
      collected INTEGER NOT NULL DEFAULT 0,
      shared INTEGER NOT NULL DEFAULT 0,
      first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
      last_checked_at TEXT NOT NULL DEFAULT (datetime('now')),
      check_count INTEGER NOT NULL DEFAULT 1,
      status TEXT NOT NULL DEFAULT 'watching'
    );
    CREATE TABLE IF NOT EXISTS results (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      note_id TEXT NOT NULL UNIQUE,
      rule_id TEXT NOT NULL,
      title TEXT NOT NULL DEFAULT '',
      content TEXT NOT NULL DEFAULT '',
      author TEXT NOT NULL DEFAULT '',
      author_id TEXT NOT NULL DEFAULT '',
      cover_image TEXT NOT NULL DEFAULT '',
      url TEXT NOT NULL DEFAULT '',
      note_type TEXT NOT NULL DEFAULT 'normal',
      topics TEXT NOT NULL DEFAULT '[]',
      published_at TEXT NOT NULL,
      likes INTEGER NOT NULL DEFAULT 0,
      comments INTEGER NOT NULL DEFAULT 0,
      collected INTEGER NOT NULL DEFAULT 0,
      shared INTEGER NOT NULL DEFAULT 0,
      promoted_at TEXT NOT NULL DEFAULT (datetime('now')),
      notified INTEGER NOT NULL DEFAULT 0,
      is_read INTEGER NOT NULL DEFAULT 0,
      is_starred INTEGER NOT NULL DEFAULT 0,
      is_used INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS crawl_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      rule_id TEXT,
      source TEXT NOT NULL,
      result_count INTEGER NOT NULL DEFAULT 0,
      new_candidates INTEGER NOT NULL DEFAULT 0,
      promoted_count INTEGER NOT NULL DEFAULT 0,
      cost_points INTEGER NOT NULL DEFAULT 0,
      error TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);

  const seed = JSON.parse(fs.readFileSync(SEED_PATH, "utf-8"));

  const insert = db.prepare(
    "INSERT OR IGNORE INTO rules (id, type, value, user_id, priority, enabled) VALUES (?, ?, ?, ?, ?, ?)"
  );

  let count = 0;

  for (const kw of seed.keywords || []) {
    const id = `kw-${kw.replace(/\s+/g, "-").toLowerCase()}`;
    insert.run(id, "keyword", kw, null, "normal", 1);
    count++;
  }

  for (const acc of seed.accounts || []) {
    const id = `acc-${(acc.name || acc).replace(/\s+/g, "-")}`;
    const name = acc.name || acc;
    const userId = acc.user_id || null;
    insert.run(id, "account", name, userId, "normal", 1);
    count++;
  }

  console.log(`Seeded ${count} rules into ${dbPath}`);
  db.close();
}

main();
