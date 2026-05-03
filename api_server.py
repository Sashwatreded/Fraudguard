#!/usr/bin/env python3
"""
FraudGuard — Slim API Server (browser demo)
============================================
Serves only the AI-engine endpoints that the frontend needs:
  POST /api/analyze-transaction  — full AI pipeline
  GET  /api/alerts               — reads fraud_alerts.log
  GET  /health                   — liveness probe
  GET  /stats                    — zero-data stub so the dashboard doesn't error
  GET  /transactions             — zero-data stub

No PostgreSQL / Redis / ML model required.
"""

import os, json, logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.fraud_ai_engine import process_transaction, ALERT_LOG_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="FraudGuard AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request schema ─────────────────────────────────────────────────────────────
class AITransactionRequest(BaseModel):
    amount: float
    hour: int
    day: Optional[int] = None
    dayofweek: Optional[int] = None
    txns_last_24h: float
    amount_last_24h: float
    risk_score: float


# ── AI endpoints ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "healthy", "model_loaded": False, "database_connected": False}

@app.get("/stats")
def stats():
    """Stub — returns zeros so the overview tab doesn't error."""
    return {
        "total_transactions": 0,
        "fraud_count": 0,
        "fraud_percentage": 0.0,
        "hourly_stats": [],
        "daily_stats": [],
    }

@app.get("/transactions")
def transactions(limit: int = 15):
    """Stub — returns empty list."""
    return {"transactions": []}

@app.post("/api/analyze-transaction")
def analyze_transaction(req: AITransactionRequest):
    txn = req.dict()
    if txn.get("day") is None and txn.get("dayofweek") is not None:
        txn["day"] = txn["dayofweek"]
    elif txn.get("dayofweek") is None and txn.get("day") is not None:
        txn["dayofweek"] = txn["day"]
    else:
        txn.setdefault("day", 0)
        txn.setdefault("dayofweek", 0)
    return process_transaction(txn)

@app.get("/api/alerts")
def get_alerts(limit: int = 20):
    if not os.path.exists(ALERT_LOG_PATH):
        return {"alerts": [], "total": 0}
    with open(ALERT_LOG_PATH, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    recent = lines[-limit:][::-1]
    alerts = []
    for line in recent:
        try:
            alerts.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return {"alerts": alerts, "total": len(lines)}

# ── Serve frontend static files at / ──────────────────────────────────────────
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")
