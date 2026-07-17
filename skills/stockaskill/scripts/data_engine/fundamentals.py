"""Core data engine: fundamentals module."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from cache import get_cache
from utils import (
    normalize_code_for_market,
    safe_float,
)

from data_engine.config import (
    _akshare_lock,
    _api_call,
    _report_no_data,
    _try_akshare,
    _try_yfinance,
)
from data_engine.helpers import (
    _backfill_missing_factors,
    _backfill_valuation_from_price,
)
from data_engine.kline import _yfinance_symbol

_cache = get_cache()
logger = logging.getLogger(__name__)


@_api_call("fundamentals_yf")
def _fetch_fundamentals_yfinance(
    code: str,
    market: str,
    yf,
) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals from yfinance (HK/US markets)."""
    symbol = _yfinance_symbol(code, market)
    if market not in ("HK", "US"):
        return None
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info:
            return None
        today = datetime.now().strftime("%Y-%m-%d")
        # Normalize yfinance scales to match AKShare expectations:
        # - dividendYield: 0-1 fraction (not percentage)
        # - roe/roa: decimal (0.15 = 15%)
        # - debtToEquity: raw ratio (1.5 = 1.5, not percentage)
        # - growth/margins: decimal
        _div_yield = safe_float(info.get("dividendYield", 0))
        if _div_yield > 1:
            _div_yield /= 100.0
        _debt = safe_float(info.get("debtToEquity", 0))
        if _debt > 10:
            _debt /= 100.0
        return {
            "code": code,
            "date": today,
            "market_cap": safe_float(info.get("marketCap", 0)),
            "pe_ttm": safe_float(info.get("trailingPE", 0)),
            "pe_static": safe_float(info.get("forwardPE", info.get("trailingPE", 0))),
            "pb": safe_float(info.get("priceToBook", 0)),
            "ps_ttm": safe_float(info.get("priceToSalesTrailing12Months", 0)),
            "pcf_ttm": safe_float(info.get("priceToCashflow", 0)),
            "dividend_yield": _div_yield,
            "roe": safe_float(info.get("returnOnEquity", 0)) / 100.0
            if safe_float(info.get("returnOnEquity", 0)) > 1
            else safe_float(info.get("returnOnEquity", 0)),
            "roa": safe_float(info.get("returnOnAssets", 0)) / 100.0
            if safe_float(info.get("returnOnAssets", 0)) > 1
            else safe_float(info.get("returnOnAssets", 0)),
            "gross_margin": safe_float(info.get("grossMargins", 0)),
            "net_margin": safe_float(info.get("profitMargins", 0)),
            "revenue_growth": safe_float(info.get("revenueGrowth", 0)),
            "profit_growth": safe_float(info.get("earningsGrowth", 0)),
            "debt_ratio": _debt,
            "current_ratio": safe_float(info.get("currentRatio", 0)),
            "eps": safe_float(info.get("trailingEps", 0)),
            "bvps": safe_float(info.get("bookValue", 0)),
        }
    except Exception:
        return None


def get_fundamentals(
    code: str,
    market: str = "A",
    force_refresh: bool = False,
    cached_only: bool = False,
    max_age_days: int = 120,
) -> Optional[Dict[str, Any]]:
    """Get latest fundamental snapshot. Graceful degradation."""
    code = normalize_code_for_market(code, market)
    cached = _cache.get_latest_factor_snapshot(code, market=market)
    if cached_only:
        return cached
    if cached and not force_refresh:
        # Add TTL check: if cached data is stale, refresh it.
        date_str = str(cached.get("date", "")).strip()
        if date_str:
            try:
                snapshot_date = datetime.strptime(date_str, "%Y-%m-%d")
                if (datetime.now() - snapshot_date).days <= max_age_days:
                    return cached
            except ValueError:
                pass
    try:
        snapshot = _fetch_fundamentals(code, market)
        if snapshot:
            snapshot["market"] = market
            _backfill_missing_factors(snapshot, code, market)
            _cache.upsert_factor_snapshot([snapshot])
            return snapshot
    except RuntimeError as exc:
        msg = str(exc)
        if "Daily API limit reached" in msg:
            logger.debug("get_fundamentals API limit for %s, using cache", code)
        else:
            logger.warning("get_fundamentals fetch failed for %s: %s", code, exc)
    except Exception as exc:
        logger.warning("get_fundamentals fetch failed for %s: %s", code, exc)
    return cached


