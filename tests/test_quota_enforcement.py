import uuid
from fastapi.testclient import TestClient
from src.main import app
from src.database import init_db, get_connection

client = TestClient(app)

def setup_module():
    init_db()

def test_hard_quota_boundary_429():
    tenant_id = f"tenant_test_quota_{uuid.uuid4().hex[:6]}"
    
    # Insert custom test tenant with max_requests = 3
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO plans (id, name, max_requests, max_tokens, price_cents)
        VALUES ('micro_test_plan', 'Micro Test Plan', 3, 10000, 0);
    """)
    cursor.execute("""
        INSERT INTO tenants (id, name, api_key, plan_id)
        VALUES (?, 'Quota Prober', ?, 'micro_test_plan');
    """, (tenant_id, f"key_{tenant_id}"))
    conn.commit()
    conn.close()

    headers = {"X-Tenant-Id": tenant_id}
    payload = {"prompt": "Quick probe message"}

    # Request 1 -> 200 OK
    res1 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res1.status_code == 200

    # Request 2 -> 200 OK
    res2 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res2.status_code == 200

    # Request 3 -> 200 OK (hits exact quota boundary 3/3)
    res3 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res3.status_code == 200

    # Request 4 -> 429 Too Many Requests (Hard quota boundary enforced!)
    res4 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res4.status_code == 429
    err = res4.json()["detail"]
    assert err["error"] == "quota_exceeded"
    assert "Monthly request limit reached" in err["message"]
    assert err["upgrade_url"] == "/v1/billing/checkout"

if __name__ == "__main__":
    test_hard_quota_boundary_429()
    print("Hard quota boundary tests passed successfully!")
