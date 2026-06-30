import pytest
from config import _deep_merge, get, load_config


class TestConfig:
    def test_load_config_returns_dict(self):
        cfg = load_config()
        assert isinstance(cfg, dict)

    def test_factor_weights_present(self):
        weights = get("factor_weights")
        assert isinstance(weights, dict)
        assert len(weights) > 0

    def test_factor_weights_sum_to_one(self):
        weights = get("factor_weights", {})
        total = sum(weights.values())
        assert total == pytest.approx(0.99)

    def test_cache_ttl_present(self):
        ttl = get("cache_ttl")
        assert isinstance(ttl, dict)
        assert "realtime" in ttl
        assert "daily_kline" in ttl
        assert "pool" in ttl

    def test_watchlist_has_stocks(self):
        wl = get("watchlist", [])
        assert len(wl) > 0
        assert all(isinstance(c, str) for c in wl)

    def test_dot_path_access(self):
        val = get("factor_weights.value")
        assert val == 0.2

    def test_dot_path_access_nested(self):
        val = get("cache_ttl.daily_kline")
        assert val == 3600

    def test_dot_path_default(self):
        val = get("nonexistent.key", "fallback")
        assert val == "fallback"

    def test_get_daily_api_limit(self):
        limit = get("daily_api_limit")
        assert limit == 500

    def test_get_retry_max(self):
        assert get("retry_max") == 3

    def test_deep_merge_replaces_scalar(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = _deep_merge(base, override)
        assert result["a"] == 1
        assert result["b"] == 3

    def test_deep_merge_nested(self):
        base = {"outer": {"inner": 1, "other": 2}}
        override = {"outer": {"inner": 99}}
        result = _deep_merge(base, override)
        assert result["outer"]["inner"] == 99
        assert result["outer"]["other"] == 2

    def test_deep_merge_adds_new_key(self):
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        assert "b" in result
        assert result["b"] == 2

    def test_config_singleton(self):
        c1 = load_config()
        c2 = load_config()
        assert c1 is c2
