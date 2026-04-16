import { NextRequest, NextResponse } from "next/server";
import { insertRule, clearAllData } from "@/lib/db";
import fs from "fs";
import path from "path";

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const secret = process.env.CRAWL_SECRET;

  if (secret && authHeader !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Load rules from JSON file
  const seedPath = path.resolve("data/seed-rules.json");
  if (!fs.existsSync(seedPath)) {
    return NextResponse.json({ error: "seed-rules.json not found" }, { status: 500 });
  }

  const seed = JSON.parse(fs.readFileSync(seedPath, "utf-8"));

  clearAllData();

  let count = 0;

  for (const kw of seed.keywords || []) {
    const id = `kw-${kw.replace(/\s+/g, "-").toLowerCase()}`;
    insertRule({ id, type: "keyword", value: kw, user_id: null, priority: "normal", enabled: 1 });
    count++;
  }

  for (const acc of seed.accounts || []) {
    const name = typeof acc === "string" ? acc : acc.name;
    const userId = typeof acc === "string" ? null : (acc.user_id || null);
    const id = `acc-${name.replace(/\s+/g, "-")}`;
    insertRule({ id, type: "account", value: name, user_id: userId, priority: "normal", enabled: 1 });
    count++;
  }

  return NextResponse.json({ success: true, seeded: count });
}
