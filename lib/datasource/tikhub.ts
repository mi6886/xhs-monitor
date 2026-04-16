import type { DataSource, NoteItem, SearchOptions, UserNotesOptions } from "./types";

const BASE_URL = "https://api.tikhub.io";

export class TikHubAdapter implements DataSource {
  readonly name = "tikhub";

  private getApiKey(): string {
    const key = process.env.TIKHUB_API_KEY;
    if (!key) throw new Error("TIKHUB_API_KEY not configured — set it in environment variables");
    return key;
  }

  async searchNotes(keyword: string, options?: SearchOptions): Promise<NoteItem[]> {
    const apiKey = this.getApiKey();
    const params = new URLSearchParams({
      keyword,
      sort: options?.sort || "general",
      page_size: String(options?.limit || 20),
    });

    const res = await fetch(
      `${BASE_URL}/api/v1/xiaohongshu/web/search_notes?${params}`,
      { headers: { Authorization: `Bearer ${apiKey}` } }
    );

    if (!res.ok) throw new Error(`TikHub search failed: HTTP ${res.status}`);
    const json = await res.json();

    return (json.data?.items || []).map(mapTikHubNote);
  }

  async getUserNotes(userId: string, options?: UserNotesOptions): Promise<NoteItem[]> {
    const apiKey = this.getApiKey();
    const params = new URLSearchParams({
      user_id: userId,
      count: String(options?.limit || 20),
    });

    const res = await fetch(
      `${BASE_URL}/api/v1/xiaohongshu/web/fetch_user_post?${params}`,
      { headers: { Authorization: `Bearer ${apiKey}` } }
    );

    if (!res.ok) throw new Error(`TikHub user notes failed: HTTP ${res.status}`);
    const json = await res.json();

    return (json.data?.items || []).map(mapTikHubNote);
  }

  async getNoteDetail(noteId: string): Promise<NoteItem> {
    const apiKey = this.getApiKey();
    const params = new URLSearchParams({ note_id: noteId });

    const res = await fetch(
      `${BASE_URL}/api/v1/xiaohongshu/web/get_note_info?${params}`,
      { headers: { Authorization: `Bearer ${apiKey}` } }
    );

    if (!res.ok) throw new Error(`TikHub note detail failed: HTTP ${res.status}`);
    const json = await res.json();

    const note = json.data;
    if (!note) throw new Error(`TikHub: note ${noteId} not found`);
    return mapTikHubNote(note);
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapTikHubNote(raw: any): NoteItem {
  const noteId = raw.note_id || raw.id || "";
  return {
    noteId,
    title: raw.title || raw.display_title || "",
    content: raw.desc || raw.description || "",
    author: raw.user?.nickname || raw.user?.nick_name || "",
    authorId: raw.user?.user_id || raw.user?.id || "",
    coverImage: raw.cover?.url || raw.image_list?.[0]?.url || "",
    url: `https://www.xiaohongshu.com/explore/${noteId}`,
    noteType: raw.type === "video" ? "video" : "normal",
    topics: (raw.tag_list || []).map((t: { name?: string }) => t.name).filter(Boolean),
    publishedAt: raw.time
      ? new Date(raw.time * 1000).toISOString()
      : raw.create_time || new Date().toISOString(),
    likes: raw.liked_count || raw.interact_info?.liked_count || 0,
    comments: raw.comments_count || raw.interact_info?.comment_count || 0,
    collected: raw.collected_count || raw.interact_info?.collected_count || 0,
    shared: raw.shared_count || raw.interact_info?.share_count || 0,
  };
}
