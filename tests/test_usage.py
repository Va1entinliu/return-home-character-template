import unittest

from app.usage import parse_provider_usage, summarize_cache_usage


class UsageTests(unittest.TestCase):
    def test_parses_provider_reported_cached_tokens(self):
        parsed = parse_provider_usage(
            {
                "prompt_tokens": 2436,
                "prompt_tokens_details": {"cached_tokens": 1582},
            }
        )
        self.assertEqual(
            parsed,
            {
                "inputTokens": 2436,
                "cachedTokens": 1582,
                "uncachedTokens": 854,
                "cacheReported": True,
            },
        )

    def test_missing_cache_details_are_unknown(self):
        parsed = parse_provider_usage({"prompt_tokens": 900})
        self.assertEqual(parsed["inputTokens"], 900)
        self.assertIsNone(parsed["cachedTokens"])
        self.assertFalse(parsed["cacheReported"])

    def test_recent_hit_rate_is_token_weighted(self):
        entries = [
            {
                "inputTokens": 100,
                "cachedTokens": 65,
                "cacheReported": True,
            }
            for _ in range(22)
        ]
        summary = summarize_cache_usage(entries, 20)
        self.assertEqual(summary["roundCount"], 20)
        self.assertEqual(summary["inputTokens"], 2000)
        self.assertEqual(summary["cachedTokens"], 1300)
        self.assertEqual(summary["hitRate"], 0.65)


if __name__ == "__main__":
    unittest.main()
