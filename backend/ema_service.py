"""EMA10 calculation using yfinance as historical data source.

Kotak Neo symbols are NSE/BSE cash stocks. For yfinance we append `.NS` for
NSE and `.BO` for BSE. We accept the raw trading_symbol as it is returned
from the broker (e.g. `RELIANCE-EQ` -> strip `-EQ`).
"""
from __future__ import annotations
import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def _normalise_symbol(symbol: str, exchange_segment: str = "nse_cm") -> str:
    s = symbol.upper().strip()
    # Remove common suffixes Kotak uses
    for suf in ("-EQ", "-BE", "-BZ", "-N1"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    if exchange_segment.startswith("bse"):
        return f"{s}.BO"
    return f"{s}.NS"


def compute_ema10(symbol: str, exchange_segment: str = "nse_cm") -> Optional[float]:
    """Return last EMA10 value on daily close. None if data unavailable."""
    ticker = _normalise_symbol(symbol, exchange_segment)
    try:
        hist = yf.Ticker(ticker).history(period="3mo", interval="1d", auto_adjust=False)
    except Exception as e:
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None
    closes = hist["Close"].dropna()
    if len(closes) < 10:
        return None
    ema = closes.ewm(span=10, adjust=False).mean()
    val = float(ema.iloc[-1])
    return round(val, 2)
