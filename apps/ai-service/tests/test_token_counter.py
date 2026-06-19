import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.token_counter import count_tokens, count_tokens_batch


class TestTokenCounter:
    def test_empty_string_returns_zero(self):
        assert count_tokens("") == 0

    def test_ascii_text(self):
        n = count_tokens("hello world")
        assert n > 0
        assert n < 10

    def test_chinese_text(self):
        n = count_tokens("你好世界")
        assert n > 0

    def test_mixed_text(self):
        n = count_tokens("今天天气不错,适合出门散步 Hello World!")
        assert n > 0

    def test_long_text(self):
        text = "这是一个穿搭推荐系统，" * 50
        n = count_tokens(text)
        assert n > 0

    def test_batch_returns_same_count(self):
        texts = ["hello", "世界"]
        counts = count_tokens_batch(texts)
        assert len(counts) == 2
        assert all(c > 0 for c in counts)
        assert counts[0] == count_tokens("hello")
        assert counts[1] == count_tokens("世界")

    def test_monotonic_longer_text(self):
        short = count_tokens("hi")
        long = count_tokens("hi there, how are you doing today?")
        assert long >= short
