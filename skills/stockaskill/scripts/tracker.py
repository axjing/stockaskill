"""Portfolio tracking: stop-loss and take-profit monitoring."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cache import get_cache
from config import get as cfg_get
from data_engine import get_kline
from utils import normalize_code_for_market, safe_float

_TRACKING_DIR = Path(__file__).resolve().parents[1] / "memory" / "trackings"


def _ensure_tracking_dir() -> None:
    _TRACKING_DIR.mkdir(parents=True, exist_ok=True)


def start_tracking(
    code: str,
    market: str = "A",
    entry_price: float = 0,
    stop_loss_pct: float = 0.15,
    take_profit_pct: float = 0.30,
    notes: str = "",
) -> Dict[str, Any]:
    """Start tracking a position with stop-loss and take-profit levels.

    Args:
        code: Stock code.
        market: Market identifier.
        entry_price: Entry price.
        stop_loss_pct: Stop-loss percentage (e.g. 0.15 = 15%).
        take_profit_pct: Take-profit percentage (e.g. 0.30 = 30%).
        notes: Optional notes.

    Returns:
        Tracking record dict.
    """
    _ensure_tracking_dir()
    code = normalize_code_for_market(code, market)
    tracking_id = str(uuid.uuid4())[:8]
    entry = safe_float(entry_price)
    stop_loss_price = round(entry * (1 - stop_loss_pct), 3) if entry > 0 else 0
    take_profit_price = round(entry * (1 + take_profit_pct), 3) if entry > 0 else 0

    record = {
        "tracking_id": tracking_id,
        "code": code,
        "market": market,
        "entry_price": entry,
        "entry_date": datetime.now().strftime("%Y-%m-%d"),
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price,
        "status": "active",
        "notes": notes,
        "last_check": None,
        "last_price": None,
        "pnl_pct": None,
    }
    path = _TRACKING_DIR / f"{tracking_id}_{code}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def list_trackings(status_filter: str = "active") -> List[Dict[str, Any]]:
    """List all tracking records.

    Args:
        status_filter: "active", "closed", or "all".

    Returns:
        List of tracking record dicts.
    """
    _ensure_tracking_dir()
    results = []
    for f in sorted(_TRACKING_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if status_filter == "all" or data.get("status") == status_filter:
                results.append(data)
        except Exception:
            continue
    return results


def check_trackings(
    market: str = "A",
    days: int = 5,
) -> List[Dict[str, Any]]:
    """Check all active trackings for stop-loss/take-profit triggers.

    Args:
        market: Market identifier.
        days: How many recent days of kline to fetch.

    Returns:
        List of updated tracking records with alert info.
    """
    trackings = list_trackings("active")
    alerts = []
    for t in trackings:
        if t.get("market", "A") != market:
            continue
        code = t["code"]
        kline = get_kline(code, market, days=days, cached_only=True)
        current_price = 0
        if kline:
            current_price = safe_float(kline[0].get("close", 0))

        if current_price <= 0:
            t["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            t["alert"] = "价格数据不可用"
            alerts.append(t)
            _save_tracking(t)
            continue

        pnl_pct = ((current_price - t["entry_price"]) / max(t["entry_price"], 1e-9)) * 100
        t["last_price"] = current_price
        t["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        t["pnl_pct"] = round(pnl_pct, 2)

        stop_hit = current_price <= t["stop_loss_price"]
        profit_hit = current_price >= t["take_profit_price"]

        if stop_hit:
            t["alert"] = "止损触发"
            t["status"] = "triggered_stop_loss"
        elif profit_hit:
            t["alert"] = "止盈触达"
            t["status"] = "triggered_take_profit"
        else:
            t["alert"] = None

        alerts.append(t)
        _save_tracking(t)
    return alerts


def close_tracking(
    tracking_id: str,
    exit_price: float = 0,
    notes: str = "",
) -> Optional[Dict[str, Any]]:
    """Close a tracking record.

    Args:
        tracking_id: The tracking record ID.
        exit_price: Exit price.
        notes: Closing notes.

    Returns:
        Updated tracking record or None.
    """
    for f in _TRACKING_DIR.glob(f"{tracking_id}_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["status"] = "closed"
            data["exit_price"] = safe_float(exit_price)
            data["exit_date"] = datetime.now().strftime("%Y-%m-%d")
            data["exit_notes"] = notes
            if exit_price > 0 and data.get("entry_price", 0) > 0:
                pnl = ((exit_price - data["entry_price"]) / data["entry_price"]) * 100
                data["exit_pnl_pct"] = round(pnl, 2)
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        except Exception:
            continue
    return None


def _save_tracking(record: Dict[str, Any]) -> None:
    """Save a tracking record to disk."""
    _ensure_tracking_dir()
    tid = record.get("tracking_id", "")
    code = record.get("code", "")
    for f in _TRACKING_DIR.glob(f"{tid}_{code}.json"):
        f.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return
