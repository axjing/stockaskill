"""Sentiment data sources: East Money guba, market breadth, north flow."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from cache import get_cache
from sentiment.dictionary import analyze_sentiment

_cache = get_cache()


def get_market_breadth() -> Dict[str, Any]:
    """Get market breadth (advance/decline ratio).

    Returns:
        Dict with advancers, decliners, ratio, sentiment_score.
    """
    # Try to get from cache first
    cached = _cache.kv_get("market_breadth")
    if cached:
        return cached

    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            advancers = len(df[df.get("涨跌幅", 0) > 0])
            decliners = len(df[df.get("涨跌幅", 0) < 0])
            total = advancers + decliners
            ratio = advancers / max(total, 1)

            result = {
                "advancers": advancers,
                "decliners": decliners,
                "flat": total - advancers - decliners,
                "ratio": round(ratio, 3),
                "sentiment_score": round(ratio, 3),
                "date": datetime.now().strftime("%Y-%m-%d"),
            }
            _cache.kv_set("market_breadth", result, ttl=3600)
            return result
    except Exception:
        pass

    return {
        "advancers": 0, "decliners": 0, "ratio": 0.5,
        "sentiment_score": 0.5, "date": datetime.now().strftime("%Y-%m-%d"),
    }


def get_north_flow(days: int = 20) -> List[Dict[str, Any]]:
    """Get northbound fund flow trend.

    Args:
        days: Number of days to look back.

    Returns:
        List of daily flow records.
    """
    cached = _cache.kv_get("north_flow")
    if cached:
        return cached

    records = []
    try:
        import akshare as ak
        start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        end = datetime.now().strftime("%Y%m%d")
        df = ak.stock_hsgt_hist_em(symbol="沪股通")
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                records.append({
                    "date": str(row.get("日期", "")),
                    "net_flow": float(row.get("当日成交净买入额", 0) or 0),
                })
    except Exception:
        pass

    _cache.kv_set("north_flow", records[:days], ttl=3600)
    return records[:days]


def get_guba_sentiment(code: str) -> Dict[str, Any]:
    """Get East Money guba sentiment for a stock.

    Args:
        code: Stock code.

    Returns:
        Dict with post_count, hot_score, sentiment_score.
    """
    # Simulated sentiment based on price action
    from data_engine import get_kline

    kline = get_kline(code, "A", days=10)
    if not kline:
        return {"post_count": 0, "hot_score": 0.5, "sentiment_score": 0.5}

    closes = [r.get("close", 0) for r in kline]
    closes = [c for c in closes if c > 0]

    if len(closes) < 2:
        return {"post_count": 0, "hot_score": 0.5, "sentiment_score": 0.5}

    # Price momentum as proxy for attention
    ret = (closes[0] - closes[-1]) / max(closes[-1], 1e-9)
    sentiment = max(-1, min(1, ret * 5))  # Scale: 20% move = 1.0

    return {
        "post_count": len(kline),
        "hot_score": min(1, abs(ret) * 3),
        "sentiment_score": round(sentiment, 3),
    }


def aggregate_market_sentiment() -> float:
    """Aggregate overall market sentiment.

    Returns:
        Score in [0, 1].
    """
    breadth = get_market_breadth()
    north = get_north_flow(20)

    # Market breadth component (40%)
    breadth_score = breadth.get("sentiment_score", 0.5)

    # North flow component (30%)
    if north:
        recent = [r.get("net_flow", 0) for r in north[:5]]
        avg_flow = sum(recent) / max(len(recent), 1)
        north_score = max(0, min(1, (avg_flow + 5e10) / 1e11))
    else:
        north_score = 0.5

    # Combined
    return round(breadth_score * 0.4 + north_score * 0.3 + 0.3, 3)
