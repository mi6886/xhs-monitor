import Database from "better-sqlite3";
import path from "path";

const DB_PATH = process.env.DB_PATH || "./data/monitor.db";

let _db: Database.Database | null = null;

function getDb(): Database.Database {
  if (!_db) {
    const dbPath = path.resolve(DB_PATH);
    _db = new Database(dbPath);
    _db.pragma("journal_mode = WAL");
    _db.pragma("foreign_keys = ON");
    initSchema(_db);
  }
  return _db;
}

function initSchema(db: Database.Database) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS rules (
      id TEXT PRIMARY KEY,
      type TEXT NOT NULL CHECK(type IN ('keyword', 'account')),
      value TEXT NOT NULL,
      user_id TEXT,
      priority TEXT NOT NULL DEFAULT 'normal' CHECK(priority IN ('high', 'normal')),
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
      status TEXT NOT NULL DEFAULT 'watching' CHECK(status IN ('watching', 'promoted', 'expired')),
      FOREIGN KEY (rule_id) REFERENCES rules(id)
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

    CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
    CREATE INDEX IF NOT EXISTS idx_candidates_first_seen ON candidates(first_seen_at);
    CREATE INDEX IF NOT EXISTS idx_results_notified ON results(notified);
    CREATE INDEX IF NOT EXISTS idx_results_promoted_at ON results(promoted_at);
    CREATE INDEX IF NOT EXISTS idx_crawl_logs_run_id ON crawl_logs(run_id);
  `);
}

// --- Rules ---

export interface Rule {
  id: string;
  type: "keyword" | "account";
  value: string;
  user_id: string | null;
  priority: "high" | "normal";
  enabled: number;
  created_at: string;
}

export function clearRules(): void {
  const db = getDb();
  db.prepare("DELETE FROM candidates").run();
  db.prepare("DELETE FROM rules").run();
}

export function clearAllData(): void {
  const db = getDb();
  db.prepare("DELETE FROM crawl_logs").run();
  db.prepare("DELETE FROM results").run();
  db.prepare("DELETE FROM candidates").run();
  db.prepare("DELETE FROM rules").run();
}

export function getEnabledRules(): Rule[] {
  return getDb().prepare("SELECT * FROM rules WHERE enabled = 1").all() as Rule[];
}

export function insertRule(rule: Omit<Rule, "created_at">): void {
  getDb()
    .prepare(
      "INSERT OR IGNORE INTO rules (id, type, value, user_id, priority, enabled) VALUES (?, ?, ?, ?, ?, ?)"
    )
    .run(rule.id, rule.type, rule.value, rule.user_id, rule.priority, rule.enabled);
}

// --- Candidates ---

export interface Candidate {
  note_id: string;
  rule_id: string;
  title: string;
  content: string;
  author: string;
  author_id: string;
  cover_image: string;
  url: string;
  note_type: string;
  topics: string;
  published_at: string;
  likes: number;
  comments: number;
  collected: number;
  shared: number;
  first_seen_at: string;
  last_checked_at: string;
  check_count: number;
  status: string;
}

export function upsertCandidate(c: {
  note_id: string;
  rule_id: string;
  title: string;
  content: string;
  author: string;
  author_id: string;
  cover_image: string;
  url: string;
  note_type: string;
  topics: string;
  published_at: string;
  likes: number;
  comments: number;
  collected: number;
  shared: number;
}): { isNew: boolean } {
  const existing = getDb()
    .prepare("SELECT note_id FROM candidates WHERE note_id = ?")
    .get(c.note_id);

  if (existing) {
    getDb()
      .prepare(
        `UPDATE candidates
         SET likes = ?, comments = ?, collected = ?, shared = ?,
             last_checked_at = datetime('now'), check_count = check_count + 1
         WHERE note_id = ?`
      )
      .run(c.likes, c.comments, c.collected, c.shared, c.note_id);
    return { isNew: false };
  }

  getDb()
    .prepare(
      `INSERT INTO candidates
       (note_id, rule_id, title, content, author, author_id, cover_image, url, note_type, topics, published_at, likes, comments, collected, shared)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      c.note_id, c.rule_id, c.title, c.content, c.author, c.author_id,
      c.cover_image, c.url, c.note_type, c.topics, c.published_at,
      c.likes, c.comments, c.collected, c.shared
    );
  return { isNew: true };
}

export function getWatchingCandidates(): Candidate[] {
  return getDb()
    .prepare("SELECT * FROM candidates WHERE status = 'watching'")
    .all() as Candidate[];
}

export function updateCandidateStatus(noteId: string, status: string): void {
  getDb()
    .prepare("UPDATE candidates SET status = ? WHERE note_id = ?")
    .run(status, noteId);
}

export function updateCandidateMetrics(
  noteId: string,
  metrics: { likes: number; comments: number; collected: number; shared: number }
): void {
  getDb()
    .prepare(
      `UPDATE candidates
       SET likes = ?, comments = ?, collected = ?, shared = ?,
           last_checked_at = datetime('now'), check_count = check_count + 1
       WHERE note_id = ?`
    )
    .run(metrics.likes, metrics.comments, metrics.collected, metrics.shared, noteId);
}

export function cleanExpiredCandidates(daysOld: number): number {
  const result = getDb()
    .prepare(
      `DELETE FROM candidates
       WHERE first_seen_at < datetime('now', ? || ' days')`
    )
    .run(`-${daysOld}`);
  return result.changes;
}

