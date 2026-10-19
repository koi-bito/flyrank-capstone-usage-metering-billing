# BUILDLOG.md — Architecture & Engineering Build Log

**Capstone Project:** Usage Metering & Billing Engine  
**Author:** Kunal Aggarwal  
**Stack:** FastAPI, Python 3.12, SQLite / PostgreSQL, Stripe API  

---

## 1. Transparency Diligence: Division of Labor

In compliance with FlyRank's transparency guidelines:

| Subsystem | Human Engineering Contribution | AI Pair-Programming Role (Claude / GPT) |
| :--- | :--- | :--- |
| **Data Architecture** | Designed relational schema with composite indexes (`idx_usage_tenant_date`, `idx_usage_idem`), defined integer microcents constraint. | Drafted initial SQLite DDL table definitions and foreign key constraints. |
| **Financial Math Engine** | Pinned pricing constants, authored integer integer-division math eliminating IEEE-754 floating point drift. | Verified compound token test scenarios and checked edge cases on division remainder truncation. |
| **Idempotency Layer** | Architected atomic two-table insert pattern (`usage_events` + `idempotency_records`) inside an isolated transaction. | Assisted in constructing Starlette/FastAPI header parsing and response serialization wrappers. |
| **Stripe Webhook Gateway** | Implemented HMAC-SHA256 signature verification, 300-second timestamp freshness window, and deduplication table. | Provided sample Stripe webhook payload fixtures for `checkout.session.completed` and `customer.subscription.deleted`. |
| **Acceptance Probes** | Authored comprehensive test runner executing all 5 acceptance probes. | Debugged test client import order and FastAPI lifespan event handling. |

---

## 2. The 3 Genuinely Hard Problems Solved

### 1. Exactly-Once Metering Under Network Retries
- **The Problem:** In high-throughput distributed systems, clients (like SDKs) automatically retry HTTP requests when network timeouts occur. If the server successfully executed the generation but the response packet was dropped in transit, a naive retry would bill the tenant twice and increment their quota count.
- **The Solution:** We implemented an **idempotency-key barrier** at the very top of the request lifecycle. Before executing generation or checking quota, the engine checks `idempotency_records`. If the key exists for that tenant, it short-circuits execution and returns the cached JSON payload with status 200 and `"cached_response": true`. No new usage event is created, and quota is decremented exactly once.

### 2. Boundary Honesty at the Quota Threshold
- **The Problem:** Many SaaS backends check quotas lazily after the work has been performed, or fail with generic 500 errors when a tenant crosses their limit.
- **The Solution:** We enforce quota boundaries *before* any compute or external model inference is initiated. If `current_usage + requested_usage > plan_limit`, the request is immediately halted at the perimeter with an explicit `HTTP 429 Too Many Requests` status code and a clear error message detailing exactly which metric (requests vs tokens) was exhausted.

### 3. Financial Precision: Microcents vs Floating Point
- **The Problem:** Token pricing rates (e.g. $0.075 per 1,000,000 tokens) involve numbers like `0.000000075`. Using standard IEEE-754 binary floating-point numbers (`float`) introduces catastrophic rounding errors across millions of transactions.
- **The Solution:** We standardized all internal ledger amounts on **integer microcents** (`1 USD = 1,000,000 Microcents`). All cost calculations use integer division and integer multiplication, guaranteeing that `$0.075 / 1M` evaluates with zero financial drift.

---

## 3. Explaining Any 2–3 Lines of Code (Evaluator Readiness)

- **Lines 17–21 in `pricing.py` (`calculate_token_cost`):**
  ```python
  cached_cost = (cached_input_tokens * PRICING_RULES["cached_input_per_million"]) // 1_000_000
  input_cost = (standard_input_tokens * PRICING_RULES["standard_input_per_million"]) // 1_000_000
  reasoning_cost = (reasoning_tokens * PRICING_RULES["reasoning_output_per_million"]) // 1_000_000
  output_cost = (output_tokens * PRICING_RULES["standard_output_per_million"]) // 1_000_000
  ```
  *Explanation:* Each token category multiplies the token count by its pinned integer cost per million microcents, followed by integer division `// 1_000_000`. This maps mathematical cost into an exact integer microcent floor with zero floating-point imprecision.

- **Lines 26–36 in `billing_service.py` (`verify_stripe_signature`):**
  ```python
  signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
  computed_signature = hmac.new(
      secret.encode("utf-8"),
      signed_payload,
      hashlib.sha256
  ).hexdigest()
  return hmac.compare_digest(computed_signature, v1_sig)
  ```
  *Explanation:* Reconstructs Stripe's canonical signed payload by prepending the extracted timestamp and a period to the raw request byte stream. We hash this with HMAC-SHA256 and use `hmac.compare_digest` to perform a constant-time comparison, preventing timing-attack vulnerabilities.
