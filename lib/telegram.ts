interface TelegramResult {
  sent: number;
  failed: number;
  errors: string[];
}

export async function sendTelegramMessage(text: string): Promise<boolean> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    console.warn("Telegram not configured, skipping push");
    return false;
  }

  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      parse_mode: "HTML",
      disable_web_page_preview: false,
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    console.error(`Telegram send failed: ${res.status} ${body}`);
    return false;
  }

  return true;
}

export function formatResultMessage(r: {
  title: string;
  author: string;
  topics: string;
  published_at: string;
  rule_value?: string;
  likes: number;
  collected: number;
  comments: number;
  shared: number;
  url: string;
}): string {
  const topicsArr: string[] = (() => {
    try { return JSON.parse(r.topics); }
    catch { return []; }
  })();
  const topicsStr = topicsArr.length > 0
    ? topicsArr.slice(0, 5).map((t) => `#${t}`).join(" ")
    : "";

  const pubDate = r.published_at
    ? new Date(r.published_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })
    : "未知";

  const lines = [
    `🔥 <b>小红书爆款笔记</b>`,
    ``,
    `📌 ${escapeHtml(r.title)}`,
    `✍️ ${escapeHtml(r.author)}`,
  ];

  if (topicsStr) lines.push(`🏷 ${escapeHtml(topicsStr)}`);
  lines.push(`📅 ${pubDate}`);
  if (r.rule_value) lines.push(`🔍 命中：${escapeHtml(r.rule_value)}`);

  lines.push(``);
  lines.push(`❤️ ${r.likes}  ⭐ ${r.collected}  💬 ${r.comments}  🔄 ${r.shared}`);
  lines.push(``);
  lines.push(`👉 <a href="${r.url}">查看原文</a>`);

  return lines.join("\n");
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export async function pushResults(
  results: Array<{
    note_id: string;
    title: string;
    author: string;
    topics: string;
    published_at: string;
    likes: number;
    collected: number;
    comments: number;
    shared: number;
    url: string;
    rule_id: string;
  }>,
  ruleMap: Map<string, string>
): Promise<TelegramResult> {
  const outcome: TelegramResult = { sent: 0, failed: 0, errors: [] };

  for (const r of results) {
    const msg = formatResultMessage({
      ...r,
      rule_value: ruleMap.get(r.rule_id),
    });

    const ok = await sendTelegramMessage(msg);
    if (ok) {
      outcome.sent++;
    } else {
      outcome.failed++;
      outcome.errors.push(`Failed to push note ${r.note_id}`);
    }

    await new Promise((resolve) => setTimeout(resolve, 200));
  }

  return outcome;
}
