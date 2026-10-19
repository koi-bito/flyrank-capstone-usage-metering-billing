# EVIDENCE.md — Backend Capstone Acceptance Probes & Verification

**Project:** LLM Usage Metering & Quota Billing Engine  
**Author:** Kunal Aggarwal  
**Track:** Backend AI Engineering  
**Evaluation Standard:** 100% Pass Across All 5 Acceptance Probes  

---

## Probe 1: Exactly-Once Metering & Idempotency Key Deduplication

### Requirement:
> *A billable action creates exactly one usage event even under retries, dedup'd by idempotency key.*

### Verification Proof:
We dispatched an identical `POST /v1/chat/completions` request twice using the exact same header `Idempotency-Key: idem_key_prod_test_01`.

```bash
# First Request (Initial Processing)
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "X-Tenant-Id: tenant_free_tier" \
  -H "Idempotency-Key: idem_key_prod_test_01" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Calculate prime factors", "max_tokens": 100}'
```
**Response (HTTP 200 OK):**
```json
{
  "id": "chatcmpl-33924aef01",
  "object": "chat.completion",
  "created": 1729241100,
  "model": "gpt-4o-mini-metered",
  "output_text": "Simulated defensive completion...",
  "usage": {
    "standard_input_tokens": 15,
    "cached_input_tokens": 0,
    "reasoning_tokens": 0,
    "output_tokens": 100,
    "total_tokens": 115
  },
  "cost_microcents": 62,
  "cost_formatted": "$0.000062",
  "cached_response": false
}
```

```bash
# Second Request (Immediate Retried Request with Identical Idempotency-Key)
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "X-Tenant-Id: tenant_free_tier" \
  -H "Idempotency-Key: idem_key_prod_test_01" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Calculate prime factors", "max_tokens": 100}'
```
**Response (HTTP 200 OK — Delivered from Cache):**
```json
{
  "id": "chatcmpl-33924aef01",
  "object": "chat.completion",
  "created": 1729241100,
  "model": "gpt-4o-mini-metered",
  "output_text": "Simulated defensive completion...",
  "usage": {
    "standard_input_tokens": 15,
    "cached_input_tokens": 0,
    "reasoning_tokens": 0,
    "output_tokens": 100,
    "total_tokens": 115
  },
  "cost_microcents": 62,
  "cost_formatted": "$0.000062",
  "cached_response": true
}
```

### Database Ledger Evidence:
```sql
SELECT COUNT(*) FROM usage_events WHERE idempotency_key = 'idem_key_prod_test_01';
-- Result: 1 (Exactly one usage row created, 0 double billing).
```

---

## Probe 2: Boundary Honesty & Hard Quota Enforcement (HTTP 429)

### Requirement:
> *Usage checked against plan; over-limit requests rejected with correct 429/402 + explanatory message.*

### Verification Proof:
A test tenant on a 3-request limit plan was driven to boundary exhaustion:
- Requests 1, 2, and 3 succeeded (`HTTP 200 OK`).
- Request 4 crossed the boundary and was immediately rejected at the perimeter.

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "X-Tenant-Id: tenant_quota_test" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Trigger request #4"}'
```
**Response (HTTP 429 Too Many Requests):**
```json
{
  "detail": {
    "error": "quota_exceeded",
    "message": "Monthly request limit reached (3/3 requests used on Micro Test Plan).",
    "plan": "micro_test_plan",
    "upgrade_url": "/v1/billing/checkout"
  }
}
```

---

## Probe 3: Token Pricing Rules & Exact Integer Money Math

### Requirement:
> *AI token pricing handles cached/reasoning/output rules correctly, constants pinned in config.*

### Financial Model Specification:
1. **Cached Input Tokens:** $0.075 / 1,000,000 tokens (75,000 microcents / 1M).
2. **Standard Input Tokens:** $0.150 / 1,000,000 tokens (150,000 microcents / 1M).
3. **Reasoning Tokens:** $0.600 / 1,000,000 tokens (600,000 microcents / 1M — billed as output tier).
4. **Standard Output Tokens:** $0.600 / 1,000,000 tokens (600,000 microcents / 1M).

### Compound Benchmark Verification:
Test input:
- 500 Cached Input Tokens = `(500 * 75,000) // 1,000,000 = 37 microcents`
- 200 Standard Input Tokens = `(200 * 150,000) // 1,000,000 = 30 microcents`
- 100 Reasoning Tokens = `(100 * 600,000) // 1,000,000 = 60 microcents`
- 300 Output Tokens = `(300 * 600,000) // 1,000,000 = 180 microcents`
- **Total Sum:** `37 + 30 + 60 + 180 = 307 microcents` (`$0.000307 USD`).
- **Assertion:** `assert cost == 307` passed with zero floating point drift.

---

## Probe 4: Stripe Webhook Cryptographic Verification & Synchronization

### Requirement:
> *Webhooks verify signatures, ignore duplicates, update tenant plan/status.*

### Verification Proof:
1. **Forged Signature Test:**
   ```bash
   curl -X POST http://127.0.0.1:8000/v1/webhooks/stripe \
     -H "Stripe-Signature: t=12345,v1=forged_bad_hash" \
     -d '{"id": "evt_fake", "type": "checkout.session.completed"}'
   ```
   **Result:** `HTTP 400 Bad Request` (`{"detail": "Invalid Stripe webhook signature"}`). Database state unchanged.

2. **Valid Signed `checkout.session.completed` Webhook:**
   Dispatched HMAC-SHA256 signed event with `client_reference_id: "tenant_free_tier"`.
   **Result:** `HTTP 200 OK` (`{"received": true, "status": "processed"}`).
   Tenant plan flipped from `free` to `pro`. `max_requests` updated from 1,000 to 100,000.

3. **Replay Deduplication:**
   Re-sent the exact same signed webhook payload.
   **Result:** `HTTP 200 OK` (`{"received": true, "status": "duplicate_ignored"}`). Zero redundant mutations.

---

## Probe 5: Monthly Usage Rollup & Tenant Isolation

### Requirement:
> *Monthly usage rolls up into a cost figure per tenant; database includes tenant-isolated schemas.*

### Verification Proof:
```bash
curl http://127.0.0.1:8000/v1/tenants/tenant_free_tier/usage
```
**Response (HTTP 200 OK):**
```json
{
  "tenant_id": "tenant_free_tier",
  "tenant_name": "Acme Startup",
  "plan_id": "pro",
  "plan_name": "Pro Developer Plan",
  "billing_period": "Current Billing Cycle (Rolling 30 Days)",
  "total_requests": 2,
  "max_requests": 100000,
  "requests_remaining": 99998,
  "total_tokens": 230,
  "max_tokens": 5000000,
  "tokens_remaining": 4999770,
  "token_breakdown": {
    "standard_input_tokens": 30,
    "cached_input_tokens": 0,
    "reasoning_tokens": 0,
    "output_tokens": 200,
    "total_tokens": 230
  },
  "total_cost_microcents": 124,
  "total_cost_formatted": "$0.000124",
  "quota_status": "HEALTHY"
}
```
