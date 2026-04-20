"""Tokenization helpers shared by sparse retrieval indexes."""

import re
from pathlib import Path
from re import Pattern

import jieba

_TERM_PATTERN: Pattern[str] = re.compile(r"\w", re.UNICODE)


def load_stopwords(path: Path | str) -> set[str]:
    with Path(path).open(encoding="utf-8") as f:
        return {word.strip() for word in set(f.read().splitlines()) if word.strip()}


def tokenize_text(text: str, stopwords: set[str]) -> list[str]:
    tokens = []
    for token in jieba.cut(text or ""):
        token = token.strip()
        if not token or token in stopwords:
            continue
        if not _TERM_PATTERN.search(token):
            continue
        tokens.append(token)
    return tokens


def to_fts5_search_text(text: str, stopwords: set[str]) -> str:
    return " ".join(tokenize_text(text, stopwords))


def quote_fts5_token(token: str) -> str:
    return '"' + token.replace('"', '""') + '"'


def build_fts5_or_query(tokens: list[str]) -> str:
    quoted_tokens = [quote_fts5_token(token) for token in tokens if token]
    return " OR ".join(quoted_tokens)
