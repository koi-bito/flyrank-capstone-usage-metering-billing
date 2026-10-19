import os
import time
import uuid
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import uvicorn

from src.database import init_db, get_connection
from src.models import (
    GenerateRequest, GenerateResponse, TokenUsageBreakdown,
    UsageSummaryResponse, CheckoutRequest, CheckoutResponse
)
from src.pricing import calculate_token_cost, microcents_to_formatted_string
from src.services.quota_service import enforce_quota, get_usage_summary, get_tenant_and_plan
from src.services.metering_service import get_idempotency_record, record_usage_and_idempotency
from src.services.billing_service import verify_stripe_signature, process_webhook_event
from src.background import run_reconciliation_job

app = FastAPI(title="Usage Metering & Billing Engine", version="1.0.0")

# Ensure schema exists on boot and during test execution
init_db()

@app.on_event("startup")
def startup_db():
    init_db()

def authenticate_tenant(
    authorization: Optional[str] = Header(None),
    x_tenant_id: Optional[str] = Header(None)
) -> dict:
    """Authenticates API requests via Bearer token or direct X-Tenant-Id header."""
    conn = get_connection()
    cursor = conn.cursor()

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        cursor.execute("SELECT id, name, plan_id FROM tenants WHERE api_key = ?;", (token,))
    elif x_tenant_id:
        cursor.execute("SELECT id, name, plan_id FROM tenants WHERE id = ?;", (x_tenant_id,))
    else:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication. Provide 'Authorization: Bearer <key>' or 'X-Tenant-Id: <id>' header."
        )

    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key or tenant ID")
    return dict(row)

@app.get("/health")
def health():
    return {"status": "ok", "service": "usage-metering-billing-engine"}

@app.post("/v1/chat/completions", response_model=GenerateResponse)
async def generate_completion(
    req: GenerateRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    tenant: dict = Depends(authenticate_tenant)
):
    tenant_id = tenant["id"]

    # Generate fallback idempotency key if client omitted header
    if not idempotency_key:
        idempotency_key = f"auto_{uuid.uuid4().hex}"

    # 1. Exactly-Once Metering: Check Idempotency Record
    cached_record = get_idempotency_record(idempotency_key, tenant_id)
    if cached_record:
        # Return identical response; DO NOT decrement quota or record additional usage
        cached_data = cached_record["body"]
        cached_data["cached_response"] = True
        return JSONResponse(status_code=cached_record["status_code"], content=cached_data)

    # 2. Estimate Token Consumption
    raw_words = len(req.prompt.split())
    if req.use_cached_prompt:
        cached_input = max(10, raw_words * 3)
        std_input = max(5, raw_words)
    else:
        cached_input = 0
        std_input = max(15, raw_words * 4)

    reasoning = 128 if req.reasoning_effort in ["high", "low"] else 0
    output_tokens = min(req.max_tokens, 150)
    total_tokens = cached_input + std_input + reasoning + output_tokens

    # 3. Quota Boundary Enforcement (429 Too Many Requests if exceeded)
    enforce_quota(tenant_id, estimated_tokens=total_tokens)

    # 4. Strict Financial Math (Microcents)
    cost_microcents = calculate_token_cost(
        standard_input_tokens=std_input,
        cached_input_tokens=cached_input,
        reasoning_tokens=reasoning,
        output_tokens=output_tokens
    )

    # 5. Construct Response
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    usage_breakdown = TokenUsageBreakdown(
        standard_input_tokens=std_input,
        cached_input_tokens=cached_input,
        reasoning_tokens=reasoning,
        output_tokens=output_tokens,
        total_tokens=total_tokens
    )

    response_payload = {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "gpt-4o-mini-metered",
        "output_text": f"Simulated defensive completion for prompt: '{req.prompt[:30]}...'",
        "usage": usage_breakdown.model_dump(),
        "cost_microcents": cost_microcents,
        "cost_formatted": microcents_to_formatted_string(cost_microcents),
        "cached_response": False
    }

    # 6. Atomic Usage Event & Idempotency Storage
    record_usage_and_idempotency(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        standard_input_tokens=std_input,
        cached_input_tokens=cached_input,
        reasoning_tokens=reasoning,
        output_tokens=output_tokens,
        cost_microcents=cost_microcents,
        response_status=status.HTTP_200_OK,
        response_body=response_payload
    )

    return JSONResponse(status_code=status.HTTP_200_OK, content=response_payload)

@app.get("/v1/tenants/me/usage", response_model=UsageSummaryResponse)
def get_my_usage(tenant: dict = Depends(authenticate_tenant)):
    return get_usage_summary(tenant["id"])

@app.get("/v1/tenants/{tenant_id}/usage", response_model=UsageSummaryResponse)
def get_tenant_usage_by_id(tenant_id: str):
    return get_usage_summary(tenant_id)

@app.post("/v1/billing/checkout", response_model=CheckoutResponse)
def create_checkout_session(
    req: CheckoutRequest,
    tenant: dict = Depends(authenticate_tenant)
):
    session_id = f"cs_test_{uuid.uuid4().hex[:14]}"
    customer_id = tenant.get("stripe_customer_id") or f"cus_{uuid.uuid4().hex[:8]}"

    return CheckoutResponse(
        checkout_url=f"https://checkout.stripe.com/c/pay/{session_id}",
        session_id=session_id,
        customer_id=customer_id
    )

@app.post("/v1/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature")
):
    payload_bytes = await request.body()

    # Verify cryptographic signature
    if not stripe_signature or not verify_stripe_signature(payload_bytes, stripe_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Stripe webhook signature")

    import json
    event_data = json.loads(payload_bytes.decode("utf-8"))
    _, status_msg = process_webhook_event(event_data)

    return {"received": True, "status": status_msg}

@app.post("/v1/jobs/reconcile")
def trigger_reconciliation():
    log = run_reconciliation_job()
    return {"status": "completed", "reconciled_tenants": len(log), "audit": log}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=True)
