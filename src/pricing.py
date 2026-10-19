from src.config import PRICING_RULES

def calculate_token_cost(
    standard_input_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
    output_tokens: int = 0
) -> int:
    """
    Computes exact integer cost in microcents (1 USD = 1,000,000 Microcents).
    Rules:
    - Cached input tokens get 50% discount ($0.075 / 1M).
    - Standard input tokens billed at ($0.150 / 1M).
    - Reasoning tokens count at output tier ($0.600 / 1M).
    - Standard output tokens billed at ($0.600 / 1M).
    """
    cached_cost = (cached_input_tokens * PRICING_RULES["cached_input_per_million"]) // 1_000_000
    input_cost = (standard_input_tokens * PRICING_RULES["standard_input_per_million"]) // 1_000_000
    reasoning_cost = (reasoning_tokens * PRICING_RULES["reasoning_output_per_million"]) // 1_000_000
    output_cost = (output_tokens * PRICING_RULES["standard_output_per_million"]) // 1_000_000

    total_microcents = cached_cost + input_cost + reasoning_cost + output_cost
    return total_microcents

def microcents_to_dollars(microcents: int) -> float:
    """Converts integer microcents to standard USD float for display."""
    return round(microcents / 1_000_000.0, 6)

def microcents_to_formatted_string(microcents: int) -> str:
    """Returns human-readable currency representation."""
    dollars = microcents / 1_000_000.0
    return f"${dollars:,.6f}"
