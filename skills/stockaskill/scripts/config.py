"""Pure-Python config with dot-path access. No YAML dependency."""

import copy
import os
import json
from pathlib import Path
from typing import Any, Dict

_DEFAULTS: Dict[str, Any] = {
    "watchlist": ["002475", "600519", "601318", "000858", "600036"],
    "factor_weights": {
        "value": 0.2,
        "quality": 0.25,
        "growth": 0.17,
        "momentum": 0.17,
        "low_vol": 0.11,
        "size": 0.09,
    },
    "enhanced_weights": {
        "momentum": 0.35,
        "low_vol": 0.18,
        "quality": 0.20,
        "value": 0.17,
        "growth": 0.10,
    },
    "etf_core": [
        {"code": "510300", "name": "沪深300ETF", "target": 0.17},
        {"code": "159915", "name": "创业板ETF", "target": 0.12},
        {"code": "588000", "name": "科创50ETF", "target": 0.11},
    ],
    "strategy_target": {
        "cagr": 0.18,
        "max_drawdown": 0.20,
        "max_positions": 6,
    },
    "signal_thresholds": {
        "buy": 65,
        "sell": 35,
        "buy_consensus_count": 4,
        "sell_consensus_count": 4,
    },
    "cache_ttl": {
        "realtime": 60,
        "daily_kline": 3600,
        "financial": 604800,
        "sentiment": 3600,
        "pool": 86400,
        "fund_nav": 3600,
        "scan_snapshot": 86400,
    },
    "daily_api_limit": 500,
    "scan_max_candidates": 200,
    "data_readiness": {
        "analysis_history_days": 365,
        "analysis_fundamentals_max_age_days": 120,
        "scan_history_days": 365,
        "scan_prefetch_limit": 200,
        "scan_pool_metadata_limit": 60,
        "scan_refresh_workers": 8,
        "scan_fundamentals": True,
        "backtest_history_days": 1500,
        "backtest_prefetch_batch": 50,
        "fund_screen_history_days": 365,
        "market_index_history_days": 1500,
    },
    "market_regime": {
        "history_days": 250,
        "breadth_history_days": 80,
        "breadth_sample_limit": 60,
        "min_breadth_sample": 15,
        "benchmarks": {
            "A": "000300",
            "HK": "2800",
            "US": "SPY",
        },
        "risk_budgets": {
            "offensive": 1.0,
            "constructive": 0.85,
            "neutral": 0.65,
            "cautious": 0.45,
            "defensive": 0.25,
        },
    },
    "request_interval": [0.5, 2.0],
    "retry_max": 3,
    "retry_base": 2,
    "retry_backoff_multiplier": 2,
    "retry_max_delay": 30,
    "pool_size_warn_min": 4000,
    "pool_size_warn_max": 6000,
    "fetch_timeout": 15,  # HTTP request timeout in seconds
    "fund_metadata_completeness_default": 0.25,
    "metadata_completeness_threshold": 0.75,
    "full_history_start_date": "20000101",
    "kline_incremental_padding_days": 30,
    "market_index_default_code": "000001",
    "market_index_default_days": 250,
    "kline_years": 3,
    "financial_reports": 8,
    "low_vol_min": 0.4,
    "commission": 0.0003,
    "stamp_tax": 0.001,
    "slippage": 0.001,
    "alpha_momentum": {
        "default_market": "A",
        "weights": {
            "momentum": 0.30,
            "low_vol": 0.28,
            "quality": 0.21,
            "value": 0.14,
            "growth": 0.07,
        },
        "top_k": 6,
        "max_per_board": 3,
        "min_kline_bars": 120,
        "min_history_bars": 1500,
        "start_date": "2018-01-01",
        "window_ranges": [
            ["2017-01-01", "2019-12-31"],
            ["2019-01-01", "2021-12-31"],
            ["2021-01-01", "2023-12-31"],
            ["2023-01-01", "2026-12-31"],
        ],
        "lot_size": 100,
    },
    "factor_ranges": {
        "value": {
            "A": {"pe": [5, 80], "pb": [0.5, 10], "dy": [0, 6]},
            "HK": {"pe": [2, 60], "pb": [0.2, 8], "dy": [0, 8]},
            "US": {"pe": [5, 100], "pb": [0.5, 15], "dy": [0, 4]},
        },
        "size": {
            "A": {"mcap": [23.03, 28.73]},
            "HK": {"mcap": [22.33, 29.53]},
            "US": {"mcap": [24.63, 31.93]},
        },
        "low_vol": {
            "A": {"vol": [0.01, 0.05], "max_drop": [0.03, 0.10]},
            "HK": {"vol": [0.015, 0.06], "max_drop": [0.03, 0.12]},
            "US": {"vol": [0.015, 0.07], "max_drop": [0.04, 0.15]},
        },
        "growth": {
            "A": {"revenue": [-0.5, 1.0], "profit": [-0.8, 2.0], "accel": [-0.3, 0.3]},
            "HK": {"revenue": [-0.6, 1.0], "profit": [-1.0, 2.0], "accel": [-0.3, 0.3]},
            "US": {"revenue": [-0.4, 1.0], "profit": [-0.8, 1.5], "accel": [-0.2, 0.4]},
        },
        "quality": {
            "A": {
                "roe": [-0.2, 0.4],
                "gross_margin": [0, 0.8],
                "debt": [0, 1],
                "net_margin": [-0.1, 0.3],
            },
            "HK": {
                "roe": [-0.15, 0.35],
                "gross_margin": [0, 0.7],
                "debt": [0, 1],
                "net_margin": [-0.1, 0.4],
            },
            "US": {
                "roe": [-0.25, 0.5],
                "gross_margin": [0, 0.85],
                "debt": [0, 1],
                "net_margin": [-0.15, 0.35],
            },
        },
        "momentum": {
            "A": {"ret_6m": [-0.4, 0.8]},
            "HK": {"ret_6m": [-0.5, 0.9]},
            "US": {"ret_6m": [-0.5, 1.0]},
        },
    },
    "sentiment": {
        "guba_max_posts": 20,
        "fallback_kline_days": 10,
        "ret_sentiment_multiplier": 5,
        "ret_hot_multiplier": 3,
        "north_flow_lookback_days": 20,
        "north_flow_recent_days": 5,
        "north_flow_norm_shift": 50000000000,
        "north_flow_norm_scale": 100000000000,
        "breadth_weight": 0.4,
        "north_weight": 0.3,
        "base_weight": 0.3,
        "adjustment_min": 0.8,
        "adjustment_range": 0.35,
        "stock_weight": 0.4,
        "market_weight": 0.6,
    },
    "expand_pool": {
        "default_batch_size": 50,
        "fetch_delay_seconds": 3,
        "min_history_bars": 1500,
    },
    "report": {
        "output_dir": "reports",
    },
    "thesis_memory": {
        "storage_dir": "memory/theses",
        "default_limit": 10,
    },
    "theme_research": {
        "default_limit": 3,
        "candidate_limit": 120,
        "supported_themes": {
            "ai_infra": {
                "aliases": ["ai", "ai基础设施", "算力", "ai infra", "人工智能"],
                "key_question": "真实扩产首先卡在哪一层，而不是谁最会讲故事。",
                "next_checks": [
                    "核对客户扩产节奏与订单兑现证据",
                    "核对毛利率和产能利用率是否验证卡点地位",
                    "核对是否存在绕开该层的技术替代",
                ],
                "lower_priority_areas": [
                    "纯概念应用层通常离真实扩产约束更远",
                    "只讲 GPU 叙事但缺少订单验证的标的先降级",
                ],
                "layers": [
                    {
                        "name": "先进封装与测试",
                        "scarce_layer": "先进封装设备/测试验证",
                        "why_here": "这一层更接近真实扩产瓶颈，客户切换成本更高。",
                        "keywords": [
                            "封装",
                            "测试",
                            "chiplet",
                            "先进封装",
                            "半导体设备",
                        ],
                        "evidence": [
                            "如果扩产受限，通常先反映在封装和测试验证环节",
                            "设备/工艺验证周期较长，容易形成产业链卡点",
                        ],
                    },
                    {
                        "name": "光通信与互连",
                        "scarce_layer": "高速光模块/连接材料",
                        "why_here": "带宽升级往往先卡在互连，而不是最显眼的终端叙事。",
                        "keywords": ["光模块", "光通信", "连接器", "CPO", "光器件"],
                        "evidence": [
                            "带宽扩张需要互连同步升级",
                            "互连层的验证和良率会影响整机交付节奏",
                        ],
                    },
                    {
                        "name": "电源与散热",
                        "scarce_layer": "服务器电源/热管理",
                        "why_here": "功耗抬升后，供电和散热约束会更快暴露。",
                        "keywords": ["电源", "散热", "液冷", "热管理", "服务器"],
                        "evidence": [
                            "系统功耗抬升后，电源与散热成为硬约束",
                            "这类环节往往能更早看到扩产与交付压力",
                        ],
                    },
                ],
            },
            "robotics": {
                "aliases": ["机器人", "robot", "automation", "自动化"],
                "key_question": "机器人渗透最先卡在控制、执行还是集成验证。",
                "next_checks": [
                    "核对客户导入节奏和真实量产验证",
                    "核对是否拥有不可替代的执行器或控制能力",
                    "核对毛利率和应收变化是否支持渗透逻辑",
                ],
                "lower_priority_areas": [
                    "单纯概念映射、没有出货验证的整机故事先降级",
                ],
                "layers": [
                    {
                        "name": "核心零部件",
                        "scarce_layer": "减速器/伺服/控制器",
                        "why_here": "核心执行与控制件更接近替代难点。",
                        "keywords": ["减速器", "伺服", "控制器", "电机", "自动化"],
                        "evidence": [
                            "零部件层更能反映真实替代难度",
                        ],
                    },
                    {
                        "name": "机器视觉与传感",
                        "scarce_layer": "感知与定位能力",
                        "why_here": "感知可靠性会直接影响产线可复制性。",
                        "keywords": ["视觉", "传感", "激光", "检测", "工业相机"],
                        "evidence": [
                            "感知层稳定性决定机器人可用边界",
                        ],
                    },
                    {
                        "name": "系统集成",
                        "scarce_layer": "场景集成与交付能力",
                        "why_here": "集成层靠项目交付，但护城河通常弱于核心件。",
                        "keywords": ["集成", "系统", "产线", "方案"],
                        "evidence": [
                            "系统层更偏工程交付，议价能力常弱于核心件",
                        ],
                    },
                ],
            },
            "battery": {
                "aliases": ["电池", "储能", "battery", "新能源"],
                "key_question": "扩产和盈利真正卡在材料、设备还是系统侧。",
                "next_checks": [
                    "核对供需、价格和盈利是否同步改善",
                    "核对材料技术路线是否发生变化",
                    "核对设备订单与下游扩产节奏是否一致",
                ],
                "lower_priority_areas": [
                    "纯景气交易但缺少技术/份额改善的方向先降级",
                ],
                "layers": [
                    {
                        "name": "上游材料",
                        "scarce_layer": "关键正负极/电解液/隔膜",
                        "why_here": "材料环节更容易体现技术路线和成本约束。",
                        "keywords": ["材料", "电解液", "隔膜", "正极", "负极"],
                        "evidence": [
                            "材料层更接近成本与良率约束",
                        ],
                    },
                    {
                        "name": "设备与制造",
                        "scarce_layer": "生产设备与工艺良率",
                        "why_here": "设备交付和良率爬坡通常领先反映扩产。",
                        "keywords": ["设备", "制造", "锂电设备", "检测", "涂布"],
                        "evidence": [
                            "设备层能更早看到资本开支兑现",
                        ],
                    },
                    {
                        "name": "储能系统",
                        "scarce_layer": "系统集成与交付验证",
                        "why_here": "系统层更接近收入兑现，但卡点未必最强。",
                        "keywords": ["储能", "系统", "逆变器", "BMS"],
                        "evidence": [
                            "系统层通常更接近订单兑现，但不一定控制卡点",
                        ],
                    },
                ],
            },
        },
    },
}

