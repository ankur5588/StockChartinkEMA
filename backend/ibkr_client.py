"""Interactive Brokers (IBKR) adapter.

Connects to a local IB Gateway (or TWS) via the ib_insync library.

Requires ib_insync and a running IB Gateway on the configured host:port.

Exchange segments used for US stocks:
  - SMART (smart-routing across NASDAQ/NYSE/AMEX)

Order types supported:
  - MKT (Market)
  - LMT (Limit)

Products (mapped from internal codes):
  - CNC / MIS / NRML → not used for US stocks (always SMART routing)
"""
from __future__ import annotations
import csv
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from ib_insync import IB, Stock, MarketOrder, LimitOrder  # type: ignore
except Exception as e:
    IB = None
    Stock = None
    MarketOrder = None
    LimitOrder = None
    logger.warning("ib_insync not importable: %s", e)


class IbkrError(Exception):
    pass


_sessions: Dict[str, Any] = {}  # {user_id: ib_insync.IB instance}
_snp500_set: set = set()
_snp500_loaded: bool = False

# Default connection params
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4001  # IB Gateway default API port
DEFAULT_CLIENT_ID = 2


def _ensure_ib_insync():
    if IB is None:
        raise IbkrError("ib_insync not installed")


def _get(user_id: str):
    ib = _sessions.get(user_id)
    if not ib:
        raise IbkrError("Interactive Brokers not connected")
    return ib


def connect(
    user_id: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    client_id: int = DEFAULT_CLIENT_ID,
) -> dict:
    _ensure_ib_insync()
    if user_id in _sessions:
        try:
            _sessions[user_id].disconnect()
        except Exception:
            pass
        del _sessions[user_id]

    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
    except Exception as e:
        raise IbkrError(f"IB Gateway connection failed: {e}")

    _sessions[user_id] = ib
    logger.info("IBKR connected for user %s (%s:%d)", user_id, host, port)
    return {"ok": True}


def is_authenticated(user_id: str) -> bool:
    ib = _sessions.get(user_id)
    return ib is not None and ib.isConnected()


def disconnect(user_id: str) -> None:
    ib = _sessions.get(user_id)
    if ib:
        try:
            ib.disconnect()
        except Exception:
            pass
        del _sessions[user_id]
        logger.info("IBKR disconnected for user %s", user_id)


def get_available_funds(user_id: str) -> float:
    """Fetch Net Liquidation Value from IB account summary.

    Returns total account value in USD.
    """
    ib = _get(user_id)
    try:
        summary = ib.accountSummary()
        for item in summary:
            if item.tag == "NetLiquidation" and item.currency == "USD":
                return float(item.value)
        # fallback: TotalCashValue
        for item in summary:
            if item.tag == "TotalCashValue" and item.currency == "USD":
                return float(item.value)
    except Exception as e:
        raise IbkrError(f"Failed to fetch account summary: {e}")
    return 0.0


def get_positions(user_id: str) -> list:
    ib = _get(user_id)
    try:
        positions = ib.positions()
    except Exception as e:
        raise IbkrError(f"Failed to fetch positions: {e}")

    out = []
    for pos in positions:
        contract = pos.contract
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(0.5)
        mkt_price = ticker.marketPrice() if ticker else None

        out.append({
            "broker": "interactive_brokers",
            "symbol": contract.symbol,
            "exchange_segment": contract.exchange or "SMART",
            "quantity": int(pos.position),
            "avg_price": float(pos.avgCost),
            "ltp": float(mkt_price) if mkt_price else None,
            "pnl": None,  # calculated below if possible
            "product": "STK",
            "currency": contract.currency or "USD",
        })
    return out


def place_order(
    user_id: str,
    symbol: str,
    transaction_type: str,
    quantity: int,
    order_type: str = "MKT",
    product: str = "STK",
    exchange_segment: str = "SMART",
    price: float = 0,
    trigger_price: float = 0,
) -> dict:
    """Place a US stock order via Interactive Brokers.

    Args:
        user_id: user identifier
        symbol: ticker symbol (e.g. AAPL, MSFT)
        transaction_type: "B" for buy, "S" for sell
        quantity: number of shares
        order_type: "MKT" or "LMT"
        product: ignored for US stocks (always STK)
        exchange_segment: "SMART" recommended for best routing
        price: limit price (required for LMT orders)
        trigger_price: not used for US stocks

    Returns:
        dict with ok, order_id, response
    """
    ib = _get(user_id)

    action = "BUY" if transaction_type.upper() in ("B", "BUY") else "SELL"
    exchange = exchange_segment or "SMART"

    contract = Stock(symbol, exchange, "USD")
    # Qualify contract to ensure valid
    try:
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            raise IbkrError(f"Could not qualify contract for {symbol}")
        contract = qualified[0]
    except Exception as e:
        if "No security definition" in str(e):
            raise IbkrError(f"Symbol '{symbol}' not found on {exchange}")
        raise IbkrError(f"Contract qualification failed: {e}")

    if order_type.upper() in ("MKT", "MARKET"):
        order = MarketOrder(action, int(quantity))
    elif order_type.upper() in ("LMT", "LIMIT", "L"):
        if price <= 0:
            raise IbkrError("Limit price required for LMT orders")
        order = LimitOrder(action, int(quantity), float(price))
    else:
        raise IbkrError(f"Unsupported order type: {order_type}")

    try:
        trade = ib.placeOrder(contract, order)
    except Exception as e:
        raise IbkrError(f"placeOrder failed: {e}")

    order_id = None
    status = "unknown"
    if trade and trade.order:
        order_id = str(trade.order.orderId)
        status = str(trade.orderStatus.status)

    return {
        "ok": True,
        "order_id": order_id,
        "status": status,
        "response": {
            "order_id": order_id,
            "status": status,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
        },
    }


def load_snp500(filepath: str) -> set:
    """Load S&P 500 symbols from a CSV file into a module-level set."""
    global _snp500_set, _snp500_loaded
    _snp500_set = set()
    try:
        import csv
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = (row.get("symbol") or "").strip().upper()
                if sym:
                    _snp500_set.add(sym)
        _snp500_loaded = True
        logger.info("Loaded %d S&P 500 symbols from %s", len(_snp500_set), filepath)
    except Exception as e:
        logger.warning("Failed to load S&P 500 list from %s: %s", filepath, e)
        _snp500_loaded = False
    return _snp500_set


def is_snp500(symbol: str) -> bool:
    """Check if a ticker is in the S&P 500."""
    return symbol.upper().strip() in _snp500_set


def get_category_pct(symbol: str) -> float:
    """Return allocation percentage for a US stock.

    S&P 500 stocks → 10% (0.10)
    Others → 5% (0.05)
    """
    return 0.10 if is_snp500(symbol) else 0.05
