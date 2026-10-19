import hmac
import hashlib
import time
import uuid
from typing import Dict, Any, Tuple
from fastapi import HTTPException, status
from src.database import get_connection
from src.config import STRIPE_WEBHOOK_SECRET

def verify_stripe_signature(payload_bytes: bytes, sig_header: str, secret: str = STRIPE_WEBHOOK_SECRET) -> bool:
    """
    Verifies Stripe's HMAC-SHA256 webhook signature.
    Format: t=timestamp,v1=signature_hash
    """
    if not sig_header:
        return False

    elements = dict(item.split("=") for item in sig_header.split(",") if "=" in item)
    timestamp = elements.get("t")
    v1_sig = elements.get("v1")

    if not timestamp or not v1_sig:
        return False

    # Prevent replay attacks older than 5 minutes
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False

    signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, v1_sig)

def generate_test_signature(payload_bytes: bytes, secret: str = STRIPE_WEBHOOK_SECRET, timestamp: int = None) -> str:
    """Helper for test suites to construct valid Stripe signatures."""
    if timestamp is None:
        timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
    signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"

def process_webhook_event(event_dict: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Idempotently processes Stripe webhook events.
    Returns (success, message).
    """
    event_id = event_dict.get("id")
    event_type = event_dict.get("type")
    data = event_dict.get("data", {}).get("object", {})

    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Malformed webhook event structure")

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Deduplication Check
    cursor.execute("SELECT event_id FROM processed_webhooks WHERE event_id = ?;", (event_id,))
    if cursor.fetchone():
        conn.close()
        return True, "duplicate_ignored"

    # 2. Event Handling
    if event_type in ["checkout.session.completed", "customer.subscription.created"]:
        # Upgrade tenant to Pro
        tenant_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        sub_id = data.get("subscription") or f"sub_{uuid.uuid4().hex[:10]}"

        if tenant_id:
            cursor.execute("""
                UPDATE tenants
                SET plan_id = 'pro', stripe_customer_id = COALESCE(?, stripe_customer_id)
                WHERE id = ?;
            """, (customer_id, tenant_id))

            cursor.execute("""
                INSERT OR REPLACE INTO subscriptions (id, tenant_id, stripe_subscription_id, status)
                VALUES (?, ?, ?, 'active');
            """, (f"sub_rec_{uuid.uuid4().hex[:8]}", tenant_id, sub_id))

    elif event_type == "customer.subscription.deleted":
        # Downgrade to Free
        customer_id = data.get("customer")
        if customer_id:
            cursor.execute("""
                UPDATE tenants
                SET plan_id = 'free'
                WHERE stripe_customer_id = ?;
            """, (customer_id,))

            cursor.execute("""
                UPDATE subscriptions
                SET status = 'canceled'
                WHERE tenant_id IN (SELECT id FROM tenants WHERE stripe_customer_id = ?);
            """, (customer_id,))

    # 3. Mark event as processed
    cursor.execute("INSERT INTO processed_webhooks (event_id, event_type) VALUES (?, ?);", (event_id, event_type))
    conn.commit()
    conn.close()

    return True, "processed"
