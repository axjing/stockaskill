"""Sentiment analysis module."""

from sentiment.aggregator import SentimentAggregator
from sentiment.dictionary import analyze_sentiment

__all__ = [
    "SentimentAggregator",
    "analyze_sentiment",
]
