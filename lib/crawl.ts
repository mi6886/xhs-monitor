import { getDataSource } from "./datasource";
import type { NoteItem } from "./datasource/types";
import {
  getEnabledRules,
  upsertCandidate,
  getWatchingCandidates,
  updateCandidateStatus,
  updateCandidateMetrics,
  promoteToResult,
  getUnnotifiedResults,
  markNotified,
  insertCrawlLog,
  cleanExpiredCandidates,
  type Rule,
  type Candidate,
} from "./db";
import { pushResults } from "./telegram";

const BATCH_SIZE = 5;
const BATCH_DELAY_MS = 2000;
const LIKES_THRESHOLD = 1000;

interface CrawlResult {
  runId: string;
  totalRules: number;
  totalFetched: number;
  newCandidates: number;
  promoted: number;
  expired: number;
  notified: number;
  errors: string[];
  durationMs: number;
}

export async function runCrawl(): Promise<CrawlResult> {
  const startTime = Date.now();
  const runId = `run-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const ds = getDataSource();
  const windowHours = Number(process.env.WATCH_WINDOW_HOURS) || 24;
  const windowMs = windowHours * 60 * 60 * 1000;

  const rules = getEnabledRules();
  const ruleMap = new Map(rules.map((r) => [r.id, r.value]));

  const result: CrawlResult = {
    runId,
    totalRules: rules.length,
    totalFetched: 0,
    newCandidates: 0,
    promoted: 0,
    expired: 0,
    notified: 0,
    errors: [],
    durationMs: 0,
  };

  // --- Phase 1: Fetch new notes from rules ---
  const batches = chunk(rules, BATCH_SIZE);

  for (const batch of batches) {
    await Promise.all(
      batch.map(async (rule) => {
        try {
          const notes = await fetchNotesForRule(ds, rule);
          let ruleNewCandidates = 0;
          let rulePromoted = 0;

          for (const note of notes) {
            const publishedMs = new Date(note.publishedAt).getTime();
            if (Date.now() - publishedMs > windowMs) continue;

            result.totalFetched++;
            const { isNew } = upsertCandidate(noteToCandidate(note, rule.id));

            if (isNew) {
              result.newCandidates++;
              ruleNewCandidates++;
            }

            if (note.likes >= LIKES_THRESHOLD) {
              const promoted = tryPromote(note.noteId, rule.id, note);
              if (promoted) {
                result.promoted++;
                rulePromoted++;
              }
            }
          }

          insertCrawlLog({
            run_id: runId,
            rule_id: rule.id,
            source: ds.name,
            result_count: notes.length,
            new_candidates: ruleNewCandidates,
            promoted_count: rulePromoted,
            cost_points: estimateCost(rule.type),
            error: null,
          });
        } catch (err) {
          const errMsg = err instanceof Error ? err.message : String(err);
          result.errors.push(`Rule ${rule.id} (${rule.value}): ${errMsg}`);
          insertCrawlLog({
            run_id: runId,
            rule_id: rule.id,
            source: ds.name,
            result_count: 0,
            new_candidates: 0,
            promoted_count: 0,
            cost_points: 0,
            error: errMsg,
          });
        }
      })
    );

    await new Promise((resolve) => setTimeout(resolve, BATCH_DELAY_MS));
  }

  // --- Phase 2: Recheck watching candidates ---
  const watching = getWatchingCandidates();
  const now = Date.now();

  for (const candidate of watching) {
    const firstSeenMs = new Date(candidate.first_seen_at).getTime();

    if (now - firstSeenMs > windowMs) {
      updateCandidateStatus(candidate.note_id, "expired");
      result.expired++;
      continue;
    }

    try {
      const detail = await ds.getNoteDetail(candidate.note_id);
      updateCandidateMetrics(candidate.note_id, {
        likes: detail.likes,
        comments: detail.comments,
        collected: detail.collected,
        shared: detail.shared,
      });

      if (detail.likes >= LIKES_THRESHOLD) {
        const promoted = tryPromote(candidate.note_id, candidate.rule_id, detail);
        if (promoted) result.promoted++;
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      result.errors.push(`Recheck ${candidate.note_id}: ${errMsg}`);
    }

    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  // --- Phase 3: Push notifications ---
  const unnotified = getUnnotifiedResults();
  if (unnotified.length > 0) {
    const pushResult = await pushResults(
      unnotified.map((r) => ({ ...r })),
      ruleMap
    );
    result.notified = pushResult.sent;

    for (const r of unnotified) {
      markNotified(r.note_id);
    }

    if (pushResult.errors.length > 0) {
      result.errors.push(...pushResult.errors);
    }
  }

  // --- Phase 4: Cleanup ---
  cleanExpiredCandidates(7);

  // --- Phase 5: Alert if high failure rate ---
  if (rules.length > 0 && result.errors.length / rules.length > 0.5) {
    const { sendTelegramMessage } = await import("./telegram");
    await sendTelegramMessage(
      `⚠️ 监控告警\n\n本次抓取失败率过高：${result.errors.length}/${rules.length} 条规则出错\n\n运行ID: ${runId}`
    );
  }

  result.durationMs = Date.now() - startTime;

  insertCrawlLog({
    run_id: runId,
    rule_id: null,
    source: ds.name,
    result_count: result.totalFetched,
    new_candidates: result.newCandidates,
    promoted_count: result.promoted,
    cost_points: 0,
    error: result.errors.length > 0 ? `${result.errors.length} errors` : null,
  });

  return result;
}

// --- Helpers ---

async function fetchNotesForRule(
  ds: ReturnType<typeof getDataSource>,
  rule: Rule
): Promise<NoteItem[]> {
  if (rule.type === "keyword") {
    return ds.searchNotes(rule.value, { sort: "latest" });
  }

  if (rule.user_id) {
    return ds.getUserNotes(rule.user_id);
  }

  return ds.searchNotes(rule.value, { sort: "latest" });
}

function noteToCandidate(note: NoteItem, ruleId: string) {
  return {
    note_id: note.noteId,
    rule_id: ruleId,
    title: note.title,
    content: note.content,
    author: note.author,
    author_id: note.authorId,
    cover_image: note.coverImage,
    url: note.url,
    note_type: note.noteType,
    topics: JSON.stringify(note.topics),
    published_at: note.publishedAt,
    likes: note.likes,
    comments: note.comments,
    collected: note.collected,
    shared: note.shared,
  };
}

function tryPromote(noteId: string, ruleId: string, note: NoteItem): boolean {
  const candidate: Candidate = {
    note_id: noteId,
    rule_id: ruleId,
    title: note.title,
    content: note.content,
    author: note.author,
    author_id: note.authorId,
    cover_image: note.coverImage,
    url: note.url,
    note_type: note.noteType,
    topics: JSON.stringify(note.topics),
    published_at: note.publishedAt,
    likes: note.likes,
    comments: note.comments,
    collected: note.collected,
    shared: note.shared,
    first_seen_at: "",
    last_checked_at: "",
    check_count: 0,
    status: "promoted",
  };

  promoteToResult(candidate);
  updateCandidateStatus(noteId, "promoted");
  return true;
}

function estimateCost(ruleType: string): number {
  return ruleType === "keyword" ? 5 : 10;
}

function chunk<T>(arr: T[], size: number): T[][] {
  const result: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    result.push(arr.slice(i, i + size));
  }
  return result;
}
