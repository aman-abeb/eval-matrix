"""Unit tests for text similarity algorithms and token estimation in evalmatrix.metrics."""

import pytest

from evalmatrix.metrics import (
    compute_similarity,
    estimate_prompt_and_completion_tokens,
    estimate_token_count,
    get_character_ngrams,
    get_word_ngrams,
    jaccard_similarity,
    levenshtein_distance,
    levenshtein_similarity,
    ngram_dice_similarity,
)


def test_levenshtein_distance_exact_and_empty():
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("abc", "abc") == 0
    assert levenshtein_distance("", "hello") == 5
    assert levenshtein_distance("world", "") == 5


def test_levenshtein_distance_known_words():
    assert levenshtein_distance("kitten", "sitting") == 3
    assert levenshtein_distance("flaw", "lawn") == 2
    assert levenshtein_distance("billing", "billing") == 0
    assert levenshtein_distance("invoice", "invoices") == 1


def test_levenshtein_similarity_bounds():
    assert levenshtein_similarity("hello", "hello") == 1.0
    assert levenshtein_similarity("", "") == 1.0
    assert levenshtein_similarity("abc", "xyz") == 0.0
    sim = levenshtein_similarity("support", "supprot")
    assert 0.70 < sim < 0.90


def test_get_character_ngrams():
    ngrams = get_character_ngrams("hello", n=3)
    assert ngrams == ["hel", "ell", "llo"]

    # Shorter than n returns full string as single item
    short_ngrams = get_character_ngrams("hi", n=3)
    assert short_ngrams == ["hi"]
    assert get_character_ngrams("", n=3) == []

    with pytest.raises(ValueError, match="greater than 0"):
        get_character_ngrams("hello", n=0)


def test_get_word_ngrams():
    ngrams = get_word_ngrams("the quick brown fox", n=2)
    assert ngrams == ["the quick", "quick brown", "brown fox"]

    single_word = get_word_ngrams("hello", n=2)
    assert single_word == ["hello"]
    assert get_word_ngrams("", n=2) == []

    with pytest.raises(ValueError, match="greater than 0"):
        get_word_ngrams("hello", n=-1)


def test_jaccard_similarity():
    # Exact match
    assert jaccard_similarity("quick fox", "quick fox") == 1.0
    # Disjoint strings
    assert jaccard_similarity("aaaa", "bbbb") == 0.0
    # Word mode
    word_sim = jaccard_similarity("refund invoice payment", "refund invoice charge", n=1, mode="word")
    assert 0.4 < word_sim < 0.6


def test_ngram_dice_similarity():
    assert ngram_dice_similarity("exact match", "exact match") == 1.0
    assert ngram_dice_similarity("abc", "xyz") == 0.0
    dice_sim = ngram_dice_similarity("billing query", "billing request", n=3, mode="char")
    assert 0.4 < dice_sim < 0.8


def test_compute_similarity_metrics():
    s1 = "Customer payment inquiry"
    s2 = "Customer payment request"

    lev_score = compute_similarity(s1, s2, metric="levenshtein")
    assert 0.7 < lev_score < 1.0

    jaccard_score = compute_similarity(s1, s2, metric="jaccard")
    assert 0.4 < jaccard_score < 1.0

    dice_score = compute_similarity(s1, s2, metric="dice")
    assert 0.5 < dice_score < 1.0

    word_jaccard = compute_similarity(s1, s2, metric="word_jaccard")
    assert 0.5 <= word_jaccard <= 0.8

    word_dice = compute_similarity(s1, s2, metric="word_dice")
    assert 0.0 <= word_dice <= 1.0


def test_compute_similarity_case_insensitivity():
    s1 = "Hello WORLD"
    s2 = "hello world"
    assert compute_similarity(s1, s2, metric="levenshtein", case_sensitive=True) < 1.0
    assert compute_similarity(s1, s2, metric="levenshtein", case_sensitive=False) == 1.0


def test_compute_similarity_unknown_metric():
    with pytest.raises(ValueError, match="Unsupported similarity metric"):
        compute_similarity("a", "b", metric="non_existent_metric")


def test_estimate_token_count_empty():
    assert estimate_token_count("") == 0
    assert estimate_token_count(None) == 0


def test_estimate_token_count_methods():
    text = "The quick brown fox jumps over the lazy dog."
    heuristic_tokens = estimate_token_count(text, method="heuristic")
    assert 8 <= heuristic_tokens <= 15

    char_tokens = estimate_token_count(text, method="char")
    assert 8 <= char_tokens <= 15

    word_tokens = estimate_token_count(text, method="word")
    assert 8 <= word_tokens <= 16


def test_estimate_prompt_and_completion_tokens():
    p = "Classify this user request"
    c = "{\"intent\": \"billing\"}"
    p_tok, c_tok, total = estimate_prompt_and_completion_tokens(p, c)
    assert p_tok > 0
    assert c_tok > 0
    assert total == p_tok + c_tok
