"""Lightweight market-regime and risk-posture analysis."""

from math import sqrt
from typing import Any, Dict, List, Sequence

import numpy as np
from config import get as cfg_get
from data_engine import get_kline, get_market_index, get_stock_pool
from data_readiness import ensure_market_index_ready, ensure_symbol_ready


def analyze_market_regime(market: str = "A") -> Dict[str, Any]:
    """Analyze the current market posture for a supported market."""
    benchmark_code = str(
        cfg_get(
            f"market_regime.benchmarks.{market}", cfg_get("market_index_default_code")
        )
    )
    history_days = int(cfg_get("market_regime.history_days", 250) or 250)

    benchmark_rows = _load_benchmark_rows(market, benchmark_code, history_days)
    closes = _extract_closes(benchmark_rows)
    if len(closes) < 120:
        return {
            "market": market,
            "benchmark_code": benchmark_code,
            "status": "insufficient_data",
            "score": 50.0,
            "posture": "neutral",
            "posture_label": "中性",
            "risk_budget": _risk_budget_for("neutral"),
            "new_positions_allowed": True,
            "reasons": ["benchmark_history_insufficient"],
            "breadth": {},
            "technical": {},
            "confidence": {
                "score": 0.45,
                "level": "low",
                "notes": ["市场基准历史不足，姿态判断按中性退化处理"],
            },
            "provenance": {
                "scope": "market_regime",
                "market": market,
                "freshness": "partial",
                "covered_through": "",
                "source": benchmark_code,
                "source_status": "benchmark_history_insufficient",
                "metadata_completeness": 0.5,
                "inputs": ["benchmark_history"],
            },
        }

    current = closes[-1]
    ma20 = _moving_average(closes, 20)
    ma60 = _moving_average(closes, 60)
    ma120 = _moving_average(closes, 120)
    ret20 = _window_return(closes, 20)
    drawdown60 = _drawdown(closes[-60:])
    vol20 = _annualized_volatility(closes[-21:])

    breadth = _compute_breadth(market)
    breadth20 = float(breadth.get("above_ma20_ratio", 0.5) or 0.5)
    breadth60 = float(breadth.get("above_ma60_ratio", 0.5) or 0.5)

    trend_score = (
        25.0 * float(current > ma20)
        + 25.0 * float(current > ma60)
        + 25.0 * float(ma20 > ma60)
        + 25.0 * float(ma60 > ma120)
    )
    breadth_score = max(0.0, min(100.0, (breadth20 * 0.6 + breadth60 * 0.4) * 100.0))
    momentum_score = max(0.0, min(100.0, ((ret20 + 0.10) / 0.20) * 100.0))
    penalty = _risk_penalty(vol20, drawdown60)

    score = max(
        0.0,
        min(
            100.0,
            trend_score * 0.40 + breadth_score * 0.35 + momentum_score * 0.25 - penalty,
        ),
    )
    posture = _classify_posture(score)

    reasons = _build_reasons(
        current=current,
        ma20=ma20,
        ma60=ma60,
        ma120=ma120,
        ret20=ret20,
        breadth20=breadth20,
        breadth60=breadth60,
        drawdown60=drawdown60,
        vol20=vol20,
    )

    confidence_score = _regime_confidence_score(breadth, len(closes))
    return {
        "market": market,
        "benchmark_code": benchmark_code,
        "status": "ok",
        "score": round(score, 1),
        "posture": posture,
        "posture_label": _posture_label(posture),
        "risk_budget": _risk_budget_for(posture),
        "new_positions_allowed": _risk_budget_for(posture) >= 0.65,
        "reasons": reasons,
        "breadth": {
            **breadth,
            "above_ma20_ratio": round(breadth20, 3),
            "above_ma60_ratio": round(breadth60, 3),
        },
        "technical": {
            "current": round(current, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "ma120": round(ma120, 2),
            "ret20": round(ret20, 4),
            "drawdown60": round(drawdown60, 4),
            "volatility20": round(vol20, 4),
        },
        "confidence": {
            "score": round(confidence_score, 3),
            "level": _confidence_level(confidence_score),
            "notes": _regime_confidence_notes(breadth, len(closes), vol20, drawdown60),
        },
        "provenance": {
            "scope": "market_regime",
            "market": market,
            "freshness": "fresh",
            "covered_through": "",
            "source": benchmark_code,
            "source_status": breadth.get("status", "ok"),
            "metadata_completeness": round(
                min(1.0, len(closes) / max(history_days, 1)),
                3,
            ),
            "inputs": [
                "benchmark_history",
                "breadth_sample",
                "moving_averages",
            ],
        },
    }


def summarize_market_regime(regime: Dict[str, Any]) -> str:
    """Return a concise one-line regime summary."""
    if regime.get("status") != "ok":
        return (
            f"市场状态: {regime.get('posture_label', '中性')} | "
            f"score={float(regime.get('score', 50) or 50):.1f} | "
            "数据不足，按中性仓位处理"
        )
    return (
        f"市场状态: {regime.get('posture_label', '中性')} | "
        f"score={float(regime.get('score', 50) or 50):.1f}/100 | "
        f"risk_budget={float(regime.get('risk_budget', 1.0) or 1.0):.2f}"
    )


def _load_benchmark_rows(
    market: str, benchmark_code: str, history_days: int
) -> List[Dict[str, Any]]:
    """Load benchmark rows for market posture analysis."""
    if market == "A":
        ensure_market_index_ready(benchmark_code, history_days=history_days)
        return get_market_index(benchmark_code, history_days)
    ensure_symbol_ready(
        benchmark_code,
        market,
        history_days=history_days,
        need_fundamentals=False,
    )
    return get_kline(benchmark_code, market, days=history_days)


def _extract_closes(rows: Sequence[Dict[str, Any]]) -> List[float]:
    """Return close prices in ascending-date order."""
    ordered = list(reversed(rows))
    closes = [float(row.get("close", 0) or 0) for row in ordered]
    return [close for close in closes if close > 0]


def _moving_average(closes: Sequence[float], window: int) -> float:
    """Return the trailing moving average."""
    if len(closes) < window:
        return float(closes[-1]) if closes else 0.0
    return float(np.mean(closes[-window:]))


def _window_return(closes: Sequence[float], window: int) -> float:
    """Return the percentage return over the provided trailing window."""
    if len(closes) <= window:
        return 0.0
    start = float(closes[-window] or 0)
    end = float(closes[-1] or 0)
    if start <= 0:
        return 0.0
    return end / start - 1.0


def _drawdown(closes: Sequence[float]) -> float:
    """Return trailing drawdown versus the period high."""
    if not closes:
        return 0.0
    peak = max(float(close or 0) for close in closes)
    current = float(closes[-1] or 0)
    if peak <= 0:
        return 0.0
    return current / peak - 1.0


def _annualized_volatility(closes: Sequence[float]) -> float:
    """Estimate annualized volatility from a trailing close window."""
    if len(closes) < 2:
        return 0.0
    returns = np.diff(np.array(closes)) / np.array(closes[:-1])
    if len(returns) == 0:
        return 0.0
    return float(np.std(returns) * sqrt(252))


def _risk_penalty(vol20: float, drawdown60: float) -> float:
    """Return a bounded downside penalty for the regime score."""
    volatility_penalty = max(0.0, min(15.0, ((vol20 - 0.18) / 0.22) * 15.0))
    drawdown_penalty = max(
        0.0,
        min(15.0, ((abs(min(drawdown60, 0.0)) - 0.05) / 0.15) * 15.0),
    )
    return volatility_penalty + drawdown_penalty


def _compute_breadth(market: str) -> Dict[str, Any]:
    """Estimate breadth from a bounded sample of the market pool."""
    pool = get_stock_pool(market)
    sample_limit = int(cfg_get("market_regime.breadth_sample_limit", 60) or 60)
    min_sample = int(cfg_get("market_regime.min_breadth_sample", 15) or 15)
    history_days = int(cfg_get("market_regime.breadth_history_days", 80) or 80)

    eligible = [
        row
        for row in pool
        if str(row.get("code", "")).strip() and bool(row.get("is_active", 1))
    ]
    selected = eligible[:sample_limit]

    def _check_one(row: Dict[str, Any]):
        """Check if a stock is above MA20/MA60."""
        code = str(row["code"])
        rows = get_kline(code, market, days=history_days, cached_only=True)
        closes = _extract_closes(rows)
        if len(closes) < 60:
            return None
        current = closes[-1]
        return (
            1 if current > _moving_average(closes, 20) else 0,
            1 if current > _moving_average(closes, 60) else 0,
        )

    from concurrent.futures import ThreadPoolExecutor, as_completed

    above_ma20 = 0
    above_ma60 = 0
    sample_size = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_check_one, row): row for row in selected}
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            sample_size += 1
            a20, a60 = result
            above_ma20 += a20
            above_ma60 += a60

    if sample_size < min_sample:
        return {
            "sample_size": sample_size,
            "sample_limit": sample_limit,
            "status": "insufficient_sample",
            "above_ma20_ratio": 0.5,
            "above_ma60_ratio": 0.5,
        }

    return {
        "sample_size": sample_size,
        "sample_limit": sample_limit,
        "status": "ok",
        "above_ma20_ratio": above_ma20 / sample_size,
        "above_ma60_ratio": above_ma60 / sample_size,
    }


