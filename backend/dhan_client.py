"""Dhan (DhanHQ) broker adapter.

Dhan auth is SIMPLE: user pastes `client_id` + `access_token` (access token
expires ~24h, regenerated on web.dhan.co). No OTP flow.

SDK: `dhanhq` (v2+).

Order-placement semantics:
  - `security_id` is required, NOT the ticker. We lazy-load the Dhan scrip
    master CSV once and cache the symbol->security_id mapping in memory.
  - exchange_segment: NSE_EQ, BSE_EQ, NSE_FNO, etc.
  - product_type: CNC | INTRADAY | MARGIN
  - order_type: MARKET | LIMIT | STOP_LOSS | STOP_LOSS_MARKET
"""
from __future__ import annotations
import io
import logging
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

try:
    from dhanhq import dhanhq as DhanSDK, DhanContext  # type: ignore
except Exception as e:  # pragma: no cover
    DhanSDK = None
    DhanContext = None
    logger.warning("dhanhq not importable: %s", e)


class DhanError(Exception):
    pass


_sessions: Dict[str, Any] = {}          # {user_id: dhanhq instance}
_symbol_map: Dict[str, str] = {}        # {"NSE:RELIANCE": "2885"}
_map_loaded: bool = False

# Auth error notifications queued for delivery (telegram_notifier processes these)
_pending_auth_notifications: list[tuple[str, str]] = []  # [(user_id, message)]


def _ensure_sdk():
    if DhanSDK is None:
        raise DhanError("dhanhq SDK not installed")


def _load_scrip_master() -> None:
    """Lazy-load Dhan's scrip master to build symbol -> security_id map."""
    global _map_loaded
    if _map_loaded:
        return
    try:
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        import pandas as pd
        df = pd.read_csv(io.StringIO(r.text), low_memory=False)
        # Common columns: SEM_EXM_EXCH_ID, SEM_SMST_SECURITY_ID, SEM_TRADING_SYMBOL
        for _, row in df.iterrows():
            exch = str(row.get("SEM_EXM_EXCH_ID", "")).strip()
            sid = str(row.get("SEM_SMST_SECURITY_ID", "")).strip()
            sym = str(row.get("SEM_TRADING_SYMBOL", "")).strip()
            if not exch or not sid or not sym:
                continue
            key = f"{exch}:{sym.upper()}"
            _symbol_map[key] = sid
        _map_loaded = True
        logger.info("Dhan scrip master loaded (%d rows)", len(_symbol_map))
    except Exception as e:
        logger.warning("Dhan scrip master load failed: %s (orders will require manual security_id)", e)


def connect(user_id: str, client_id: str, access_token: str) -> dict:
    _ensure_sdk()
    client_id = (client_id or "").strip()
    access_token = (access_token or "").strip()
    if not client_id or not access_token:
        raise DhanError("client_id and access_token are required")
    try:
        ctx = DhanContext(client_id, access_token)
        client = DhanSDK(ctx)
        # Quick validation: fund_limit is a cheap auth-required call
        try:
            resp = client.get_fund_limits()
            if isinstance(resp, dict) and resp.get("status") == "failure":
                raise DhanError(resp.get("remarks") or "Dhan rejected credentials")
        except DhanError:
            raise
        except Exception as e:
            raise DhanError(f"Dhan credential validation failed: {e}")
    except DhanError:
        raise
    except Exception as e:
        raise DhanError(f"Dhan SDK init failed: {e}")
    _sessions[user_id] = client
    return {"ok": True}


def is_authenticated(user_id: str) -> bool:
    return user_id in _sessions


def disconnect(user_id: str) -> None:
    _sessions.pop(user_id, None)


_AUTH_ERROR_INDICATORS = ("DH-901", "Invalid_Authentication", "access token is invalid", "access token invalid")


def _invalidate_on_auth_error(user_id: str, result) -> bool:
    """If a Dhan response/exception indicates an expired token, disconnect
    the user so subsequent calls skip instead of failing."""
    if result is None:
        return False
    msg = str(result.get("remarks") if isinstance(result, dict) else result)
    if any(ind in msg for ind in _AUTH_ERROR_INDICATORS):
        _sessions.pop(user_id, None)
        logger.warning("Dhan auth error detected for user %s — disconnected session", user_id)
        _pending_auth_notifications.append((user_id, msg))
        return True
    return False


