"""Local-first thesis memory and postmortem persistence."""

import json
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from config import get as cfg_get
from models import ThesisPostmortem, ThesisRecord
from postmortem import build_postmortem_attribution
from report_generator import format_thesis_summary
from scorecards import build_thesis_scorecard


def _storage_dir() -> Path:
    path = Path(str(cfg_get("thesis_memory.storage_dir", "memory/theses")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _record_path(thesis_id: str) -> Path:
    return _storage_dir() / f"{thesis_id}.json"


def _markdown_path(thesis_id: str) -> Path:
    return _storage_dir() / f"{thesis_id}.md"


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_thesis_record(
    report: Dict[str, Any],
    source: str = "diagnose",
    thesis_status: str = "active",
    notes: str = "",
) -> ThesisRecord:
    """Build a thesis record from a diagnosis report."""
    code = str(report.get("code", "")).strip()
    market = str(report.get("market", "A")).strip() or "A"
    created_at = _now()
    compact_created_at = (
        created_at.replace("-", "")
        .replace(":", "")
        .replace("T", "_")
        .replace("Z", "")
    )
    thesis_id = f"{market}_{code}_{compact_created_at}_{uuid.uuid4().hex[:6]}"
    decision = report.get("final_decision", {}) or {}
    confidence = report.get("confidence", {}) or {}
    signal = str(decision.get("signal", "HOLD")).strip() or "HOLD"
    score = float(decision.get("adjusted_score", 50) or 50)
    confidence_level = str(confidence.get("level", "medium")).strip() or "medium"
    confidence_score = float(confidence.get("score", 0.5) or 0.5)
    summary = (
        f"{signal} 观点，score={score:.1f}/100，"
        f"confidence={confidence_level}({confidence_score:.2f})"
    )

    thesis = ThesisRecord(
        thesis_id=thesis_id,
        code=code,
        market=market,
        created_at=created_at,
        source=source,
        thesis_status=thesis_status,
        signal=signal,
        score=score,
        confidence_level=confidence_level,
        confidence_score=confidence_score,
        summary=summary,
        bull_case=list(decision.get("bull_case", []) or []),
        bear_case=list(decision.get("bear_case", []) or []),
        invalidation_conditions=list(decision.get("invalidation_conditions", []) or []),
        notes=notes,
        provenance=dict(report.get("provenance", {}) or {}),
        diagnosis_report=report,
    )
    thesis.scorecard = build_thesis_scorecard(thesis.to_dict())
    return thesis


def save_thesis_record(record: ThesisRecord) -> Dict[str, str]:
    """Persist a thesis record as JSON and Markdown."""
    json_path = _record_path(record.thesis_id)
    md_path = _markdown_path(record.thesis_id)
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(record.to_dict(), handle, indent=2, ensure_ascii=False, default=str)
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(format_thesis_summary(record.to_dict()))
    return {"json_path": str(json_path), "md_path": str(md_path)}


def _load_record(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def list_thesis_records(
    market: str = "",
    code: str = "",
    thesis_status: str = "",
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    """List locally saved thesis records ordered by creation time descending."""
    records: List[Dict[str, Any]] = []
    for path in sorted(_storage_dir().glob("*.json"), reverse=True):
        record = _load_record(path)
        if market and str(record.get("market", "")).strip() != market:
            continue
        if code and str(record.get("code", "")).strip() != code:
            continue
        if (
            thesis_status
            and str(record.get("thesis_status", "")).strip() != thesis_status
        ):
            continue
        records.append(record)
    if limit is not None:
        return records[:limit]
    return records


def get_thesis_record(
    thesis_id: str = "",
    code: str = "",
    market: str = "",
) -> Dict[str, Any] | None:
    """Get a thesis record by id or latest matching code/market."""
    if thesis_id:
        path = _record_path(thesis_id)
        if not path.exists():
            return None
        return _load_record(path)
    records = list_thesis_records(market=market, code=code, limit=1)
    return records[0] if records else None


def update_thesis_postmortem(
    outcome: str,
    notes: str,
    thesis_id: str = "",
    code: str = "",
    market: str = "",
    thesis_status: str = "closed",
) -> Dict[str, Any]:
    """Attach a postmortem to an existing thesis record and persist it."""
    record = get_thesis_record(thesis_id=thesis_id, code=code, market=market)
    if not record:
        raise ValueError("thesis_not_found")
    postmortem = ThesisPostmortem(
        outcome=outcome,
        reviewed_at=_now(),
        notes=notes,
        thesis_status=thesis_status,
    )
    record["postmortem"] = asdict(postmortem)
    record["thesis_status"] = thesis_status
    thesis = ThesisRecord(
        thesis_id=str(record.get("thesis_id", "")).strip(),
        code=str(record.get("code", "")).strip(),
        market=str(record.get("market", "")).strip(),
        created_at=str(record.get("created_at", "")).strip(),
        source=str(record.get("source", "diagnose")).strip(),
        thesis_status=str(record.get("thesis_status", "closed")).strip(),
        signal=str(record.get("signal", "HOLD")).strip(),
        score=float(record.get("score", 50) or 50),
        confidence_level=str(record.get("confidence_level", "medium")).strip(),
        confidence_score=float(record.get("confidence_score", 0.5) or 0.5),
        summary=str(record.get("summary", "")).strip(),
        bull_case=list(record.get("bull_case", []) or []),
        bear_case=list(record.get("bear_case", []) or []),
        invalidation_conditions=list(record.get("invalidation_conditions", []) or []),
        notes=str(record.get("notes", "")).strip(),
        postmortem=postmortem,
        provenance=dict(record.get("provenance", {}) or {}),
        scorecard=dict(record.get("scorecard", {}) or {}),
        attribution=dict(record.get("attribution", {}) or {}),
        diagnosis_report=dict(record.get("diagnosis_report", {}) or {}),
    )
    thesis.scorecard = build_thesis_scorecard(thesis.to_dict())
    thesis.attribution = build_postmortem_attribution(thesis.to_dict())
    save_thesis_record(thesis)
    return thesis.to_dict()


def check_active_theses(
    market: str = "",
    code: str = "",
    auto_close: bool = False,
) -> List[Dict[str, Any]]:
    """Check active theses against latest price and invalidation conditions.

    Evaluates:
      - Latest price vs entry price (PnL %)
      - MA20 trend (above/below MA20)
      - Hard stop-loss (-8% threshold)
      - Returns structured status list: 'HEALTHY', 'CAUTION', 'INVALIDATED'
    """
    from data_engine import get_kline
    from utils import safe_float

    records = list_thesis_records(market=market, code=code, thesis_status="active")
    results: List[Dict[str, Any]] = []

    for record in records:
        thesis_id = str(record.get("thesis_id", "")).strip()
        c = str(record.get("code", "")).strip()
        m = str(record.get("market", "A")).strip() or "A"

        diag = record.get("diagnosis_report", {}) or {}
        entry_price = safe_float(
            diag.get("technical", {}).get("current_price")
            or diag.get("technical", {}).get("current")
            or diag.get("price")
            or record.get("entry_price", 0.0)
        )

        kline = []
        try:
            kline = get_kline(c, m, days=30, cached_only=True)
            if not kline:
                kline = get_kline(c, m, days=30, cached_only=False)
        except Exception:
            kline = []

        latest_price = entry_price
        ma20 = entry_price
        if kline:
            latest_price = safe_float(kline[0].get("close", 0.0))
            closes = [
                safe_float(r.get("close", 0.0))
                for r in kline
                if safe_float(r.get("close", 0.0)) > 0
            ]
            if closes:
                ma20 = sum(closes[:20]) / min(len(closes), 20)
                if entry_price <= 0:
                    entry_price = closes[-1]

        pnl_pct = 0.0
        if entry_price > 0 and latest_price > 0:
            pnl_pct = round((latest_price - entry_price) / entry_price * 100, 2)

        if latest_price <= 0 and entry_price <= 0:
            status = "NO_DATA"
            reason = "行情数据缺失，请先运行 sync symbol 同步数据"
        elif pnl_pct <= -8.0 or (ma20 > 0 and latest_price < ma20 * 0.97):
            status = "INVALIDATED"
            reason = f"触发失效: 收益率={pnl_pct:+.2f}%, 跌破MA20({ma20:.2f})"
        elif pnl_pct <= -4.0 or (ma20 > 0 and latest_price < ma20):
            status = "CAUTION"
            reason = f"需防守: 收益率={pnl_pct:+.2f}%, 贴近MA20({ma20:.2f})"
        else:
            status = "HEALTHY"
            reason = f"运行正常: 收益率={pnl_pct:+.2f}%, 站稳均线"

        auto_closed = False
        if auto_close and status == "INVALIDATED":
            try:
                update_thesis_postmortem(
                    outcome="loss" if pnl_pct < 0 else "neutral",
                    notes=f"Auto-closed by invalidation check: {reason}",
                    thesis_id=thesis_id,
                    thesis_status="closed",
                )
                auto_closed = True
            except Exception:
                pass

        results.append(
            {
                "thesis_id": thesis_id,
                "code": c,
                "market": m,
                "signal": record.get("signal", "HOLD"),
                "entry_price": entry_price,
                "latest_price": latest_price,
                "pnl_pct": pnl_pct,
                "ma20": round(ma20, 2),
                "status": status,
                "reason": reason,
                "auto_closed": auto_closed,
                "invalidation_conditions": list(
                    record.get("invalidation_conditions", []) or []
                ),
                "created_at": record.get("created_at", ""),
            }
        )

    return results

