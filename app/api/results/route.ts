import { NextRequest, NextResponse } from "next/server";
import { getResults, updateResultStatus } from "@/lib/db";

export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;

  const filter = (params.get("filter") as "all" | "unread" | "starred" | "used") || "all";
  const sort = (params.get("sort") as "time" | "likes") || "time";
  const q = params.get("q") || undefined;
  const from = params.get("from") || undefined;
  const to = params.get("to") || undefined;
  const limit = Number(params.get("limit")) || 50;
  const offset = Number(params.get("offset")) || 0;

  const data = getResults({ filter, sort, q, from, to, limit, offset });
  return NextResponse.json(data);
}

export async function PATCH(req: NextRequest) {
  const body = await req.json();
  const { id, is_read, is_starred, is_used } = body;

  if (!id) {
    return NextResponse.json({ error: "id is required" }, { status: 400 });
  }

  updateResultStatus(id, { is_read, is_starred, is_used });
  return NextResponse.json({ success: true });
}
