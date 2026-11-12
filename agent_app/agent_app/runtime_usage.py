"""The token fields of a model call's usage, as inference reads them (the rollout measuring
that once lived here was not called; removed after the review of 2026-10-07)."""

FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "reasoning_output_tokens",
)
