"""End‑to‑end API integration tests with mocked DB and broker clients."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from tests.conftest import MockCursor, TEST_USER_ID, TEST_SESSION_TOKEN


@pytest.fixture
def authed_client(client, mock_db):
    """Client with session cookie set and auth mocks in place."""
    mock_db.users.find_one = AsyncMock(return_value={
        "user_id": TEST_USER_ID, "email": "test@test.com",
        "name": "Test", "created_at": "2024-01-01T00:00:00",
    })
    mock_db.user_sessions.find_one = AsyncMock(return_value={
        "user_id": TEST_USER_ID,
        "session_token": TEST_SESSION_TOKEN,
        "expires_at": "2099-01-01T00:00:00+00:00",
    })
    mock_db.dhan_credentials.find_one = AsyncMock(return_value={
        "user_id": TEST_USER_ID, "broker": "dhan",
    })
    mock_db.delta_credentials.find_one = AsyncMock(return_value={
        "user_id": TEST_USER_ID, "broker": "delta_exchange",
    })
    mock_db.ibkr_credentials.find_one = AsyncMock(return_value={
        "user_id": TEST_USER_ID, "broker": "interactive_brokers",
    })
    client.cookies.set("session_token", TEST_SESSION_TOKEN)
    return client


class TestBrokersStatus:
    def test_brokers_status_returns_all_three(self, authed_client):
        resp = authed_client.get("/api/brokers/status")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "dhan" in data
        assert "delta_exchange" in data
        assert "interactive_brokers" in data

    def test_brokers_status_401_without_auth(self, client, mock_db):
        mock_db.user_sessions.find_one = AsyncMock(return_value=None)
        resp = client.get("/api/brokers/status")
        assert resp.status_code == 401


class TestBrokersPositions:
    def test_positions_all_returns_empty(self, authed_client):
        resp = authed_client.get("/api/positions/all")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "positions" in data
        assert data["positions"] == []


class TestIbkrEndpoints:
    def test_ib_status_connected(self, authed_client, mock_ibkr):
        mock_ibkr.is_authenticated = MagicMock(return_value=True)
        mock_ibkr.get_available_funds = MagicMock(return_value=100000.0)
        resp = authed_client.get("/api/ib/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("is_authenticated") is True
        assert data.get("account_value") == 100000.0

    def test_ib_status_not_connected(self, authed_client, mock_ibkr):
        mock_ibkr.is_authenticated = MagicMock(return_value=False)
        mock_ibkr.get_available_funds = MagicMock(return_value=0.0)
        resp = authed_client.get("/api/ib/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("is_authenticated") is False


class TestSymbolMappings:
    def test_list_empty(self, authed_client, mock_db):
        mock_db.symbol_mappings.find = MagicMock(return_value=MockCursor([]))
        resp = authed_client.get("/api/symbol-mappings")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["mappings"] == []

    def test_list_with_mappings(self, authed_client, mock_db):
        mock_db.symbol_mappings.find = MagicMock(return_value=MockCursor([
            {"chartink_symbol": "AAPL", "nse_symbol": "AAPL",
             "broker": "dhan", "quantity": 1, "category": "midcap"},
        ]))
        resp = authed_client.get("/api/symbol-mappings")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["mappings"]) == 1
        assert data["mappings"][0]["chartink_symbol"] == "AAPL"


class TestUsSignals:
    def test_us_signal_skips_when_ib_not_authenticated(self, client, mock_db, mock_ibkr):
        mock_ibkr.is_authenticated = MagicMock(return_value=False)
        mock_db.users.find_one = AsyncMock(return_value={
            "user_id": TEST_USER_ID, "email": "test@test.com",
            "name": "Test", "created_at": "2024-01-01T00:00:00",
        })
        mock_db.user_sessions.find_one = AsyncMock(return_value={
            "user_id": TEST_USER_ID,
            "session_token": TEST_SESSION_TOKEN,
            "expires_at": "2099-01-01T00:00:00+00:00",
        })
        client.cookies.set("session_token", TEST_SESSION_TOKEN)
        resp = client.post("/api/signals/us", json={
            "action": "BUY",
            "symbol": "AAPL",
            "price": 150.0,
        })
        assert resp.status_code == 400
        assert "not connected" in resp.text.lower()

    def test_us_signal_with_category_pct(self, client, mock_db, mock_ibkr):
        mock_ibkr.is_authenticated = MagicMock(return_value=True)
        mock_ibkr.is_snp500 = MagicMock(return_value=True)
        mock_ibkr.get_category_pct = MagicMock(return_value=0.10)
        mock_ibkr.get_available_funds = MagicMock(return_value=100000.0)
        mock_ibkr.place_order = MagicMock(return_value={
            "ok": True, "order_id": "IB_ORD_1001", "response": "Filled",
        })
        mock_db.users.find_one = AsyncMock(return_value={
            "user_id": TEST_USER_ID, "email": "test@test.com",
            "name": "Test", "created_at": "2024-01-01T00:00:00",
        })
        mock_db.user_sessions.find_one = AsyncMock(return_value={
            "user_id": TEST_USER_ID,
            "session_token": TEST_SESSION_TOKEN,
            "expires_at": "2099-01-01T00:00:00+00:00",
        })
        mock_db.trade_logs.insert_one = AsyncMock()
        client.cookies.set("session_token", TEST_SESSION_TOKEN)
        resp = client.post("/api/signals/us", json={
            "action": "BUY",
            "symbol": "AAPL",
            "price": 150.0,
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "success"
        # 10% of 100000 = 10000 / 150 = 66
        assert data["quantity"] == 66
        assert data["symbol"] == "AAPL"


class TestWebhookUnknownToken:
    def test_unknown_token_returns_404(self, client, mock_db):
        mock_db.user_webhooks.find_one = AsyncMock(return_value=None)
        resp = client.post(
            "/api/webhooks/chartink/bad_token",
            json={"stocks": "AAPL"},
        )
        assert resp.status_code == 404
