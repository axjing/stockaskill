import pytest
from sentiment.dictionary import analyze_sentiment


class TestSentimentDictionary:
    def test_empty_text(self):
        assert analyze_sentiment("") == 0.0
        assert analyze_sentiment(None) == 0.0

    def test_positive_text(self):
        score = analyze_sentiment("利好大涨")
        assert score > 0

    def test_negative_text(self):
        score = analyze_sentiment("利空暴跌")
        assert score < 0

    def test_mixed_text(self):
        score = analyze_sentiment("利好利空")
        assert score == 0.0

    def test_neutral_text(self):
        score = analyze_sentiment("普通消息")
        assert score == 0.0

    def test_strong_positive(self):
        score = analyze_sentiment("大利好 业绩爆发")
        assert score > 0.5

    def test_strong_negative(self):
        score = analyze_sentiment("大利空 业绩暴雷")
        assert score < -0.5


class TestSentimentSources:
    def test_get_market_breadth_fallback(self):
        from sentiment.sources import get_market_breadth
        result = get_market_breadth()
        assert isinstance(result, dict)
        assert "sentiment_score" in result
        assert "advancers" in result

    def test_aggregate_market_sentiment(self):
        from sentiment.sources import aggregate_market_sentiment
        score = aggregate_market_sentiment()
        assert 0 <= score <= 1


class TestSentimentAggregator:
    def test_init(self):
        from sentiment.aggregator import SentimentAggregator
        agg = SentimentAggregator("601318")
        assert agg.code == "601318"
        assert agg.market == "A"

    def test_get_adjustment_factor(self):
        from sentiment.aggregator import SentimentAggregator
        agg = SentimentAggregator("601318")
        factor = agg.get_adjustment_factor()
        assert 0.8 <= factor <= 1.15

    def test_get_sentiment_report(self):
        from sentiment.aggregator import SentimentAggregator
        agg = SentimentAggregator("601318")
        report = agg.get_sentiment_report()
        assert "overall_score" in report
        assert "adjustment_factor" in report
        assert "stock_sentiment" in report
        assert "market_sentiment" in report