def _fetch_fundamentals_us_akshare(code: str, ak) -> Optional[Dict[str, Any]]:
    """Fetch US stock fundamentals via AKShare stock_financial_us_analysis_indicator_em.

    Returns a dict with the same schema as other fundamental fetchers.
    """
    try:
        with _akshare_lock:
            df = ak.stock_financial_us_analysis_indicator_em(symbol=code)
    except Exception:
        return None
    if df is None or df.empty:
        return None

    # Latest report row (AKShare returns newest first, row 0 = most recent)
    latest = df.iloc[0]
    today = datetime.now().strftime("%Y-%m-%d")

    def _get_num(col: str, default: float = 0.0) -> float:
        """Safely extract a numeric value from the AKShare DataFrame."""
        try:
            val = latest.get(col)
            if val is None or str(val).strip() in ("", "--", "-"):
                return default
            if isinstance(val, float) and val != val:  # NaN check
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    # EPS / BVPS (BPS not available, derive from equity ratio)
    eps = _get_num("BASIC_EPS")
    bvps = 0.0

    # PE/PB — compute from price if not directly available
    pe_ttm = _get_num("PE_TTM")
    pb = _get_num("PB")
    if pe_ttm <= 0 and eps > 0:
        # Fallback: compute PE from cached close price
        cached_rows = _cache.get_daily_price(code, market="US")
        if cached_rows:
            closes = [r.get("close", 0) for r in cached_rows if r.get("close", 0) > 0]
            if closes:
                pe_ttm = round(closes[-1] / eps, 2)
    if pb <= 0 and bvps > 0:
        cached_rows = _cache.get_daily_price(code, market="US")
        if cached_rows:
            closes = [r.get("close", 0) for r in cached_rows if r.get("close", 0) > 0]
            if closes:
                pb = round(closes[-1] / bvps, 2)

    # Growth rates (AKShare returns percentage, convert to decimal)
    revenue_growth = _get_num("OPERATE_INCOME_YOY") / 100.0
    profit_growth = _get_num("PARENT_HOLDER_NETPROFIT_YOY") / 100.0

    # ROE/ROA (AKShare returns percentage, convert to decimal)
    roe = _get_num("ROE_AVG") / 100.0
    roa = _get_num("ROA") / 100.0

    # Margins (AKShare returns percentage, convert to decimal)
    gross_margin = _get_num("GROSS_PROFIT_RATIO") / 100.0
    net_margin = _get_num("NET_PROFIT_RATIO") / 100.0

    # Debt / liquidity (AKShare returns percentage for ratios)
    debt_ratio = _get_num("DEBT_ASSET_RATIO") / 100.0
    current_ratio = _get_num("CURRENT_RATIO")

    return {
        "code": code,
        "date": today,
        "market_cap": 0.0,
        "pe_ttm": pe_ttm,
        "pe_static": pe_ttm,
        "pb": pb,
        "ps_ttm": 0.0,
        "pcf_ttm": 0.0,
        "dividend_yield": 0.0,
        "roe": roe,
        "roa": roa,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "revenue_growth": revenue_growth,
        "profit_growth": profit_growth,
        "debt_ratio": debt_ratio,
        "current_ratio": current_ratio,
        "eps": eps,
        "bvps": bvps,
    }


