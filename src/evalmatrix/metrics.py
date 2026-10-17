"""Offline text similarity metrics and heuristic token count estimators."""

import math
import re
from collections import Counter
from typing import Any, List, Tuple


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    Time complexity: O(len(s1) * len(s2)), Space complexity: O(min(len(s1), len(s2))).
    """
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    # Ensure s2 is the shorter string to optimize memory allocation
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1] * (len(s2) + 1)
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (0 if c1 == c2 else 1)
            curr_row[j + 1] = min(insertions, deletions, substitutions)
        prev_row = curr_row

    return prev_row[-1]


def levenshtein_similarity(s1: str, s2: str) -> float:
    """Compute normalized Levenshtein similarity score bounded in [0.0, 1.0]."""
    if s1 == s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    dist = levenshtein_distance(s1, s2)
    return max(0.0, min(1.0, 1.0 - (dist / max_len)))


def get_character_ngrams(text: str, n: int = 3) -> List[str]:
    """Extract character n-grams from input text.

    If the input string is shorter than n, returns [text] to preserve matching capability.
    """
    if n <= 0:
        raise ValueError(f"n must be greater than 0, got {n}")
    if not text:
        return []
    if len(text) < n:
        return [text]
    return [text[i : i + n] for i in range(len(text) - n + 1)]


def get_word_ngrams(text: str, n: int = 2) -> List[str]:
    """Extract word n-grams from input text using word boundary tokenization."""
    if n <= 0:
        raise ValueError(f"n must be greater than 0, got {n}")
    words = re.findall(r"\b\w+\b", text)
    if not words:
        return []
    if len(words) < n:
        return [" ".join(words)]
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


def jaccard_similarity(s1: str, s2: str, n: int = 3, mode: str = "char") -> float:
    """Compute Jaccard similarity index: |A ∩ B| / |A ∪ B| based on n-grams."""
    if s1 == s2:
        return 1.0

    if mode == "word":
        set1 = set(get_word_ngrams(s1, n))
        set2 = set(get_word_ngrams(s2, n))
    else:
        set1 = set(get_character_ngrams(s1, n))
        set2 = set(get_character_ngrams(s2, n))

    if not set1 and not set2:
        return 1.0 if s1 == s2 else 0.0
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return float(intersection / union) if union > 0 else 0.0

def ngram_dice_similarity(s1: str, s2: str, n: int = 3, mode: str = "char") -> float:
    """Compute Sørensen–Dice similarity coefficient: 2 * |A ∩ B| / (|A| + |B|)."""
    if s1 == s2:
        return 1.0

    if mode == "word":
        list1 = get_word_ngrams(s1, n)
        list2 = get_word_ngrams(s2, n)
    else:
        list1 = get_character_ngrams(s1, n)
        list2 = get_character_ngrams(s2, n)

    if not list1 and not list2:
        return 1.0 if s1 == s2 else 0.0
    if not list1 or not list2:
        return 0.0

    counts1 = Counter(list1)
    counts2 = Counter(list2)
    overlap = sum((counts1 & counts2).values())
    total = len(list1) + len(list2)
    return float((2.0 * overlap) / total) if total > 0 else 0.0


def compute_similarity(
    s1: str,
    s2: str,
    metric: str = "levenshtein",
    case_sensitive: bool = True,
    **kwargs: Any,
) -> float:
    """Compute text similarity score using the specified algorithm.

    Supported metrics:
        - 'levenshtein' / 'lev': Normalized Levenshtein ratio
        - 'jaccard' / 'char_jaccard': Character n-gram Jaccard index (default n=3)
        - 'word_jaccard': Word n-gram Jaccard index (default n=1)
        - 'dice' / 'ngram' / 'ngram_dice': Sørensen–Dice character n-gram coefficient (default n=3)
        - 'word_dice': Sørensen–Dice word n-gram coefficient (default n=2)
    """
    target1 = s1 if case_sensitive else s1.lower()
    target2 = s2 if case_sensitive else s2.lower()

    m = metric.lower().strip()
    if m in ("levenshtein", "lev"):
        return levenshtein_similarity(target1, target2)
    elif m in ("jaccard", "char_jaccard"):
        n = kwargs.get("n", 3)
        return jaccard_similarity(target1, target2, n=n, mode="char")
    elif m in ("word_jaccard",):
        n = kwargs.get("n", 1)
        return jaccard_similarity(target1, target2, n=n, mode="word")
    elif m in ("dice", "ngram", "ngram_dice", "char_dice"):
        n = kwargs.get("n", 3)
        return ngram_dice_similarity(target1, target2, n=n, mode="char")
    elif m in ("word_dice", "word_ngram"):
        n = kwargs.get("n", 2)
        return ngram_dice_similarity(target1, target2, n=n, mode="word")
    else:
        raise ValueError(
            f"Unsupported similarity metric '{metric}'. Available metrics: "
            f"'levenshtein', 'jaccard', 'dice', 'ngram_dice', 'word_jaccard', 'word_dice'"
        )


def estimate_token_count(text: str, method: str = "heuristic") -> int:
    """Estimate token count for a text string without external tokenizer dependencies.

    Args:
        text: Input string to estimate tokens for.
        method: Estimation algorithm ('heuristic', 'char', or 'word').
            - 'heuristic': Subword and punctuation-aware BPE approximation (~4 chars/token)
            - 'char': Pure character ratio ((len + 3) // 4)
            - 'word': Word count heuristic (words * 1.33)

    Returns:
        Estimated non-negative integer token count.
    """
    if not text:
        return 0

    m = method.lower().strip()
    if m in ("char", "chars"):
        return max(1, (len(text) + 3) // 4)
    elif m in ("word", "words"):
        words = text.split()
        return max(1, int(math.ceil(len(words) * 1.33))) if words else 0
    else:
        # Subword and punctuation-aware BPE approximation
        chunks = re.findall(r"\w+|[^\w\s]|\s+", text)
        count = 0
        for chunk in chunks:
            if chunk.isspace():
                count += len(chunk) // 4
            elif chunk.isalnum():
                if len(chunk) <= 4:
                    count += 1
                else:
                    count += (len(chunk) + 3) // 4
            else:
                count += max(1, (len(chunk) + 1) // 2)
        return max(1, count)


def estimate_prompt_and_completion_tokens(
    prompt: str, completion: str, method: str = "heuristic"
) -> Tuple[int, int, int]:
    """Estimate prompt, completion, and total token usage counts."""
    p_tokens = estimate_token_count(prompt, method=method)
    c_tokens = estimate_token_count(completion, method=method)
    return p_tokens, c_tokens, p_tokens + c_tokens
