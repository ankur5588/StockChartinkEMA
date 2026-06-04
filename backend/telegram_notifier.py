"""Telegram notification helper for broker auth errors and trade alerts."""
from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

BOT_TOKEN: str | None = None
CHAT_ID: str | None = None


def init() -> None:
    global BOT_TOKEN, CHAT_ID
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
    CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip() or None
    if BOT_TOKEN and CHAT_ID:
        logger.info("Telegram notifier configured (chat: %s)", CHAT_ID)
    else:
        logger.info("Telegram notifier disabled — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")


def send(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        if r.status_code == 200:
            logger.info("Telegram message sent (len=%d)", len(text))
        else:
            logger.warning("Telegram send failed: %s %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as e:
        logger.warning("Telegram send exception: %s", e)
        return False
