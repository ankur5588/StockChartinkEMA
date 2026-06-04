#!/usr/bin/env python3
"""Automated Dhan access-token renewal via headless browser.

Usage:
  # First-time: store Dhan web login credentials
  python dhan_auto_auth.py --setup-login BO_ID PASSWORD

  # Renew access token (prompts for OTP via Telegram + file)
  python dhan_auto_auth.py --renew

  # Provide OTP during an active renewal session
  python dhan_auto_auth.py --otp 123456

  # Check token status
  python dhan_auto_auth.py --status
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

# ── helpers ────────────────────────────────────────────────────────────────

TELEGRAM_BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
FERNET_KEY = os.environ.get("FERNET_KEY", "")
OTP_REPLY_FILE = "/tmp/dhan_otp_reply.txt"
STATE_FILE = "/tmp/dhan_auto_auth_state.json"

try:
    from pymongo import MongoClient as _MC
    _url = os.environ.get("MONGO_URL", "")
    if not _url:
        _env_file = Path(__file__).parent / ".env"
        if _env_file.exists():
            for line in _env_file.read_text().splitlines():
                if line.startswith("MONGO_URL="):
                    _url = line.split("=", 1)[1].strip().strip("\"'")
                    break
    _DB_NAME = os.environ.get("DB_NAME", "chartink_trade")
    _db = _MC(_url or "mongodb://localhost:27017")[_DB_NAME]
except Exception as e:
    _db = None
    print(f"MongoDB not available: {e}", file=sys.stderr)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


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


def _encrypt(data: dict) -> str:
    from cryptography.fernet import Fernet
    return Fernet(FERNET_KEY.encode()).encrypt(json.dumps(data).encode()).decode()


def _decrypt(raw: str) -> dict:
    from cryptography.fernet import Fernet
    return json.loads(Fernet(FERNET_KEY.encode()).decrypt(raw.encode()).decode())


# ── credential storage for Dhan WEB login (BO ID + password) ──────────────

AUTH_COLL = "dhan_auto_auth"

def store_login_creds(bo_id: str, password: str) -> None:
    if _db is None:
        print("No MongoDB connection")
        return
    encrypted = _encrypt({"bo_id": bo_id.strip(), "password": password.strip()})
    _db[AUTH_COLL].update_one(
        {"_id": "dhan_web"},
        {"$set": {"encrypted": encrypted, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    print(f"✅ Dhan login credentials stored for BO ID: {bo_id}")


def get_login_creds() -> dict | None:
    if _db is None:
        return None
    doc = _db[AUTH_COLL].find_one({"_id": "dhan_web"})
    if not doc:
        return None
    return _decrypt(doc["encrypted"])


def store_access_token(access_token: str, client_id: str) -> None:
    """Store the new Dhan API access token in the credentials collection."""
    if _db is None:
        return
    encrypted = _encrypt({"access_token": access_token, "client_id": client_id})
    user_id = "user_13805a0b2618"
    if _db is not None:
        alert_user = _db.alert_configs.find_one({"enabled": True}, {"user_id": 1})
        if alert_user:
            user_id = alert_user["user_id"]
    _db.dhan_credentials.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "encrypted": encrypted, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    print(f"✅ New Dhan access token stored for client: {client_id}")


# ── OTP helpers ────────────────────────────────────────────────────────────

def _wait_for_otp(timeout_min: int = 5) -> str | None:
    """Wait for user to provide OTP (via file or Telegram)."""
    if os.path.exists(OTP_REPLY_FILE):
        os.remove(OTP_REPLY_FILE)

    msg = (
        "🔐 <b>Dhan OTP Required</b>\n"
        f"Login session needs OTP. Reply with: <code>dhan-otp CODE</code>\n"
        f"Or SSH and run: <code>dhan_auto_auth.py --otp CODE</code>\n"
        f"Timeout: {timeout_min} minutes"
    )
    tg_send(msg)
    print(f"\n🔐 OTP required. Sent Telegram notification.")
    print(f"   Reply in Telegram with: dhan-otp CODE")
    print(f"   Or run: dhan_auto_auth.py --otp CODE")
    print(f"   Waiting up to {timeout_min} minutes...\n")

    deadline = time.time() + timeout_min * 60
    last_offset = 0

    while time.time() < deadline:
        # Check file
        if os.path.exists(OTP_REPLY_FILE):
            with open(OTP_REPLY_FILE) as f:
                val = f.read().strip()
            if val:
                os.remove(OTP_REPLY_FILE)
                return val

        # Check Telegram via getUpdates
        if TELEGRAM_BOT and TELEGRAM_CHAT:
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT}/getUpdates",
                    params={"offset": last_offset, "timeout": 5, "allowed_updates": ["message"]},
                    timeout=10,
                )
                updates = r.json().get("result", [])
                for upd in updates:
                    last_offset = upd["update_id"] + 1
                    msg_text = (upd.get("message") or {}).get("text", "").strip()
                    chat_id = str((upd.get("message") or {}).get("chat", {}).get("id", ""))
                    if chat_id == TELEGRAM_CHAT and msg_text.lower().startswith("dhan-otp"):
                        otp = msg_text[len("dhan-otp"):].strip()
                        if otp and otp.isdigit():
                            return otp
            except Exception:
                pass

        time.sleep(2)

    tg_send("⏰ Dhan OTP request timed out (5 min). Run <code>--renew</code> again.")
    return None


# ── browser automation ────────────────────────────────────────────────────

def _renew_token(bo_id: str, password: str) -> bool:
    """Login to Dhan web portal and renew access token."""
    print(f"\n{'='*55}")
    print(f"  Dhan Auto-Auth — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*55}")
    print(f"  BO ID: {bo_id}")
    print(f"  Logging in...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(15000)

        try:
            # ── Step 1: Login page ─────────────────────────────────────────
            page.goto("https://web.dhan.co/", wait_until="domcontentloaded")
            time.sleep(2)

            # Enter BO ID
            bo_input = page.locator('input[type="text"], input[name="boId"], input[placeholder*="BO"], input[id*="bo"]').first
            bo_input.fill(bo_id)
            print("  ✅ BO ID entered")

            # Enter password
            pw_input = page.locator('input[type="password"]').first
            pw_input.fill(password)
            print("  ✅ Password entered")

            # Click login
            login_btn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign In")').first
            login_btn.click()
            print("  ✅ Login submitted")

            # ── Step 2: OTP ────────────────────────────────────────────────
            time.sleep(3)

            # Check if OTP page appeared
            otp_page = page.locator('input[type="tel"], input[name*="otp"], input[placeholder*="OTP"], input[id*="otp"]').first
            if otp_page.is_visible(timeout=5000):
                print("  🔐 OTP page detected")
                otp = _wait_for_otp()
                if not otp:
                    print("  ❌ OTP not provided, aborting")
                    tg_send("❌ Dhan auto-auth failed: OTP timeout")
                    browser.close()
                    return False

                # Enter OTP digit by digit
                digits = otp_page.locator('input[type="tel"]')
                count = digits.count()
                if count > 1:
                    for i, ch in enumerate(otp):
                        if i < count:
                            digits.nth(i).fill(ch)
                else:
                    otp_page.fill(otp)

                print("  ✅ OTP entered")
                time.sleep(1)

                # Submit OTP
                submit_btn = page.locator('button[type="submit"], button:has-text("Verify"), button:has-text("Submit")').first
                if submit_btn.is_visible(timeout=3000):
                    submit_btn.click()
                else:
                    page.keyboard.press("Enter")

                time.sleep(3)
                print("  ✅ OTP submitted")

            # ── Step 3: Navigate to API settings ────────────────────────────
            print("  📍 Navigating to API settings...")
            page.goto("https://web.dhan.co/settings/api", wait_until="domcontentloaded")
            time.sleep(3)

            # Check if we arrived
            current_url = page.url
            print(f"  Current URL: {current_url}")

            # ── Step 4: Regenerate / copy token ────────────────────────────
            # Look for the access token display or regenerate button
            token_input = page.locator('input[type="text"][value*="eyJ"], input[id*="token"], input[name*="token"]').first
            if token_input.is_visible(timeout=5000):
                token = token_input.input_value()
                print(f"  ✅ Token found in input field")
            else:
                # Try to find token text on page
                token_text = page.locator('text=/eyJ[a-zA-Z0-9._-]+/').first
                if token_text.is_visible(timeout=3000):
                    full_text = token_text.text_content()
                    import re
                    match = re.search(r'eyJ[a-zA-Z0-9._-]+', full_text)
                    token = match.group(0) if match else None
                    print(f"  ✅ Token extracted from page text")
                else:
                    # Click regenerate button if available
                    regen_btn = page.locator(
                        'button:has-text("Regenerate"), button:has-text("Generate"), '
                        'button:has-text("New Token"), button:has-text("Create")'
                    ).first
                    if regen_btn.is_visible(timeout=3000):
                        regen_btn.click()
                        time.sleep(2)
                        # Wait for new token to appear
                        token_input = page.locator('input[type="text"][value*="eyJ"]').first
                        if token_input.is_visible(timeout=5000):
                            token = token_input.input_value()
                            print(f"  ✅ Token regenerated")
                        else:
                            token = None
                    else:
                        token = None

            if token:
                client_id = "QFVX70943P"
                store_access_token(token, client_id)
                tg_send("✅ <b>Dhan access token renewed automatically!</b>")
                print(f"\n  ✅ New token stored successfully")
                print(f"  Token preview: {token[:50]}...")
                browser.close()
                return True
            else:
                print(f"  ❌ Could not find/regenerate token")
                tg_send("❌ Dhan auto-auth: could not find/regenerate token")
                # Save screenshot for debugging
                page.screenshot(path="/tmp/dhan_auto_auth_debug.png")
                print("  Screenshot saved to /tmp/dhan_auto_auth_debug.png")
                browser.close()
                return False

        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.screenshot(path="/tmp/dhan_auto_auth_error.png")
                print("  Screenshot saved to /tmp/dhan_auto_auth_error.png")
            except Exception:
                pass
            tg_send(f"❌ Dhan auto-auth error: {e}")
            browser.close()
            return False


# ── status ─────────────────────────────────────────────────────────────────

def _show_status() -> None:
    """Check current token status from MongoDB."""
    if _db is None:
        print("No MongoDB connection")
        return

    uid = "user_13805a0b2618"
    if _db is not None:
        alert_user = _db.alert_configs.find_one({"enabled": True}, {"user_id": 1})
        if alert_user:
            uid = alert_user["user_id"]
    cred_doc = _db.dhan_credentials.find_one({"user_id": uid})
    login_doc = _db[AUTH_COLL].find_one({"_id": "dhan_web"})

    print(f"\n{'='*50}")
    print(f"  Dhan Auto-Auth Status")
    print(f"{'='*50}")

    if login_doc:
        print(f"  Web login credentials: ✅ stored")
        print(f"  Last updated: {login_doc.get('updated_at', '?')}")
    else:
        print(f"  Web login credentials: ❌ not set (run --setup-login)")

    if cred_doc:
        try:
            creds = _decrypt(cred_doc["encrypted"])
            token = creds.get("access_token", "")
            cid = creds.get("client_id", "")
            print(f"  API access token: ✅ present")
            print(f"  Client ID: {cid}")
            print(f"  Token preview: {token[:50]}...")

            # Try to decode JWT to check expiry
            import base64
            try:
                parts = token.split(".")
                if len(parts) == 3:
                    padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(padded))
                    exp = payload.get("exp", 0)
                    exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
                    remaining = exp_dt - datetime.now(timezone.utc)
                    print(f"  Expires: {exp_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                    print(f"  Remaining: {remaining}")
                    if remaining.total_seconds() < 3600:
                        print(f"  ⚠️  Token expires soon, renewal recommended")
            except Exception:
                pass
        except Exception as e:
            print(f"  API access token: ❌ decrypt error ({e})")
    else:
        print(f"  API access token: ❌ not set")

    # Check state file
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
        print(f"\n  Pending OTP session: {'yes' if state.get('awaiting_otp') else 'no'}")


# ── main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Automated Dhan access-token renewal")
    parser.add_argument("--setup-login", nargs=2, metavar=("BO_ID", "PASSWORD"), help="Store Dhan web login credentials")
    parser.add_argument("--renew", action="store_true", help="Renew access token via headless browser")
    parser.add_argument("--otp", type=str, help="Provide OTP for active renewal session")
    parser.add_argument("--status", action="store_true", help="Check token expiry and login status")
    args = parser.parse_args()

    if args.setup_login:
        store_login_creds(args.setup_login[0], args.setup_login[1])
        return

    if args.status:
        _show_status()
        return

    if args.otp:
        with open(OTP_REPLY_FILE, "w") as f:
            f.write(args.otp.strip())
        print(f"✅ OTP {args.otp} written to {OTP_REPLY_FILE}")
        return

    if args.renew:
        creds = get_login_creds()
        if not creds:
            print("❌ No Dhan web login credentials found.")
            print("   Run: dhan_auto_auth.py --setup-login BO_ID PASSWORD")
            sys.exit(1)
        success = _renew_token(creds["bo_id"], creds["password"])
        sys.exit(0 if success else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