def _get(user_id: str):
    c = _sessions.get(user_id)
    if not c:
        raise DhanError("Dhan not connected. Please connect first.")
    return c


def _security_id_for(symbol: str, exchange_segment: str = "NSE_EQ") -> Optional[str]:
    _load_scrip_master()
    exch = "NSE" if exchange_segment.startswith("NSE") else "BSE"
    sym = symbol.upper().strip()
    # Dhan master often stores base symbol - try a few variants
    for candidate in (sym, sym.replace("-EQ", ""), f"{sym}-EQ"):
        key = f"{exch}:{candidate}"
        if key in _symbol_map:
            return _symbol_map[key]
    return None


def get_positions(user_id: str) -> list:
    client = _get(user_id)
    try:
        resp = client.get_positions()
    except Exception as e:
        _invalidate_on_auth_error(user_id, e)
        raise DhanError(f"get_positions failed: {e}")
    data = resp.get("data") if isinstance(resp, dict) else resp
    positions = data if isinstance(data, list) else []
    out = []
    for p in positions:
        qty = int(p.get("netQty") or p.get("quantity") or 0)
        out.append({
            "broker": "dhan",
            "symbol": (p.get("tradingSymbol") or p.get("trading_symbol") or "UNKNOWN").upper(),
            "exchange_segment": p.get("exchangeSegment") or p.get("exchange_segment") or "NSE_EQ",
            "security_id": p.get("securityId") or p.get("security_id"),
            "quantity": qty,
            "avg_price": float(p.get("buyAvg") or p.get("costPrice") or p.get("netAvgPrice") or 0),
            "ltp": float(p.get("lastTradedPrice") or p.get("ltp") or 0) or None,
            "pnl": float(p.get("realizedProfit") or 0) + float(p.get("unrealizedProfit") or 0) or None,
            "product": p.get("productType") or p.get("product"),
        })
    return [o for o in out if o["quantity"] != 0]


def get_holdings(user_id: str) -> list:
    """Return delivery holdings (CNC long positions) from Dhan.

    Holdings represent shares held in the demat account (delivery),
    as opposed to get_positions() which returns intraday open positions.
    """
    client = _get(user_id)
    try:
        resp = client.get_holdings()
    except Exception as e:
        _invalidate_on_auth_error(user_id, e)
        raise DhanError(f"get_holdings failed: {e}")
    data = resp.get("data") if isinstance(resp, dict) else resp
    holdings = data if isinstance(data, list) else []
    out = []
    for h in holdings:
        qty = int(h.get("totalQty") or h.get("availableQty") or h.get("dpQty") or 0)
        if qty <= 0:
            continue
        out.append({
            "broker": "dhan",
            "symbol": (h.get("tradingSymbol") or h.get("trading_symbol") or "UNKNOWN").upper(),
            "exchange_segment": "NSE_EQ",
            "security_id": h.get("securityId") or h.get("security_id"),
            "quantity": qty,
            "avg_price": float(h.get("avgCostPrice") or h.get("costPrice") or 0),
            "ltp": float(h.get("lastTradedPrice") or h.get("ltp") or 0) or None,
            "pnl": None,
            "product": "CNC",
            "source": "holding",
        })
    return out


