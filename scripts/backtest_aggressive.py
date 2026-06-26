"""Aggressive Momentum: 6 stocks, enhanced weights, no ETFs. Monthly rebalance."""

import sqlite3
from collections import defaultdict
from datetime import datetime
import numpy as np
from cache import get_cache
from data_engine import get_fundamentals
from factors.momentum import MomentumFactor
from factors.low_vol import LowVolFactor
from factors.quality import QualityFactor
from factors.value import ValueFactor
from factors.growth import GrowthFactor
from utils import is_st

LOW_VOL_MIN = 0.40
MAX_PER_BOARD = 2

ENHANCED_W = {"momentum": 0.35, "low_vol": 0.18, "quality": 0.20, "value": 0.17, "growth": 0.10}
ORIGINAL_W = {"momentum": 0.30, "low_vol": 0.28, "quality": 0.21, "value": 0.14, "growth": 0.07}

def run(mode="enhanced"):
    w = ENHANCED_W if mode == "enhanced" else ORIGINAL_W
    label = f"Momentum ({mode} weights, 6 stocks)"
    print(f"\n{'='*60}")
    print(label)
    print(f"{'='*60}")

    c = get_cache()
    conn = sqlite3.connect(str(c.db_path))
    cur = conn.execute("""
        SELECT d.code, d.date, d.close, COALESCE(s.name, '') as name
        FROM daily_price d
        LEFT JOIN stock_pool s ON d.code = s.code
        WHERE d.code IN (
            SELECT code FROM daily_price GROUP BY code HAVING COUNT(*) >= 1200
        )
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
    print(f"Pool: {len(codes)} stocks")

    fc = {}
    for code in codes:
        f = get_fundamentals(code, "A", force_refresh=False)
        if f and f.get("eps", 0) > 0:
            fc[code] = f
    codes = sorted(fc.keys())
    print(f"After EPS>0: {len(codes)} stocks")

    all_d = sorted(set(d["date"] for code in codes for d in sd[code]))
    all_d = [d for d in all_d if d >= "2018-01-01"]
    rd = sorted({d[:7]: d for d in all_d}.values())
    print(f"Timeline: {len(rd)} months")

    mf, lf, qf, vf, gf = MomentumFactor(), LowVolFactor(), QualityFactor(), ValueFactor(), GrowthFactor()

    def _score(code, kslice):
        fund = fc.get(code, {})
        try:
            s = mf.compute(fund, kslice, "A")
            l = lf.compute(kslice, "A")
            q = qf.compute(fund, kslice, "A")
            v = vf.compute(fund, kslice, "A")
            g = gf.compute(fund, kslice, "A")
            if l < LOW_VOL_MIN:
                return 0
            return s * w["momentum"] + l * w["low_vol"] + q * w["quality"] + v * w["value"] + g * w["growth"]
        except Exception:
            return 0

    def _board(code):
        if code.startswith("60"): return "SH"
        if code.startswith("688"): return "STAR"
        if code.startswith("000"): return "SZ"
        if code.startswith("002"): return "SME"
        if code.startswith("300"): return "GEM"
        return "OTHER"

    cap, cash, positions = 1000000, 1000000, {}
    nav = []

    for i, reb_date in enumerate(rd):
        if i == 0:
            continue

        scored = []
        for code in codes:
            kslice = [x for x in sd[code] if x["date"] <= reb_date]
            if len(kslice) < 120:
                continue
            s = _score(code, kslice)
            if s > 0:
                scored.append((code, s))
        scored.sort(key=lambda x: x[1], reverse=True)

        selected, bc = [], {}
        for code, sc in scored:
            b = _board(code)
            if bc.get(b, 0) >= MAX_PER_BOARD:
                continue
            selected.append(code)
            bc[b] = bc.get(b, 0) + 1
            if len(selected) >= 6:
                break

        for code in list(positions.keys()):
            if code not in selected:
                p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                price = p[-1] if p else 0
                if price > 0:
                    cash += positions[code] * price * (1 - 0.0003 - 0.001)
                    del positions[code]

        nav_before = cash
        for code, shares in list(positions.items()):
            p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
            if p:
                nav_before += shares * p[-1]

        alloc = nav_before / max(len(selected), 1)
        for code in selected:
            if code not in positions:
                p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
                price = p[-1] if p else 0
                if price > 0:
                    shares = max(100, int(alloc / price / 100) * 100)
                    cost = shares * price * 1.0003
                    if cost <= cash and shares > 0:
                        positions[code] = shares
                        cash -= cost

        total = cash
        for code, shares in positions.items():
            p = [x["close"] for x in sd[code] if x["date"] <= reb_date]
            if p:
                total += shares * p[-1]
        nav.append(total)

    final_date = all_d[-1]
    total = cash
    for code, shares in positions.items():
        p = [x["close"] for x in sd[code] if x["date"] <= final_date]
        if p:
            total += shares * p[-1]
    nav.append(total)

    na = np.array(nav)
    tr = (na[-1] - na[0]) / na[0]

    start_dt = datetime.strptime(rd[0], "%Y-%m-%d")
    end_dt = datetime.strptime(final_date, "%Y-%m-%d")
    yr = max((end_dt - start_dt).days / 365.25, 0.1)
    cagr = (na[-1] / na[0]) ** (1 / yr) - 1

    ra = np.array([(na[k] - na[k-1]) / na[k-1] for k in range(1, len(na)) if na[k-1] > 0])
    sh = np.mean(ra) / np.std(ra) * np.sqrt(12) if len(ra) > 1 and np.std(ra) > 0 else 0
    cum = np.cumprod(1 + ra) if len(ra) > 0 else np.array([1])
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak
    mdd = np.min(dd) if len(dd) > 0 else 0

    print(f"  CAGR: {cagr*100:.2f}%  Sharpe: {sh:.2f}  MaxDD: {mdd*100:.2f}%")
    print(f"  Total: {tr*100:.2f}%  Final: {na[-1]:,.0f}")
    return {"cagr": cagr, "sharpe": sh, "mdd": mdd, "total": tr}

if __name__ == "__main__":
    run("original")
    run("enhanced")
