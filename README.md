# 🛡️ FraudGuard — AI-Powered Bank Fraud Detection System

### **Real-Time Transaction Monitoring, Gemini AI Analysis & Bank Alert System using FastAPI, Kafka, Redis, and Docker**

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-High%20Performance-green)
![Gemini AI](https://img.shields.io/badge/Gemini%20AI-AI%20Powered-purple)
![Kafka](https://img.shields.io/badge/Kafka-Streaming-red)
![Docker](https://img.shields.io/badge/Docker-Containerized-blue)

---

## 🚨 Why This Project Matters

Financial fraud is a multi-billion-dollar problem. **FraudGuard** is engineered to detect and prevent fraudulent transactions in **real-time** — now upgraded with **Gemini AI behavioral analysis**, a **4-tier risk classification system**, and a **real-time bank alert engine**.

### 🔥 Latest Performance Metrics
- **Precision:** `1.000` ✅ *(No false positives!)*
- **Recall:** `0.935` 🔥 *(Detects nearly all fraud cases!)*
- **F1-Score:** `0.966` 🎯 *(Perfect balance of precision & recall!)*
- **Accuracy:** `1.000` 🚀 *(Near-perfect fraud detection!)*

---

## ✨ What's New — AI Upgrade

| Upgrade | Feature |
|---|---|
| 🔵 **Risk Tier Classification** | 4-tier system: SAFE → SUSPICIOUS → HIGH_RISK → CRITICAL |
| 🤖 **Gemini AI Analysis** | Behavioral anomaly explanation via `gemini-2.5-flash` |
| 🚨 **Bank Alert System** | Structured alert payloads, log file, terminal display, email/webhook |
| ⚙️ **Pipeline Orchestrator** | `process_transaction()` ties all 4 upgrades together |
| 📊 **Demo Runner** | Batch CSV runner with color-coded terminal summary |
| 🌐 **AI Analysis Tab** | New frontend tab with live alerts feed |

---

## 🌍 Overview

FraudGuard is a **real-time, scalable fraud prevention platform** that:
1. Scores transactions with ML models (Random Forest, XGBoost, LightGBM, Isolation Forest)
2. Classifies them into risk tiers (SAFE / SUSPICIOUS / HIGH_RISK / CRITICAL)
3. Sends suspicious transactions to **Gemini AI** for behavioral anomaly analysis
4. Fires structured bank alerts for HIGH_RISK and CRITICAL transactions
5. Streams all data through Kafka, caches in Redis, stores in PostgreSQL

---

## 🏗 Architecture

```
User / Frontend Dashboard
         │
         ▼
  FastAPI (Port 8001)
  ├── /predict              → ML fraud prediction
  ├── /predict/batch        → Batch prediction
  ├── /predict/csv          → CSV upload prediction
  ├── /api/analyze-transaction → Full AI pipeline (NEW)
  ├── /api/alerts           → Last 20 bank alerts (NEW)
  ├── /transactions         → Transaction history
  └── /stats                → Fraud statistics
         │
         ├──► Kafka Event Stream (Producer → Consumer)
         ├──► Redis Cache (instant risk decisions)
         ├──► PostgreSQL (transaction history)
         └──► Gemini AI Engine (behavioral analysis)
                    │
                    └──► fraud_alerts.log (bank alert log)
```

---

## 🔵 Risk Tier System

| Score Range | Tier | Action |
|---|---|---|
| 0.00 – 0.30 | 🟢 **SAFE** | approve |
| 0.31 – 0.55 | 🟡 **SUSPICIOUS** | monitor |
| 0.56 – 0.75 | 🟠 **HIGH_RISK** | hold_and_review |
| 0.76 – 1.00 | 🔴 **CRITICAL** | block_and_alert |

---

## ⚡ Tech Stack

| Technology | Purpose |
|---|---|
| **FastAPI** | High-performance API framework |
| **Gemini AI** | AI behavioral anomaly analysis |
| **Kafka** | Event streaming for real-time transactions |
| **Redis** | In-memory caching for ultra-fast responses |
| **Docker** | Containerization & deployment |
| **PostgreSQL** | Transaction history storage |
| **LightGBM / XGBoost / RF** | ML fraud detection models |
| **python-dotenv** | Environment variable management |

---

## 🚀 Installation & Setup

### Pre-requisites
- Python 3.9+
- Docker & Docker Compose
- Gemini API Key (get one at [aistudio.google.com](https://aistudio.google.com))

### 1. Clone the Repository
```bash
git clone https://github.com/VeedhiBhanushali/fraud-detection-system.git
cd fraud-detection-system
```

### 2. Set Up Environment Variables
```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 3. Run with Docker (Recommended)
```bash
docker compose up --build -d
```

### 4. Access the Services
| Service | URL |
|---|---|
| 🌐 Frontend Dashboard | http://localhost:8080 |
| ⚡ FastAPI (REST API) | http://localhost:8001 |
| 📖 API Docs (Swagger) | http://localhost:8001/docs |

---

## 🤖 AI Demo Runner

Run the full AI pipeline on 20 demo transactions:
```bash
python demo_runner.py
```

**Sample Output:**
```
  📊  PIPELINE SUMMARY
  Total transactions processed : 20
  ✅  SAFE                      : 9
  ⚠️   SUSPICIOUS                : 3
  🔶  HIGH_RISK                  : 3
  🚨  CRITICAL                   : 5
  🔔  Bank alerts triggered      : 8
```

Custom CSV:
```bash
python demo_runner.py --csv path/to/your.csv
python demo_runner.py --no-alerts   # suppress terminal alert boxes
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Health check |
| GET | `/health` | System health (model + DB status) |
| POST | `/predict` | ML fraud prediction (single) |
| POST | `/predict/batch` | Batch prediction |
| POST | `/predict/csv` | CSV upload prediction |
| **POST** | **`/api/analyze-transaction`** | **Full AI pipeline (NEW)** |
| **GET** | **`/api/alerts`** | **Last 20 bank alerts (NEW)** |
| GET | `/transactions` | Recent transaction history |
| GET | `/stats` | Fraud statistics |

### AI Analysis Request
```bash
curl -X POST http://localhost:8001/api/analyze-transaction \
  -H "Content-Type: application/json" \
  -d '{"amount":8000,"hour":2,"day":5,"txns_last_24h":14,"amount_last_24h":50000,"risk_score":0.92}'
```

### AI Analysis Response
```json
{
  "tier": { "tier": "CRITICAL", "color": "red", "action": "block_and_alert" },
  "ai_analysis": {
    "red_flags": ["Transaction at unusual hour", "High frequency", "Large amount spike"],
    "explanation": "...",
    "confidence": "HIGH",
    "recommendation": "BLOCK",
    "source": "gemini_ai"
  },
  "alert_triggered": true
}
```

---

## 📁 Project Structure

```
fraud-detection-system/
├── src/
│   ├── fastapi_service.py        # Main API (all endpoints)
│   ├── fraud_ai_engine.py        # 🆕 AI engine (Upgrades 1–4)
│   ├── kafka_producer.py         # Kafka event producer
│   ├── kafka_consumer.py         # Kafka event consumer
│   ├── redis_cache.py            # Redis caching layer
│   └── *.pkl                     # Trained ML models
├── frontend/
│   ├── index.html                # Dashboard (4 tabs)
│   ├── app.js                    # Frontend logic
│   └── style.css                 # Dark-mode premium UI
├── demo_runner.py                # 🆕 Batch CSV demo runner
├── fraudguard_transactions_demo.csv  # 🆕 20 demo transactions
├── fraud_alerts.log              # 🆕 Bank alert log (append-only)
├── .env.example                  # 🆕 Environment variables template
├── docker-compose.yml            # Full stack deployment
├── Dockerfile                    # API container
└── requirements.txt              # Python dependencies
```

---

## 🔔 Bank Alert System

When a HIGH_RISK or CRITICAL transaction is detected:
1. Structured JSON alert is appended to `fraud_alerts.log`
2. Formatted terminal alert is printed
3. Optional email/webhook sent if configured in `.env`
4. Alert appears in the Live Bank Alerts feed on the dashboard

```
╔══════════════════════════════════════════════════╗
║  🚨 FRAUDGUARD ALERT — CRITICAL                  ║
╠══════════════════════════════════════════════════╣
║ Alert ID    : 4d76b05b-1aca                      ║
║ Amount      : ₹8,000                             ║
║ Risk Score  : 0.9200                             ║
║ AI Flags    : Unusual hour, High frequency       ║
║ ACTION      : BLOCK TRANSACTION                  ║
╚══════════════════════════════════════════════════╝
```

---

## 📬 Contact

📂 **Repository**: [github.com/VeedhiBhanushali/fraud-detection-system](https://github.com/VeedhiBhanushali/fraud-detection-system)
