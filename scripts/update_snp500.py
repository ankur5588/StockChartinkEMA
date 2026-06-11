#!/usr/bin/env python3
"""Fetch current S&P 500 constituents from Wikipedia and write to data/snp500.csv.

Usage:
    python scripts/update_snp500.py

Requires: beautifulsoup4, lxml, requests
"""
from __future__ import annotations
import csv
import logging
import os
import sys

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "snp500.csv")


def fetch_snp500() -> list[dict]:
    """Scrape S&P 500 constituents table from Wikipedia."""
    r = requests.get(WIKI_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    table = soup.find("table", {"id": "constituents"})
    if not table:
        raise RuntimeError("Could not find constituents table on Wikipedia page")
    rows = table.find_all("tr")[1:]  # skip header
    symbols = []
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        symbol = cols[0].get_text(strip=True)
        name = cols[1].get_text(strip=True)
        sector = cols[3].get_text(strip=True) if len(cols) > 3 else ""
        if symbol:
            symbols.append({"symbol": symbol, "name": name, "sector": sector})
    logger.info("Fetched %d S&P 500 symbols from Wikipedia", len(symbols))
    return symbols


def write_csv(symbols: list[dict], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "name", "sector"])
        writer.writeheader()
        writer.writerows(symbols)
    logger.info("Written %d symbols to %s", len(symbols), path)


def main():
    symbols = fetch_snp500()
    write_csv(symbols, OUTPUT)
    print(f"Updated {OUTPUT} with {len(symbols)} symbols")


if __name__ == "__main__":
    main()
