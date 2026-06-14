import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "chartink_test")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DELTA_EXCHANGE_API_KEY", "test-key")
os.environ.setdefault("DELTA_EXCHANGE_API_SECRET", "test-secret")

TEST_USER_ID = "user_test"
TEST_SESSION_TOKEN = "sess_test"


class MockCursor:
    """Simulates a Motor async cursor for testing."""
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        return self._async_gen()

    async def _async_gen(self):
        for item in self._items:
            yield item

    def sort(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def skip(self, n):
        return self


@pytest.fixture(autouse=True)
def mock_db():
    """Mock all MongoDB collections used across the app."""
    with patch("server.db") as mock_database:
        for col in [
            "symbol_mappings", "alert_configs", "category_amounts",
            "trade_logs", "webhook_logs", "users", "user_sessions",
            "user_webhooks", "ibkr_credentials", "ema_sl_runs",
            "dhan_credentials", "delta_credentials", "dhan_auto_auth",
            "ema_schedules", "backtest_configs", "backtest_results",
        ]:
            setattr(mock_database, col, AsyncMock())

        mock_database.dhan_auto_auth.find_one = AsyncMock(return_value=None)
        mock_database.dhan_credentials.find_one = AsyncMock(return_value=None)
        mock_database.delta_credentials.find_one = AsyncMock(return_value=None)
        mock_database.ibkr_credentials.find_one = AsyncMock(return_value=None)
        mock_database.alert_configs.find_one = AsyncMock(return_value=None)
        mock_database.category_amounts.find_one = AsyncMock(return_value=None)

        yield mock_database


@pytest.fixture(autouse=True)
def mock_dhan():
    with patch("server.dhan_client") as mock_dc:
        mock_dc.is_authenticated = MagicMock(return_value=True)
        mock_dc.get_available_funds = MagicMock(return_value=50000.0)
        mock_dc.place_order = MagicMock(return_value={"order_id": "ORD123"})
        mock_dc.connect = MagicMock()
        mock_dc.disconnect = MagicMock()
        yield mock_dc


@pytest.fixture(autouse=True)
def mock_delta():
    with patch("server.delta_client") as mock_dc:
        mock_dc.is_authenticated = MagicMock(return_value=True)
        mock_dc.place_order = MagicMock(return_value={"order_id": "DELTA_ORD1"})
        mock_dc.connect = MagicMock()
        mock_dc.disconnect = MagicMock()
        yield mock_dc


@pytest.fixture(autouse=True)
def mock_ibkr():
    with patch("server.ibkr_client") as mock_ib:
        mock_ib.is_snp500 = MagicMock(return_value=True)
        mock_ib.get_category_pct = MagicMock(return_value=0.10)
        mock_ib.ib_connect = MagicMock(return_value=True)
        mock_ib.ib_disconnect = MagicMock()
        mock_ib.is_authenticated = MagicMock(return_value=True)
        mock_ib.is_connected = MagicMock(return_value=True)
        mock_ib.get_positions = MagicMock(return_value=[])
        mock_ib.get_available_funds = MagicMock(return_value=100000.0)
        mock_ib.place_order = MagicMock(return_value={
            "ok": True, "order_id": "IB_ORD_1001", "response": "Filled",
        })
        yield mock_ib


@pytest.fixture(autouse=True)
def mock_telegram():
    with patch("server.telegram_notifier") as mock_tg:
        mock_tg.send = MagicMock()
        yield mock_tg


@pytest.fixture(autouse=True)
def mock_env():
    old_token = os.environ.get("WEBHOOK_TOKEN")
    old_url = os.environ.get("REACT_APP_BACKEND_URL")
    if "WEBHOOK_TOKEN" in os.environ:
        del os.environ["WEBHOOK_TOKEN"]
    if "REACT_APP_BACKEND_URL" in os.environ:
        del os.environ["REACT_APP_BACKEND_URL"]
    yield
    if old_token:
        os.environ["WEBHOOK_TOKEN"] = old_token
    if old_url:
        os.environ["REACT_APP_BACKEND_URL"] = old_url


@pytest.fixture
def client():
    """FastAPI TestClient pointed at the live server.
    Uses mocked MongoDB and broker clients via autouse fixtures.
    """
    from server import app
    return TestClient(app)


@pytest.fixture
def auth_client(client, mock_db):
    """Pre‑authenticated test client with a session cookie."""
    from server import app
    mock_db.users.find_one = AsyncMock(return_value={
        "user_id": TEST_USER_ID,
        "name": "Test User",
        "email": "test@test.com",
        "created_at": "2024-01-01T00:00:00",
    })
    mock_db.user_sessions.find_one = AsyncMock(return_value={
        "user_id": TEST_USER_ID,
        "session_token": TEST_SESSION_TOKEN,
        "expires_at": "2099-01-01T00:00:00+00:00",
    })
    tc = TestClient(app)
    tc.cookies.set("session_token", TEST_SESSION_TOKEN)
    return tc


@pytest.fixture
def mock_webhook_config():
    """Standard enabled alert config."""
    return {
        "user_id": TEST_USER_ID,
        "alert_name": "TEST_ALERT",
        "enabled": True,
        "broker": "dhan",
        "transaction_type": "BUY",
        "quantity": 5,
        "product": "CNC",
        "exchange_segment": "nse_cm",
    }


@pytest.fixture
def mock_symbol_mapping():
    """Default symbol mapping with category=midcap, quantity=1."""
    return {
        "user_id": TEST_USER_ID,
        "chartink_symbol": "AAPL",
        "nse_symbol": "AAPL",
        "broker": "dhan",
        "quantity": 1,
        "category": "midcap",
        "transaction_type": "BUY",
        "product": "CNC",
    }
