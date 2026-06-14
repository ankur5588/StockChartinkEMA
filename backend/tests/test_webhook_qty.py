"""Tests for webhook quantity calculation priority."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import MockCursor, TEST_USER_ID


def _call_webhook(client, token="test_token", overrides=None):
    payload = {
        "stocks": "AAPL",
        "trigger_prices": "150.00",
        "alert_name": "TEST_ALERT",
        ** (overrides or {}),
    }
    return client.post(f"/api/webhooks/chartink/{token}", json=payload)


class TestQtyPriorityChain:
    """Verify that category % of available funds takes priority over fixed mapping quantity."""

    def _setup_mocks(self, mock_db, webhook_config, symbol_mapping):
        mock_db.user_webhooks.find_one = AsyncMock(
            return_value={"user_id": TEST_USER_ID}
        )
        mock_db.alert_configs.find_one = AsyncMock(return_value=webhook_config)
        mock_db.symbol_mappings.find = MagicMock(
            return_value=MockCursor(symbol_mapping)
        )
        mock_db.trade_logs.insert_one = AsyncMock()
        mock_db.webhook_logs.insert_one = AsyncMock()
        mock_db.users.find_one = AsyncMock(
            return_value={"user_id": TEST_USER_ID, "name": "Test"}
        )

    def test_category_pct_overrides_fixed_qty(self, client, mock_db,
                                              mock_webhook_config, mock_symbol_mapping):
        mock_db.category_amounts.find_one = AsyncMock(
            return_value={"percentage": 0.10}
        )
        self._setup_mocks(mock_db, mock_webhook_config, [mock_symbol_mapping])

        resp = _call_webhook(client)
        data = resp.json()
        assert data["ok"] is True
        note = data["notes"][0]
        assert "qty=33" in note, (
            f"Expected qty=33 (10% of 50000 / 150), got: {note}"
        )

    def test_fallback_to_fixed_qty_when_no_category(
        self, client, mock_db, mock_webhook_config, mock_symbol_mapping
    ):
        mapping_no_cat = {**mock_symbol_mapping, "category": None}
        self._setup_mocks(mock_db, mock_webhook_config, [mapping_no_cat])

        resp = _call_webhook(client)
        data = resp.json()
        note = data["notes"][0]
        assert "qty=1" in note, f"Expected fallback to qty=1, got: {note}"

    def test_fallback_to_fixed_qty_when_no_funds(
        self, client, mock_db, mock_webhook_config, mock_symbol_mapping
    ):
        import server
        server.dhan_client.get_available_funds = MagicMock(return_value=0.0)
        mock_db.category_amounts.find_one = AsyncMock(
            return_value={"percentage": 0.10}
        )
        self._setup_mocks(mock_db, mock_webhook_config, [mock_symbol_mapping])

        resp = _call_webhook(client)
        data = resp.json()
        note = data["notes"][0]
        assert "qty=1" in note, f"Expected fallback to qty=1 when funds=0, got: {note}"

    def test_fallback_when_category_unset_in_db(
        self, client, mock_db, mock_webhook_config, mock_symbol_mapping
    ):
        mock_db.category_amounts.find_one = AsyncMock(return_value=None)
        self._setup_mocks(mock_db, mock_webhook_config, [mock_symbol_mapping])

        resp = _call_webhook(client)
        data = resp.json()
        note = data["notes"][0]
        assert "qty=1" in note, (
            f"Expected fallback to qty=1 when category% doc absent, got: {note}"
        )

    def test_no_mapping_uses_alert_config_quantity(
        self, client, mock_db, mock_webhook_config
    ):
        self._setup_mocks(mock_db, mock_webhook_config, [])

        resp = _call_webhook(client)
        data = resp.json()
        note = data["notes"][0]
        assert "qty=5" in note, (
            f"Expected fallback to config qty=5, got: {note}"
        )

    def test_price_zero_skips_category_calc(
        self, client, mock_db, mock_webhook_config, mock_symbol_mapping
    ):
        self._setup_mocks(mock_db, mock_webhook_config, [mock_symbol_mapping])

        resp = _call_webhook(client, overrides={"trigger_prices": "0"})
        data = resp.json()
        note = data["notes"][0]
        assert "qty=1" in note, f"Expected qty=1 when price=0, got: {note}"

    def test_amount_based_qty_when_no_quantity_in_mapping(
        self, client, mock_db, mock_webhook_config
    ):
        mapping_with_amount = {
            "user_id": TEST_USER_ID,
            "chartink_symbol": "AAPL",
            "nse_symbol": "AAPL",
            "broker": "dhan",
            "amount": 20000,
            "transaction_type": "BUY",
            "product": "CNC",
        }
        self._setup_mocks(mock_db, mock_webhook_config, [mapping_with_amount])

        resp = _call_webhook(client, overrides={"trigger_prices": "150.00"})
        data = resp.json()
        note = data["notes"][0]
        assert "qty=133" in note, (
            f"Expected qty=133 from amount 20000//150, got: {note}"
        )

    def test_multiple_stocks_all_get_correct_qty(
        self, client, mock_db, mock_webhook_config
    ):
        self._setup_mocks(mock_db, mock_webhook_config, [])

        resp = _call_webhook(client, overrides={
            "stocks": "AAPL,GOOGL,MSFT",
            "trigger_prices": "150.00,200.00,300.00",
        })
        data = resp.json()
        notes = data["notes"]
        assert len(notes) == 3
        for note in notes:
            assert "qty=" in note

    def test_mapping_with_category_but_no_price_uses_fixed_qty(
        self, client, mock_db, mock_webhook_config, mock_symbol_mapping
    ):
        self._setup_mocks(mock_db, mock_webhook_config, [mock_symbol_mapping])

        resp = _call_webhook(client, overrides={"trigger_prices": ""})
        data = resp.json()
        note = data["notes"][0]
        assert "qty=1" in note, f"Expected qty=1 when no price, got: {note}"

    def test_different_category_pcts_produce_correct_qty(
        self, client, mock_db, mock_webhook_config, mock_symbol_mapping
    ):
        for pct, expected_qty in [(0.05, 16), (0.08, 26), (0.10, 33)]:
            mock_db.category_amounts.find_one = AsyncMock(
                return_value={"percentage": pct}
            )
            import server
            server.dhan_client.get_available_funds = MagicMock(return_value=50000.0)
            self._setup_mocks(mock_db, mock_webhook_config, [mock_symbol_mapping])

            resp = _call_webhook(client)
            data = resp.json()
            note = data["notes"][0]
            assert f"qty={expected_qty}" in note, (
                f"For {pct*100:.0f}% of 50000 at 150, expected qty={expected_qty}, "
                f"got: {note}"
            )
