import os

# Pricing configuration (in microcents: 1 USD = 100 Cents = 1,000,000 Microcents)
# This prevents IEEE-754 floating point precision errors in financial calculations.
PRICING_RULES = {
    "cached_input_per_million": 75000,      # $0.075 / 1M tokens
    "standard_input_per_million": 150000,   # $0.150 / 1M tokens
    "reasoning_output_per_million": 600000, # $0.600 / 1M tokens
    "standard_output_per_million": 600000,  # $0.600 / 1M tokens
    "api_call_base_microcents": 0           # 0 base surcharge
}

PLANS = {
    "free": {
        "id": "free",
        "name": "Free Starter Plan",
        "max_requests": 1000,
        "max_tokens": 50000,
        "price_cents": 0
    },
    "pro": {
        "id": "pro",
        "name": "Pro Developer Plan",
        "max_requests": 100000,
        "max_tokens": 5000000,
        "price_cents": 2900 # $29.00/mo
    }
}

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_mock_12345")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_mock_67890")
DATABASE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "metering.db")
