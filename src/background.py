import time
import datetime
from typing import Dict, Any, List
from src.database import get_connection
from src.services.quota_service import get_current_period_usage
from src.pricing import microcents_to_formatted_string

def run_reconciliation_job() -> List[Dict[str, Any]]:
    """
    Background job that audits all tenant usage, reconciles period metrics,
    and purges expired idempotency records.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, plan_id FROM tenants;")
    tenants = [dict(r) for r in cursor.fetchall()]

    audit_log = []
    for t in tenants:
        usage = get_current_period_usage(t["id"])
        summary = {
            "tenant_id": t["id"],
            "name": t["name"],
            "plan_id": t["plan_id"],
            "requests": usage["total_requests"],
            "tokens": usage["total_tokens"],
            "cost": microcents_to_formatted_string(usage["total_cost_microcents"]),
            "timestamp": time.time()
        }
        audit_log.append(summary)
        print(f"[RECONCILIATION WORKER] Tenant: {t['id']} | Req: {usage['total_requests']} | Tokens: {usage['total_tokens']} | Cost: {summary['cost']}")

    # Purge idempotency keys older than 7 days
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM idempotency_records WHERE created_at < ?;", (cutoff,))
    purged_count = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"[RECONCILIATION WORKER] Reconciled {len(tenants)} tenants. Purged {purged_count} stale idempotency keys.")
    return audit_log
