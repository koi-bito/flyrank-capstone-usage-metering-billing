import datetime
from fastapi import HTTPException, status
from src.database import get_connection
from src.config import PLANS
from src.models import UsageSummaryResponse, TokenUsageBreakdown
from src.pricing import microcents_to_formatted_string

def get_tenant_and_plan(tenant_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.name, t.api_key, t.plan_id, t.stripe_customer_id,
               p.name as plan_name, p.max_requests, p.max_tokens, p.price_cents
        FROM tenants t
        LEFT JOIN plans p ON t.plan_id = p.id
        WHERE t.id = ?;
    """, (tenant_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")
    return dict(row)

def get_current_period_usage(tenant_id: str):
    """Calculates total usage within the current 30-day billing window."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Rolling 30 days or current calendar month
    start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        SELECT 
            COALESCE(SUM(request_count), 0) as total_requests,
            COALESCE(SUM(standard_input_tokens), 0) as std_input,
            COALESCE(SUM(cached_input_tokens), 0) as cached_input,
            COALESCE(SUM(reasoning_tokens), 0) as reasoning,
            COALESCE(SUM(output_tokens), 0) as output,
            COALESCE(SUM(cost_microcents), 0) as total_cost
        FROM usage_events
        WHERE tenant_id = ? AND created_at >= ?;
    """, (tenant_id, start_date))
    row = cursor.fetchone()
    conn.close()

    total_tokens = row["std_input"] + row["cached_input"] + row["reasoning"] + row["output"]

    return {
        "total_requests": row["total_requests"],
        "total_tokens": total_tokens,
        "std_input": row["std_input"],
        "cached_input": row["cached_input"],
        "reasoning": row["reasoning"],
        "output": row["output"],
        "total_cost_microcents": row["total_cost"]
    }

def enforce_quota(tenant_id: str, estimated_tokens: int = 500):
    """
    Validates tenant quota before executing any billable action.
    Returns HTTP 429 if request or token limits are exceeded.
    """
    tenant = get_tenant_and_plan(tenant_id)
    usage = get_current_period_usage(tenant_id)

    max_reqs = tenant["max_requests"]
    max_tokens = tenant["max_tokens"]

    # 1. Check Request Quota Boundary
    if usage["total_requests"] + 1 > max_reqs:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "message": f"Monthly request limit reached ({usage['total_requests']}/{max_reqs} requests used on {tenant['plan_name']}).",
                "plan": tenant["plan_id"],
                "upgrade_url": "/v1/billing/checkout"
            }
        )

    # 2. Check Token Quota Boundary
    if usage["total_tokens"] + estimated_tokens > max_tokens:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "quota_exceeded",
                "message": f"Monthly token limit reached ({usage['total_tokens']}/{max_tokens} tokens used on {tenant['plan_name']}).",
                "plan": tenant["plan_id"],
                "upgrade_url": "/v1/billing/checkout"
            }
        )

    return tenant

def get_usage_summary(tenant_id: str) -> UsageSummaryResponse:
    tenant = get_tenant_and_plan(tenant_id)
    usage = get_current_period_usage(tenant_id)

    req_rem = max(0, tenant["max_requests"] - usage["total_requests"])
    tok_rem = max(0, tenant["max_tokens"] - usage["total_tokens"])

    status_str = "HEALTHY"
    if req_rem == 0 or tok_rem == 0:
        status_str = "EXCEEDED"
    elif req_rem < (tenant["max_requests"] * 0.2) or tok_rem < (tenant["max_tokens"] * 0.2):
        status_str = "WARNING"

    return UsageSummaryResponse(
        tenant_id=tenant["id"],
        tenant_name=tenant["name"],
        plan_id=tenant["plan_id"],
        plan_name=tenant["plan_name"],
        billing_period="Current Billing Cycle (Rolling 30 Days)",
        total_requests=usage["total_requests"],
        max_requests=tenant["max_requests"],
        requests_remaining=req_rem,
        total_tokens=usage["total_tokens"],
        max_tokens=tenant["max_tokens"],
        tokens_remaining=tok_rem,
        token_breakdown=TokenUsageBreakdown(
            standard_input_tokens=usage["std_input"],
            cached_input_tokens=usage["cached_input"],
            reasoning_tokens=usage["reasoning"],
            output_tokens=usage["output"],
            total_tokens=usage["total_tokens"]
        ),
        total_cost_microcents=usage["total_cost_microcents"],
        total_cost_formatted=microcents_to_formatted_string(usage["total_cost_microcents"]),
        quota_status=status_str
    )
