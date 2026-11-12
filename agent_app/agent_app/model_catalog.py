"""Models offered for runs and their API prices: trace any model from here.

- Claude: the fixed list CLAUDE_MODELS (Claude Code has no model catalog to read).
- GPT: read on every request from the Codex CLI's catalog cache (codex_models), so the
  list follows the CLI; the rules in codex_models decide which of them are shown.
- Prices: API_RATES (OpenAI) and CLAUDE_RATES, used by costs.api_cost. A model without
  a price still runs, but its cost is reported as unknown.
The menu order across the two CLIs is set by codex_execution.execution_models.
"""

import json
import os
import re
from pathlib import Path

# Claude Code models offered for runs (ID -> display name), in menu order.
CLAUDE_MODELS = {
    "claude-opus-5-5": "Claude Opus 5.5",
    "claude-sonnet-5-5": "Claude Sonnet 5.5",
    # Released 2026-10-07 (user 2026-10-08: "use it; it may suit the judging").
    "claude-haiku-5-5": "Claude Haiku 5.5",
}


# The most a worker's view gets, for every model: the smallest size the models take in as it
# is, Claude's (Anthropic's vision docs: a long edge over 1568 px, or over about 1,600 image
# tokens = width x height / 750, is scaled down first; GPT-6-Astra's "high" takes 2,500
# 32-px patches). Claude Code scaled 1024x1536 views before sending them, so the worker got
# other bytes than the view's and the run's check that it saw the whole image failed (found
# 2026-10-07). With the setting's 1024 this never binds; it guards a larger setting.
WORKER_VIEW_MAX_SIDE = 1568
WORKER_VIEW_MAX_PIXELS = 1_150_000


def claude_models():
    """Claude models in the same shape as codex_models."""
    return [
        {
            "model": model,
            "display_name": name,
            "efforts": ["low", "medium", "high", "xhigh", "max"],
            "default_effort": "medium",
            # Claude Code's fast mode is for Opus only.
            "speeds": [
                {"id": "fast", "name": "Fast", "description": "Claude Code fast mode"}
            ]
            if "opus" in model
            else [],
        }
        for model, name in CLAUDE_MODELS.items()
    ]


def codex_models():
    """Image-capable public Codex models and efforts from the CLI's catalog cache."""
    models = []
    path = (
        Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        / "models_cache.json"
    )
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        for entry in cached["models"]:
            if entry.get("visibility") != "list" or "image" not in entry.get(
                "input_modalities", []
            ):
                continue
            slug = entry["slug"]
            # Hide the gpt-5 family (added with GPT-6 and Opus 5.5 support in fcf002c,
            # 2026-09-23; no reason recorded) and gpt-6-sol (replaced by gpt-6.1-sol,
            # user 2026-09-30). Their prices stay for old runs.
            # Luna is not offered either (user 2026-10-09: clearly not good enough to read).
            if (
                re.match(r"^gpt-5(?:[.-]|$)", slug)
                or slug == "gpt-6-sol"
                or "luna" in slug
            ):
                continue
            efforts = [e["effort"] for e in entry["supported_reasoning_levels"]]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", slug):
                continue
            if not efforts or any(
                not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", e) for e in efforts
            ):
                continue
            models.append(
                {
                    "model": slug,
                    "display_name": entry.get("display_name") or slug,
                    "efforts": efforts,
                    "default_effort": entry.get("default_reasoning_level"),
                    # Faster service tiers the CLI offers ("priority" is shown as Fast).
                    "speeds": [
                        {
                            "id": tier["id"],
                            "name": tier.get("name") or tier["id"],
                            "description": tier.get("description") or "",
                        }
                        for tier in entry.get("service_tiers") or []
                        if isinstance(tier, dict) and tier.get("id")
                    ],
                }
            )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []
    return models


# OpenAI Standard prices per version (checked on its date). Keep old versions for replay.
API_PRICE_VERSION = "openai-api-2026-10-27"
# Runs recorded before prices had versions are priced with this one.
LEGACY_API_PRICE_VERSION = "openai-api-2026-09-23"
API_PRICE_URL = "https://developers.openai.com/api/docs/pricing"
# Per MTok: input, cache read, cache write, output.
_OPENAI_2026_09_23 = {
    "gpt-6-astra": ("10", "1", "12.50", "50"),
    "gpt-6-sol": ("2", "0.20", "2.50", "10"),
    "gpt-6-luna": ("0.10", "0.01", "0.125", "0.50"),
    "gpt-5.6-sol": ("4", "0.40", "5", "20"),
    "gpt-5.6-terra": ("2", "0.20", "2.50", "12"),
    "gpt-5.6-luna": ("0.20", "0.02", "0.25", "1.20"),
}
_OPENAI_2026_09_30 = {**_OPENAI_2026_09_23, "gpt-6.1-sol": ("2", "0.10", "2.50", "10")}
API_RATES = {
    LEGACY_API_PRICE_VERSION: _OPENAI_2026_09_23,
    "openai-api-2026-09-30": _OPENAI_2026_09_30,
    # GPT-6.1 Terra added (user 2026-10-27: it came out); the page's other GPT-6 prices were
    # unchanged that day.
    API_PRICE_VERSION: {
        **_OPENAI_2026_09_30,
        "gpt-6.1-terra": ("1", "0.05", "1.25", "5"),
    },
}

# Claude Standard prices per version (checked on its date). Keep old versions for replay.
CLAUDE_PRICE_VERSION = "anthropic-api-2026-10-08"
CLAUDE_PRICE_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
_CLAUDE_OPUS_5_5 = {
    "input": "4",
    "output": "20",
    "cache_read": "0.20",
    "cache_write_5m": "5",
    "cache_write_1h": "8",
}
CLAUDE_RATES = {
    "anthropic-api-2026-09-23": {"claude-opus-5-5": _CLAUDE_OPUS_5_5},
    "anthropic-api-2026-09-29": {
        "claude-opus-5-5": _CLAUDE_OPUS_5_5,
        "claude-sonnet-5-5": {
            "input": "2",
            "output": "10",
            "cache_read": "0.20",
            "cache_write_5m": "2.50",
            "cache_write_1h": "4",
        },
    },
    CLAUDE_PRICE_VERSION: {
        "claude-opus-5-5": _CLAUDE_OPUS_5_5,
        # Cache hits are 0.05x input on Sonnet 5.5 ($0.10), the page says on 2026-10-08.
        "claude-sonnet-5-5": {
            "input": "2",
            "output": "10",
            "cache_read": "0.10",
            "cache_write_5m": "2.50",
            "cache_write_1h": "4",
        },
        # Haiku 5.5 is priced by each request's prompt: these are for 100,000 tokens or less
        # (over it: 0.50 / 2.50 / 0.05 / 0.625 / 1). A CLI turn's total does not say each
        # request's length, so the lower prices are assumed and said so (costs.claude_cost).
        "claude-haiku-5-5": {
            "input": "0.10",
            "output": "0.50",
            "cache_read": "0.01",
            "cache_write_5m": "0.125",
            "cache_write_1h": "0.20",
            "prompt_up_to": "100000",
        },
    },
}
