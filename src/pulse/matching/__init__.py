"""Brand matching — Boolean AST queries and alias-aware scoring."""

from pulse.matching.ast import BooleanQuery, parse_boolean_query
from pulse.matching.matcher import BrandMatchResult, match_mention_against_brands

__all__ = [
    "BooleanQuery",
    "BrandMatchResult",
    "match_mention_against_brands",
    "parse_boolean_query",
]
