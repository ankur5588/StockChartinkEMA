#!/usr/bin/env python3
"""Automated Dhan access-token renewal via Dhan's Renew Token API.

Usage:
  # Renew access token (call this daily via cron)
  python dhan_auto_auth.py --renew

  # Check token status
  python dhan_auto_auth.py --status

  # Fallback: renew via TOTP (requires TOTP setup in Dhan)
  python dhan_auto_auth.py --totp CLIENT_ID PIN TOTP_SECRET
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── helpers ────────────────────────────────────────────────────────────────

TELEGRAM_BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
FERNET_KEY = os.environ.get("FERNET_KEY", "")

# MongoDB connection (load MONGO_URL from .env directly if missing from env)
try:
    _url = os.environ.get("MONGO_URL", "")
    if not _url:
        _env_file = Path(__file__).parent / ".env"
        if _env_file.exists():
            for line in _env_file.read_text().splitlines():
                if line.startswith("MONGO_URL="):
                    _url = line.split("=", 1)[1].strip().strip("\"'")
                    break
    from pymongo import MongoClient as _MC

    _DB_NAME = os.environ.get("DB_NAME", "chartink_trade")
    _db = _MC(_url or "mongodb://localhost:27017")[_DB_NAME]
except Exception as e:
    _db = None
    print(f"MongoDB not available: {e}", file=sys.stderr)

# ── utils ──────────────────────────────────────────────────────────────────

def _get_user_id() -> str:
    """Auto-detect the user_id that owns alert configs or dhan credentials."""
    uid = "user_13805a0b2618"
    if _db is not None:
        doc = _db.alert_configs.find_one({"enabled": True}, {"user_id": 1})
        if doc:
            uid = doc["user_id"]
        else:
            doc = _db.dhan_credentials.find_one({}, {"user_id": 1})
            if doc:
                uid = doc["user_id"]
    return uid


def _encrypt(data: dict) -> str:
    from cryptography.fernet import Fernet
    return Fernet(FERNET_KEY.encode()).encrypt(json.dumps(data).encode()).decode()


def _decrypt(raw: str) -> dict:
    from cryptography.fernet import Fernet
    return json.loads(Fernet(FERNET_KEY.encode()).decrypt(raw.encode()).decode())


def tg_send(text: str) -> None:
    if not TELEGRAM_BOT or not TELEGRAM_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram send failed: {e}")


# ── get current credentials from MongoDB ──────────────────────────────────

def get_current_creds() -> dict | None:
    """Decrypt and return current Dhan credentials from MongoDB."""
    if _db is None:
        return None
    uid = _get_user_id()
    doc = _db.dhan_credentials.find_one({"user_id": uid})
    if not doc:
        doc = _db.dhan_credentials.find_one({})
    if not doc:
        return None
    try:
        return _decrypt(doc["encrypted"])
    except Exception:
        return None


def store_creds(access_token: str, client_id: str) -> bool:
    """Store new access token in MongoDB."""
    if _db is None:
        return False
    encrypted = _encrypt({"access_token": access_token, "client_id": client_id})
    uid = _get_user_id()
    _db.dhan_credentials.update_one(
        {"user_id": uid},
        {"$set": {"user_id": uid, "encrypted": encrypted, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return True


def decode_jwt_payload(token: str) -> dict | None:
    """Decode JWT payload (without verification) to check expiry."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None


# ── Renew Token API ───────────────────────────────────────────────────────
# POST https://api.dhan.co/v2/RenewToken
# Headers: access-token, dhanClientId
# Extends current token by 24h (only works if token is still active)


def renew_via_api(access_token: str, client_id: str) -> str | None:
    """Call Dhan's Renew Token API to extend the access token by 24h."""
    headers = {
        "access-token": access_token,
        "dhanClientId": client_id,
    }
    try:
        r = requests.post(
            "https://api.dhan.co/v2/RenewToken",
            headers=headers,
            timeout=15,
        )
        data = r.json()
        if isinstance(data, dict):
            if data.get("status") == "failure":
                err = data.get("remarks", data.get("errorMessage", "unknown"))
                raise Exception(f"Dhan API error: {err}")
            new_token = data.get("accessToken") or data.get("data", {}).get("accessToken")
            if new_token:
                return new_token
        return None
    except Exception as e:
        raise


# ── TOTP generation ──────────────────────────────────────────────────────
# RFC 6238 TOTP (Google Authenticator compatible)
# Called if the user has TOTP enabled in Dhan


