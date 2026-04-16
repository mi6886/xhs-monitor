"use client";

import { useEffect, useState, useCallback } from "react";

interface ResultItem {
  id: number;
  note_id: string;
  title: string;
  author: string;
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
  is_read: number;
  is_starred: number;
  is_used: number;
  rule_id: string;
}

interface Stats {
  totalResults: number;
  todayNew: number;
  unreadCount: number;
  lastCrawlAt: string | null;
  monthlyPoints: number;
}

type Filter = "all" | "unread" | "starred" | "used";
type Sort = "time" | "likes";

export default function Home() {
  const [results, setResults] = useState<ResultItem[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("time");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchResults = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ filter, sort, limit: "50", offset: "0" });
    if (search) params.set("q", search);
    const res = await fetch(`/api/results?${params}`);
    const data = await res.json();
    setResults(data.results);
    setTotal(data.total);
    setLoading(false);
  }, [filter, sort, search]);

  const fetchStats = useCallback(async () => {
    const res = await fetch("/api/stats");
    setStats(await res.json());
  }, []);

  useEffect(() => { fetchResults(); }, [fetchResults]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  async function updateStatus(id: number, updates: Record<string, number>) {
    await fetch("/api/results", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, ...updates }),
    });
    fetchResults();
    fetchStats();
  }

  function handleTitleClick(item: ResultItem) {
    window.open(item.url, "_blank");
    if (!item.is_read) updateStatus(item.id, { is_read: 1 });
  }

  const lastCrawlWarning = stats?.lastCrawlAt
    ? Date.now() - new Date(stats.lastCrawlAt).getTime() > 24 * 60 * 60 * 1000
    : false;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-bold">📡 AI情报中台</h1>
        <nav className="flex gap-4 text-sm">
          <span className="text-red-600 font-medium border-b-2 border-red-600 pb-1">📕 小红书爆款</span>
          <span className="text-gray-400 cursor-not-allowed">𝕏 AI热点</span>
        </nav>
      </header>

      {/* Filters */}
      <div className="bg-white border-b px-6 py-3 flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {(["all", "unread", "starred", "used"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded text-sm ${
                filter === f ? "bg-red-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {{ all: "全部", unread: "未读", starred: "已标星", used: "已采用" }[f]}
              {f === "unread" && stats ? ` (${stats.unreadCount})` : ""}
            </button>
          ))}
        </div>
        <div className="flex gap-1 ml-auto">
          {(["time", "likes"] as Sort[]).map((s) => (
            <button
              key={s}
              onClick={() => setSort(s)}
              className={`px-3 py-1 rounded text-sm ${
                sort === s ? "bg-gray-800 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {{ time: "按时间", likes: "按点赞" }[s]}
            </button>
          ))}
        </div>
        <input
          type="text"
          placeholder="搜索标题/作者/话题"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && fetchResults()}
          className="border rounded px-3 py-1.5 text-sm w-48"
        />
      </div>

      {/* Results list */}
      <main className="flex-1 px-6 py-4">
        {loading ? (
          <div className="text-center text-gray-400 py-20">加载中...</div>
        ) : results.length === 0 ? (
          <div className="text-center text-gray-400 py-20">暂无结果</div>
        ) : (
          <div className="space-y-3">
            {results.map((item) => (
              <ResultCard
                key={item.id}
                item={item}
                onTitleClick={() => handleTitleClick(item)}
                onToggleStar={() => updateStatus(item.id, { is_starred: item.is_starred ? 0 : 1 })}
                onToggleUsed={() => updateStatus(item.id, { is_used: item.is_used ? 0 : 1 })}
              />
            ))}
          </div>
        )}
        {total > results.length && (
          <div className="text-center text-gray-400 text-sm mt-4">
            显示 {results.length} / {total} 条
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t px-6 py-2 text-xs text-gray-400 flex justify-between">
        <span>
          上次抓取：
          <span className={lastCrawlWarning ? "text-red-500 font-medium" : ""}>
            {stats?.lastCrawlAt
              ? new Date(stats.lastCrawlAt).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
              : "从未"}
          </span>
          {lastCrawlWarning && " ⚠️ 超过24小时未抓取"}
        </span>
        <span>今日新增 {stats?.todayNew || 0} 条 · 共 {stats?.totalResults || 0} 条 · 本月消耗 {stats?.monthlyPoints || 0} 积分</span>
      </footer>
    </div>
  );
}

function ResultCard({
  item,
  onTitleClick,
  onToggleStar,
  onToggleUsed,
}: {
  item: ResultItem;
  onTitleClick: () => void;
  onToggleStar: () => void;
  onToggleUsed: () => void;
}) {
  const topics: string[] = (() => {
    try { return JSON.parse(item.topics); }
    catch { return []; }
  })();

  const pubDate = new Date(item.published_at).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
  });

  return (
    <div className={`bg-white rounded-lg border p-4 flex gap-4 ${item.is_read ? "opacity-75" : ""}`}>
      {item.cover_image && (
        <img
          src={item.cover_image}
          alt=""
          className="w-20 h-20 object-cover rounded flex-shrink-0"
          loading="lazy"
        />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-start gap-2">
          <h3
            onClick={onTitleClick}
            className="font-medium text-sm cursor-pointer hover:text-red-600 line-clamp-1 flex-1"
          >
            {item.title}
          </h3>
          {!item.is_read && (
            <span className="bg-red-500 text-white text-xs px-1.5 py-0.5 rounded flex-shrink-0">NEW</span>
          )}
        </div>
        <p className="text-xs text-gray-500 mt-1">
          {item.author} · {pubDate}
          {item.note_type === "video" && " · 📹"}
        </p>
        {topics.length > 0 && (
          <p className="text-xs text-gray-400 mt-0.5 line-clamp-1">
            {topics.slice(0, 3).map((t) => `#${t}`).join(" ")}
          </p>
        )}
        <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
          <span>❤️ {item.likes}</span>
          <span>⭐ {item.collected}</span>
          <span>💬 {item.comments}</span>
          <span>🔄 {item.shared}</span>
          <div className="ml-auto flex gap-2">
            <button
              onClick={onToggleStar}
              className={`px-2 py-0.5 rounded ${item.is_starred ? "bg-yellow-100 text-yellow-700" : "bg-gray-100 text-gray-500 hover:bg-yellow-50"}`}
            >
              {item.is_starred ? "⭐ 已标星" : "☆ 标星"}
            </button>
            <button
              onClick={onToggleUsed}
              className={`px-2 py-0.5 rounded ${item.is_used ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500 hover:bg-green-50"}`}
            >
              {item.is_used ? "✅ 已采用" : "采用"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
