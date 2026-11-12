"""Disjoint billing quantities from explicit usage subset relationships."""

from decimal import Decimal

from .errors import ApiError
from .model_catalog import (
    API_PRICE_URL,
    API_RATES,
    CLAUDE_PRICE_URL,
    CLAUDE_RATES,
    LEGACY_API_PRICE_VERSION,
)

AUX = {
    "cache_read": "cached_input_tokens",
    "cache_write": "cache_write_input_tokens",
    "reasoning": "reasoning_output_tokens",
}

# Rate every run used before usd_to_jpy became an app setting (2026-09-27).
LEGACY_USD_TO_JPY = "160"


def api_cost(usage, settings, *, reason=None):
    """API-equivalent token estimate for one dedicated CLI turn, not its bill.

    CLI turn totals span model calls: never use their sum as a context length.
    Preserve missing measurements and disclose conditions used for comparison.
    """
    settings = settings or {}
    model, tier = settings.get("model"), settings.get("tier")
    # The run's own rate (app setting at start); runs before the setting used a fixed one.
    rate = str(settings.get("usd_to_jpy") or LEGACY_USD_TO_JPY)
    version = settings.get("api_price_version") or LEGACY_API_PRICE_VERSION
    result = {
        "usd": None,
        "jpy": None,
        "known_usd": None,
        "known_jpy": None,
        "usd_to_jpy": rate,
        "missing_reason": reason,
        "assumptions": [],
        "basis": {
            "model": model,
            "requested_tier": tier,
            "price_version": version,
            "source_url": API_PRICE_URL,
            "checked_at": version.split("-api-")[-1],
            "billing_basis": "hypothetical",
            "per_units": 1000000,
            "model_source": "recorded_cli_invocation",
            "usage_source": "dedicated_cli_turn_total",
        },
    }
    if str(model).startswith("claude-"):
        return claude_cost(result, usage, model, version, tier)
    if reason:
        return result
    if version not in API_RATES:
        result["missing_reason"] = "The price table version is not registered"
        return result
    if model not in API_RATES[version]:
        result["missing_reason"] = "The model's prices are not registered"
        return result
    factors = {
        None: "1",
        "default": "1",
        "standard": "1",
        "priority": "2",
        "fast": "2",
        "flex": "0.5",
        "batch": "0.5",
    }
    if tier not in factors:
        result["missing_reason"] = "The prices of the requested tier are unknown"
        return result
    if not usage or any(
        type(usage.get(k)) is not int or usage[k] < 0
        for k in ("input_tokens", "output_tokens", "cached_input_tokens")
    ):
        result["missing_reason"] = (
            "Measured input, output or cache read usage is missing"
        )
        return result
    assumptions = result["assumptions"]
    if not settings.get("api_price_version"):
        assumptions.append(
            "Older history without a price version is recalculated with the 2026-09-23 reference prices; saved usage is not changed."
        )
    assumptions.extend(
        [
            "Not the Codex subscription's actual charge: API prices applied to the requested model and the measured tokens.",
            "Each request's input length is not recorded, so each is estimated as short context (272K or less), not judged from the cumulative input.",
            "No regional surcharge; tool fees other than tokens are not included.",
            "CLI usage cache reads are counted within input (an inclusion stated in the record takes precedence).",
            "The tier is the requested one, not a confirmed billing value, converted to API prices."
            if tier
            else "The tier is not recorded, so Standard is assumed.",
        ]
    )
    inclusion = usage.get("inclusion", {})
    projected = {**usage, "inclusion": dict(inclusion)}
    for field, parent in (
        ("cached_input_tokens", "input"),
        ("cache_write_input_tokens", "input"),
        ("reasoning_output_tokens", "output"),
    ):
        if inclusion.get(field, "unknown") == "unknown":
            projected["inclusion"][field] = parent
        elif inclusion[field] not in (parent, "external"):
            result["missing_reason"] = "The usage inclusions are inconsistent"
            return result
    cached, _ = quantity(projected, "cache_read")
    writes = usage.get("cache_write_input_tokens")
    input_count = usage["input_tokens"]
    if projected["inclusion"]["cached_input_tokens"] == "input":
        input_count -= cached
    if writes is None:
        assumptions.append(
            "Cache write amounts are not recorded; input other than cache reads uses the normal input price (the cache write price difference is not included)."
        )
    elif type(writes) is not int or writes < 0:
        result["missing_reason"] = "The cache write amount is invalid"
        return result
    else:
        try:
            input_count, _ = quantity(projected, "input")
        except ApiError:
            result["missing_reason"] = "The input inclusions are inconsistent"
            return result
    output_count = usage["output_tokens"]
    reasoning = usage.get("reasoning_output_tokens")
    if reasoning is not None and (
        type(reasoning) is not int
        or reasoning < 0
        or (
            projected["inclusion"]["reasoning_output_tokens"] == "output"
            and reasoning > output_count
        )
    ):
        result["missing_reason"] = "The reasoning inclusions are inconsistent"
        return result
    if projected["inclusion"]["reasoning_output_tokens"] == "external":
        if reasoning is None:
            result["missing_reason"] = (
                "The reasoning amount outside the output is unknown"
            )
            return result
        output_count += reasoning
    else:
        assumptions.append("Reasoning is counted within output, not added twice.")
    if input_count is None or input_count < 0:
        result["missing_reason"] = "The input inclusions are inconsistent"
        return result
    factor = Decimal(factors[tier])
    rates = dict(
        zip(
            ("input", "cache_read", "cache_write", "output"),
            API_RATES[version][model],
            strict=True,
        )
    )
    rates = {key: str(Decimal(value) * factor) for key, value in rates.items()}
    quantities = {
        "input": input_count,
        "cache_read": cached,
        "cache_write": writes,
        "output": output_count,
    }
    total = sum(
        (
            Decimal(count) * Decimal(rates[key]) / Decimal(1000000)
            for key, count in quantities.items()
            if count is not None
        ),
        Decimal(0),
    )
    result.update(usd=str(total), jpy=str(total * Decimal(result["usd_to_jpy"])))
    result["basis"].update(
        context="short_assumed_per_request",
        tier="standard" if tier is None else tier,
        rates=rates,
        quantities=quantities,
    )
    return result


