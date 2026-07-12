"""CLI command handlers for scheduler, cache, and track functionality."""

import argparse
import sys

from cache import get_cache
from config import get as cfg_get
from data_engine import is_api_limit_exhausted

from commands._common import _cmd_output, _save_report


def cmd_scheduler(args: argparse.Namespace) -> None:
    """Run scheduled analysis."""
    watchlist = cfg_get("watchlist", [])
    if not watchlist:
        print("No watchlist configured")
        return

    if args.run_now:
        print(f"Running scheduled analysis for {len(watchlist)} stocks...")
        for code in watchlist:
            if is_api_limit_exhausted():
                print(f"  [INFO] API limit reached, skipping remaining stocks.", flush=True)
                break
            print(f"\n--- {code} ---")
            from commands.analyze import cmd_analyze

            fake_args = argparse.Namespace(code=code, market="A", output_dir="reports")
            cmd_analyze(fake_args)
    else:
        print("Scheduler mode: use --run-now for immediate execution")
        print("In production, integrate with cron/systemd Task Scheduler")
        print(f"Watching: {', '.join(watchlist)}")



def cmd_cache(args: argparse.Namespace) -> None:
    """Cache management: stats, cleanup."""
    action = args.action
    cache = get_cache()

    if action == "stats":
        s = cache.stats()
        print(f"DB size: {s['db_size_mb']:.1f} MB")
        if is_api_limit_exhausted():
            print("[WARN] Some upstream APIs are currently rate-limited.")
        print("Table row counts:")
        for tbl, cnt in sorted(s.items()):
            if tbl in ("db_size_mb", "api_calls_today"):
                continue
            print(f"  {tbl}: {cnt}")
    elif action == "cleanup":
        days = getattr(args, "days", 30)
        removed = cache.cleanup(max_age_days=days)
        total = sum(removed.values())
        print(f"Cleaned up {total} old entries:")
        for tbl, cnt in removed.items():
            if cnt:
                print(f"  {tbl}: {cnt} rows removed")
    else:
        print(f"Unknown cache action: {action}")



def cmd_track(args: argparse.Namespace) -> None:
    """Manage portfolio stop-loss/take-profit tracking."""
    action = getattr(args, "action", "")
    output_dir, fmt = _cmd_output(args)

    if action == "start":
        code = args.code
        market = getattr(args, "market", "A") or "A"
        price = getattr(args, "price", 0) or 0
        stop_loss = (getattr(args, "stop_loss", 15) or 15) / 100.0
        take_profit = (getattr(args, "take_profit", 30) or 30) / 100.0
        notes = getattr(args, "notes", "") or ""

        from tracker import start_tracking
        record = start_tracking(code, market, price, stop_loss, take_profit, notes)

        print(f"开始跟踪: {record['code']} ({record['market']})")
        print(f"  跟踪ID: {record['tracking_id']}")
        print(f"  买入价: {record['entry_price']}")
        print(f"  止损价: {record['stop_loss_price']} ({record['stop_loss_pct']:.0%})")
        print(f"  止盈价: {record['take_profit_price']} ({record['take_profit_pct']:.0%})")
        print(f"  日期: {record['entry_date']}")
        if notes:
            print(f"  备注: {notes}")

        if fmt != "none":
            _save_report(
                f"track_start_{record['tracking_id']}",
                fmt,
                output_dir,
                data=record,
                metadata={"command": "track-start", "code": code},
            )
        return

    if action == "status":
        from tracker import list_trackings
        status_filter = getattr(args, "status", "active") or "active"
        market = getattr(args, "market", "A") or "A"
        trackings = list_trackings(status_filter)
        trackings = [t for t in trackings if t.get("market") == market]

        if not trackings:
            print(f"无跟踪记录 ({market}, {status_filter})")
            return

        print(f"跟踪记录 ({market}, {status_filter}, 共{len(trackings)}条):")
        for t in trackings:
            pnl_str = ""
            if t.get("pnl_pct") is not None:
                pnl_str = f" | 盈亏={t['pnl_pct']:+.2f}%"
            elif t.get("status") == "closed" and t.get("exit_pnl_pct") is not None:
                pnl_str = f" | 已平仓 盈亏={t['exit_pnl_pct']:+.2f}%"
            alert_str = f" | ⚠️ {t['alert']}" if t.get("alert") else ""
            print(
                f"  [{t['tracking_id']}] {t['code']}: 买入价={t['entry_price']}"
                f" | 止损={t['stop_loss_price']} | 止盈={t['take_profit_price']}"
                f"{pnl_str}{alert_str}"
            )

        if fmt != "none":
            _save_report(
                "track_status",
                fmt,
                output_dir,
                data={"trackings": trackings},
                metadata={"command": "track-status", "market": market},
            )
        return

    if action == "check":
        from tracker import check_trackings
        market = getattr(args, "market", "A") or "A"
        days = getattr(args, "days", 5) or 5

        print(f"检查持仓预警 ({market})...")
        alerts = check_trackings(market, days)

        if not alerts:
            print("  无活跃跟踪")
            return

        triggered = [a for a in alerts if a.get("alert")]
        print(f"  共 {len(alerts)} 个持仓:")
        for a in alerts:
            price_str = f"当前价={a['last_price']}" if a.get("last_price") else "价格未知"
            pnl_str = ""
            if a.get("pnl_pct") is not None:
                pnl_str = f" | 盈亏={a['pnl_pct']:+.2f}%"
            alert_str = f" | ⚠️ {a['alert']}" if a.get("alert") else " | 正常"
            print(f"    {a['code']}: {price_str}{pnl_str}{alert_str}")

        if triggered:
            print(f"\n  ⚠️ {len(triggered)} 个持仓触发预警!")
            for a in triggered:
                advice = "止损离场" if "止损" in str(a["alert"]) else "止盈减仓"
                print(f"    {a['code']}: {a['alert']} (建议: {advice})")

        if fmt != "none":
            _save_report(
                "track_check",
                fmt,
                output_dir,
                data={"alerts": alerts},
                metadata={"command": "track-check", "market": market},
            )
        return

    if action == "close":
        from tracker import close_tracking
        tid = args.tracking_id
        price = getattr(args, "price", 0) or 0
        notes = getattr(args, "notes", "") or ""

        result = close_tracking(tid, price, notes)
        if result:
            print(f"已平仓: {result['code']} (跟踪ID: {tid})")
            if price > 0:
                print(f"  平仓价: {price}")
                if result.get("exit_pnl_pct") is not None:
                    print(f"  盈亏: {result['exit_pnl_pct']:+.2f}%")
            if notes:
                print(f"  备注: {notes}")
        else:
            print(f"未找到跟踪记录: {tid}", file=sys.stderr)
        return

    print(f"Unknown track action: {action}", file=sys.stderr)