def place_order(
    user_id: str,
    symbol: str,
    transaction_type: str,   # "B" | "S" (our internal convention)
    quantity: int,
    order_type: str = "MKT",  # MKT | L | SL | SL-M (internal)
    product: str = "CNC",     # internal
    exchange_segment: str = "NSE_EQ",
    price: float = 0,
    trigger_price: float = 0,
    security_id: Optional[str] = None,
    amo: bool = False,
) -> dict:
    client = _get(user_id)

    sid = security_id or _security_id_for(symbol, exchange_segment)
    if not sid:
        raise DhanError(f"Could not resolve Dhan security_id for '{symbol}' on {exchange_segment}")

    dhan_txn = "BUY" if transaction_type.upper() in ("B", "BUY") else "SELL"
    ot_map = {
        "MKT": "MARKET", "MARKET": "MARKET",
        "L": "LIMIT", "LIMIT": "LIMIT",
        "SL": "STOP_LOSS", "SL-M": "STOP_LOSS_MARKET",
    }
    pt_map = {
        "CNC": "CNC", "MIS": "INTRADAY", "NRML": "MARGIN",
        "INTRADAY": "INTRADAY", "MARGIN": "MARGIN",
    }
    dhan_ot = ot_map.get(order_type.upper(), "MARKET")
    dhan_pt = pt_map.get(product.upper(), "CNC")

    # Build payload matching Dhan v2 API spec (see SDK _order.py place_order)
    payload = {
        "transactionType": dhan_txn,
        "exchangeSegment": exchange_segment,
        "productType": dhan_pt,
        "orderType": dhan_ot,
        "validity": "DAY",
        "securityId": str(sid),
        "quantity": int(quantity),
        "disclosedQuantity": 0,
        "price": float(price),
        "triggerPrice": float(trigger_price),
        "afterMarketOrder": amo,
    }

    logger.info("Dhan order payload: %s", payload)
    try:
        resp = client.dhan_http.post("/orders", payload)
    except Exception as e:
        logger.warning("Dhan place_order exception: %s", e)
        _invalidate_on_auth_error(user_id, e)
        raise DhanError(f"place_order failed: {e}")

    logger.info("Dhan order response: %s", resp)
    if isinstance(resp, dict) and resp.get("status") == "failure":
        _invalidate_on_auth_error(user_id, resp)
        raise DhanError(resp.get("remarks") or "Dhan order rejected")

    order_id = None
    if isinstance(resp, dict):
        data = resp.get("data") or {}
        order_id = data.get("orderId") if isinstance(data, dict) else None
    return {"ok": True, "order_id": order_id, "response": _clean(resp)}


def get_open_orders(user_id: str) -> list:
    client = _get(user_id)
    try:
        resp = client.get_order_list()
    except Exception as e:
        _invalidate_on_auth_error(user_id, e)
        raise DhanError(f"get_order_list failed: {e}")
    data = resp.get("data") if isinstance(resp, dict) else resp
    orders = data if isinstance(data, list) else []
    out = []
    for o in orders:
        qty = int(o.get("quantity") or o.get("netQty") or 0)
        out.append({
            "order_id": o.get("orderId") or o.get("dhanOrderId"),
            "symbol": (o.get("tradingSymbol") or o.get("trading_symbol") or "").upper(),
            "order_type": o.get("orderType") or "",
            "status": o.get("orderStatus") or "",
            "trigger_price": float(o.get("triggerPrice") or 0),
            "price": float(o.get("price") or 0),
            "quantity": qty,
            "filled_qty": int(o.get("filledQty") or 0),
            "exchange_segment": o.get("exchangeSegment") or o.get("exchange_segment") or "NSE_EQ",
            "security_id": o.get("securityId") or o.get("security_id"),
        })
    return out


def modify_sl_order(
    user_id: str,
    order_id: str,
    new_trigger_price: float,
    new_limit_price: float,
    quantity: int,
) -> dict:
    client = _get(user_id)
    try:
        resp = client.modify_order(
            order_id=order_id,
            order_type="STOP_LOSS",
            leg_name="ENTRY",
            quantity=int(quantity),
            price=float(new_limit_price),
            trigger_price=float(new_trigger_price),
            disclosed_quantity=0,
            validity="DAY",
        )
    except Exception as e:
        _invalidate_on_auth_error(user_id, e)
        raise DhanError(f"modify_order failed: {e}")
    if isinstance(resp, dict) and resp.get("status") == "failure":
        _invalidate_on_auth_error(user_id, resp)
        raise DhanError(resp.get("remarks") or "Dhan modify order rejected")
    return {"ok": True, "order_id": order_id, "response": _clean(resp)}


def get_available_funds(user_id: str) -> float:
    """Fetch available balance from Dhan fund limits API."""
    client = _get(user_id)
    try:
        resp = client.get_fund_limits()
    except Exception as e:
        _invalidate_on_auth_error(user_id, e)
        raise DhanError(f"get_fund_limits failed: {e}")
    data = resp.get("data") if isinstance(resp, dict) else resp
    if isinstance(data, dict):
        return float(data.get("availableBalance", 0))
    if isinstance(data, list) and len(data) > 0:
        return float(data[0].get("availableBalance", 0))
    return 0.0


def _clean(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(x) for x in obj]
    return str(obj)
