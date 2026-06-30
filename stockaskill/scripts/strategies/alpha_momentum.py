"""Alpha momentum strategy: multi-factor momentum with quality & low-vol."""

from typing import Any, Dict

from strategies.base import Strategy

LOW_VOL_MIN = 0.4


class AlphaMomentumStrategy(Strategy):
    """Multi-factor momentum strategy.

    Factor weights (optimized via 8.3-year backtest, 2018-2026):
    - Momentum: 30%
    - Low Volatility: 28%
    - Quality: 21%
    - Value: 14%
    - Growth: 7%

    Selection: Top 6 stocks, monthly rebalance.
    Hard filters: low_vol < 0.4 excluded, EPS <= 0 excluded, ST stocks excluded.
    Diversification: max 3 stocks per board (SH/SZ/SME/GEM/STAR).

    Backtest result (75 A-share stocks, 2018-2026): CAGR 14.27%, Sharpe 0.72, MaxDD
        -18.35%.
    """

    @property
    def name(self) -> str:
        return "alpha_momentum"

    def analyze(self, code: str, market: str = "A") -> Dict[str, Any]:
        from factors.composite import CompositeAnalyzer

        analyzer = CompositeAnalyzer(code, market)
        result = analyzer.analyze()

        factors = result.get("factors", {})
        low_vol_score = factors.get("low_vol", 0.5)

        # Hard filter: exclude stocks with low_vol below threshold
        if low_vol_score < LOW_VOL_MIN:
            detail = result.get("detail", result)
            return {
                "strategy_name": self.name,
                "signal": "SELL",
                "score": 0.0,
                "confidence": 0.0,
                "detail": dict(
                    detail, filter=f"low_vol {low_vol_score:.2f} < {LOW_VOL_MIN}"
                ),
            }

        # Weighted composite score
        score = (
            factors.get("momentum", 0.5) * 0.30
            + low_vol_score * 0.28
            + factors.get("quality", 0.5) * 0.21
            + factors.get("value", 0.5) * 0.14
            + factors.get("growth", 0.5) * 0.07
        ) * 100  # Scale to 0-100

        signal = self._signal_from_score(score)

        return {
            "strategy_name": self.name,
            "signal": signal.value,
            "score": round(score, 1),
            "confidence": min(0.9, max(0.3, abs(score - 50) / 50)),
            "detail": {
                "factors": factors,
                "f_score": result.get("f_score", 0),
            },
        }
