#!/usr/bin/env python3
"""CLI to verify whether orders placed via the system actually filled on the broker side.

Usage:
  python verify_orders.py                          # recent orders
  python verify_orders.py --all                    # all open orders
  python verify_orders.py --watch                  # poll every 10s
  python verify_orders.py --broker dhan            # specific broker
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# MongoDB helpers (read-only, no Motor needed)
# ---------------------------------------------------------------------------
try:
    from pymongo import MongoClient
except ImportError:
    print("pymongo not installed. Run: pip install pymongo")
    sys.exit(1)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "chartink_trade")
_db = MongoClient(MONGO_URL)[DB_NAME]


def _get_creds(user_id: str | None = None) -> dict | None:
    """Fetch and decrypt Dhan credentials from MongoDB."""
    from cryptography.fernet import Fernet

    key = os.environ.get("FERNET_KEY", "")
    if not key:
        print("FERNET_KEY not set")
        return None
    cipher = Fernet(key.encode())

    q = {} if not user_id else {"user_id": user_id}
    doc = _db.dhan_credentials.find_one(q, {"_id": 0})
    if not doc:
        return None

    try:
        raw = cipher.decrypt(doc["encrypted"].encode()).decode()
        creds = json.loads(raw)
        return creds
    except Exception as e:
        print(f"Decryption failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Dhan API direct (no SDK dependency)
# ---------------------------------------------------------------------------
DHAN_BASE = "https://api.dhan.co/v2"


def dhan_get_order_list(access_token: str, client_id: str) -> list[dict]:
    """Fetch today's orders via Dhan v2 API."""
    headers = {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
    }
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = requests.get(
        f"{DHAN_BASE}/orders",
        params={"from_date": today, "to_date": today},
        headers=headers,
        timeout=15,
    )
    data = r.json()
    if data.get("status") == "failure":
        err = data.get("remarks", {})
        raise Exception(f"Dhan API error: {err}")
    orders = data.get("data") or data if isinstance(data, list) else data.get("data", [])
    return orders if isinstance(orders, list) else []


def dhan_get_order_by_id(order_id: str, access_token: str, client_id: str) -> dict:
    headers = {
        "access-token": access_token,
        "client-id": client_id,
        "Content-Type": "application/json",
    }
    r = requests.get(f"{DHAN_BASE}/orders/{order_id}", headers=headers, timeout=15)
    data = r.json()
    if data.get("status") == "failure":
        raise Exception(f"Dhan API error: {data.get('remarks')}")
    return data.get("data") or data


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------
STATUS_ICON = {
    "TRADED": "✅",
    "FILLED": "✅",
    "COMPLETE": "✅",
    "TRANSIT": "🔄",
    "PENDING": "⏳",
    "OPEN": "⏳",
    "NEW": "⏳",
    "REJECTED": "❌",
    "CANCELLED": "🚫",
}


def show_order(o: dict, idx: int = 0) -> None:
    icon = STATUS_ICON.get(o.get("orderStatus", "").upper(), "❓")
    status = o.get("orderStatus", "?").ljust(14)
    symbol = (o.get("tradingSymbol") or o.get("trading_symbol") or "?").ljust(12)
    qty = str(o.get("quantity", "?")).rjust(4)
    filled = str(o.get("filledQty") or o.get("filled_qty") or "0").rjust(4)
    price = str(o.get("price") or o.get("averageTradedPrice") or "0").rjust(8)
    oid = o.get("orderId") or o.get("dhanOrderId") or "?"
    print(f"  {icon} #{idx:<2} {symbol} qty={qty} filled={filled} @{price}  {status}  id={oid}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Verify broker order status")
    parser.add_argument("--all", action="store_true", help="Show all orders (not just today)")
    parser.add_argument("--order", type=str, help="Check a specific order ID")
    parser.add_argument("--watch", action="store_true", help="Poll every 10s until all resolve")
    parser.add_argument("--broker", default="dhan", choices=["dhan"])
    parser.add_argument("--user", type=str, default=None, help="MongoDB user_id")
    args = parser.parse_args()

    creds = _get_creds(args.user)
    if not creds:
        print("No Dhan credentials found in MongoDB.")
        print("Add them via the frontend dashboard: https://invesment.pro")
        sys.exit(1)

    access_token = creds.get("access_token") or creds.get("accesstoken", "")
    client_id = creds.get("client_id") or creds.get("clientId", "")

    if not access_token or not client_id:
        print("Incomplete Dhan credentials (missing access_token or client_id)")
        sys.exit(1)

    try:
        if args.order:
            order = dhan_get_order_by_id(args.order, access_token, client_id)
            print(f"\n{'='*60}")
            print(f"  Order {args.order}")
            print(f"{'='*60}")
            for k, v in order.items():
                print(f"  {k}: {v}")
        else:
            orders = dhan_get_order_list(access_token, client_id)
            if not orders:
                print("No orders found for today.")
                return

            print(f"\n{'='*60}")
            print(f"  Dhan Orders — {len(orders)} total")
            print(f"{'='*60}")
            for i, o in enumerate(orders):
                show_order(o, i + 1)

            filled = [o for o in orders if o.get("orderStatus", "").upper() in ("TRADED", "FILLED", "COMPLETE")]
            pending = [o for o in orders if o.get("orderStatus", "").upper() in ("TRANSIT", "PENDING", "OPEN", "NEW")]
            rejected = [o for o in orders if o.get("orderStatus", "").upper() in ("REJECTED", "CANCELLED")]

            print(f"\n  Summary: {len(filled)} filled  {len(pending)} pending  {len(rejected)} rejected")
            print()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
