"""Batch fetch full K-line history for more A-share stocks."""

import sqlite3
import sys
import time
from pathlib import Path

_scripts = str(Path(__file__).resolve().parent.parent / "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from data_engine import get_stock_pool, get_cache

_cache = get_cache()


def _sina_code(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "3")):
        return f"sz{code}"
    return code


def fetch_and_upsert(code: str, market: str = "A") -> int:
    """Fetch and upsert K-line data for a stock."""
    import akshare as ak
    try:
        symbol = _sina_code(code)
        df = ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")
        if df is None or df.empty:
            return 0
        df["date"] = df["date"].astype(str)
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "code": code,
                "date": str(r.get("date", "")),
                "open": float(r.get("open", 0)),
                "high": float(r.get("high", 0)),
                "low": float(r.get("low", 0)),
                "close": float(r.get("close", 0)),
                "volume": float(r.get("volume", 0)),
                "amount": float(r.get("amount", 0)),
                "market": market,
            })
        if rows:
            _cache.upsert_daily_price(rows)
        return len(rows)
    except Exception as exc:
        print(f"    Error: {exc}")
        return 0


def main() -> None:
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 50

    print(f"Expanding candidate pool: fetching full history for up to {target} more 
        stocks...")

    pool = get_stock_pool("A")
    if not pool:
        print("  ERROR: empty stock pool")
        return

    conn = sqlite3.connect(str(_cache.db_path))
    existing = set(
        r[0] for r in conn.execute("SELECT DISTINCT code FROM daily_price").fetchall()
    )
    conn.close()
    print(f"  Pool: {len(pool)} stocks, existing w/ data: {len(existing)}")

    candidates = [s for s in pool if s["code"] not in existing and not s["code"
        ].startswith("bj")]

    if not candidates:
        print("  All pool stocks already have data!")
        return

    # Sort candidates: prefer those starting with 6 (SH main board) then 0/3 (SZ)
    candidates.sort(key=lambda s: (not s["code"].startswith("6"), s["code"]))

    print(f"  Candidates to fetch: {len(candidates)}")
    print(f"  First 5: {[c['code'] for c in candidates[:5]]}")

    fetched = 0
    success = 0
    fail = 0
    start = time.time()

    batch = candidates[:target]
    for i, stock in enumerate(batch):
        code = stock["code"]
        name = stock.get("name", "")
        print(f"  [{i+1}/{len(batch)}] {code} {name} ...", end=" ")
        sys.stdout.flush()
        count = fetch_and_upsert(code)
        if count > 0:
            fetched += count
            success += 1
            print(f"ok ({count} rows)")
        else:
            fail += 1
            print("no data")
        if i < len(batch) - 1:
            time.sleep(3)

    elapsed = time.time() - start
    print(f"\nDone: {success} ok, {fail} failed, {fetched} total rows in {elapsed:.0f}s"
        )

    conn2 = sqlite3.connect(str(_cache.db_path))
    total_with_data = conn2.execute(
        "SELECT COUNT(DISTINCT code) FROM daily_price"
    ).fetchone()[0]
    total_full = conn2.execute(
        "SELECT COUNT(*) FROM (SELECT code FROM daily_price GROUP BY code HAVING COUNT(
        *) >= 1500)"
    ).fetchone()[0]
    conn2.close()
    print(f"  Stocks with any daily_price data: {total_with_data}")
    print(f"  Stocks with >=1500 rows: {total_full}")


if __name__ == "__main__":
    main()