def _fetch_fundamentals(code: str, market: str) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals from available source (THS -> Sina -> yfinance).

    For A-shares: THS provides detailed financials (ROE, margins, growth).
    PE/PB are computed from cached price + EPS/BVPS when available.
    For US/HK: yfinance is the primary source (AKShare US financials unreliable).
    """
    # US: AKShare first (yfinance often rate-limited)
    if market == "US":
        ak = _try_akshare()
        if ak is not None:
            result = _fetch_fundamentals_us_akshare(code, ak)
            if result:
                _backfill_valuation_from_price(result, code, market)
                return result
        # Fallback: yfinance
        yf = _try_yfinance()
        if yf is not None:
            result = _fetch_fundamentals_yfinance(code, market, yf)
            if result:
                _backfill_valuation_from_price(result, code, market)
                return result

    # HK: yfinance first (AKShare US/HK financial endpoints are unreliable)
    if market == "HK":
        yf = _try_yfinance()
        if yf is not None:
            result = _fetch_fundamentals_yfinance(code, market, yf)
            if result:
                _backfill_valuation_from_price(result, code, market)
                return result
        ak = _try_akshare()
        if ak is not None:
            result = _fetch_fundamentals_hk_analysis(code, ak)
            if result:
                _backfill_valuation_from_price(result, code, market)
                return result

    # A-shares: THS -> Sina path
    ak = _try_akshare()
    result: Optional[Dict[str, Any]] = None
    if ak is not None:
        ths_result = _fetch_fundamentals_ths(code, ak)
        sina_result = _fetch_fundamentals_ak(code, market, ak)
        if ths_result is not None:
            result = ths_result
            if sina_result is not None:
                for vk in (
                    "market_cap",
                    "pe_ttm",
                    "pe_static",
                    "pb",
                    "ps_ttm",
                    "pcf_ttm",
                    "dividend_yield",
                ):
                    if sina_result.get(vk) and not result.get(vk):
                        result[vk] = sina_result[vk]
        else:
            result = sina_result
    if result:
        _backfill_valuation_from_price(result, code, market)
        return result
    _report_no_data(code, market, "fundamentals")
    return None


def _fetch_fundamentals_ths(code: str, ak) -> Optional[Dict[str, Any]]:
    """Fetch A-share fundamentals via THS financial abstract (primary source).

    Provides richer data than the Sina fallback, including recent-period
    revenue, profit, margins, ROE, leverage, and liquidity ratios.
    """
    try:
        with _akshare_lock:
            df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    except Exception:
        return None
    if df is None or df.empty:
        return None

    latest = df.iloc[-1]
    today = datetime.now().strftime("%Y-%m-%d")
    result = {
        "code": code,
        "date": today,
        "market_cap": 0.0,
        "pe_ttm": 0.0,
        "pe_static": 0.0,
        "pb": 0.0,
        "ps_ttm": 0.0,
        "pcf_ttm": 0.0,
        "dividend_yield": 0.0,
        "roe": 0.0,
        "roa": 0.0,
        "gross_margin": 0.0,
        "net_margin": 0.0,
        "revenue_growth": 0.0,
        "profit_growth": 0.0,
        "debt_ratio": 0.0,
        "current_ratio": 0.0,
        "eps": 0.0,
        "bvps": 0.0,
    }
    _map_ths_field(latest, "基本每股收益", result, "eps")
    _map_ths_field(latest, "每股净资产", result, "bvps")
    _map_ths_field(latest, "净资产收益率", result, "roe")
    _map_ths_field(latest, "销售毛利率", result, "gross_margin")
    _map_ths_field(latest, "销售净利率", result, "net_margin")
    _map_ths_field(latest, "资产负债率", result, "debt_ratio")
    _map_ths_field(latest, "营业总收入同比增长率", result, "revenue_growth")
    _map_ths_field(latest, "净利润同比增长率", result, "profit_growth")
    _map_ths_field(latest, "流动比率", result, "current_ratio")
    return result


def _parse_chinese_number(text: Any) -> float:
    """Convert a Chinese-formatted number string to float.

    Handles formats like:
      "8827.11万" -> 88271100.0
      "29.57亿"   -> 2957000000.0
      "31.00%"    -> 0.31
      "0.1040"    -> 0.104
      "--"        -> 0.0
    """
    if text is None:
        return 0.0
    if isinstance(text, (int, float)):
        return float(text) if not (isinstance(text, float) and text != text) else 0.0
    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s or s in ("--", "-", ""):
        return 0.0
    if s.endswith("%"):
        try:
            return float(s[:-1]) / 100.0
        except (ValueError, TypeError):
            return 0.0
    multiplier = 1.0
    if s.endswith("亿"):
        multiplier = 1e8
        s = s[:-1]
    elif s.endswith("万"):
        multiplier = 1e4
        s = s[:-1]
    elif s.endswith("元"):
        s = s[:-1]
    try:
        return float(s) * multiplier
    except (ValueError, TypeError):
        return 0.0


def _map_ths_field(row, col_name: str, target: dict, key: str) -> None:
    """Extract a field from a THS financial abstract row into a target dict.

    ``_parse_chinese_number`` already handles percentage (``%``) and
            Chinese-unit (``万``/``亿``) suffixes.
    """
    if col_name not in row.index:
        return
    target[key] = _parse_chinese_number(row[col_name])


@_api_call("fundamentals_hk")
def _fetch_fundamentals_hk_analysis(code: str, ak) -> Optional[Dict[str, Any]]:
    """Fetch HK fundamentals via stock_financial_hk_analysis_indicator_em.

    The older stock_financial_hk_report_em endpoint currently returns an HTML
    error page for most HK stocks; this function uses the working alternative.
    """
    try:
        with _akshare_lock:
            df = ak.stock_financial_hk_analysis_indicator_em(symbol=code)
        if df is None or df.empty:
            return None
        row = df.iloc[0]
        # Use REPORT_DATE if available, else today
        date_str = str(row.get("REPORT_DATE", ""))[:10]
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        return {
            "code": code,
            "date": date_str,
            "market": "HK",
            "market_cap": 0.0,  # backfilled from price later
            "pe_ttm": 0.0,
            "pe_static": 0.0,
            "pb": 0.0,
            "ps_ttm": 0.0,
            "pcf_ttm": 0.0,
            "dividend_yield": 0.0,
            "roe": safe_float(row.get("ROE_AVG", 0)) / 100.0,
            "roa": safe_float(row.get("ROA", 0)) / 100.0,
            "gross_margin": safe_float(row.get("GROSS_PROFIT_RATIO", 0)) / 100.0,
            "net_margin": safe_float(row.get("NET_PROFIT_RATIO", 0)) / 100.0,
            "revenue_growth": safe_float(row.get("OPERATE_INCOME_YOY", 0)) / 100.0,
            "profit_growth": safe_float(row.get("HOLDER_PROFIT_YOY", 0)) / 100.0,
            "debt_ratio": safe_float(row.get("DEBT_ASSET_RATIO", 0)) / 100.0,
            "current_ratio": safe_float(row.get("CURRENT_RATIO", 0)),
            "eps": safe_float(row.get("EPS_TTM", 0)),
            "bvps": safe_float(row.get("BPS", 0)),
        }
    except Exception:
        return None


@_api_call("fundamentals")
def _fetch_fundamentals_ak(code: str, market: str, ak) -> Optional[Dict[str, Any]]:
    """Fetch fundamentals via Sina financial abstract.

    Extracts ALL quarterly periods from the API response (not just the latest),
    enabling point-in-time historical backtesting.
    """
    try:
        with _akshare_lock:
            if market == "A":
                df = ak.stock_financial_report_sina(symbol=code, name="主要指标")
            elif market == "HK":
                result = _fetch_fundamentals_hk_analysis(code, ak)
                if result:
                    return result
                # Fallback: try the old endpoint (may work for some stocks)
                df = ak.stock_financial_hk_report_em(symbol=code)
            elif market == "US":
                df = ak.stock_financial_us_report_em(symbol=code)
            else:
                return None
        if df is None or df.empty or len(df.columns) < 3:
            return None

        # Discover date columns (columns that look like dates)
        date_cols = []
        for col_idx in range(2, len(df.columns)):
            col_name = str(df.columns[col_idx])
            if len(col_name.replace("-", "")) >= 6:
                date_cols.append(col_name)

        if not date_cols:
            date_cols = [df.columns[2]]

        def _parse_one_period(df, col_name: str) -> Dict[str, Any]:
            """Build one fundamental snapshot from a single period column."""
            snap: Dict[str, Any] = {
                "code": code,
                "date": col_name,
                "market_cap": 0.0,
                "pe_ttm": 0.0,
                "pe_static": 0.0,
                "pb": 0.0,
                "ps_ttm": 0.0,
                "pcf_ttm": 0.0,
                "dividend_yield": 0.0,
                "roe": 0.0,
                "roa": 0.0,
                "gross_margin": 0.0,
                "net_margin": 0.0,
                "revenue_growth": 0.0,
                "profit_growth": 0.0,
                "debt_ratio": 0.0,
                "current_ratio": 0.0,
                "eps": 0.0,
                "bvps": 0.0,
            }
            for i in range(len(df)):
                name = str(df.iloc[i, 1])
                val = df.iloc[i][col_name]
                if val is None or (isinstance(val, float) and (val != val)):
                    continue
                v = safe_float(val)
                if name == "基本每股收益":
                    snap["eps"] = v
                elif name == "每股净资产":
                    snap["bvps"] = v
                elif name == "净资产收益率(ROE)":
                    snap["roe"] = v / 100.0
                elif name == "毛利率":
                    snap["gross_margin"] = v / 100.0
                elif name == "销售净利率":
                    snap["net_margin"] = v / 100.0
                elif name == "资产负债率":
                    snap["debt_ratio"] = v / 100.0
                elif name == "营业收入增长率":
                    snap["revenue_growth"] = v / 100.0
                elif name == "归属母公司净利润增长率":
                    snap["profit_growth"] = v / 100.0
                elif name == "流动比率":
                    snap["current_ratio"] = v
            return snap

        # HK/US: return only latest (API structure differs)
        if market != "A":
            result = _parse_one_period(df, date_cols[0])
            result["market"] = market
            return result

        # A-shares: extract ALL periods for point-in-time history
        snapshots = []
        for dc in date_cols:
            snap = _parse_one_period(df, dc)
            snap["market"] = market
            snapshots.append(snap)

        if snapshots:
            _cache.upsert_factor_snapshot(snapshots)
            # Return the latest for API compatibility
            return snapshots[0]
        return None
    except Exception:
        return None
