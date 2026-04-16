import type { DataSource, NoteItem, SearchOptions, UserNotesOptions } from "./types";

const BASE_URL = "https://api.yddm.com";

const ENDPOINTS = {
  searchNotes: "/xhs/search_note_web",
  searchNotesFallback: "/xhs/search_note_app",
  userNotes: "/xhs/user_post",
  noteDetail: "/xhs/note_detail2",
  noteDetailFallback: "/xhs/note_detail4",
};

const RETRY_DELAYS_MS = [5_000, 15_000, 30_000];

// --- Response types for search endpoint (noteInfo/userInfo structure) ---

interface JZLSearchResponse {
  code: number;
  msg: string;
  data: {
    cost?: number;
    balance?: number;
    data?: JZLSearchItem[];
    has_more?: boolean;
    total?: number;
    keyword?: string;
    [key: string]: unknown;
  };
}

interface JZLSearchItem {
  noteInfo: {
    noteId: string;
    title: string;
    noteLink: string;
    notePublishTime: string; // "2026-03-25 20:00:09"
    likeNum: number;
    cmtNum: number;
    favNum: number;
    readNum: number;
    noteType: number; // 2 = video
    videoDuration?: number;
    noteImages?: Array<{ imageUrl: string }>;
    isAdNote: number;
  };
  userInfo: {
    nickName: string;
    userId: string;
    avatar: string;
    fansNum: number;
  };
}

// --- Response types for detail endpoint (note_list structure) ---

interface JZLDetailResponse {
  code: number;
  msg: string;
  data: {
    cost?: number;
    balance?: number;
    note_list?: JZLDetailNote[];
    user?: { nickname?: string; userid?: string };
    [key: string]: unknown;
  };
}

interface JZLDetailNote {
  id?: string;
  note_id?: string;
  title?: string;
  desc?: string;
  type?: string;
  time?: number;
  liked_count?: number;
  shared_count?: number;
  comments_count?: number;
  collected_count?: number;
  hash_tag?: Array<{ name: string }>;
  images_list?: Array<{ url?: string; original?: string }>;
  user?: { nickname?: string; userid?: string; name?: string; id?: string };
}

// --- Fetch helper ---

async function jzlFetch<T extends { code: number; msg: string }>(
  endpoint: string,
  body: Record<string, unknown>,
  fallbackEndpoint?: string
): Promise<T> {
  const apiKey = process.env.JZL_API_KEY;
  if (!apiKey) throw new Error("JZL_API_KEY not configured");

  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
    try {
      const res = await fetch(`${BASE_URL}${endpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": apiKey,
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const json = (await res.json()) as T;

      if (json.code === 0) return json;

      // Rate limited — retry
      if (json.code === 1003 && attempt < RETRY_DELAYS_MS.length) {
        await sleep(RETRY_DELAYS_MS[attempt]);
        continue;
      }

      // Try fallback on non-rate-limit errors
      if (fallbackEndpoint && attempt === 0 && json.code !== 1003) {
        console.log(`JZL ${endpoint} failed (code ${json.code}), trying fallback ${fallbackEndpoint}`);
        return jzlFetch<T>(fallbackEndpoint, body);
      }

      throw new Error(`JZL API error code ${json.code}: ${json.msg}`);
    } catch (err) {
      if (attempt === RETRY_DELAYS_MS.length) throw err;
      if (err instanceof Error && err.message.startsWith("JZL API error")) throw err;
      await sleep(RETRY_DELAYS_MS[attempt]);
    }
  }

  throw new Error("JZL API: max retries exceeded");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// --- Mappers ---

function mapSearchItem(item: JZLSearchItem): NoteItem {
  const ni = item.noteInfo;
  const ui = item.userInfo;
  const firstImage = ni.noteImages?.[0];

  return {
    noteId: ni.noteId,
    title: ni.title || "",
    content: "", // search results don't include full content
    author: ui.nickName || "",
    authorId: ui.userId || "",
    coverImage: firstImage?.imageUrl || "",
    url: ni.noteLink || `https://www.xiaohongshu.com/explore/${ni.noteId}`,
    noteType: ni.noteType === 2 ? "video" : "normal",
    topics: [], // search results don't include topics
    publishedAt: ni.notePublishTime
      ? new Date(ni.notePublishTime).toISOString()
      : new Date().toISOString(),
    likes: ni.likeNum || 0,
    comments: ni.cmtNum || 0,
    collected: ni.favNum || 0,
    shared: ni.readNum || 0, // readNum used as shares proxy
  };
}

function mapDetailNote(raw: JZLDetailNote): NoteItem {
  const noteId = raw.id || raw.note_id || "";
  const user = raw.user || {};
  const topics = (raw.hash_tag || []).map((t) => t.name).filter(Boolean);
  const firstImage = raw.images_list?.[0];
  const coverImage = firstImage?.original || firstImage?.url || "";
  const publishedAt = raw.time
    ? new Date(raw.time * 1000).toISOString()
    : new Date().toISOString();

  return {
    noteId,
    title: raw.title || "",
    content: raw.desc || "",
    author: user.nickname || user.name || "",
    authorId: user.userid || user.id || "",
    coverImage,
    url: `https://www.xiaohongshu.com/explore/${noteId}`,
    noteType: raw.type === "video" ? "video" : "normal",
    topics,
    publishedAt,
    likes: raw.liked_count || 0,
    comments: raw.comments_count || 0,
    collected: raw.collected_count || 0,
    shared: raw.shared_count || 0,
  };
}

// --- Adapter ---

export class JZLAdapter implements DataSource {
  readonly name = "jzl";

  async searchNotes(keyword: string, options?: SearchOptions): Promise<NoteItem[]> {
    const body: Record<string, unknown> = {
      keyword,
      page: 1,
      sort: options?.sort || "general",
    };
    if (options?.noteType && options.noteType !== "all") {
      body.note_type = options.noteType;
    }

    const res = await jzlFetch<JZLSearchResponse>(
      ENDPOINTS.searchNotes,
      body,
      ENDPOINTS.searchNotesFallback
    );

    const items = res.data.data || [];
    return items
      .filter((item) => item.noteInfo && item.noteInfo.isAdNote !== 1)
      .map(mapSearchItem);
  }

  async getUserNotes(userId: string, _options?: UserNotesOptions): Promise<NoteItem[]> {
    // user_post endpoint may fail (-1) for some users.
    // On failure, caller (crawl.ts) falls back to searchNotes with username.
    const res = await jzlFetch<JZLSearchResponse>(ENDPOINTS.userNotes, {
      user_id: userId,
      page: 1,
    });

    // user_post may return same noteInfo/userInfo structure as search
    const items = res.data.data || [];
    if (items.length > 0 && "noteInfo" in items[0]) {
      return items.map(mapSearchItem);
    }

    // Or it could return note_list (detail format) — handle both
    const noteList = (res.data as unknown as { note_list?: JZLDetailNote[] }).note_list || [];
    return noteList.map(mapDetailNote);
  }

  async getNoteDetail(noteId: string): Promise<NoteItem> {
    const res = await jzlFetch<JZLDetailResponse>(
      ENDPOINTS.noteDetail,
      { note_id: noteId },
      ENDPOINTS.noteDetailFallback
    );

    const note = res.data.note_list?.[0];
    if (!note) throw new Error(`Note ${noteId} not found`);

    // note_detail2 returns user at top level
    if (res.data.user && !note.user) {
      note.user = res.data.user;
    }

    return mapDetailNote(note);
  }
}
