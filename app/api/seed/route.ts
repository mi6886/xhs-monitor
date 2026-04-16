import { NextRequest, NextResponse } from "next/server";
import { insertRule, clearAllData } from "@/lib/db";

const SEED_RULES = {
  keywords: [
    "小龙虾", "养龙虾", "openclaw", "小红书科技AMA", "AI新手村",
    "人工智能", "AI工具", "ai工具", "vibecoding大赏", "谷歌",
    "Gemini", "gemini", "效率神器", "AIChannel", "ai视频",
    "agent", "ai教程", "ai数字人", "大模型", "驯服AI",
    "智能体", "编程", "obsidian", "OpenAI", "AI设计",
    "AIAgent", "AIGC", "aigc", "Claudecode", "千问",
  ],
  accounts: [
    "晓白和林亦", "AI红发魔女", "田同学Tino", "三次方-科技风口",
    "Minko的AI魔法屋", "阿博粒", "豆芽AI笔记本", "蜗牛的科技笔记",
    "宅急颂AI", "赛文乔伊", "dontbesilent聊赚钱", "料到Ai",
    "Rico有三猫", "徐老师AI", "小e同学", "Super Winnie",
    "小林AI养成记", "捏捏番茄", "黄白", "瑞哥那",
    "树懒TV", "章炎炎", "AI张同学", "赛博自由老爹",
    "林亦LYi", "47的朋友们", "皮蛋的科技日记", "火山的AIGC",
    "小梨蛋包", "朋克周", "AI视次方", "科技捕手",
  ],
};

export async function POST(req: NextRequest) {
  const authHeader = req.headers.get("authorization");
  const secret = process.env.CRAWL_SECRET;

  if (secret && authHeader !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  clearAllData();

  let count = 0;

  for (const kw of SEED_RULES.keywords) {
    const id = `kw-${kw.replace(/\s+/g, "-").toLowerCase()}`;
    insertRule({ id, type: "keyword", value: kw, user_id: null, priority: "normal", enabled: 1 });
    count++;
  }

  for (const name of SEED_RULES.accounts) {
    const id = `acc-${name.replace(/\s+/g, "-")}`;
    insertRule({ id, type: "account", value: name, user_id: null, priority: "normal", enabled: 1 });
    count++;
  }

  return NextResponse.json({ success: true, seeded: count });
}
