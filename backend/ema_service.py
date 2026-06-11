"""EMA10 calculation using yfinance with MongoDB caching layer.

Kotak Neo symbols are NSE/BSE cash stocks. For yfinance we append `.NS` for
NSE and `.BO` for BSE. We accept the raw trading_symbol as it is returned
from the broker (e.g. `RELIANCE-EQ` -> strip `-EQ`).

Caching strategy:
  1. Check MongoDB for a cached EMA10 value (TTL = 1 day).
  2. On cache MISS or stale, try yfinance with a desktop User-Agent.
  3. On yfinance SUCCESS -> update cache and return value.
  4. On yfinance FAILURE -> return stale cache if < 7 days old, else None.
"""
from __future__ import annotations
import logging
import os
from datetime import datetime
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent requests Session with desktop User-Agent
# ---------------------------------------------------------------------------
_session = requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

# ---------------------------------------------------------------------------
# MongoDB cache (lazy-init via pymongo — sync, same as yfinance)
# ---------------------------------------------------------------------------
_cache_client = None
_cache_db = None


def _get_cache_collection():
    global _cache_client, _cache_db
    if _cache_db is None:
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "chartink_trade")
        try:
            from pymongo import MongoClient
            _cache_client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
            _cache_client.admin.command("ping")  # verify connection
            _cache_db = _cache_client[db_name]
        except Exception as e:
            logger.warning("MongoDB cache unavailable: %s", e)
    return _cache_db["yfinance_cache"] if _cache_db is not None else None


# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

def _normalise_symbol(symbol: str, exchange_segment: str = "nse_cm") -> str:
    """Convert a broker's trading symbol + exchange segment into a yfinance ticker.

    Accepts exchange_segment strings from multiple brokers (case-insensitive):
      - Kotak Neo: 'nse_cm', 'bse_cm'
      - Dhan:       'NSE_EQ',  'BSE_EQ',  'NSE_FNO', 'BSE_FNO'
      - Alice Blue: 'NSE',     'BSE',     'NFO',     'BFO'
    Returns 'SYMBOL.NS' for NSE and 'SYMBOL.BO' for BSE.
    """
    s = symbol.upper().strip()
    for suf in ("-EQ", "-BE", "-BZ", "-N1"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    seg = (exchange_segment or "").strip().lower()
    if seg.startswith("bse") or seg.startswith("bfo") or seg.startswith("b_"):
        return f"{s}.BO"
    return f"{s}.NS"


# ---------------------------------------------------------------------------
# EMA10 computation with caching
# ---------------------------------------------------------------------------

CACHE_TTL_SECS = 86400       # 1 day
STALE_TTL_SECS = 604800      # 7 days — still usable if yfinance is down


def compute_ema10(symbol: str, exchange_segment: str = "nse_cm") -> Optional[float]:
    """Return last EMA10 value on daily close. None if data unavailable."""
    ticker = _normalise_symbol(symbol, exchange_segment)
    return _compute_ema10(ticker)


def compute_ema10_us(symbol: str) -> Optional[float]:
    """Return last EMA10 value for a US stock ticker on daily close.

    US tickers are passed directly to yfinance without any suffix (e.g. 'AAPL').
    """
    ticker = symbol.upper().strip()
    return _compute_ema10(ticker)


def _compute_ema10(ticker: str) -> Optional[float]:
    """Internal EMA10 computation shared by compute_ema10 and compute_ema10_us."""
    now = datetime.utcnow()

    # 1. Check cache
    coll = _get_cache_collection()
    cached = coll.find_one({"ticker": ticker}) if coll is not None else None

    if cached is not None:
        cached_at = cached.get("cached_at")
        if isinstance(cached_at, datetime):
            # Normalize to timezone-naive UTC for comparison
            if cached_at.tzinfo is not None:
                cached_at = cached_at.replace(tzinfo=None)
            age = (now - cached_at).total_seconds()
        else:
            age = float("inf")
        if age < CACHE_TTL_SECS:
            # Fresh cache
            val = cached.get("ema10")
            if val is not None:
                return float(val)
        elif age < STALE_TTL_SECS:
            # Stale but usable — try yfinance first, fall back to stale
            val = _fetch_and_cache(ticker, coll)
            if val is not None:
                return val
            stale = cached.get("ema10")
            if stale is not None:
                logger.info("yfinance failed for %s — returning stale cache (%.1f h old)", ticker, age / 3600)
                return float(stale)
            return None
        else:
            # Too old — force fresh fetch
            return _fetch_and_cache(ticker, coll)

    # 2. No cache at all
    return _fetch_and_cache(ticker, coll)


def _fetch_and_cache(ticker: str, coll) -> Optional[float]:
    """Fetch close prices from yfinance, compute EMA10, store in cache."""
    try:
        yf_ticker = yf.Ticker(ticker)
        yf_ticker.session = _session
        hist = yf_ticker.history(period="3mo", interval="1d", auto_adjust=False)
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return None

    if hist is None or hist.empty or "Close" not in hist.columns:
        return None

    closes = hist["Close"].dropna()
    if len(closes) < 10:
        return None

    ema = closes.ewm(span=10, adjust=False).mean()
    val = round(float(ema.iloc[-1]), 2)

    # Store in MongoDB
    if coll is not None:
        try:
            coll.update_one(
                {"ticker": ticker},
                {
                    "$set": {
                        "ticker": ticker,
                        "ema10": val,
                        "close_prices": closes.tail(30).tolist(),
                        "cached_at": datetime.utcnow(),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning("Failed to cache EMA10 for %s: %s", ticker, e)

    return val
