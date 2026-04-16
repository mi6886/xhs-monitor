import type { DataSource } from "./types";
import { JZLAdapter } from "./jzl";
import { TikHubAdapter } from "./tikhub";

export function getDataSource(): DataSource {
  const source = process.env.DATA_SOURCE || "jzl";
  if (source === "tikhub") {
    return new TikHubAdapter();
  }
  return new JZLAdapter();
}

export type { DataSource, NoteItem, SearchOptions, UserNotesOptions } from "./types";
