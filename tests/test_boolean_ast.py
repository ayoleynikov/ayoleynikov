"""Boolean query AST parser / evaluator tests."""

from __future__ import annotations

import pytest

from pulse.ingestion.normalize import fold_text
from pulse.matching.ast import QueryParseError, evaluate_ast, parse_boolean_query


def test_parse_and_or_not_phrase() -> None:
    q = parse_boolean_query('"Acme Corp" AND (widget OR gadget) NOT spam')
    assert q.root.type.value == "and"
    data = q.to_dict()
    assert data["source"].startswith('"Acme Corp"')
    # Round-trip
    restored = type(q).from_dict(data)
    assert restored.source == q.source


def test_evaluate_boolean_query() -> None:
    q = parse_boolean_query("Acme AND (widget OR gadget) NOT spam")
    hay = fold_text("Acme launches a new widget today")
    assert evaluate_ast(q.root, hay) is True
    hay2 = fold_text("Acme launches spam widget")
    assert evaluate_ast(q.root, hay2) is False


def test_phrase_match() -> None:
    q = parse_boolean_query('"exact phrase"')
    assert evaluate_ast(q.root, fold_text("an exact phrase here"))
    assert not evaluate_ast(q.root, fold_text("exact other phrase"))


def test_rejects_empty_and_bad_syntax() -> None:
    with pytest.raises(QueryParseError):
        parse_boolean_query("   ")
    with pytest.raises(QueryParseError):
        parse_boolean_query("(Acme AND")


def test_ast_is_not_sql() -> None:
    q = parse_boolean_query("Acme OR Beta")
    dumped = str(q.to_dict())
    assert "SELECT" not in dumped.upper()
    assert "DROP" not in dumped.upper()
