"""Lexicographic ranking: level > coverage > score; inventory only breaks ties."""

from advisor.recommendation.ranking import RankedOutput, rank

__all__ = ["RankedOutput", "rank"]
