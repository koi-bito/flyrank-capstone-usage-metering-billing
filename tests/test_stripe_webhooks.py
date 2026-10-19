import json
import uuid
import time
from fastapi.testclient import TestClient
from src.main import app
from src.database import init_db, get_connection
from src.services.billing_service import generate_test_signature
from src.config import STRIPE_WEBHOOK_SECRET

client = TestClient(app)

def setup_module():
    init_db()

def test_forged_webhook_signature_rejected():
    payload = json.dumps({"id": "evt_fake_1", "type": "checkout.session.completed"}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": "t=12345,v1=bad_forged_signature_hex"
    }
    res = client.post("/v1/webhooks/stripe", content=payload, headers=headers)
    assert res.status_code == 400
    assert "Invalid Stripe webhook signature" in res.json()["detail"]

def test_valid_checkout_completed_upgrades_tenant_and_deduplicates():
    tenant_id = "tenant_free_tier"
    event_id = f"evt_stripe_{uuid.uuid4().hex[:10]}"
    now = int(time.time())

    event_payload = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_session_123",
                "client_reference_id": tenant_id,
                "customer": "cus_acme_new_123",
                "subscription": "sub_acme_pro_456"
            }
        }
    }
    payload_bytes = json.dumps(event_payload).encode("utf-8")
    valid_sig = generate_test_signature(payload_bytes, secret=STRIPE_WEBHOOK_SECRET, timestamp=now)

    headers = {
        "Content-Type": "application/json",
        "Stripe-Signature": valid_sig
    }

    # 1. Process valid webhook
    res1 = client.post("/v1/webhooks/stripe", content=payload_bytes, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "processed"

    # Verify tenant is now on PRO plan
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan_id FROM tenants WHERE id = ?;", (tenant_id,))
    plan = cursor.fetchone()[0]
    assert plan == "pro", "Tenant must be upgraded to 'pro' plan upon checkout completion"

    # 2. Replay duplicate event -> Ignored
    res2 = client.post("/v1/webhooks/stripe", content=payload_bytes, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate_ignored"

    # 3. Process subscription cancellation -> Downgrade back to Free
    cancel_id = f"evt_cancel_{uuid.uuid4().hex[:10]}"
    cancel_payload = {
        "id": cancel_id,
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_acme_new_123"
            }
        }
    }
    cancel_bytes = json.dumps(cancel_payload).encode("utf-8")
    cancel_sig = generate_test_signature(cancel_bytes, secret=STRIPE_WEBHOOK_SECRET, timestamp=now)
    res_cancel = client.post("/v1/webhooks/stripe", content=cancel_bytes, headers={"Content-Type": "application/json", "Stripe-Signature": cancel_sig})
    assert res_cancel.status_code == 200

    cursor.execute("SELECT plan_id FROM tenants WHERE id = ?;", (tenant_id,))
    downgraded_plan = cursor.fetchone()[0]
    conn.close()
    assert downgraded_plan == "free", "Tenant must downgrade to 'free' upon subscription cancellation"

if __name__ == "__main__":
    test_forged_webhook_signature_rejected()
    test_valid_checkout_completed_upgrades_tenant_and_deduplicates()
    print("Stripe webhook verification and synchronization tests passed successfully!")
