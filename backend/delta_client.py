"""Delta Exchange broker adapter via `delta-rest-client` SDK.

Delta Exchange is a crypto derivatives exchange (BTC, ETH, etc. futures & options).
Auth: API Key + API Secret from https://www.delta.exchange/ (or india.delta.exchange).

SDK: `delta-rest-client` (v1.0.14+) — https://pypi.org/project/delta-rest-client/

Delta Exchange uses product_ids (integers) instead of ticker symbols for orders.
We lazy-load the product list once and cache symbol -> product_id mapping.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from delta_rest_client import DeltaRestClient as DeltaSDK  # type: ignore
except Exception as e:
    DeltaSDK = None
    logger.warning("delta-rest-client not importable: %s", e)


class DeltaError(Exception):
    pass


_sessions: Dict[str, Any] = {}
_product_map: Dict[str, int] = {}
_product_map_loaded: bool = False

_BASE_URLS = {
    "india_prod": "https://api.india.delta.exchange",
    "global_prod": "https://api.delta.exchange",
    "india_testnet": "https://cdn-ind.testnet.deltaex.org",
    "global_testnet": "https://testnet-api.delta.exchange",
}


def _ensure_sdk():
    if DeltaSDK is None:
        raise DeltaError("delta-rest-client SDK not installed (pip install delta-rest-client)")


def _load_products(client) -> None:
    global _product_map_loaded
    if _product_map_loaded:
        return
    try:
        products = client.get_products()
        for p in products if isinstance(products, list) else (products.get("result") if isinstance(products, dict) and "result" in products else []):
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            sym = (p.get("symbol") or "").upper().strip()
            if pid and sym:
                _product_map[sym] = pid
        _product_map_loaded = True
        logger.info("Delta products loaded (%d symbols)", len(_product_map))
    except Exception as e:
        logger.warning("Delta product load failed: %s", e)


def _product_id_for(symbol: str) -> Optional[int]:
    sym = symbol.upper().strip()
    if sym in _product_map:
        return _product_map[sym]
    return None


def connect(user_id: str, api_key: str, api_secret: str, environment: str = "india_prod") -> dict:
    _ensure_sdk()
    api_key = (api_key or "").strip()
    api_secret = (api_secret or "").strip()
    if not api_key or not api_secret:
        raise DeltaError("api_key and api_secret are required")
    base_url = _BASE_URLS.get(environment, _BASE_URLS["india_prod"])
    try:
        client = DeltaSDK(base_url=base_url, api_key=api_key, api_secret=api_secret)
        resp = client.get_assets()
        if not isinstance(resp, list) or len(resp) == 0:
            raise DeltaError("Delta rejected credentials — could not fetch assets")
    except DeltaError:
        raise
    except Exception as e:
        raise DeltaError(f"Delta connect failed: {e}")
    _load_products(client)
    _sessions[user_id] = client
    return {"ok": True}


def is_authenticated(user_id: str) -> bool:
    return user_id in _sessions


def disconnect(user_id: str) -> None:
    _sessions.pop(user_id, None)


def _get(user_id: str):
    c = _sessions.get(user_id)
    if not c:
        raise DeltaError("Delta Exchange not connected. Please connect first.")
    return c


def get_positions(user_id: str) -> list:
    client = _get(user_id)
    try:
        resp = client.request("GET", "/v2/positions", auth=True)
    except Exception as e:
        raise DeltaError(f"get_positions failed: {e}")
    try:
        data = resp.json()
    except Exception:
        raise DeltaError("get_positions: non-JSON response")
    positions = data if isinstance(data, list) else data.get("result") if isinstance(data, dict) else []
    if not isinstance(positions, list):
        return []
    out = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        product_info = p.get("product") or {}
        sym = (product_info.get("symbol") or p.get("symbol") or "UNKNOWN").upper()
        size = int(p.get("size") or 0)
        qty = abs(size)
        if qty == 0:
            continue
        try:
            entry = float(p.get("entry_price") or 0)
        except Exception:
            entry = 0.0
        try:
            mark = float(p.get("mark_price") or 0) or None
        except Exception:
            mark = None
        try:
            pnl = float(p.get("pnl") or 0) or None
        except Exception:
            pnl = None
        out.append({
            "broker": "delta_exchange",
            "symbol": sym,
            "exchange_segment": "CRYPTO",
            "quantity": qty,
            "avg_price": round(entry, 2) if entry else 0.0,
            "ltp": round(mark, 2) if mark else None,
            "pnl": pnl,
            "product": f"perpetual_{size > 0 and 'long' or 'short'}",
        })
    return out


def place_order(
    user_id: str,
    symbol: str,
    transaction_type: str,
    quantity: int,
    order_type: str = "MKT",
    product: str = "CNC",
    exchange_segment: str = "CRYPTO",
    price: float = 0,
    trigger_price: float = 0,
    amo: bool = False,
) -> dict:
    client = _get(user_id)
    pid = _product_id_for(symbol)
    if pid is None:
        _load_products(client)
        pid = _product_id_for(symbol)
    if pid is None:
        raise DeltaError(f"Could not resolve Delta product_id for '{symbol}'")

    side = "buy" if transaction_type.upper() in ("B", "BUY") else "sell"
    ot_map = {
        "MKT": "market_order", "MARKET": "market_order",
        "L": "limit_order", "LIMIT": "limit_order",
    }
    delta_ot = ot_map.get(order_type.upper(), "market_order")

    kwargs = dict(product_id=pid, size=int(quantity), side=side, order_type=delta_ot)
    if delta_ot == "limit_order":
        kwargs["limit_price"] = float(price)
    if trigger_price > 0:
        kwargs["limit_price"] = float(trigger_price)

    try:
        resp = client.place_order(**kwargs)
    except Exception as e:
        raise DeltaError(f"place_order failed: {e}")

    order_id = None
    if isinstance(resp, dict):
        order_id = resp.get("id") or resp.get("order_id")
    return {"ok": True, "order_id": order_id, "response": _clean(resp)}


def _clean(obj):
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(x) for x in obj]
    return str(obj)
