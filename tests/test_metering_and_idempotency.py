import uuid
from fastapi.testclient import TestClient
from src.main import app
from src.database import init_db, get_connection

client = TestClient(app)

def setup_module():
    init_db()

def test_idempotent_metering_deduplication():
    tenant_id = "tenant_free_tier"
    key = f"idem_key_{uuid.uuid4().hex}"
    payload = {
        "prompt": "Explain the difference between SQLite and PostgreSQL in two sentences.",
        "max_tokens": 100,
        "reasoning_effort": "none"
    }
    headers = {
        "X-Tenant-Id": tenant_id,
        "Idempotency-Key": key
    }

    # 1. First Request
    res1 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["cached_response"] is False
    completion_id = data1["id"]

    # Verify 1 record in usage_events table
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM usage_events WHERE idempotency_key = ?;", (key,))
    count1 = cursor.fetchone()[0]
    assert count1 == 1, "Exactly one usage event must be created on initial request"

    # 2. Replay duplicate request with same idempotency key
    res2 = client.post("/v1/chat/completions", json=payload, headers=headers)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["id"] == completion_id, "Replayed response must match original completion ID"
    assert data2["cached_response"] is True, "Response must indicate cached delivery"

    # Verify STILL exactly 1 record in database (zero double-charging)
    cursor.execute("SELECT COUNT(*) FROM usage_events WHERE idempotency_key = ?;", (key,))
    count2 = cursor.fetchone()[0]
    conn.close()
    assert count2 == 1, "Duplicate request must NEVER create a second usage event"

if __name__ == "__main__":
    test_idempotent_metering_deduplication()
    print("Idempotent metering tests passed successfully!")
