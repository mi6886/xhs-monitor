import { NextRequest, NextResponse } from "next/server";
import { getUnnotifiedResults, markNotified, getEnabledRules } from "@/lib/db";
import { pushResults } from "@/lib/telegram";

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const secret = process.env.CRAWL_SECRET;

  if (secret && authHeader !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const rules = getEnabledRules();
  const ruleMap = new Map(rules.map((r) => [r.id, r.value]));
  const unnotified = getUnnotifiedResults();

  if (unnotified.length === 0) {
    return NextResponse.json({ success: true, sent: 0, message: "No unnotified results" });
  }

  const pushResult = await pushResults(
    unnotified.map((r) => ({ ...r })),
    ruleMap
  );

  // Only mark as notified if push succeeded
  for (let i = 0; i < unnotified.length; i++) {
    if (i < pushResult.sent) {
      markNotified(unnotified[i].note_id);
    }
  }

  return NextResponse.json({
    success: true,
    sent: pushResult.sent,
    failed: pushResult.failed,
    errors: pushResult.errors,
  });
}