def _classify_posture(score: float) -> str:
    """Map a numeric score to a posture bucket."""
    if score >= 75:
        return "offensive"
    if score >= 60:
        return "constructive"
    if score >= 45:
        return "neutral"
    if score >= 30:
        return "cautious"
    return "defensive"


def _risk_budget_for(posture: str) -> float:
    """Return the configured risk budget for a posture bucket."""
    return float(cfg_get(f"market_regime.risk_budgets.{posture}", 1.0) or 1.0)


def _posture_label(posture: str) -> str:
    """Return a compact Chinese label for a posture bucket."""
    labels = {
        "offensive": "积极",
        "constructive": "偏积极",
        "neutral": "中性",
        "cautious": "谨慎",
        "defensive": "防御",
    }
    return labels.get(posture, "中性")


def _regime_confidence_score(breadth: Dict[str, Any], history_bars: int) -> float:
    """Return a bounded confidence score for regime analysis."""
    score = 0.55
    if history_bars >= 180:
        score += 0.2
    if breadth.get("status") == "ok":
        score += 0.15
    if (
        int(breadth.get("sample_size", 0) or 0)
        >= int(breadth.get("sample_limit", 0) or 0) * 0.6
    ):
        score += 0.1
    return max(0.0, min(1.0, score))


def _regime_confidence_notes(
    breadth: Dict[str, Any],
    history_bars: int,
    vol20: float,
    drawdown60: float,
) -> List[str]:
    """Return concise confidence notes for regime analysis."""
    notes = []
    if history_bars >= 180:
        notes.append("市场基准历史覆盖较充分")
    else:
        notes.append("市场基准历史覆盖一般")
    if breadth.get("status") == "ok":
        notes.append("breadth 样本满足最小要求")
    else:
        notes.append("breadth 样本不足，横截面判断偏弱")
    if vol20 <= 0.25 and drawdown60 >= -0.15:
        notes.append("波动与回撤未显著削弱姿态判断")
    else:
        notes.append("波动或回撤较大，姿态判断需要保守解释")
    return notes


