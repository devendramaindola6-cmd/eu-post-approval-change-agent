"""Small UI matching helpers for guided Streamlit selectors."""
from __future__ import annotations

import re
from difflib import SequenceMatcher


QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "i",
    "in",
    "is",
    "need",
    "please",
    "the",
    "to",
    "change",
    "modify",
    "update",
    "want",
    "wnat",
    "would",
}

QUERY_SYNONYMS = {
    "analysis": {"test", "procedure"},
    "analyses": {"test", "procedure"},
    "analytical": {"test", "procedure"},
    "assay": {"test", "procedure"},
    "method": {"test", "procedure"},
    "methods": {"test", "procedure"},
    "testing": {"test"},
    "validation": {"test", "procedure"},
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").casefold())


def _meaningful_query_terms(query: str) -> list[str]:
    terms = [token for token in _tokens(query) if token not in QUERY_STOPWORDS]
    expanded_terms = set()
    for term in terms:
        expanded_terms.update(QUERY_SYNONYMS.get(term, {term}))
    return sorted(expanded_terms)


def _token_matches(query_term: str, option_token: str) -> bool:
    if query_term == option_token:
        return True
    if len(query_term) >= 3 and option_token.startswith(query_term):
        return True
    if len(query_term) >= 4 and SequenceMatcher(None, query_term, option_token).ratio() >= 0.82:
        return True
    return False


def _option_match_score(option: str, query_terms: list[str]) -> tuple[int, int, str]:
    option_tokens = _tokens(option)
    matched_terms = sum(
        1
        for term in query_terms
        if any(_token_matches(term, option_token) for option_token in option_tokens)
    )
    exact_phrase_bonus = 1 if " ".join(query_terms) in " ".join(option_tokens) else 0
    return matched_terms, exact_phrase_bonus, str(option).casefold()


def _direct_match_count(option: str, query: str) -> int:
    option_tokens = _tokens(option)
    return sum(
        1
        for term in _tokens(query)
        if term not in QUERY_STOPWORDS
        and any(_token_matches(term, option_token) for option_token in option_tokens)
    )


def filter_options_by_query(options, query: str) -> list[str]:
    query_terms = _meaningful_query_terms(query)
    if not query_terms:
        return []

    scored_options = [
        (_option_match_score(option, query_terms), option)
        for option in options
    ]
    matches = [
        (score, option)
        for score, option in scored_options
        if score[0] == len(query_terms)
    ]
    if not matches:
        matches = [
            (score, option)
            for score, option in scored_options
            if score[0] >= 2 and _direct_match_count(option, query) >= 1
        ]
    return [
        option
        for _, option in sorted(matches, key=lambda scored: (-scored[0][1], scored[0][2]))
    ]
