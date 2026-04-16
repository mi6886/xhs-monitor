import { NextRequest, NextResponse } from "next/server";
import { insertRule } from "@/lib/db";

const SEED_RULES = {
  keywords: [
    "AI工具", "ChatGPT", "Claude", "AI绘画", "AI视频",
    "Midjourney", "Sora", "AI写作", "AI效率", "AI自媒体",
  ],
  accounts: [
    { name: "Next蔡蔡", user_id: "62a08c3f0000000021029c8c" },
  ],
};

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const secret = process.env.CRAWL_SECRET;

  if (secret && authHeader !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let count = 0;

  for (const kw of SEED_RULES.keywords) {
    const id = `kw-${kw.replace(/\s+/g, "-").toLowerCase()}`;
    insertRule({ id, type: "keyword", value: kw, user_id: null, priority: "normal", enabled: 1 });
    count++;
  }

  for (const acc of SEED_RULES.accounts) {
    const id = `acc-${acc.name.replace(/\s+/g, "-")}`;
    insertRule({ id, type: "account", value: acc.name, user_id: acc.user_id, priority: "normal", enabled: 1 });
    count++;
  }

  return NextResponse.json({ success: true, seeded: count });
}
