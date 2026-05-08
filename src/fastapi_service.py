from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
import joblib
import pandas as pd
import numpy as np
from lightgbm import LGBMClassifier
from pydantic import BaseModel
from typing import List, Optional
import json
import uuid
import datetime
import os
from fastapi.middleware.cors import CORSMiddleware
import logging
import csv
import io

# Load .env if present (for GEMINI_API_KEY etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import AI engine (Upgrades 1–4)
try:
    from src.fraud_ai_engine import process_transaction, classify_risk_tier, ALERT_LOG_PATH
    _AI_ENGINE_AVAILABLE = True
except Exception as _ai_import_err:
    _AI_ENGINE_AVAILABLE = False
    logging.getLogger(__name__).warning(f"AI engine not available: {_ai_import_err}")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Import Redis cache
from src.redis_cache import get_cached_transaction, cache_transaction

# Database connection (PostgreSQL)
try:
    import psycopg2
    from psycopg2.extras import Json
    
    # Initialize database connection
    # Replace with your actual database credentials
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_NAME = os.getenv("DB_NAME", "fraud_detection")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
    
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    
    # Create predictions table if it doesn't exist
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id SERIAL PRIMARY KEY,
            transaction_id VARCHAR(50),
            transaction_data JSONB,
            prediction BOOLEAN,
            confidence FLOAT,
            timestamp TIMESTAMP
        )
        """)
        conn.commit()
    
    db_available = True
    logger.info("Database connection established")
except Exception as e:
    logger.warning(f"Database connection failed: {str(e)}")
    db_available = False

app = FastAPI(title="Fraud Detection API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Load trained model
try:
    model = joblib.load('src/fraud_detection_model.pkl')
    logger.info("Model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load model: {str(e)}")
    model = None

# Define request body schema
class Transaction(BaseModel):
    amount: float
    hour: int
    dayofweek: int
    txns_last_24h: float
    amount_last_24h: float
    risk_score: float
    transaction_id: Optional[str] = None

class BatchTransactions(BaseModel):
    transactions: List[Transaction]

class PredictionResponse(BaseModel):
    transaction_id: str
    is_fraud: bool
    confidence: float
    timestamp: str

class BatchPredictionResponse(BaseModel):
    predictions: List[PredictionResponse]
    summary: dict

def log_prediction(transaction_id, transaction_data, prediction, confidence):
    """Log prediction to database if available"""
    if db_available:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO predictions 
                    (transaction_id, transaction_data, prediction, confidence, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        transaction_id,
                        Json(transaction_data),
                        prediction,
                        confidence,
                        datetime.datetime.now()
                    )
                )
                conn.commit()
            logger.info(f"Prediction logged for transaction {transaction_id}")
        except Exception as e:
            logger.error(f"Failed to log prediction: {str(e)}")
    else:
        logger.warning("Database not available, prediction not logged")

@app.get("/")
def home():
    return {"message": "Fraud Detection API is running!"}

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "database_connected": db_available
    }

@app.post("/predict", response_model=PredictionResponse)
def predict_fraud(transaction: Transaction):
    """Predict fraud for a single transaction"""
    if model is None:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    try:
        # Generate transaction ID if not provided
        transaction_id = transaction.transaction_id or str(uuid.uuid4())
        
        # Check cache first
        cached_result = get_cached_transaction(transaction_id)
        if cached_result:
            return PredictionResponse(
                transaction_id=transaction_id,
                is_fraud=cached_result["is_fraud"],
                confidence=cached_result["confidence"],
                timestamp=datetime.datetime.now().isoformat()
            )
        
        # Prepare data for prediction
        df = pd.DataFrame([transaction.dict()])
        
        # Remove transaction_id from features
        if "transaction_id" in df.columns:
            df = df.drop("transaction_id", axis=1)
        
        # Ensure feature names match the model's training data
        df.rename(columns={"amount": "Amount"}, inplace=True)
        
        # Predict fraud using the trained model
        is_fraud = bool(model.predict(df)[0])
        
        # Get prediction probabilities for confidence score
        proba = model.predict_proba(df)[0]
        confidence = float(proba[1] if is_fraud else proba[0])
        
        # Cache the result
        result = {
            "is_fraud": is_fraud,
            "confidence": confidence
        }
        cache_transaction(transaction_id, result)
        
        # Log prediction to database
        log_prediction(
            transaction_id=transaction_id,
            transaction_data=transaction.dict(),
            prediction=is_fraud,
            confidence=confidence
        )
        
        return PredictionResponse(
            transaction_id=transaction_id,
            is_fraud=is_fraud,
            confidence=confidence,
            timestamp=datetime.datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Prediction error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/predict/batch", response_model=BatchPredictionResponse)
def predict_batch(batch: BatchTransactions):
    """Predict fraud for a batch of transactions"""
    if model is None:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    try:
        predictions = []
        
        for transaction in batch.transactions:
            transaction_id = transaction.transaction_id or str(uuid.uuid4())
            
            # Check cache first
            cached_result = get_cached_transaction(transaction_id)
            if cached_result:
                predictions.append(
                    PredictionResponse(
                        transaction_id=transaction_id,
                        is_fraud=cached_result["is_fraud"],
                        confidence=cached_result["confidence"],
                        timestamp=datetime.datetime.now().isoformat()
                    )
                )
                continue
            
            # Prepare data for prediction
            df = pd.DataFrame([transaction.dict()])
            
            # Remove transaction_id from features
            if "transaction_id" in df.columns:
                df = df.drop("transaction_id", axis=1)
            
            # Ensure feature names match the model's training data
            df.rename(columns={"amount": "Amount"}, inplace=True)
            
            # Predict fraud using the trained model
            is_fraud = bool(model.predict(df)[0])
            
            # Get prediction probabilities for confidence score
            proba = model.predict_proba(df)[0]
            confidence = float(proba[1] if is_fraud else proba[0])
            
            # Cache the result
            result = {
                "is_fraud": is_fraud,
                "confidence": confidence
            }
            cache_transaction(transaction_id, result)
            
            # Log prediction to database
            log_prediction(
                transaction_id=transaction_id,
                transaction_data=transaction.dict(),
                prediction=is_fraud,
                confidence=confidence
            )
            
            predictions.append(
                PredictionResponse(
                    transaction_id=transaction_id,
                    is_fraud=is_fraud,
                    confidence=confidence,
                    timestamp=datetime.datetime.now().isoformat()
                )
            )
        
        # Generate summary statistics
        fraud_count = sum(1 for p in predictions if p.is_fraud)
        total_count = len(predictions)
        
        summary = {
            "total_transactions": total_count,
            "fraud_count": fraud_count,
            "fraud_percentage": (fraud_count / total_count) * 100 if total_count > 0 else 0,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return BatchPredictionResponse(
            predictions=predictions,
            summary=summary
        )
    except Exception as e:
        logger.error(f"Batch prediction error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/predict/csv")
async def predict_from_csv(file: UploadFile = File(...)):
    """Predict fraud from CSV file upload"""
    if model is None:
        raise HTTPException(status_code=500, detail="Model not loaded")
    
    try:
        # Read CSV file
        contents = await file.read()
        buffer = io.StringIO(contents.decode('utf-8'))
        csv_reader = csv.DictReader(buffer)
        
        transactions = []
        for row in csv_reader:
            try:
                # Convert string values to appropriate types
                transaction = Transaction(
                    amount=float(row.get('amount', 0)),
                    hour=int(row.get('hour', 0)),
                    dayofweek=int(row.get('dayofweek', 0)),
                    txns_last_24h=float(row.get('txns_last_24h', 0)),
                    amount_last_24h=float(row.get('amount_last_24h', 0)),
                    risk_score=float(row.get('risk_score', 0)),
                    transaction_id=row.get('transaction_id', str(uuid.uuid4()))
                )
                transactions.append(transaction)
            except Exception as e:
                logger.warning(f"Skipping invalid row: {str(e)}")
        
        # Use batch prediction logic
        batch = BatchTransactions(transactions=transactions)
        return predict_batch(batch)
    except Exception as e:
        logger.error(f"CSV prediction error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/transactions")
def get_recent_transactions(limit: int = 100):
    """Get recent transactions from the database"""
    if not db_available:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT transaction_id, transaction_data, prediction, confidence, timestamp
                FROM predictions
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,)
            )
            rows = cur.fetchall()
            
            transactions = []
            for row in rows:
                transactions.append({
                    "transaction_id": row[0],
                    "transaction_data": row[1],
                    "is_fraud": row[2],
                    "confidence": row[3],
                    "timestamp": row[4].isoformat()
                })
            
            return {"transactions": transactions}
    except Exception as e:
        logger.error(f"Database query error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
def get_fraud_stats():
    """Get fraud statistics for dashboard"""
    if not db_available:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        with conn.cursor() as cur:
            # Get total transactions and fraud count
            cur.execute(
                """
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN prediction = true THEN 1 ELSE 0 END) as fraud_count
                FROM predictions
                """
            )
            total, fraud_count = cur.fetchone()
            
            # Get fraud by hour
            cur.execute(
                """
                SELECT 
                    EXTRACT(HOUR FROM timestamp) as hour,
                    COUNT(*) as count,
                    SUM(CASE WHEN prediction = true THEN 1 ELSE 0 END) as fraud_count
                FROM predictions
                GROUP BY hour
                ORDER BY hour
                """
            )
            hourly_stats = []
            for row in cur.fetchall():
                hourly_stats.append({
                    "hour": int(row[0]),
                    "total": row[1],
                    "fraud_count": row[2],
                    "fraud_percentage": (row[2] / row[1]) * 100 if row[1] > 0 else 0
                })
            
            # Get recent trend (last 7 days)
            cur.execute(
                """
                SELECT 
                    DATE(timestamp) as date,
                    COUNT(*) as count,
                    SUM(CASE WHEN prediction = true THEN 1 ELSE 0 END) as fraud_count
                FROM predictions
                WHERE timestamp >= NOW() - INTERVAL '7 days'
                GROUP BY date
                ORDER BY date
                """
            )
            daily_stats = []
            for row in cur.fetchall():
                daily_stats.append({
                    "date": row[0].isoformat(),
                    "total": row[1],
                    "fraud_count": row[2],
                    "fraud_percentage": (row[2] / row[1]) * 100 if row[1] > 0 else 0
                })
            
            return {
                "total_transactions": total,
                "fraud_count": fraud_count,
                "fraud_percentage": (fraud_count / total) * 100 if total > 0 else 0,
                "hourly_stats": hourly_stats,
                "daily_stats": daily_stats
            }
    except Exception as e:
        logger.error(f"Stats query error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# AI Engine Endpoints (Upgrades 1–4)
# ─────────────────────────────────────────────────────────────────────────────

class AITransactionRequest(BaseModel):
    amount: float
    hour: int
    day: Optional[int] = None
    dayofweek: Optional[int] = None
    txns_last_24h: float
    amount_last_24h: float
    risk_score: float


@app.post("/api/analyze-transaction")
def analyze_transaction_ai(req: AITransactionRequest):
    """
    Run a transaction through the full FraudGuard AI pipeline.

    Returns: risk tier, AI explanation (if risk_score > 0.45),
             alert details (if HIGH_RISK or CRITICAL), and pipeline timestamp.
    """
    if not _AI_ENGINE_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI engine not loaded")

    try:
        txn_dict = req.dict()
        # Normalise day/dayofweek
        if txn_dict.get("day") is None and txn_dict.get("dayofweek") is not None:
            txn_dict["day"] = txn_dict["dayofweek"]
        elif txn_dict.get("dayofweek") is None and txn_dict.get("day") is not None:
            txn_dict["dayofweek"] = txn_dict["day"]
        elif txn_dict.get("day") is None:
            txn_dict["day"] = 0
            txn_dict["dayofweek"] = 0

        result = process_transaction(txn_dict)
        return result
    except Exception as e:
        logger.error(f"AI analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
def get_alerts(limit: int = 20):
    """
    Return the last `limit` alerts from fraud_alerts.log (most recent first).
    Returns an empty list if the log file does not yet exist.
    """
    if not _AI_ENGINE_AVAILABLE:
        raise HTTPException(status_code=503, detail="AI engine not loaded")

    try:
        if not os.path.exists(ALERT_LOG_PATH):
            return {"alerts": [], "total": 0}

        with open(ALERT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]

        # Most recent first, capped at limit
        recent = lines[-limit:][::-1]
        alerts = []
        for line in recent:
            try:
                alerts.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # Skip malformed lines

        return {"alerts": alerts, "total": len(lines)}
    except Exception as e:
        logger.error(f"Alerts read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

print(" ✅  Fraud Detection API is running.")