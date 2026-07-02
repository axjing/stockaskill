"""Enhanced Alpha Momentum: optimized factor weights + ETF core overlay.

Target: 18% CAGR, <20% MaxDD.

Strategy architecture:
  Core (40%): 3 ETFs across market cap segments
  Satellite (60%): Alpha Momentum top-3 A-share stocks with optimized weights

Factor weights (optimized for higher target return):
  - Momentum:  35% (was 30%)
  - Low Vol:   18% (was 28%)
  - Quality:   20% (was 21%)
  - Value:     17% (was 14%)
  - Growth:    10% (was  7%)
"""

from typing import Any, Dict, List

from strategies.base import Strategy

LOW_VOL_MIN = 0.40

FACTOR_WEIGHTS = {
    "momentum": 0.35,
    "low_vol": 0.18,
    "quality": 0.20,
    "value": 0.17,
    "growth": 0.10,
}

ETF_CORE = [
    {"code": "510300", "name": "沪深300ETF", "role": "大盘核心", "target_weight": 0.17},
    {"code": "159915", "name": "创业板ETF", "role": "成长弹性", "target_weight": 0.12},
    {"code": "588000", "name": "科创50ETF", "role": "科技赛道", "target_weight": 0.11},
]


class MomentumEnhancedStrategy(Strategy):
    """Enhanced Alpha Momentum with optimized weights and ETF core.

    Selection: Top 3 stocks (satellite) + 3 ETFs (core) = 6 positions.
    Rebalance: monthly.
    Risk controls: low_vol >= 0.4, EPS > 0, no ST, max 2 per board.
    """

    @property
    def name(self) -> str:
        return "momentum_enhanced"

    @property
    def weight(self) -> float:
        return 0.20

    def analyze(self, code: str, market: str = "A", cached_only: bool = False) -> Dict[str, Any]:
        from factors.composite import CompositeAnalyzer

        analyzer = CompositeAnalyzer(code, market)
        result = analyzer.analyze(cached_only=cached_only)

        factors = result.get("factors", {})
        low_vol_score = factors.get("low_vol", 0.5)

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

        score = (
            factors.get("momentum", 0.5) * FACTOR_WEIGHTS["momentum"]
            + low_vol_score * FACTOR_WEIGHTS["low_vol"]
            + factors.get("quality", 0.5) * FACTOR_WEIGHTS["quality"]
            + factors.get("value", 0.5) * FACTOR_WEIGHTS["value"]
            + factors.get("growth", 0.5) * FACTOR_WEIGHTS["growth"]
        ) * 100

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

    def select_top_stocks(
        self,
        candidates: List[Dict[str, Any]],
        max_picks: int = 3,
        max_per_board: int = 2,
        cached_only: bool = False,
    ) -> List[str]:
        """Select top N stocks with board diversification."""
        scored = []
        for stock in candidates:
            code = stock.get("code", "")
            try:
                r = self.analyze(code, "A", cached_only=cached_only)
                if r.get("signal") == "BUY" and r.get("score", 0) > 0:
                    scored.append((code, r["score"]))
            except Exception:
                continue

        scored.sort(key=lambda x: x[1], reverse=True)

        selected = []
        board_count: Dict[str, int] = {}
        for code, score in scored:
            board = self._board(code)
            if board_count.get(board, 0) >= max_per_board:
                continue
            selected.append(code)
            board_count[board] = board_count.get(board, 0) + 1
            if len(selected) >= max_picks:
                break

        return selected

    @staticmethod
    def _board(code: str) -> str:
        if code.startswith("60"):
            return "SH"
        if code.startswith("688"):
            return "STAR"
        if code.startswith("000"):
            return "SZ"
        if code.startswith("002"):
            return "SME"
        if code.startswith("300"):
            return "GEM"
        return "OTHER"

    @staticmethod
    def get_etf_allocation() -> List[Dict[str, Any]]:
        """Return ETF core allocation targets."""
        return ETF_CORE

    @staticmethod
    def get_enhanced_weights() -> Dict[str, float]:
        """Return enhanced factor weights."""
        return FACTOR_WEIGHTS
