#!/usr/bin/env python3
"""Bridge between the US Screener output and the Chartink backend.

Reads the latest screener results file from the US Screener project and
POSTs each new match to the Chartink backend's /api/signals/us endpoint.

Runs via cron every 1-5 minutes during US market hours.

Configuration via environment variables:
  SCREENER_RESULTS_DIR  – path to the screener results/ directory
  BACKEND_URL           – Chartink backend base URL (default: http://127.0.0.1:8001)
  API_TOKEN             – (optional) bearer token if backend requires auth
  STATE_FILE            – path to dedup state file (default: /tmp/us_signal_bridge_state.json)
"""
from __future__ import annotations
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SCREENER_RESULTS_DIR = os.environ.get(
    "SCREENER_RESULTS_DIR",
    os.path.expanduser("~/usstocks/results"),
)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8001")
API_TOKEN = os.environ.get("API_TOKEN", "")
STATE_FILE = os.environ.get(
    "STATE_FILE",
    "/tmp/us_signal_bridge_state.json",
)

# Only process results from the last N days
MAX_AGE_DAYS = 2


def load_state() -> dict:
    """Load dedup state: which tickers have already been signaled per date."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def parse_screener_results(filepath: str) -> list[str]:
    """Parse a screener output file and return list of matched tickers."""
    tickers = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("=") or line.startswith("US Stocks Screener"):
                    continue
                # Lines look like: "AAPL" or "AAPL - Apple Inc." or similar
                # Extract the first word/ticker
                parts = line.replace('"', "").split()
                if parts:
                    ticker = parts[0].strip().upper()
                    if ticker and len(ticker) <= 5 and ticker.isalpha():
                        tickers.append(ticker)
    except Exception as e:
        logger.warning("Failed to parse %s: %s", filepath, e)
    return tickers


def find_latest_result() -> str | None:
    """Find the most recent screener output file."""
    results_dir = Path(SCREENER_RESULTS_DIR)
    if not results_dir.exists():
        logger.warning("Results directory not found: %s", SCREENER_RESULTS_DIR)
        return None

    today = date.today()
    for i in range(MAX_AGE_DAYS):
        d = today.isoformat() if i == 0 else date.fromordinal(today.toordinal() - i).isoformat()
        candidates = list(results_dir.glob(f"screener_{d}*.txt"))
        if candidates:
            return str(sorted(candidates)[-1])
    return None


def send_signal(symbol: str) -> dict:
    """POST a buy signal for a symbol to the backend."""
    url = f"{BACKEND_URL}/api/signals/us"
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    payload = {
        "action": "buy",
        "symbol": symbol,
        "source": "us_screener",
        "date": date.today().isoformat(),
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error("Signal for %s failed: %s", symbol, e)
        return {"status": "error", "message": str(e)}


def main():
    state = load_state()
    today_key = date.today().isoformat()
    today_state = state.get(today_key, [])

    result_file = find_latest_result()
    if not result_file:
        logger.info("No recent screener results found")
        return

    logger.info("Processing screener results: %s", result_file)
    tickers = parse_screener_results(result_file)
    logger.info("Found %d matches in screener output", len(tickers))

    new_count = 0
    for ticker in tickers:
        if ticker in today_state:
            logger.debug("Skipping already signaled: %s", ticker)
            continue
        logger.info("Signaling %s", ticker)
        resp = send_signal(ticker)
        status = resp.get("status", "error")
        if status == "success":
            today_state.append(ticker)
            new_count += 1
            logger.info("  %s → order placed (%s)", ticker, resp.get("order_id", "?"))
        else:
            logger.warning("  %s → %s: %s", ticker, status, resp.get("message", ""))

    if new_count:
        state[today_key] = today_state
        save_state(state)

    logger.info("Bridge run complete: %d new signals, %d total today", new_count, len(today_state))


if __name__ == "__main__":
    main()
