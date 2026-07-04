"""Chinese financial sentiment dictionary."""

POSITIVE = {
    "利好": 1.0,
    "业绩爆发": 1.0,
    "重大突破": 1.0,
    "强势涨停": 1.0,
    "大幅增长": 1.0,
    "超预期增长": 1.0,
    "涨停": 0.8,
    "大涨": 0.8,
    "反弹": 0.8,
    "增长": 0.6,
    "回升": 0.6,
    "改善": 0.6,
    "盈利": 0.6,
    "突破": 0.6,
    "创新高": 0.6,
    "业绩增长": 0.6,
    "盈利能力": 0.6,
    "扭亏为盈": 0.6,
    "分红": 0.6,
    "回暖": 0.3,
    "企稳": 0.3,
    "震荡上行": 0.3,
    "小幅增长": 0.3,
    "利空出尽": 0.3,
}

NEGATIVE = {
    "利空": 1.0,
    "暴雷": 1.0,
    "跌停": 1.0,
    "业绩暴雷": 1.0,
    "大幅亏损": 1.0,
    "重大利空": 1.0,
    "亏损": 0.8,
    "大跌": 0.7,
    "下跌": 0.6,
    "下调": 0.6,
    "减持": 0.6,
    "利好出尽": 0.6,
    "资金流出": 0.6,
    "业绩下滑": 0.6,
    "风险提示": 0.6,
    "st": 0.6,
    "退市": 0.6,
    "震荡": 0.3,
    "波动": 0.3,
    "回调": 0.3,
    "低迷": 0.3,
    "疲软": 0.3,
}


def analyze_sentiment(text: str) -> float:
    """Analyze sentiment of a Chinese financial text.

    Args:
        text: Input text.

    Returns:
        Score in [-1, 1]. Positive = bullish, negative = bearish.
    """
    if not text:
        return 0.0

    pos_score = 0.0
    neg_score = 0.0
    total_weight = 0.0

    for word, weight in POSITIVE.items():
        if word in text:
            pos_score += weight
            total_weight += weight

    for word, weight in NEGATIVE.items():
        if word in text:
            neg_score += weight
            total_weight += weight

    if total_weight == 0:
        return 0.0

    return (pos_score - neg_score) / total_weight
