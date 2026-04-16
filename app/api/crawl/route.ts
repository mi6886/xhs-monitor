import { NextRequest, NextResponse } from "next/server";
import { runCrawl } from "@/lib/crawl";

export const maxDuration = 300; // 5 minutes (Render starter plan supports up to 5min)

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const secret = process.env.CRAWL_SECRET;

  if (secret && authHeader !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Check if caller wants fire-and-forget (GitHub Actions doesn't need to wait)
  const async = req.nextUrl.searchParams.get("async") === "1";

  if (async) {
    // Fire and forget — start crawl in background, return immediately
    runCrawl().catch((err) => {
      console.error("Background crawl failed:", err instanceof Error ? err.message : err);
    });
    return NextResponse.json({ success: true, mode: "async", message: "Crawl started in background" });
  }

  // Synchronous mode — wait for result
  try {
    const result = await runCrawl();
    return NextResponse.json({ success: true, ...result });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("Crawl failed:", message);
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
