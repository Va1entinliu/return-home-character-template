from __future__ import annotations


def _non_negative_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return value
    return None


def _first_non_negative(*values):
    for value in values:
        parsed = _non_negative_number(value)
        if parsed is not None:
            return parsed
    return None


def parse_provider_usage(usage: dict | None) -> dict:
    """Parse provider-reported usage without inventing cache-hit estimates."""
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _first_non_negative(
        usage.get("prompt_tokens"),
        usage.get("input_tokens"),
    )
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict):
        details = usage.get("input_tokens_details")
    details = details if isinstance(details, dict) else {}
    cached_tokens = _first_non_negative(
        details.get("cached_tokens"),
        usage.get("cached_tokens"),
    )
    cache_reported = input_tokens is not None and cached_tokens is not None
    uncached_tokens = (
        max(0, input_tokens - cached_tokens) if cache_reported else None
    )
    return {
        "inputTokens": input_tokens,
        "cachedTokens": cached_tokens if cache_reported else None,
        "uncachedTokens": uncached_tokens,
        "cacheReported": cache_reported,
    }


def summarize_cache_usage(entries: list[dict], window_size: int = 20) -> dict:
    """Return the token-weighted hit rate for recent provider-reported rounds."""
    valid = [
        entry
        for entry in entries[-max(1, window_size) :]
        if entry.get("cacheReported")
        and _non_negative_number(entry.get("inputTokens")) is not None
        and _non_negative_number(entry.get("cachedTokens")) is not None
    ]
    input_tokens = sum(entry["inputTokens"] for entry in valid)
    cached_tokens = sum(entry["cachedTokens"] for entry in valid)
    return {
        "roundCount": len(valid),
        "inputTokens": input_tokens,
        "cachedTokens": cached_tokens,
        "hitRate": cached_tokens / input_tokens if input_tokens else None,
    }