def _confidence_level(score: float) -> str:
    """Map a confidence score to a compact level."""
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _build_reasons(
    *,
    current: float,
    ma20: float,
    ma60: float,
    ma120: float,
    ret20: float,
    breadth20: float,
    breadth60: float,
    drawdown60: float,
    vol20: float,
) -> List[str]:
    """Build human-readable reason strings for the final posture."""
    reasons: List[str] = []
    if current > ma20 > ma60:
        reasons.append("指数位于短中期均线上方")
    elif current < ma20 and ma20 < ma60:
        reasons.append("指数跌破短中期均线")

    if breadth20 >= 0.60:
        reasons.append("样本 breadth 较强")
    elif breadth20 <= 0.40:
        reasons.append("样本 breadth 偏弱")

    if ret20 >= 0.05:
        reasons.append("近 20 日趋势向上")
    elif ret20 <= -0.05:
        reasons.append("近 20 日趋势承压")

    if drawdown60 <= -0.10:
        reasons.append("相对 60 日高点回撤较深")

    if vol20 >= 0.28:
        reasons.append("短期波动偏高")

    if breadth60 >= 0.60 and "样本 breadth 较强" not in reasons:
        reasons.append("中期 breadth 维持扩散")
    elif breadth60 <= 0.40 and "样本 breadth 偏弱" not in reasons:
        reasons.append("中期 breadth 收缩")

    return reasons or ["市场信号中性，建议控制节奏"]
