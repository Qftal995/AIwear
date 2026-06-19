"""Token counting using tiktoken for accurate cost tracking.

Uses cl100k_base encoding (compatible with DeepSeek, GPT-4, and most OpenAI-compatible models).
Falls back to character-based estimation when tiktoken is not installed.
"""

import logging

logger = logging.getLogger(__name__)

_enc = None
_tiktoken_loaded = False
TIKTOKEN_AVAILABLE = False


def _ensure_tiktoken():
    global _enc, _tiktoken_loaded, TIKTOKEN_AVAILABLE
    if _tiktoken_loaded:
        return
    _tiktoken_loaded = True
    try:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
        TIKTOKEN_AVAILABLE = True
    except Exception:
        TIKTOKEN_AVAILABLE = False


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken cl100k_base encoding.

    Falls back to char/2 estimation for CJK text, char/4 for ASCII,
    when tiktoken is not installed.
    """
    if not text:
        return 0
    _ensure_tiktoken()
    if TIKTOKEN_AVAILABLE and _enc is not None:
        return len(_enc.encode(text))
    # Fallback: CJK chars ≈ 1.5 tokens/char, ASCII ≈ 0.25 tokens/char
    cjk = sum(1 for c in text if '一' <= c <= '鿿' or '　' <= c <= '〿')
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - cjk - ascii_chars
    return int(cjk * 1.5 + ascii_chars * 0.25 + other * 0.75)


def count_tokens_batch(texts: list[str]) -> list[int]:
    """Count tokens for multiple texts at once."""
    return [count_tokens(t) for t in texts]
