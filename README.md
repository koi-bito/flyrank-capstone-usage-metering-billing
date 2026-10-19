# Backend Capstone: Usage Metering & Quota Billing Engine

**Track:** Backend AI Engineering (Primary Declared Track)  
**Capstone Option:** Option 1 — Usage Metering & Billing Engine  
**Intern:** Kunal Aggarwal  
**Stack:** FastAPI, Python 3.12, SQLite / PostgreSQL Schema, Stripe Subscriptions Engine, Microcents Financial Math  

---

## 1. System Architecture & Overview

This service powers the core monetization infrastructure of modern AI SaaS platforms: metering tenant requests, enforcing hard quota boundaries, calculating accurate token pricing, and synchronizing plan tiers via Stripe billing webhooks.

```
+---------------------------------------------------------------------------------------------------+
|                                  LAYERED SERVICE ARCHITECTURE                                     |
|                                                                                                   |
|   1. HTTP & BOUNDARY LAYER (`src/main.py`)                                                        |
|      - Bearer Token Auth / Header Parsing (`Idempotency-Key`, `Stripe-Signature`)                 |
|      - Pydantic Schema Validation (Rejects malformed input with 400 Bad Request)                  |
|                                                                                                   |
|   2. IDEMPOTENCY BARRIER (`src/services/metering_service.py`)                                     |
|      - Short-circuits duplicate retries -> Returns cached 200 payload (0 double-charging)         |
|                                                                                                   |
|   3. QUOTA ENFORCEMENT ENGINE (`src/services/quota_service.py`)                                   |
|      - Checks current rolling usage against plan limits                                           |
|      - Hard boundary honesty -> Returns 429 Too Many Requests if over limit                       |
|                                                                                                   |
|   4. FINANCIAL PRICING ENGINE (`src/pricing.py`)                                                  |
|      - Microcents integer arithmetic (1 USD = 1,000,000 Microcents)                               |
|      - Discounts cached input (50%), bills reasoning as output tier                               |
|                                                                                                   |
|   5. BILLING & STRIPE GATEWAY (`src/services/billing_service.py`)                                 |
|      - Cryptographic HMAC-SHA256 signature verification                                           |
|      - Idempotent webhook processing (Flips Free -> Pro upon checkout)                            |
|                                                                                                   |
|   6. ASYNC BACKGROUND WORKER (`src/background.py`)                                                |
|      - Periodic usage rollups, tenant reconciliation, and stale key purging                       |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. Plans & Token Pricing Rules

### Plan Tiers:
| Plan ID | Plan Name | Monthly Requests | Monthly Tokens | Price (USD) |
| :--- | :--- | :--- | :--- | :--- |
| `free` | Free Starter Plan | 1,000 | 50,000 | **$0.00** |
| `pro` | Pro Developer Plan | 100,000 | 5,000,000 | **$29.00 / month** |

### Pinned Token Pricing Rates (Integer Microcents):
- **Cached Input Tokens:** **$0.075 / 1,000,000** (75,000 microcents / 1M tokens)
- **Standard Input Tokens:** **$0.150 / 1,000,000** (150,000 microcents / 1M tokens)
- **Reasoning Tokens:** **$0.600 / 1,000,000** (600,000 microcents / 1M tokens — output rate)
- **Standard Output Tokens:** **$0.600 / 1,000,000** (600,000 microcents / 1M tokens)

> **Why Microcents?** Standard IEEE-754 binary floating-point numbers (`0.000000075`) suffer from rounding drift over millions of calls. Standardizing on integer microcents ensures financial calculations are exact to the last decimal with zero floating point error.

---

## 3. Database Schema & Indexes

The relational schema strictly enforces tenant isolation and high-throughput query performance:

- `tenants` (`id`, `name`, `api_key`, `plan_id`, `stripe_customer_id`, `created_at`)
- `plans` (`id`, `name`, `max_requests`, `max_tokens`, `price_cents`)
- `subscriptions` (`id`, `tenant_id`, `stripe_subscription_id`, `status`, `created_at`)
- `usage_events` (`id`, `tenant_id`, `idempotency_key`, `event_type`, `request_count`, `standard_input_tokens`, `cached_input_tokens`, `reasoning_tokens`, `output_tokens`, `cost_microcents`, `created_at`)
- `idempotency_records` (`key`, `tenant_id`, `response_status`, `response_body`, `created_at`)
- `processed_webhooks` (`event_id`, `event_type`, `processed_at`)

### Performance Indexes:
```sql
CREATE INDEX idx_usage_tenant_date ON usage_events(tenant_id, created_at);
CREATE INDEX idx_usage_idem ON usage_events(tenant_id, idempotency_key);
CREATE INDEX idx_tenant_apikey ON tenants(api_key);
CREATE INDEX idx_tenant_stripe_cust ON tenants(stripe_customer_id);
```

---

## 4. How to Run

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Initialize Database & Seed Plans
```bash
python -m src.database
# Output: Database initialized with indexes and seeded plans.
```

### Step 3: Run the API Server
```bash
uvicorn src.main:app --reload --port 8000
```
Interactive documentation is available at `http://127.0.0.1:8000/docs`.

### Step 4: Run the Complete Capstone Verification Suite
```bash
python run_tests.py
```

---

## 5. API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Service health status |
| `POST` | `/v1/chat/completions` | Billable completion endpoint (idempotent, quota-checked, metered) |
| `GET` | `/v1/tenants/me/usage` | Inspect current tenant's usage, quota balance, and cost rollup |
| `GET` | `/v1/tenants/{id}/usage` | Admin inspection of specific tenant usage |
| `POST` | `/v1/billing/checkout` | Generate Stripe checkout session for Free -> Pro upgrade |
| `POST` | `/v1/webhooks/stripe` | Handle Stripe webhooks (`checkout.session.completed`, `customer.subscription.deleted`) |
| `POST` | `/v1/jobs/reconcile` | Trigger background reconciliation and rollup job |

---

## 6. Acceptance Probes Verification Summary

| Probe # | Requirement Verified | Status |
| :--- | :--- | :--- |
| **Probe 1** | Same request + idempotency key sent twice -> exactly one usage event created in DB | **PASS** |
| **Probe 2** | Drive tenant to exact quota -> next request returns clean `HTTP 429 Too Many Requests` | **PASS** |
| **Probe 3** | Stripe checkout completed -> webhook verifies HMAC signature, flips tenant from Free to Pro | **PASS** |
| **Probe 4** | Forged webhook returns `HTTP 400`; replayed webhook is deduplicated and processed once | **PASS** |
| **Probe 5** | Pinned token pricing constants produce exact expected compound microcents totals | **PASS** |

Full evidence logs and terminal outputs are documented in [`EVIDENCE.md`](EVIDENCE.md).  
Architecture reflections and AI transparency logs are documented in [`BUILDLOG.md`](BUILDLOG.md).
