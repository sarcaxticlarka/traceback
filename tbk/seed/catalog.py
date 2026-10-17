"""Static vocabulary for the synthetic company (service names, teams, signals, people)."""
from __future__ import annotations

SERVICES_BY_LAYER: dict[int, list[str]] = {
    0: ["auth-service", "db-proxy", "message-bus", "cache-redis", "config-service", "identity-gateway"],
    1: ["ledger-store", "orders-store", "inventory-store", "catalog-store", "sessions-store", "profile-store",
        "search-index", "media-store", "analytics-store", "audit-log", "billing-store", "notifications-queue",
        "events-stream", "scheduler-queue"],
    2: ["payments-worker", "ledger-service", "orders-service", "inventory-service", "pricing-service",
        "promotions-service", "tax-service", "currency-service", "fraud-service", "risk-service", "kyc-service",
        "shipping-service", "invoicing-service", "refunds-service", "notifications-service", "email-sender",
        "sms-sender", "recommendations-service", "reviews-service", "loyalty-service", "geo-service",
        "uploads-service", "reporting-service", "workflow-engine"],
    3: ["payments-api", "checkout-api", "cart-api", "orders-api", "catalog-api", "search-api", "shipping-api",
        "billing-api", "refunds-api", "profile-api", "onboarding-api", "sessions-api", "notifications-api",
        "loyalty-api", "promotions-api", "recommendations-api", "reviews-api", "wishlist-api", "partners-api",
        "webhooks-api", "analytics-api", "reporting-api", "media-api", "admin-api"],
    4: ["web-bff", "mobile-bff", "partner-gateway", "public-api-gateway", "admin-console", "checkout-web",
        "support-portal", "seller-portal", "internal-tools", "status-page", "ops-dashboard", "developer-portal"],
}

TIER_BY_LAYER = {0: 0, 1: 1, 2: 1, 3: 2, 4: 3}

TEAMS = ["payments", "checkout", "platform", "data", "identity", "growth", "logistics", "trust"]
LEGACY_TEAM = "legacy-platform"
GHOST_SERVICES = ["reviews-api", "wishlist-api", "email-sender", "sms-sender"]   # owned by a team nobody is on

TEAM_KEYWORDS = {
    "payments": ["payment", "ledger", "billing", "invoic", "refund", "tax", "currency"],
    "checkout": ["checkout", "cart", "orders", "promotions", "pricing", "inventory"],
    "identity": ["auth", "identity", "sessions", "profile", "onboarding", "kyc"],
    "trust": ["fraud", "risk", "audit"],
    "data": ["analytics", "reporting", "events", "search", "recommendations", "catalog"],
    "logistics": ["shipping", "geo", "scheduler"],
    "growth": ["loyalty", "notifications", "wishlist", "reviews", "partner", "media", "uploads", "webhooks"],
    "platform": ["db-proxy", "message-bus", "cache", "config", "workflow", "internal", "ops", "status",
                 "admin", "developer", "gateway", "bff", "portal", "console", "web"],
}

GENERAL_SIGNALS = ["high-latency", "error-rate", "queue-backlog", "oom-kill", "cert-expiry", "disk-pressure"]
SPECIAL_SIGNALS = {"cache-redis": "redis-timeout", "db-proxy": "conn-pool-exhaustion"}
ALL_SIGNALS = GENERAL_SIGNALS + ["redis-timeout", "conn-pool-exhaustion"]

RUNBOOK_STEPS = {
    "high-latency": ["Compare p99 against the last deploy", "Scale replicas by 50%", "Enable request shedding"],
    "error-rate": ["Check last deploy diff", "Roll back the latest release", "Flush poison messages"],
    "queue-backlog": ["Add consumers", "Pause producers", "Drain dead-letter queue"],
    "oom-kill": ["Raise memory limit", "Capture heap dump", "Restart rolling"],
    "cert-expiry": ["Rotate certificate", "Reload ingress", "Verify chain"],
    "disk-pressure": ["Expand volume", "Prune logs", "Move cold data"],
    "redis-timeout": ["Check connection count", "Fail over to replica", "Raise client timeout"],
    "conn-pool-exhaustion": ["Raise pool size", "Kill idle sessions", "Restart the proxy"],
}

FIRST = ["Ava", "Noah", "Mia", "Liam", "Zoe", "Ethan", "Ira", "Kabir", "Lena", "Omar", "Priya", "Ravi", "Sara",
         "Tariq", "Uma", "Victor", "Wen", "Xiao", "Yusuf", "Zara", "Aditi", "Bruno", "Chloe", "Dev", "Elif",
         "Felix", "Gita", "Hugo", "Isla", "Jonas", "Kira", "Leo", "Maya", "Nico", "Opal", "Pablo", "Quinn",
         "Rhea", "Sven", "Tess"]
LAST = ["Alvarez", "Bose", "Chen", "Diaz", "Evans", "Fischer", "Gupta", "Haas", "Ito", "Jones", "Khan", "Lopez",
        "Mehta", "Novak", "Okafor", "Park", "Quist", "Rossi", "Singh", "Tanaka"]

TECH_CHOICES = [
    ("Postgres", "ledger writes"), ("Kafka", "event delivery"), ("gRPC", "internal calls"),
    ("Redis Cluster", "session caching"), ("OpenTelemetry", "tracing"), ("Feature flags", "rollouts"),
    ("Blue/green deploys", "releases"), ("mTLS", "service auth"),
]
