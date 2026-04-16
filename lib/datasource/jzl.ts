import type { DataSource, NoteItem, SearchOptions, UserNotesOptions } from "./types";

const BASE_URL = "https://api.yddm.com";

const ENDPOINTS = {
  searchNotes: "/xhs/search_note_web",
  userNotes: "/xhs/user_note_web",
  noteDetail: "/xhs/note_detail2",
  searchNotesFallback: "/xhs/search_note_app",
  userNotesFallback: "/xhs/user_note_app",
  noteDetailFallback: "/xhs/note_detail4",
};

const RETRY_DELAYS_MS = [5_000, 15_000, 30_000];

interface JZLResponse {
  code: number;
  msg: string;
  data: {
    cost?: number;
    balance?: number;
    note_list?: JZLNote[];
    items?: JZLSearchItem[];
    notes?: JZLSearchItem[];
    has_more?: boolean;
    [key: string]: unknown;
  };
}

interface JZLNote {
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
  ip_location?: string;
  hash_tag?: Array<{ name: string }>;
  images_list?: Array<{ url?: string; original?: string }>;
  user?: { nickname?: string; userid?: string; name?: string; id?: string };
}

interface JZLSearchItem {
  note_card?: JZLNote;
  id?: string;
  [key: string]: unknown;
}

async function jzlFetch(
  endpoint: string,
  body: Record<string, unknown>,
  fallbackEndpoint?: string
): Promise<JZLResponse> {
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

      const json = (await res.json()) as JZLResponse;

      if (json.code === 0) return json;

      if (json.code === 1003 && attempt < RETRY_DELAYS_MS.length) {
        await sleep(RETRY_DELAYS_MS[attempt]);
        continue;
      }

      if (fallbackEndpoint && attempt === 0 && json.code !== 0 && json.code !== 1003) {
        console.log(`JZL primary ${endpoint} failed (code ${json.code}), trying fallback ${fallbackEndpoint}`);
        return jzlFetch(fallbackEndpoint, body);
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

function mapNote(raw: JZLNote): NoteItem {
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

    const res = await jzlFetch(ENDPOINTS.searchNotes, body, ENDPOINTS.searchNotesFallback);

    const items = res.data.items || res.data.notes || [];
    const noteList = res.data.note_list || [];

    if (noteList.length > 0) {
      return noteList.map(mapNote);
    }

    return items.map((item: JZLSearchItem) => {
      if (item.note_card) return mapNote(item.note_card);
      return mapNote(item as unknown as JZLNote);
    });
  }

  async getUserNotes(userId: string, options?: UserNotesOptions): Promise<NoteItem[]> {
    const body: Record<string, unknown> = {
      user_id: userId,
      page: 1,
    };
    if (options?.limit) body.num = options.limit;

    const res = await jzlFetch(ENDPOINTS.userNotes, body, ENDPOINTS.userNotesFallback);

    const noteList = res.data.note_list || res.data.notes || res.data.items || [];
    return noteList.map((n: JZLNote | JZLSearchItem) => {
      if ("note_card" in n && n.note_card) return mapNote(n.note_card as JZLNote);
      return mapNote(n as JZLNote);
    });
  }

  async getNoteDetail(noteId: string): Promise<NoteItem> {
    const res = await jzlFetch(
      ENDPOINTS.noteDetail,
      { note_id: noteId },
      ENDPOINTS.noteDetailFallback
    );

    const note = res.data.note_list?.[0];
    if (!note) throw new Error(`Note ${noteId} not found`);

    const user = (res.data as unknown as { user?: JZLNote["user"] }).user;
    if (user && !note.user) {
      note.user = user;
    }

    return mapNote(note);
  }
}
