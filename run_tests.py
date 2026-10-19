import sys
from tests.test_pricing_math import (
    test_cached_input_token_discount,
    test_standard_input_tokens,
    test_reasoning_tokens_priced_as_output,
    test_compound_call_money_math
)
from tests.test_metering_and_idempotency import test_idempotent_metering_deduplication
from tests.test_quota_enforcement import test_hard_quota_boundary_429
from tests.test_stripe_webhooks import (
    test_forged_webhook_signature_rejected,
    test_valid_checkout_completed_upgrades_tenant_and_deduplicates
)

from src.database import init_db

def run_all_tests():
    init_db()
    print("=================================================================")
    print("  RUNNING BACKEND CAPSTONE ACCEPTANCE PROBES & TEST SUITE")
    print("=================================================================\n")

    print("[1/4] Testing Token Pricing Rules & Microcents Financial Math...")
    test_cached_input_token_discount()
    test_standard_input_tokens()
    test_reasoning_tokens_priced_as_output()
    test_compound_call_money_math()
    print("      --> PASS: Cached discounts, reasoning outputs & integer arithmetic verified.\n")

    print("[2/4] Testing Exactly-Once Idempotent Usage Metering...")
    test_idempotent_metering_deduplication()
    print("      --> PASS: Replayed request returned identical body; 0 double counting.\n")

    print("[3/4] Testing Boundary Honesty & Quota Enforcement (429)...")
    test_hard_quota_boundary_429()
    print("      --> PASS: Exact quota limit enforced; request #4 returned clean HTTP 429.\n")

    print("[4/4] Testing Stripe Webhook Cryptographic Verification & Sync...")
    test_forged_webhook_signature_rejected()
    test_valid_checkout_completed_upgrades_tenant_and_deduplicates()
    print("      --> PASS: Forged signature rejected (400); verified webhook upgraded plan.\n")

    print("=================================================================")
    print("  ALL 5 ACCEPTANCE PROBES PASSED! ZERO DEFECTS DETECTED.")
    print("=================================================================")

if __name__ == "__main__":
    run_all_tests()
