"""Resend the latest exported digest without crawling or changing push records."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from src.config import load_config, setup_logging
from src.push import _format_digest_messages, _send_telegram

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_notes(period: str) -> list[dict]:
    data_path = _repo_root() / "site" / "data" / f"latest-{period.lower()}.json"
    if not data_path.exists():
        raise FileNotFoundError(f"Digest file not found: {data_path}")

    data = json.loads(data_path.read_text(encoding="utf-8"))
    notes = data.get("notes") or []
    if not isinstance(notes, list):
        raise ValueError(f"Invalid notes payload in {data_path}")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period",
        choices=["Morning", "Afternoon", "Evening"],
        required=True,
        help="Which latest digest to resend.",
    )
    args = parser.parse_args()

    setup_logging()
    cfg = load_config()

    tg_cfg = cfg.get("telegram", {})
    bot_token = tg_cfg.get("bot_token", "")
    chat_id = tg_cfg.get("chat_id", "")
    if not bot_token or not chat_id:
        logger.error("Telegram 未配置，无法重发")
        return 1

    notes = _load_notes(args.period)
    if not notes:
        logger.info("最新 %s 列表为空，不重发", args.period)
        return 0

    sent_all = True
    messages = _format_digest_messages(notes)
    for idx, msg in enumerate(messages, 1):
        ok = _send_telegram(bot_token, chat_id, msg)
        if ok:
            logger.info("重发汇总消息成功: part=%s/%s notes=%s", idx, len(messages), len(notes))
        else:
            sent_all = False
            logger.error("重发汇总消息失败: part=%s/%s", idx, len(messages))
            break

    return 0 if sent_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
