from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Prompt text to process")
    max_tokens: Optional[int] = Field(256, ge=1, le=4096)
    reasoning_effort: Optional[str] = Field("none", description="Reasoning mode: 'none', 'low', 'high'")
    use_cached_prompt: Optional[bool] = Field(False, description="Whether prompt matches cached system prompt prefix")

class TokenUsageBreakdown(BaseModel):
    standard_input_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

class GenerateResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str = "gpt-4o-mini-metered"
    output_text: str
    usage: TokenUsageBreakdown
    cost_microcents: int
    cost_formatted: str
    cached_response: bool = False

class UsageSummaryResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    plan_id: str
    plan_name: str
    billing_period: str
    total_requests: int
    max_requests: int
    requests_remaining: int
    total_tokens: int
    max_tokens: int
    tokens_remaining: int
    token_breakdown: TokenUsageBreakdown
    total_cost_microcents: int
    total_cost_formatted: str
    quota_status: str

class CheckoutRequest(BaseModel):
    target_plan: str = "pro"

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    customer_id: str
