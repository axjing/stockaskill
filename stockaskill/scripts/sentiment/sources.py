"""Sentiment data sources: East Money guba, market breadth, north flow."""

# Import the global AKShare lock to prevent Chromium allocator crashes
# when multiple threads initialize AKShare simultaneously
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from cache import get_cache

_de = str(Path(__file__).resolve().parent.parent)
if _de not in sys.path:
    sys.path.insert(0, _de)
from data_engine import _akshare_lock  # noqa: E402

from sentiment.dictionary import analyze_sentiment  # noqa: E402
from utils import normalize_code  # noqa: E402

_cache = get_cache()


@contextmanager
def _suppress_output():
    """Temporarily suppress stdout/stderr to prevent library error leaks."""
    devnull = open(os.devnull, 'w')
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = devnull, devnull
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        devnull.close()

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

        with _akshare_lock:
            with _suppress_output():
                df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            total = len(df)
            advancers = len(df[df.get("涨跌幅", 0) > 0])
            decliners = len(df[df.get("涨跌幅", 0) < 0])
            flat = total - advancers - decliners
            ratio = advancers / max(total, 1)

            result = {
                "advancers": advancers,
                "decliners": decliners,
                "flat": flat,
                "ratio": round(ratio, 3),
                "sentiment_score": round(ratio, 3),
                "date": datetime.now().strftime("%Y-%m-%d"),
            }
            _cache.kv_set("market_breadth", result, ttl=3600)
            return result
    except Exception:
        pass

    return {
        "advancers": 0,
        "decliners": 0,
        "ratio": 0.5,
        "sentiment_score": 0.5,
        "date": datetime.now().strftime("%Y-%m-%d"),
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

        _start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        _end = datetime.now().strftime("%Y%m%d")
        with _akshare_lock:
            with _suppress_output():
                df = ak.stock_hsgt_hist_em(symbol="沪股通")
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                records.append(
                    {
                        "date": str(row.get("日期", "")),
                        "net_flow": float(row.get("当日成交净买入额", 0) or 0),
                    }
                )
    except Exception:
        pass

    _cache.kv_set("north_flow", records[:days], ttl=3600)
    return records[:days]


def get_guba_sentiment(code: str) -> Dict[str, Any]:
    """Get East Money guba sentiment for a stock.

    Fetches recent posts from East Money guba and analyzes sentiment
    using the financial sentiment dictionary.

    Args:
        code: Stock code (6-digit A-share code).

    Returns:
        Dict with post_count, hot_score, sentiment_score in [-1, 1].
    """
    # Guba sentiment is A-share only — skip for HK/US/FUND
    digits = normalize_code(code)
    if len(digits) != 6 or not digits.startswith(("0", "3", "6", "9")):
        return {"post_count": 0, "hot_score": 0.5, "sentiment_score": 0.5}

    try:
        import akshare as ak
        from utils import exchange_suffix

        prefix = exchange_suffix(code)
        # Fetch guba posts for the stock
        with _akshare_lock:
            with _suppress_output():
                df = ak.stock_comment_em(symbol=prefix + code)

        if df is not None and not df.empty:
            posts = df.head(20)  # Analyze latest 20 posts
            titles = posts.get("content", posts.iloc[:, -1]).tolist()

            # Analyze sentiment using dictionary
            scores = [analyze_sentiment(str(t)) for t in titles if t]
            if scores:
                avg_score = sum(scores) / len(scores)
                return {
                    "post_count": len(posts),
                    "hot_score": min(1, len(posts) / 20),
                    "sentiment_score": round(avg_score, 3),
                }

    except Exception:
        pass

    # Fallback: use price momentum as sentiment proxy
    from data_engine import get_kline

    kline = get_kline(code, "A", days=10)
    if not kline:
        return {"post_count": 0, "hot_score": 0.5, "sentiment_score": 0.5}

    closes = [r.get("close", 0) for r in kline]
    closes = [c for c in closes if c > 0]

    if len(closes) < 2:
        return {"post_count": 0, "hot_score": 0.5, "sentiment_score": 0.5}

    ret = (closes[0] - closes[-1]) / max(closes[-1], 1e-9)
    sentiment = max(-1, min(1, ret * 5))

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