def _generate_totp(secret: str, interval: int = 30) -> str:
    """Generate a TOTP code from a base32-encoded secret."""
    key = base64.b32decode(secret.upper().replace(" ", ""))
    counter = struct.pack(">Q", int(time.time()) // interval)
    mac = hmac.new(key, counter, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"


def renew_via_totp(
    dhan_client_id: str, pin: str, totp_secret: str
) -> dict | None:
    """Generate a fresh access token using Dhan's TOTP-based token endpoint."""
    totp = _generate_totp(totp_secret)
    url = (
        f"https://auth.dhan.co/app/generateAccessToken"
        f"?dhanClientId={dhan_client_id}&pin={pin}&totp={totp}"
    )
    try:
        r = requests.post(url, timeout=15)
        data = r.json()
        if data.get("accessToken"):
            return data
        raise Exception(f"TOTP auth failed: {data}")
    except Exception as e:
        raise


# ── commands ──────────────────────────────────────────────────────────────

def cmd_status():
    """Show current token status and expiry."""
    creds = get_current_creds()
    if not creds:
        print("❌ No Dhan credentials found in MongoDB.")
        print("   Add them via the frontend dashboard at https://invesment.pro")
        return 1

    token = creds.get("access_token", "")
    cid = creds.get("client_id", "")

    print(f"\n{'='*50}")
    print(f"  Dhan Token Status")
    print(f"{'='*50}")
    print(f"  Client ID:   {cid}")
    print(f"  Token:       {token[:50]}...")

    payload = decode_jwt_payload(token)
    if payload:
        exp = payload.get("exp", 0)
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        remaining = exp_dt - datetime.now(timezone.utc)
        print(f"  Expires:     {exp_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  Remaining:   {remaining}")
        if remaining.total_seconds() < 0:
            print(f"  ⚠️  EXPIRED — renew won't work, use --totp or regenerate from dashboard")
        elif remaining.total_seconds() < 3600:
            print(f"  ⚠️  Expiring soon — renew immediately")
        else:
            print(f"  ✅  Token is active")
    else:
        print(f"  ⚠️  Could not decode token (not a JWT?)")

    # Check if auto-auth creds exist
    if _db is not None:
        totp_doc = _db.dhan_auto_auth.find_one({"_id": "dhan_totp"})
        if totp_doc and totp_doc.get("totp_secret"):
            print(f"\n  TOTP auto-auth: ✅ configured")
        else:
            print(f"\n  TOTP auto-auth: ❌ not configured (optional for --totp)")

    return 0


def cmd_renew():
    """Renew access token via Dhan's Renew Token API."""
    creds = get_current_creds()
    if not creds:
        print("❌ No Dhan credentials found.")
        return 1

    token = creds.get("access_token", "")
    cid = creds.get("client_id", "")

    # Check if token is expired
    payload = decode_jwt_payload(token)
    if payload:
        exp = payload.get("exp", 0)
        if exp and exp < time.time():
            print(f"❌ Token already expired. Cannot renew via API.")
            print("   Use --totp or regenerate from Dhan dashboard.")
            return 1

    print(f"🔄 Renewing Dhan access token for client {cid}...")
    try:
        new_token = renew_via_api(token, cid)
    except Exception as e:
        print(f"❌ Renew failed: {e}")
        tg_send(f"❌ Dhan token renewal failed: {e}")
        return 1

    if not new_token:
        print("❌ Renew API returned no new token")
        return 1

    store_creds(new_token, cid)

    new_payload = decode_jwt_payload(new_token)
    if new_payload:
        exp = new_payload.get("exp", 0)
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else "?"
        print(f"✅ Token renewed successfully!")
        print(f"   New expiry: {exp_dt}")
        print(f"   Preview: {new_token[:50]}...")
        tg_send(f"✅ Dhan access token renewed. Expires: {exp_dt}")
    else:
        print(f"✅ Token renewed (could not decode expiry)")

    return 0


def cmd_setup_totp(client_id: str, pin: str, totp_secret: str):
    """Store TOTP credentials for automatic token generation (no headless browser)."""
    if _db is None:
        print("❌ No MongoDB connection")
        return 1

    # Validate by generating a token
    print("🔐 Testing TOTP by generating a token...")
    try:
        result = renew_via_totp(client_id, pin, totp_secret)
        token = result.get("accessToken", "")
        print(f"✅ TOTP works! Token generated: {token[:50]}...")
        store_creds(token, client_id)
        print(f"✅ Token stored in MongoDB")
    except Exception as e:
        print(f"❌ TOTP validation failed: {e}")
        print("   Check that TOTP is enabled in your Dhan settings.")
        return 1

    # Store TOTP creds encrypted for future use
    encrypted = _encrypt({
        "dhan_client_id": client_id,
        "pin": pin,
        "totp_secret": totp_secret,
    })
    _db.dhan_auto_auth.update_one(
        {"_id": "dhan_totp"},
        {"$set": {"encrypted": encrypted, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    print(f"✅ TOTP credentials stored for auto-renewal")
    return 0


def cmd_totp_renew():
    """Fallback: generate fresh token via TOTP (when Renew API fails due to expiry)."""
    if _db is None:
        print("❌ No MongoDB connection")
        return 1

    doc = _db.dhan_auto_auth.find_one({"_id": "dhan_totp"})
    if not doc:
        print("❌ No TOTP credentials stored. Run: dhan_auto_auth.py --setup-totp CLIENT_ID PIN SECRET")
        return 1

    try:
        creds = _decrypt(doc["encrypted"])
    except Exception as e:
        print(f"❌ Failed to decrypt TOTP creds: {e}")
        return 1

    cid = creds["dhan_client_id"]
    pin = creds["pin"]
    secret = creds["totp_secret"]

    print(f"🔄 Generating fresh token via TOTP...")
    try:
        result = renew_via_totp(cid, pin, secret)
        token = result.get("accessToken", "")
        store_creds(token, cid)
        print(f"✅ Fresh token generated and stored")
        print(f"   Preview: {token[:50]}...")
        tg_send(f"✅ Dhan token renewed via TOTP")
        return 0
    except Exception as e:
        print(f"❌ TOTP renewal failed: {e}")
        tg_send(f"❌ Dhan TOTP renewal failed: {e}")
        return 1


# ── main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Automated Dhan access-token renewal")
    parser.add_argument("--renew", action="store_true", help="Renew token via Renew Token API")
    parser.add_argument("--status", action="store_true", help="Check token expiry")
    parser.add_argument("--setup-totp", nargs=3, metavar=("CLIENT_ID", "PIN", "TOTP_SECRET"),
                        help="Store TOTP credentials for auto-renewal")
    parser.add_argument("--totp-renew", action="store_true",
                        help="Generate fresh token via TOTP (fallback when token expired)")
    args = parser.parse_args()

    if args.status:
        return cmd_status()
    if args.renew:
        return cmd_renew()
    if args.setup_totp:
        return cmd_setup_totp(*args.setup_totp)
    if args.totp_renew:
        return cmd_totp_renew()

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
