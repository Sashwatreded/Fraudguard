#!/usr/bin/env python3
"""
FraudGuard — Slim API Server (browser demo)
============================================
Serves only the AI-engine endpoints that the frontend needs:
  POST /api/analyze-transaction  — full AI pipeline
  POST /api/analyze-csv          — batch CSV upload & analysis
  GET  /api/alerts               — reads fraud_alerts.log
  GET  /health                   — liveness probe
  GET  /stats                    — zero-data stub so the dashboard doesn't error
  GET  /transactions             — zero-data stub

No PostgreSQL / Redis / ML model required.
"""

import os, json, logging, csv, io
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
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


# ── CSV Batch endpoint ─────────────────────────────────────────────────────────
REQUIRED_CSV_COLS = {"amount", "hour", "risk_score", "txns_last_24h", "amount_last_24h"}

@app.post("/api/analyze-csv")
async def analyze_csv(file: UploadFile = File(...)):
    """
    Accept a CSV file upload.  Each row must contain at minimum:
      amount, hour, risk_score, txns_last_24h, amount_last_24h
    Optional: day / dayofweek  (defaults to 0 if absent)

    Returns:
      summary  — totals and tier counts
      results  — per-row analysis objects (capped at 200 rows)
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    contents = await file.read()
    try:
        text = contents.decode("utf-8-sig")   # handle BOM from Excel exports
    except UnicodeDecodeError:
        text = contents.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no header row.")

    # Normalise header names (strip whitespace, lowercase)
    fieldnames_norm = [f.strip().lower() for f in reader.fieldnames]
    missing = REQUIRED_CSV_COLS - set(fieldnames_norm)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"CSV is missing required columns: {', '.join(sorted(missing))}. "
                   f"Required: {', '.join(sorted(REQUIRED_CSV_COLS))}"
        )

    results = []
    errors  = []
    tier_counts = {"SAFE": 0, "SUSPICIOUS": 0, "HIGH_RISK": 0, "CRITICAL": 0}
    alert_count = 0
    MAX_ROWS = 200

    for i, raw_row in enumerate(reader, start=1):
        if i > MAX_ROWS:
            break
        # Normalise keys
        row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k}
        try:
            txn = {
                "amount":          float(row.get("amount", 0)),
                "hour":            int(float(row.get("hour", 0))),
                "txns_last_24h":   float(row.get("txns_last_24h", 0)),
                "amount_last_24h": float(row.get("amount_last_24h", 0)),
                "risk_score":      float(row.get("risk_score", 0)),
            }
            # Accept either 'day' or 'dayofweek'
            if "day" in row:
                txn["day"] = int(float(row["day"]))
                txn["dayofweek"] = txn["day"]
            elif "dayofweek" in row:
                txn["dayofweek"] = int(float(row["dayofweek"]))
                txn["day"] = txn["dayofweek"]
            else:
                txn["day"] = 0
                txn["dayofweek"] = 0

            result = process_transaction(txn)
            tier   = result["tier"]["tier"]
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            if result.get("alert_triggered"):
                alert_count += 1

            results.append({
                "row":             i,
                "transaction":     txn,
                "tier":            result["tier"],
                "ai_analysis":     result.get("ai_analysis"),
                "alert_triggered": result.get("alert_triggered", False),
                "timestamp":       result.get("timestamp"),
            })
        except (ValueError, KeyError) as exc:
            errors.append({"row": i, "error": str(exc)})

    total = len(results)
    fraud_rows = tier_counts.get("HIGH_RISK", 0) + tier_counts.get("CRITICAL", 0)

    return JSONResponse(content={
        "summary": {
            "total_rows":          total,
            "total_transactions":  total,          # legacy key kept for compatibility
            "fraud_count":         fraud_rows,
            "alert_count":         alert_count,
            "tier_counts":         tier_counts,
            "parse_errors":        len(errors),
            "truncated":           i > MAX_ROWS if total else False,
        },
        "results": results,
        "errors":  errors,
    })


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
