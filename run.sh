#!/bin/bash
# 小红书监控系统 — crontab 触发脚本
cd /Users/elainewang/Downloads/xhs-monitor

export TIKHUB_API_KEY="1JcOEOcAxFCqnnLPE5il4R78bDuoSsRk7yGdrBWFa+K7jH6wP0WBdgOkNw=="
export TELEGRAM_BOT_TOKEN="8669975304:AAF6oBjWFPlzsMbITVxeaf2qNLH3SWydEEs"
export TELEGRAM_CHAT_ID="8640597958"

# 运行完整流程
venv/bin/python3 -m src.runner all >> logs/cron.log 2>&1

# 记录运行时间
echo "--- cron 运行完成: $(date) ---" >> logs/cron.log
