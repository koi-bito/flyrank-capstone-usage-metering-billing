import pytest
from src.pricing import calculate_token_cost, microcents_to_dollars, microcents_to_formatted_string

def test_cached_input_token_discount():
    # 1,000,000 cached input tokens = $0.075 = 75,000 microcents
    cost = calculate_token_cost(cached_input_tokens=1_000_000)
    assert cost == 75_000
    assert microcents_to_dollars(cost) == 0.075

def test_standard_input_tokens():
    # 1,000,000 standard input tokens = $0.150 = 150,000 microcents
    cost = calculate_token_cost(standard_input_tokens=1_000_000)
    assert cost == 150_000
    assert microcents_to_dollars(cost) == 0.15

def test_reasoning_tokens_priced_as_output():
    # 1,000,000 reasoning tokens = $0.600 = 600,000 microcents
    cost = calculate_token_cost(reasoning_tokens=1_000_000)
    assert cost == 600_000
    assert microcents_to_dollars(cost) == 0.60

def test_compound_call_money_math():
    # Call with 500 cached input, 200 standard input, 100 reasoning, 300 output
    cost = calculate_token_cost(
        cached_input_tokens=500,
        standard_input_tokens=200,
        reasoning_tokens=100,
        output_tokens=300
    )
    # Expected:
    # 500 * 75000 / 1M = 37 microcents
    # 200 * 150000 / 1M = 30 microcents
    # 100 * 600000 / 1M = 60 microcents
    # 300 * 600000 / 1M = 180 microcents
    # Total = 37 + 30 + 60 + 180 = 307 microcents
    assert cost == 307
    formatted = microcents_to_formatted_string(cost)
    assert "$0.000307" == formatted

if __name__ == "__main__":
    test_cached_input_token_discount()
    test_standard_input_tokens()
    test_reasoning_tokens_priced_as_output()
    test_compound_call_money_math()
    print("Pricing money math tests passed successfully!")