// --- Results ---

export interface Result {
  id: number;
  note_id: string;
  rule_id: string;
  title: string;
  content: string;
  author: string;
  author_id: string;
  cover_image: string;
  url: string;
  note_type: string;
  topics: string;
  published_at: string;
  likes: number;
  comments: number;
  collected: number;
  shared: number;
  promoted_at: string;
  notified: number;
  is_read: number;
  is_starred: number;
  is_used: number;
}

export function promoteToResult(c: Candidate): void {
  getDb()
    .prepare(
      `INSERT OR IGNORE INTO results
       (note_id, rule_id, title, content, author, author_id, cover_image, url, note_type, topics, published_at, likes, comments, collected, shared)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      c.note_id, c.rule_id, c.title, c.content, c.author, c.author_id,
      c.cover_image, c.url, c.note_type, c.topics, c.published_at,
      c.likes, c.comments, c.collected, c.shared
    );
}

export function getResults(params: {
  filter?: "all" | "unread" | "starred" | "used";
  sort?: "time" | "likes";
  q?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}): { results: Result[]; total: number } {
  const conditions: string[] = [];
  const args: unknown[] = [];

  if (params.filter === "unread") {
    conditions.push("is_read = 0");
  } else if (params.filter === "starred") {
    conditions.push("is_starred = 1");
  } else if (params.filter === "used") {
    conditions.push("is_used = 1");
  }

  if (params.q) {
    conditions.push("(title LIKE ? OR author LIKE ? OR topics LIKE ?)");
    const q = `%${params.q}%`;
    args.push(q, q, q);
  }

  if (params.from) {
    conditions.push("promoted_at >= ?");
    args.push(params.from);
  }
  if (params.to) {
    conditions.push("promoted_at <= ?");
    args.push(params.to);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const orderBy = params.sort === "likes" ? "likes DESC" : "promoted_at DESC";
  const limit = params.limit || 50;
  const offset = params.offset || 0;

  const total = (
    getDb().prepare(`SELECT COUNT(*) as count FROM results ${where}`).get(...args) as {
      count: number;
    }
  ).count;

  const results = getDb()
    .prepare(`SELECT * FROM results ${where} ORDER BY ${orderBy} LIMIT ? OFFSET ?`)
    .all(...args, limit, offset) as Result[];

  return { results, total };
}

export function getUnnotifiedResults(): Result[] {
  return getDb()
    .prepare("SELECT * FROM results WHERE notified = 0")
    .all() as Result[];
}

export function markNotified(noteId: string): void {
  getDb().prepare("UPDATE results SET notified = 1 WHERE note_id = ?").run(noteId);
}

export function updateResultStatus(
  id: number,
  updates: { is_read?: number; is_starred?: number; is_used?: number }
): void {
  const sets: string[] = [];
  const args: unknown[] = [];

  if (updates.is_read !== undefined) {
    sets.push("is_read = ?");
    args.push(updates.is_read);
  }
  if (updates.is_starred !== undefined) {
    sets.push("is_starred = ?");
    args.push(updates.is_starred);
  }
  if (updates.is_used !== undefined) {
    sets.push("is_used = ?");
    args.push(updates.is_used);
  }

  if (sets.length === 0) return;
  args.push(id);
  getDb().prepare(`UPDATE results SET ${sets.join(", ")} WHERE id = ?`).run(...args);
}

// --- Crawl Logs ---

export function insertCrawlLog(log: {
  run_id: string;
  rule_id: string | null;
  source: string;
  result_count: number;
  new_candidates: number;
  promoted_count: number;
  cost_points: number;
  error: string | null;
}): void {
  getDb()
    .prepare(
      `INSERT INTO crawl_logs
       (run_id, rule_id, source, result_count, new_candidates, promoted_count, cost_points, error)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    )
    .run(
      log.run_id, log.rule_id, log.source, log.result_count,
      log.new_candidates, log.promoted_count, log.cost_points, log.error
    );
}

// --- Stats ---

export function getStats(): {
  totalResults: number;
  todayNew: number;
  unreadCount: number;
  lastCrawlAt: string | null;
  monthlyPoints: number;
} {
  const db = getDb();

  const totalResults = (db.prepare("SELECT COUNT(*) as c FROM results").get() as { c: number }).c;

  const todayNew = (
    db.prepare("SELECT COUNT(*) as c FROM results WHERE promoted_at >= date('now')").get() as {
      c: number;
    }
  ).c;

  const unreadCount = (
    db.prepare("SELECT COUNT(*) as c FROM results WHERE is_read = 0").get() as { c: number }
  ).c;

  const lastCrawl = db
    .prepare("SELECT created_at FROM crawl_logs ORDER BY created_at DESC LIMIT 1")
    .get() as { created_at: string } | undefined;

  const monthlyPoints = (
    db
      .prepare(
        "SELECT COALESCE(SUM(cost_points), 0) as total FROM crawl_logs WHERE created_at >= date('now', 'start of month')"
      )
      .get() as { total: number }
  ).total;

  return {
    totalResults,
    todayNew,
    unreadCount,
    lastCrawlAt: lastCrawl?.created_at ?? null,
    monthlyPoints,
  };
}
