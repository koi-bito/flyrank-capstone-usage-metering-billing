import uuid
import json
from typing import Optional, Dict, Any
from src.database import get_connection

def get_idempotency_record(idempotency_key: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Checks if this exact request has already been processed for this tenant.
    Guarantees exactly-once metering semantics under network retries.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT response_status, response_body, created_at
        FROM idempotency_records
        WHERE key = ? AND tenant_id = ?;
    """, (idempotency_key, tenant_id))
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "status_code": row["response_status"],
            "body": json.loads(row["response_body"]),
            "created_at": row["created_at"]
        }
    return None

def record_usage_and_idempotency(
    tenant_id: str,
    idempotency_key: str,
    standard_input_tokens: int,
    cached_input_tokens: int,
    reasoning_tokens: int,
    output_tokens: int,
    cost_microcents: int,
    response_status: int,
    response_body: Dict[str, Any]
):
    """
    Atomically inserts one usage event and stores the response against the idempotency key.
    """
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # 1. Insert Usage Event
        cursor.execute("""
            INSERT INTO usage_events (
                id, tenant_id, idempotency_key, event_type, request_count,
                standard_input_tokens, cached_input_tokens, reasoning_tokens,
                output_tokens, cost_microcents
            ) VALUES (?, ?, ?, 'generate', 1, ?, ?, ?, ?, ?);
        """, (
            event_id, tenant_id, idempotency_key,
            standard_input_tokens, cached_input_tokens, reasoning_tokens,
            output_tokens, cost_microcents
        ))

        # 2. Insert Idempotency Record
        cursor.execute("""
            INSERT INTO idempotency_records (key, tenant_id, response_status, response_body)
            VALUES (?, ?, ?, ?);
        """, (
            idempotency_key, tenant_id, response_status, json.dumps(response_body)
        ))

        conn.commit()
    finally:
        conn.close()
