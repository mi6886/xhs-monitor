export interface NoteItem {
  noteId: string;
  title: string;
  content: string;
  author: string;
  authorId: string;
  coverImage: string;
  url: string;
  noteType: "video" | "normal";
  topics: string[];
  publishedAt: string;
  likes: number;
  comments: number;
  collected: number;
  shared: number;
}

export interface SearchOptions {
  sort?: "general" | "latest" | "hottest";
  noteType?: "all" | "video" | "image";
  limit?: number;
}

export interface UserNotesOptions {
  limit?: number;
}

export interface DataSource {
  readonly name: string;
  searchNotes(keyword: string, options?: SearchOptions): Promise<NoteItem[]>;
  getUserNotes(userId: string, options?: UserNotesOptions): Promise<NoteItem[]>;
  getNoteDetail(noteId: string): Promise<NoteItem>;
}