def claude_cost(result, usage, model, version, tier):
    """Claude standard API equivalent; cache reads/writes are outside input."""
    result["basis"]["source_url"] = CLAUDE_PRICE_URL
    if result["missing_reason"]:
        return result
    rates = CLAUDE_RATES.get(version, {}).get(model)
    if rates is None or tier != "standard":
        result["missing_reason"] = (
            "The Claude price version, model or tier is not supported"
        )
        return result
    raw = (usage or {}).get("raw", {})
    quantities = {
        "input": (usage or {}).get("input_tokens"),
        "output": (usage or {}).get("output_tokens"),
        "cache_read": (usage or {}).get("cached_input_tokens"),
        "cache_write_5m": raw.get("ephemeral_5m_input_tokens"),
        "cache_write_1h": raw.get("ephemeral_1h_input_tokens"),
    }
    if (
        not usage
        or any(type(v) is not int or v < 0 for v in quantities.values())
        or quantities["cache_write_5m"] + quantities["cache_write_1h"]
        != usage.get("cache_write_input_tokens")
        or usage.get("inclusion", {}).get("cached_input_tokens") != "external"
        or usage.get("inclusion", {}).get("cache_write_input_tokens") != "external"
    ):
        result["missing_reason"] = (
            "Measured Claude usage, or the cache write breakdown by retention, is missing"
        )
        return result
    total = sum(
        (Decimal(v) * Decimal(rates[k]) / 1000000 for k, v in quantities.items()),
        Decimal(0),
    )
    result.update(usd=str(total), jpy=str(total * Decimal(result["usd_to_jpy"])))
    result["basis"].update(rates=rates, quantities=quantities, tier="standard")
    result["assumptions"] = [
        "Not the Claude subscription's actual charge: Standard API prices applied to the measured tokens.",
        "Cache reads and writes are outside normal input; 5-minute and 1-hour writes are priced separately, and reasoning is counted within output.",
        "No regional surcharge; tool fees other than tokens are not included.",
    ]
    if "prompt_up_to" in rates:
        result["basis"]["context"] = "short_assumed_per_request"
        result["assumptions"].append(
            f"Each request's prompt is assumed to be {rates['prompt_up_to']} tokens or less"
            " (the lower prices); the turn's total does not say each request's length."
        )
    return result


def sum_api_costs(costs):
    """Sum once per target/repair, without rounding or hiding incomplete work."""
    known = [c for c in costs if c.get("usd") is not None]
    subtotal = sum((Decimal(c["usd"]) for c in known), Decimal(0))
    # Each image's yen was fixed with its run's rate, so yen is summed as recorded.
    yen = sum((Decimal(c["jpy"]) for c in known), Decimal(0))
    rates = {c.get("usd_to_jpy") for c in known}
    complete = bool(costs) and len(known) == len(costs)
    return {
        "usd": str(subtotal) if complete else None,
        "jpy": str(yen) if complete else None,
        "known_usd": str(subtotal) if known else None,
        "known_jpy": str(yen) if known else None,
        "usd_to_jpy": rates.pop() if len(rates) == 1 else None,
        "missing_reason": None if complete else "Some items cannot be estimated",
        "assumptions": list(
            dict.fromkeys(a for c in costs for a in c.get("assumptions", []))
        ),
        "basis": {"scope": "execution", "counted": len(known), "total": len(costs)},
    }


def quantity(usage, category):
    if category in AUX:
        field = AUX[category]
        parent = "output" if category == "reasoning" else "input"
        if usage["inclusion"].get(field) not in (parent, "external"):
            return None, [field]
        return usage.get(field), [field]
    total = category + "_tokens"
    value = usage.get(total)
    fields = [total]
    for field in (
        (AUX["reasoning"],)
        if category == "output"
        else (AUX["cache_read"], AUX["cache_write"])
    ):
        relation = usage["inclusion"].get(field, "unknown")
        if relation not in (category, "external"):
            return None, fields
        if relation == category:
            fields.append(field)
            if usage.get(field) is None or value is None:
                value = None
            else:
                value -= usage[field]
    if value is not None and value < 0:
        raise ApiError(422, "invalid_input", "Token subsets exceed their total")
    return value, fields
