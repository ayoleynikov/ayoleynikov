"""Boolean query AST parser (AND / OR / NOT / phrases).

User query text is never interpolated into SQL — only evaluated in-process against
normalized mention text, or stored as structured AST JSON.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterator


class QueryParseError(ValueError):
    """Invalid Boolean query syntax."""


class NodeType(StrEnum):
    AND = "and"
    OR = "or"
    NOT = "not"
    TERM = "term"
    PHRASE = "phrase"


@dataclass(frozen=True, slots=True)
class QueryNode:
    type: NodeType
    value: str | None = None
    children: tuple[QueryNode, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "value": self.value,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueryNode:
        return cls(
            type=NodeType(data["type"]),
            value=data.get("value"),
            children=tuple(cls.from_dict(c) for c in data.get("children") or []),
        )


@dataclass(frozen=True, slots=True)
class BooleanQuery:
    source: str
    root: QueryNode

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "root": self.root.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BooleanQuery:
        return cls(source=data["source"], root=QueryNode.from_dict(data["root"]))


_TOKEN_RE = re.compile(
    r"""
    \s+
    | (?P<phrase>"[^"]*")
    | (?P<lparen>\()
    | (?P<rparen>\))
    | (?P<op>AND|OR|NOT)
    | (?P<term>[^\s()]+)
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _tokenize(query: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    for match in _TOKEN_RE.finditer(query):
        if match.start() != pos:
            raise QueryParseError(f"unexpected input near {query[pos:match.start()]!r}")
        pos = match.end()
        if match.group(0).isspace():
            continue
        if match.group("phrase"):
            tokens.append(("phrase", match.group("phrase")[1:-1]))
        elif match.group("lparen"):
            tokens.append(("lparen", "("))
        elif match.group("rparen"):
            tokens.append(("rparen", ")"))
        elif match.group("op"):
            tokens.append(("op", match.group("op").upper()))
        elif match.group("term"):
            tokens.append(("term", match.group("term")))
    if pos != len(query):
        raise QueryParseError(f"unexpected trailing input {query[pos:]!r}")
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.i = 0

    def _peek(self) -> tuple[str, str] | None:
        if self.i >= len(self.tokens):
            return None
        return self.tokens[self.i]

    def _advance(self) -> tuple[str, str]:
        tok = self._peek()
        if tok is None:
            raise QueryParseError("unexpected end of query")
        self.i += 1
        return tok

    def parse(self) -> QueryNode:
        if not self.tokens:
            raise QueryParseError("empty query")
        node = self._parse_or()
        if self._peek() is not None:
            raise QueryParseError(f"unexpected token {self._peek()!r}")
        return node

    def _parse_or(self) -> QueryNode:
        left = self._parse_and()
        children = [left]
        while self._peek() and self._peek()[0] == "op" and self._peek()[1] == "OR":
            self._advance()
            children.append(self._parse_and())
        if len(children) == 1:
            return children[0]
        return QueryNode(type=NodeType.OR, children=tuple(children))

    def _parse_and(self) -> QueryNode:
        left = self._parse_unary()
        children = [left]
        while True:
            nxt = self._peek()
            if nxt is None or nxt[0] == "rparen":
                break
            if nxt[0] == "op" and nxt[1] == "OR":
                break
            if nxt[0] == "op" and nxt[1] == "AND":
                self._advance()
                children.append(self._parse_unary())
                continue
            # Implicit AND between adjacent terms/groups
            if nxt[0] in {"term", "phrase", "lparen"} or (nxt[0] == "op" and nxt[1] == "NOT"):
                children.append(self._parse_unary())
                continue
            break
        if len(children) == 1:
            return children[0]
        return QueryNode(type=NodeType.AND, children=tuple(children))

    def _parse_unary(self) -> QueryNode:
        nxt = self._peek()
        if nxt and nxt[0] == "op" and nxt[1] == "NOT":
            self._advance()
            child = self._parse_unary()
            return QueryNode(type=NodeType.NOT, children=(child,))
        return self._parse_primary()

    def _parse_primary(self) -> QueryNode:
        tok = self._advance()
        kind, value = tok
        if kind == "lparen":
            node = self._parse_or()
            closing = self._advance()
            if closing[0] != "rparen":
                raise QueryParseError("expected ')'")
            return node
        if kind == "phrase":
            return QueryNode(type=NodeType.PHRASE, value=value)
        if kind == "term":
            return QueryNode(type=NodeType.TERM, value=value)
        raise QueryParseError(f"unexpected token {tok!r}")


def parse_boolean_query(query: str) -> BooleanQuery:
    """Parse a Boolean query string into an AST. Never returns SQL."""
    cleaned = query.strip()
    if not cleaned:
        raise QueryParseError("empty query")
    root = _Parser(_tokenize(cleaned)).parse()
    return BooleanQuery(source=cleaned, root=root)


def evaluate_ast(node: QueryNode, haystack_folded: str) -> bool:
    """Evaluate AST against already-folded haystack text."""
    if node.type is NodeType.TERM:
        assert node.value is not None
        needle = node.value.casefold()
        return needle in haystack_folded
    if node.type is NodeType.PHRASE:
        assert node.value is not None
        needle = " ".join(node.value.casefold().split())
        return needle in haystack_folded
    if node.type is NodeType.NOT:
        return not evaluate_ast(node.children[0], haystack_folded)
    if node.type is NodeType.AND:
        return all(evaluate_ast(c, haystack_folded) for c in node.children)
    if node.type is NodeType.OR:
        return any(evaluate_ast(c, haystack_folded) for c in node.children)
    raise QueryParseError(f"unknown node type {node.type}")


def iter_terms(node: QueryNode) -> Iterator[str]:
    if node.type in {NodeType.TERM, NodeType.PHRASE} and node.value:
        yield node.value
    for child in node.children:
        yield from iter_terms(child)
