"""Tests for data_engine.sync_update dynamic incremental synchronization."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from data_engine.sync_update import (
    compute_incremental_fetch_window,
    get_market_watermark,
    get_symbol_watermark,
    update_symbol_incremental,
    update_symbols_batch,
    validate_ohlc_record,
)


class TestValidateOHLCRecord:
    """Tests for validate_ohlc_record data validation logic."""

    def test_valid_record(self):
        row = {
            "date": "2026-05-10",
            "open": 10.0,
            "high": 12.0,
            "low": 9.5,
            "close": 11.0,
            "volume": 100000,
        }
        assert validate_ohlc_record(row) is True

    def test_reject_negative_price(self):
        row = {
            "date": "2026-05-10",
            "open": -10.0,
            "high": 12.0,
            "low": 9.5,
            "close": 11.0,
        }
        assert validate_ohlc_record(row) is False

    def test_reject_zero_close(self):
        row = {
            "date": "2026-05-10",
            "open": 10.0,
            "high": 12.0,
            "low": 9.5,
            "close": 0.0,
        }
        assert validate_ohlc_record(row) is False

    def test_reject_inverted_high_low(self):
        row = {
            "date": "2026-05-10",
            "open": 10.0,
            "high": 8.0,
            "low": 12.0,
            "close": 9.0,
        }
        assert validate_ohlc_record(row) is False

    def test_reject_close_exceeding_high(self):
        row = {
            "date": "2026-05-10",
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 12.0,
        }
        assert validate_ohlc_record(row) is False

    def test_reject_future_date(self):
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        row = {
            "date": future_date,
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
        }
        assert validate_ohlc_record(row) is False


class TestComputeIncrementalFetchWindow:
    """Tests for compute_incremental_fetch_window range detection."""

    def test_cold_start_window(self):
        start, end = compute_incremental_fetch_window(None, market="A")
        assert start is not None
        assert end is not None
        assert start.startswith("2000-01-01")

    def test_already_fresh_skips_fetch(self):
        latest = "2026-12-31"
        start, end = compute_incremental_fetch_window(latest, market="A")
        assert start is None
        assert end is not None

    def test_stale_data_with_padding(self):
        last_date = "2026-06-15"
        start, end = compute_incremental_fetch_window(
            last_date, market="A", padding_days=3
        )
        assert start == "2026-06-12"
        assert end is not None


class TestWatermarks:
    """Tests for watermark reader functions."""

    @patch("data_engine.sync_update.get_cache")
    def test_symbol_watermark(self, mock_get_cache):
        mock_cache = MagicMock()
        mock_cache.get_latest_date.return_value = "2026-07-17"
        mock_get_cache.return_value = mock_cache

        watermark = get_symbol_watermark("600519", "A")
        assert watermark == "2026-07-17"
        mock_cache.get_latest_date.assert_called_with("600519", market="A")

    @patch("data_engine.sync_update.get_cache")
    def test_market_watermark(self, mock_get_cache):
        mock_cache = MagicMock()
        mock_cache.get_latest_daily_price_date.return_value = "2026-07-17"
        mock_get_cache.return_value = mock_cache

        watermark = get_market_watermark("A")
        assert watermark == "2026-07-17"
        mock_cache.get_latest_daily_price_date.assert_called_with(market="A")


class TestUpdateSymbolIncremental:
    """Tests for update_symbol_incremental flow."""

    @patch("data_engine.sync_update.get_symbol_watermark")
    @patch("data_engine.sync_update.compute_incremental_fetch_window")
    def test_up_to_date_short_circuit(self, mock_window, mock_watermark):
        mock_watermark.return_value = "2026-10-30"
        mock_window.return_value = (None, "2026-10-30")

        res = update_symbol_incremental("600519", "A")
        assert res["status"] == "up_to_date"
        assert res["fetched_rows"] == 0

    @patch("data_engine.sync_update.get_symbol_watermark")
    @patch("data_engine.sync_update.compute_incremental_fetch_window")
    @patch("data_engine.kline._fetch_kline")
    @patch("data_engine.sync_update.get_cache")
    def test_fetches_and_filters_bad_records(
        self, mock_get_cache, mock_fetch, mock_window, mock_watermark
    ):
        mock_watermark.side_effect = ["2026-07-15", "2026-07-18"]
        mock_window.return_value = ("2026-07-12", "2026-07-18")
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        mock_fetch.return_value = [
            {
                "date": "2026-07-16",
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 102.0,
            },
            {
                "date": "2026-07-17",
                "open": -10.0,
                "high": 10.0,
                "low": 5.0,
                "close": 8.0,
            },  # Bad!
        ]

        res = update_symbol_incremental("600519", "A", trigger_snapshot=False)
        assert res["status"] == "updated"
        assert res["fetched_rows"] == 2
        assert res["validated_rows"] == 1
        assert res["rejected_rows"] == 1
        mock_cache.upsert_daily_price.assert_called_once()


class TestUpdateSymbolsBatch:
    """Tests for batch updating multiple symbols."""

    @patch("data_engine.sync_update.update_symbol_incremental")
    def test_batch_execution(self, mock_update):
        mock_update.side_effect = [
            {"status": "updated", "validated_rows": 5, "rejected_rows": 0},
            {"status": "up_to_date", "validated_rows": 0, "rejected_rows": 0},
        ]

        res = update_symbols_batch(
            ["600519", "000858"], market="A", trigger_snapshot=False
        )
        assert res["total_symbols"] == 2
        assert res["updated_symbols"] == 1
        assert res["already_up_to_date"] == 1
        assert res["total_ingested_rows"] == 5
