import sqlite3
import os
from src.config import DATABASE_FILE, PLANS

def get_connection():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Plans Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            max_requests INTEGER NOT NULL,
            max_tokens INTEGER NOT NULL,
            price_cents INTEGER NOT NULL
        );
    """)

    # 2. Tenants Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            plan_id TEXT NOT NULL DEFAULT 'free',
            stripe_customer_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. Subscriptions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            stripe_subscription_id TEXT UNIQUE,
            status TEXT NOT NULL DEFAULT 'active',
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );
    """)

    # 4. Usage Events Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_events (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'generate',
            request_count INTEGER NOT NULL DEFAULT 1,
            standard_input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cost_microcents INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        );
    """)

    # 5. Idempotency Records Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_records (
            key TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            response_status INTEGER NOT NULL,
            response_body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (key, tenant_id)
        );
    """)

    # 6. Processed Webhooks Table (Deduplication)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_webhooks (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Indexes for production performance and tenant isolation
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_tenant_date ON usage_events(tenant_id, created_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_idem ON usage_events(tenant_id, idempotency_key);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_apikey ON tenants(api_key);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_stripe_cust ON tenants(stripe_customer_id);")

    # Seed Plans
    for plan_id, plan in PLANS.items():
        cursor.execute("""
            INSERT OR REPLACE INTO plans (id, name, max_requests, max_tokens, price_cents)
            VALUES (?, ?, ?, ?, ?);
        """, (plan["id"], plan["name"], plan["max_requests"], plan["max_tokens"], plan["price_cents"]))

    # Seed Default Tenants
    cursor.execute("""
        INSERT OR IGNORE INTO tenants (id, name, api_key, plan_id, stripe_customer_id)
        VALUES ('tenant_free_tier', 'Acme Startup', 'key_acme_free_123', 'free', 'cus_mock_acme_1');
    """)
    cursor.execute("""
        INSERT OR IGNORE INTO tenants (id, name, api_key, plan_id, stripe_customer_id)
        VALUES ('tenant_pro_tier', 'Globex Enterprise', 'key_globex_pro_456', 'pro', 'cus_mock_globex_2');
    """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized with indexes and seeded plans.")
