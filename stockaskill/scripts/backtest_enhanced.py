"""Backtest: Momentum Enhanced Core-Satellite strategy.

Combines 3 ETFs (40% core) with Alpha Momentum top-3 stocks (60% satellite).
Monthly rebalance with market trend filter.

Target: 18% CAGR, <20% MaxDD.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
# ]
# ///

import argparse
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import TypedDict

import numpy as np
from cache import get_cache
from data_engine import get_fundamentals
from data_readiness import ensure_backtest_ready
from factors.growth import GrowthFactor
from factors.low_vol import LowVolFactor
from factors.momentum import MomentumFactor
from factors.quality import QualityFactor
from factors.value import ValueFactor
from report_generator import (
    format_backtest_summary,
    save_markdown,
    save_report,
)
from utils import is_st

LOW_VOL_MIN = 0.40

FACTOR_W = {
    "momentum": 0.35,
    "low_vol": 0.18,
    "quality": 0.20,
    "value": 0.17,
    "growth": 0.10,
}


class EtfCoreHolding(TypedDict):
    """Static ETF allocation entry."""

    code: str
    name: str
    target: float


ETF_CORE: list[EtfCoreHolding] = [
    {"code": "510300", "name": "沪深300ETF", "target": 0.17},
    {"code": "159915", "name": "创业板ETF", "target": 0.12},
    {"code": "588000", "name": "科创50ETF", "target": 0.11},
]
ETF_CODES = {e["code"] for e in ETF_CORE}
ETF_TOTAL = sum(float(e["target"]) for e in ETF_CORE)

STOCK_TARGET = 0.60
MAX_PER_BOARD = 2


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


def _trend_filter(
    kline: list[dict[str, float]],
    ma_short: int = 50,
    ma_long: int = 200,
) -> bool:
    closes = [x["close"] for x in kline if x["close"] > 0]
    if len(closes) < ma_long:
        return True
    ma50 = np.mean(closes[:ma_short])
    ma200 = np.mean(closes[:ma_long])
    return bool(ma50 > ma200)


def run_backtest():
    ensure_backtest_ready(
        "A",
        extra_symbols=((code, "FUND") for code in ETF_CODES),
    )
    print("=" * 60)
    print("Momentum Enhanced Core-Satellite Backtest")
    print("=" * 60)

    c = get_cache()
    conn = sqlite3.connect(str(c.db_path))

    cur = conn.execute("""
        SELECT d.code, d.date, d.close, COALESCE(s.name, '') as name
        FROM daily_price_v2 d
        LEFT JOIN stock_pool_v2 s ON s.market='A' AND d.code = s.code
        WHERE d.market='A' AND d.code IN (
            SELECT code FROM daily_price_v2 WHERE market='A'
            GROUP BY code HAVING COUNT(*) >= 1200
        )
        OR d.code IN ('510300', '159915', '588000')
        ORDER BY d.code, d.date ASC
    """)
    sd = defaultdict(list)
    st_codes = set()
    for row in cur.fetchall():
        sd[row[0]].append({"date": row[1], "close": float(row[2])})
        if is_st(row[0], row[3]):
            st_codes.add(row[0])
    conn.close()

    codes = sorted(sd.keys())
    codes = [c for c in codes if c not in st_codes]
    print(f"\nStock pool: {len(codes)} stocks with >=1200 trading days")

    fc = {}
    for code in codes:
        try:
            f = get_fundamentals(code, "A", force_refresh=False)
            if f and f.get("eps", 0) > 0:
                fc[code] = f
        except Exception:
            pass
    codes = sorted(fc.keys())
    print(f"After EPS>0 filter: {len(codes)} stocks")

    all_d = sorted(set(d["date"] for code in codes for d in sd[code]))
    all_d = [d for d in all_d if d >= "2018-01-01"]
    md = {}
    for d in all_d:
        md[d[:7]] = d
    rd = sorted(md.values())
    print(f"Timeline: {len(rd)} months ({rd[0]} ~ {rd[-1]})")

    mf = MomentumFactor()
    lf = LowVolFactor()
    qf = QualityFactor()
    vf = ValueFactor()
    gf = GrowthFactor()

    def _score(code, kslice):
        fund = fc.get(code, {})
        try:
            s = mf.compute(fund, kslice, "A")
            lv = lf.compute(kslice, "A")
            q = qf.compute(fund, kslice, "A")
            v = vf.compute(fund, kslice, "A")
            g = gf.compute(fund, kslice, "A")
            if lv < LOW_VOL_MIN:
                return 0
            return s * 0.35 + lv * 0.18 + q * 0.20 + v * 0.17 + g * 0.10
        except Exception:
            return 0

    _INDEX_CSI300 = "000300"
    index_kline = {}
    try:
        conn2 = sqlite3.connect(str(c.db_path))
        cur2 = conn2.execute(
            "SELECT date, close FROM market_index "
            "WHERE index_code = ? ORDER BY date",
            (_INDEX_CSI300,),
        )
        for row in cur2.fetchall():
            index_kline[row[0]] = float(row[1])
        conn2.close()
    except Exception:
        pass

    def _get_price(code: str, date: str) -> float:
        if code in sd:
            bars = [x for x in sd[code] if x["date"] <= date]
            if bars:
                return float(bars[-1]["close"])
        if code in index_kline:
            return float(index_kline.get(date, 0))
        return 0.0

    def _get_index_kline(up_to_date: str) -> list[dict[str, float]]:
        return [
            {"close": index_kline[d]}
            for d in sorted(index_kline.keys())
            if d <= up_to_date
        ]

    cap = 1000000
    positions = {}
    cash = cap
    nav = []

    for i, reb_date in enumerate(rd):
        if i == 0:
            continue

        trend_ok = True
        if index_kline:
            ik = _get_index_kline(reb_date)
            trend_ok = _trend_filter(ik)
        equity_factor = 0.40 if not trend_ok else 1.0

        scored = []
        for code in codes:
            if code in ETF_CODES:
                continue
            kslice = [x for x in sd[code] if x["date"] <= reb_date]
            if len(kslice) < 120:
                continue
            s = _score(code, kslice)
            if s > 0:
                scored.append((code, s))
        scored.sort(key=lambda x: x[1], reverse=True)

        selected_stocks = []
        board_count = {}
        for code, sc in scored:
            board = _board(code)
            if board_count.get(board, 0) >= MAX_PER_BOARD:
                continue
            selected_stocks.append(code)
            board_count[board] = board_count.get(board, 0) + 1
            if len(selected_stocks) >= 3:
                break

        all_targets = set(selected_stocks) | ETF_CODES
        for code in list(positions.keys()):
            if code not in all_targets:
                price = _get_price(code, reb_date)
                if price > 0 and positions[code] > 0:
                    cash += positions[code] * price * (1 - 0.0003 - 0.001)
                    del positions[code]

        nav_before = cash
        for code, shares in list(positions.items()):
            price = _get_price(code, reb_date)
            if price > 0:
                nav_before += shares * price

        for etf in ETF_CORE:
            code = etf["code"]
            if code not in positions:
                target_value = nav_before * etf["target"] * equity_factor
                price = _get_price(code, reb_date)
                if price > 0:
                    shares = max(100, int(target_value / price / 100) * 100)
                    cost = shares * price * 1.0003
                    if cost <= cash and shares > 0:
                        positions[code] = shares
                        cash -= cost

        stock_alloc = nav_before * STOCK_TARGET * equity_factor
        n_stocks = max(len(selected_stocks), 1)
        for code in selected_stocks:
            if code not in positions:
                per_stock = stock_alloc / n_stocks
                price = _get_price(code, reb_date)
                if price > 0:
                    shares = max(100, int(per_stock / price / 100) * 100)
                    cost = shares * price * 1.0003
                    if cost <= cash and shares > 0:
                        positions[code] = shares
                        cash -= cost

        total = cash
        for code, shares in positions.items():
            price = _get_price(code, reb_date)
            if price > 0:
                total += shares * price
        nav.append(total)

        if i % 12 == 0 or i == len(rd) - 1:
            print(f"  {reb_date}: NAV={total:,.0f} ({((total/cap)-1)*100:+.1f}%)")

    final_date = all_d[-1]
    total = cash
    for code, shares in positions.items():
        price = _get_price(code, final_date)
        if price > 0:
            total += shares * price
    nav.append(total)

    na = np.array(nav)
    tr = (na[-1] - na[0]) / na[0]
    start_dt = datetime.strptime(rd[1] if len(rd) > 1 else rd[0], "%Y-%m-%d")
    ed_dt = datetime.strptime(final_date, "%Y-%m-%d")
    yr = max((ed_dt - start_dt).days / 365.25, 0.1)
    cagr = (na[-1] / na[0]) ** (1 / yr) - 1

    ra = [((na[k] - na[k - 1]) / na[k - 1]) for k in range(1, len(na)) if na[k - 1] > 0]
    ra = np.array(ra)
    sh = 0
    if len(ra) > 1 and np.std(ra) > 0:
        sh = np.mean(ra) / np.std(ra) * np.sqrt(12)
    cum = np.cumprod(1 + ra) if len(ra) > 0 else np.array([1])
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    mdd = np.min(dd) if len(dd) > 0 else 0
    calmar = cagr / abs(mdd) if mdd != 0 else 0

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Period:     {rd[1] if len(rd) > 1 else rd[0]} ~ {final_date} ({yr:.1f}y)")
    print(f"  CAGR:       {cagr*100:.2f}%")
    print(f"  Total Ret:  {tr*100:.2f}%")
    print(f"  Sharpe:     {sh:.2f}")
    print(f"  Max DD:     {mdd*100:.2f}%")
    print(f"  Calmar:     {calmar:.2f}")
    print(f"  Final NAV:  {na[-1]:,.0f}")
    print("  Target:     18.00% CAGR, <20% MaxDD")

    if cagr >= 0.18 and abs(mdd) <= 0.20:
        print("\n  VERDICT: PASS")
    elif cagr >= 0.18:
        print(f"\n  VERDICT: PARTIAL (CAGR OK, MaxDD {mdd*100:.1f}%)")
    elif abs(mdd) <= 0.20:
        print(f"\n  VERDICT: PARTIAL (MaxDD OK, CAGR {(0.18-cagr)*100:.1f}% short)")
    else:
        print("\n  VERDICT: FAIL")

    return {
        "cagr": cagr,
        "total_return": tr,
        "sharpe": sh,
        "max_drawdown": mdd,
        "calmar": calmar,
        "final_nav": float(na[-1]),
        "months": len(rd) - 1,
        "years": yr,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enhanced Core-Satellite Backtest")
    parser.add_argument(
        "--output-dir",
        default="reports",
        help="Report output directory",
    )
    args = parser.parse_args()

    result = run_backtest()
    save_report(
        result,
        "backtest_enhanced_direct",
        output_dir=args.output_dir,
        metadata={
            "command": "backtest_enhanced",
            "engine": "CoreSatellite",
        },
    )
    md = format_backtest_summary(result)
    save_markdown(md, "backtest_enhanced_direct", output_dir=args.output_dir)
