#!/usr/bin/env python3
"""CLI to verify whether orders placed via the system actually filled on the broker side.

Usage:
  python verify_orders.py                                          # recent orders
  python verify_orders.py --all                                    # all open orders
  python verify_orders.py --watch                                  # poll every 10s
  python verify_orders.py --broker dhan                            # specific broker

  # Store Dhan credentials (run once after DB reset):
  python verify_orders.py --store-dhan CLIENT_ID ACCESS_TOKEN

  # Upload symbol mappings CSV:
  python verify_orders.py --upload-csv /path/to/symbol_mappings.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import uuid
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
    r = requests.get(f"{DHAN_BASE}/orders", headers=headers, timeout=15)
    data = r.json()
    if isinstance(data, dict):
        if data.get("status") == "failure":
            err = data.get("remarks", {})
            raise Exception(f"Dhan API error: {err}")
        return data.get("data") or []
    if isinstance(data, list):
        return data
    return []


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
    error = o.get("omsErrorDescription", "")
    err_str = f"  ⚠ {error[:70]}" if error and error != "0" and "0001" not in error else ""
    print(f"  {icon} #{idx:<2} {symbol} qty={qty} filled={filled} @{price}  {status}  id={oid}{err_str}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _store_dhan(access_token: str, client_id: str, user_id: str | None = None) -> None:
    """Encrypt and store Dhan credentials in MongoDB."""
    from cryptography.fernet import Fernet
    import json

    key = os.environ.get("FERNET_KEY", "")
    if not key:
        print("FERNET_KEY not set in .env")
        return
    cipher = Fernet(key.encode())

    payload = json.dumps({"access_token": access_token, "client_id": client_id})
    encrypted = cipher.encrypt(payload.encode()).decode()

    uid = user_id or "user_13805a0b2618"
    _db.dhan_credentials.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "encrypted": encrypted}},
        upsert=True,
    )
    print(f"Dhan credentials stored for user {uid}")


def _upload_csv(path: str, user_id: str | None = None) -> None:
    """Upload symbol_mappings CSV to MongoDB (same format as frontend upload)."""
    import csv

    uid = user_id or "user_13805a0b2618"
    _db.symbol_mappings.delete_many({"user_id": uid})

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        count = 0
        for row in reader:
            row["user_id"] = uid
            _db.symbol_mappings.insert_one(row)
            count += 1

    print(f"Uploaded {count} symbol mappings for user {uid}")


def _set_category_amount(category: str, pct: float, user_id: str | None = None) -> None:
    """Set category percentage.  pct is a whole number (e.g. 10 = 10%), stored as decimal (0.10)."""
    uid = user_id or "user_13805a0b2618"
    _db.category_amounts.update_one(
        {"user_id": uid, "category": category},
        {"$set": {"percentage": pct / 100.0}},
        upsert=True,
    )
    print(f"Set {category} = {pct}% of available funds for user {uid}")


def _ensure_alert_config(name: str, user_id: str | None = None) -> None:
    """Create a simple pass-through alert config if none exists."""
    import uuid

    uid = user_id or "user_13805a0b2618"
    existing = _db.alert_configs.find_one({"user_id": uid, "alert_name": name})
    if existing:
        print(f"Alert config '{name}' already exists")
        return

    doc = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "alert_name": name,
        "enabled": True,
        "broker": "dhan",
        "transaction_type": "B",
        "product": "CNC",
        "exchange_segment": "NSE_EQ",
        "quantity": 1,
        "scan_name": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _db.alert_configs.insert_one(doc)
    print(f"Created alert config '{name}' for user {uid}")


def main():
    parser = argparse.ArgumentParser(description="Verify broker order status")
    parser.add_argument("--all", action="store_true", help="Show all orders (not just today)")
    parser.add_argument("--order", type=str, help="Check a specific order ID")
    parser.add_argument("--watch", action="store_true", help="Poll every 10s until all resolve")
    parser.add_argument("--broker", default="dhan", choices=["dhan"])
    parser.add_argument("--user", type=str, default=None, help="MongoDB user_id")
    parser.add_argument("--store-dhan", nargs=2, metavar=("CLIENT_ID", "ACCESS_TOKEN"), help="Store Dhan credentials")
    parser.add_argument("--upload-csv", type=str, metavar="PATH", help="Upload symbol_mappings CSV")
    parser.add_argument("--set-category", nargs=2, metavar=("CATEGORY", "PERCENT"), help="Set category %% of available funds (e.g. largecap 10)")
    parser.add_argument("--setup-alert", type=str, metavar="ALERT_NAME", help="Create a default alert config (e.g. BUY)")
    args = parser.parse_args()

    if args.store_dhan:
        _store_dhan(args.store_dhan[1], args.store_dhan[0], args.user)
        return

    if args.upload_csv:
        _upload_csv(args.upload_csv, args.user)
        return

    if args.set_category:
        _set_category_amount(args.set_category[0], float(args.set_category[1]), args.user)
        return

    if args.setup_alert:
        _ensure_alert_config(args.setup_alert, args.user)
        return

    creds = _get_creds(args.user)
    if not creds:
        print("No Dhan credentials found in MongoDB.")
        print("  To add:  verify_orders.py --store-dhan CLIENT_ID ACCESS_TOKEN")
        print("  Or use:  https://invesment.pro")
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