_cache: Dict[str, Any] | None = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* and return *base*."""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> Dict[str, Any]:
    """Return cached defaults. Supports env override via STOCKASKILL_CONFIG."""
    global _cache
    if _cache is not None:
        return _cache
    _cache = copy.deepcopy(_DEFAULTS)
    config_path = os.environ.get("STOCKASKILL_CONFIG")
    if config_path and Path(config_path).is_file():
        with open(config_path) as f:
            user_config = json.load(f)
        _deep_merge(_cache, user_config)
    return _cache


def get(key: str, default: Any = None) -> Any:
    """Dot-path access: get('factor_weights.value') -> 0.18."""
    parts = key.split(".")
    val: Any = load_config()
    for p in parts:
        if isinstance(val, dict):
            val = val.get(p, default)
        else:
            return default
    return val


def signal_from_score(score: float) -> str:
    """Return 'BUY'/'SELL'/'HOLD' based on configured thresholds."""
    buy = get("signal_thresholds.buy", 65)
    sell = get("signal_thresholds.sell", 35)
    if score >= buy:
        return "BUY"
    if score <= sell:
        return "SELL"
    return "HOLD"


def signal_thresholds() -> dict:
    """Return the full signal threshold config."""
    return get("signal_thresholds", {"buy": 65, "sell": 35, "buy_consensus_count": 4})
