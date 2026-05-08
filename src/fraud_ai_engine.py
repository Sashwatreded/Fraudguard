"""
FraudGuard AI Engine — Upgrades 1–4
=====================================
Provides:
  - classify_risk_tier()      → Risk tier classification (SAFE → CRITICAL)
  - get_ai_fraud_explanation() → Gemini AI behavioral anomaly analysis
  - send_bank_alert()          → Real-time bank alert with log + terminal display
  - process_transaction()      → Full pipeline orchestrator
"""

import os
import json
import uuid
import logging
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually

try:
    from google import genai
    from google.genai import types
    _GEMINI_AVAILABLE = True
except ImportError:
    _GEMINI_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Alert log file path ────────────────────────────────────────────────────────
ALERT_LOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fraud_alerts.log"
)

# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 1 — Risk Tier Classification
# ─────────────────────────────────────────────────────────────────────────────

def classify_risk_tier(risk_score: float) -> dict:
    """
    Classify a risk_score (0.0–1.0) into one of four risk tiers.

    Returns:
        dict with keys: tier, color, action
    """
    score = float(risk_score)

    if score <= 0.30:
        return {"tier": "SAFE",      "color": "green",  "action": "approve"}
    elif score <= 0.55:
        return {"tier": "SUSPICIOUS","color": "yellow", "action": "monitor"}
    elif score <= 0.75:
        return {"tier": "HIGH_RISK", "color": "orange", "action": "hold_and_review"}
    else:
        return {"tier": "CRITICAL",  "color": "red",    "action": "block_and_alert"}


# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 2 — AI Behavioral Anomaly Explanation (Gemini API)
# ─────────────────────────────────────────────────────────────────────────────

_RULE_BASED_THRESHOLDS = {
    "unusual_hour":      lambda t: t.get("hour", 12) < 5 or t.get("hour", 12) > 22,
    "high_amount":       lambda t: t.get("amount", 0) > 5000,
    "high_frequency":    lambda t: t.get("txns_last_24h", 0) > 8,
    "amount_spike":      lambda t: (
        t.get("amount_last_24h", 0) > 0
        and t.get("amount", 0) > t.get("amount_last_24h", 0) * 0.5
    ),
    "weekend_large_txn": lambda t: t.get("day", 0) >= 5 and t.get("amount", 0) > 3000,
    "critical_risk":     lambda t: t.get("risk_score", 0) > 0.75,
}

_RULE_MESSAGES = {
    "unusual_hour":      "Transaction made at an unusual hour (outside 05:00–22:00)",
    "high_amount":       "Transaction amount significantly above typical threshold (>₹5,000)",
    "high_frequency":    "High transaction frequency in last 24 hours (>8 transactions)",
    "amount_spike":      "Current transaction represents a large spike vs 24h spending history",
    "weekend_large_txn": "Large transaction on weekend — elevated risk window",
    "critical_risk":     "ML risk score in critical range (>0.75)",
}

def _rule_based_explanation(transaction: dict) -> dict:
    """Fallback explanation when Gemini API is unavailable."""
    flags = [
        _RULE_MESSAGES[key]
        for key, check in _RULE_BASED_THRESHOLDS.items()
        if check(transaction)
    ]

    score = float(transaction.get("risk_score", 0))
    if score > 0.75:
        confidence = "HIGH"
        recommendation = "BLOCK"
    elif score > 0.55:
        confidence = "MEDIUM"
        recommendation = "HOLD"
    elif score > 0.45:
        confidence = "LOW-MEDIUM"
        recommendation = "MONITOR"
    else:
        confidence = "LOW"
        recommendation = "APPROVE"

    explanation = (
        f"Rule-based analysis detected {len(flags)} red flag(s). "
        f"Risk score of {score:.2f} places this transaction in an elevated risk category."
        if flags
        else f"No significant anomalies detected. Risk score {score:.2f} is within normal range."
    )

    return {
        "red_flags": flags if flags else ["No significant anomalies detected"],
        "explanation": explanation,
        "confidence": confidence,
        "recommendation": recommendation,
        "source": "rule_based_fallback",
    }


def get_ai_fraud_explanation(transaction: dict) -> dict:
    """
    Call Gemini AI to explain why a transaction is or isn't suspicious.
    Only intended to be called when risk_score > 0.45.

    Returns structured dict: { red_flags, explanation, confidence, recommendation, source }
    Falls back to rule-based analysis on API failure.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")

    if not _GEMINI_AVAILABLE or not api_key:
        logger.warning("Gemini API not available — using rule-based fallback")
        return _rule_based_explanation(transaction)

    # Build structured prompt
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_label = day_names[int(transaction.get("day", 0))] if 0 <= int(transaction.get("day", 0)) <= 6 else "Unknown"

    prompt = f"""You are FraudGuard, an expert bank fraud detection AI. Analyze the following transaction and return your assessment as valid JSON only — no markdown, no explanation outside JSON.

Transaction Details:
- Amount: ₹{transaction.get('amount', 0):,}
- Hour of Day: {transaction.get('hour', 0):02d}:00
- Day of Week: {day_label} (day index {transaction.get('day', 0)})
- Transactions by this user in last 24h: {transaction.get('txns_last_24h', 0)}
- Total amount spent by this user in last 24h: ₹{transaction.get('amount_last_24h', 0):,}
- ML Risk Score: {transaction.get('risk_score', 0):.4f} (scale 0.0–1.0)

Your task:
1. Analyze why this transaction is or is NOT suspicious given the above context.
2. List specific red flags in bullet format (e.g., unusual hour, high frequency, large spike).
3. Give a confidence assessment of your analysis.
4. Recommend one of: APPROVE / MONITOR / HOLD / BLOCK

Return ONLY this JSON structure:
{{
  "red_flags": ["<flag 1>", "<flag 2>", ...],
  "explanation": "<2-3 sentence explanation of your reasoning>",
  "confidence": "<LOW | MEDIUM | HIGH>",
  "recommendation": "<APPROVE | MONITOR | HOLD | BLOCK>"
}}"""

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )

        raw = response.text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        result["source"] = "gemini_ai"
        logger.info("Gemini AI explanation obtained successfully")
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response as JSON: {e}")
        fallback = _rule_based_explanation(transaction)
        fallback["source"] = "rule_based_fallback_json_error"
        return fallback
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        fallback = _rule_based_explanation(transaction)
        fallback["source"] = f"rule_based_fallback_api_error"
        return fallback


# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 3 — Real-Time Bank Alert System
# ─────────────────────────────────────────────────────────────────────────────

_TIER_ICONS = {
    "SAFE":      "✅",
    "SUSPICIOUS":"⚠️ ",
    "HIGH_RISK": "🔶",
    "CRITICAL":  "🚨",
}

_TIER_ACTIONS_DISPLAY = {
    "SAFE":      "APPROVE TRANSACTION",
    "SUSPICIOUS":"MONITOR ACCOUNT",
    "HIGH_RISK": "HOLD & REVIEW",
    "CRITICAL":  "BLOCK TRANSACTION",
}


def _build_alert_payload(transaction: dict, tier: dict, ai_analysis: dict) -> dict:
    """Build the full structured alert payload."""
    return {
        "alert_id": str(uuid.uuid4()),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "transaction": transaction,
        "risk_tier": tier,
        "ai_analysis": ai_analysis,
        "recommended_action": _TIER_ACTIONS_DISPLAY.get(tier["tier"], tier["action"].upper()),
    }


def _log_alert_to_file(payload: dict) -> None:
    """Append alert JSON to fraud_alerts.log (one JSON object per line)."""
    try:
        with open(ALERT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
        logger.info(f"Alert {payload['alert_id']} written to {ALERT_LOG_PATH}")
    except Exception as e:
        logger.error(f"Failed to write alert to log: {e}")


def _print_terminal_alert(payload: dict) -> None:
    """Print a formatted terminal alert box."""
    tier_name = payload["risk_tier"]["tier"]
    icon = _TIER_ICONS.get(tier_name, "🔔")
    alert_id   = payload["alert_id"][:13]
    amount     = payload["transaction"].get("amount", 0)
    risk_score = payload["transaction"].get("risk_score", 0)
    action     = payload["recommended_action"]
    red_flags  = payload["ai_analysis"].get("red_flags", [])
    flags_str  = ", ".join(red_flags[:2]) if red_flags else "N/A"
    if len(flags_str) > 38:
        flags_str = flags_str[:35] + "..."

    W = 50  # box inner width
    border_top    = "╔" + "═" * W + "╗"
    border_mid    = "╠" + "═" * W + "╣"
    border_bot    = "╚" + "═" * W + "╝"

    def row(label: str, value: str) -> str:
        content = f" {label:<12}: {value}"
        pad = W - len(content)
        return "║" + content + " " * max(pad, 0) + "║"

    title = f"  {icon} FRAUDGUARD ALERT — {tier_name}"
    title_pad = W - len(title)
    title_line = "║" + title + " " * max(title_pad, 0) + "║"

    rec_text = f" {'ACTION':<12}: {action}"
    rec_pad  = W - len(rec_text)
    rec_line = "║" + rec_text + " " * max(rec_pad, 0) + "║"

    # ANSI color map
    _COLORS = {
        "green":  "\033[92m",
        "yellow": "\033[93m",
        "orange": "\033[38;5;208m",
        "red":    "\033[91m",
    }
    color   = _COLORS.get(payload["risk_tier"]["color"], "")
    reset   = "\033[0m"

    print(f"\n{color}{border_top}")
    print(title_line)
    print(border_mid)
    print(row("Alert ID", alert_id))
    print(row("Amount", f"\u20b9{amount:,}"))
    print(row("Risk Score", f"{risk_score:.4f}"))
    print(row("AI Flags", flags_str))
    print(rec_line)
    print(f"{border_bot}{reset}\n")


def _send_optional_notifications(payload: dict) -> None:
    """Send email or webhook alert if env vars are configured."""
    webhook_url = os.getenv("WEBHOOK_URL", "")
    if webhook_url:
        try:
            import requests
            requests.post(webhook_url, json=payload, timeout=5)
            logger.info(f"Webhook alert sent to {webhook_url}")
        except Exception as e:
            logger.warning(f"Webhook delivery failed: {e}")

    smtp_host = os.getenv("SMTP_HOST", "")
    alert_email = os.getenv("ALERT_EMAIL", "")
    if smtp_host and alert_email:
        try:
            smtp_user = os.getenv("SMTP_USER", "")
            smtp_pass = os.getenv("SMTP_PASSWORD", "")
            smtp_port = int(os.getenv("SMTP_PORT", "465"))

            tier = payload["risk_tier"]["tier"]
            subject = f"[FraudGuard ALERT] {tier} — Alert {payload['alert_id'][:8]}"

            body = (
                f"FraudGuard Bank Alert\n"
                f"{'='*40}\n"
                f"Alert ID   : {payload['alert_id']}\n"
                f"Timestamp  : {payload['timestamp']}\n"
                f"Risk Tier  : {tier}\n"
                f"Amount     : ₹{payload['transaction'].get('amount',0):,}\n"
                f"Risk Score : {payload['transaction'].get('risk_score',0):.4f}\n"
                f"Action     : {payload['recommended_action']}\n"
                f"\nAI Red Flags:\n"
                + "\n".join(f"  • {f}" for f in payload["ai_analysis"].get("red_flags", []))
                + f"\n\nExplanation:\n{payload['ai_analysis'].get('explanation','')}\n"
            )

            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = alert_email
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, alert_email, msg.as_string())

            logger.info(f"Email alert sent to {alert_email}")
        except Exception as e:
            logger.warning(f"Email alert delivery failed: {e}")


def send_bank_alert(transaction: dict, tier: dict, ai_analysis: dict) -> dict:
    """
    Send a real-time bank alert for HIGH_RISK or CRITICAL transactions.

    Steps:
      1. Build structured alert payload with UUID + timestamp
      2. Log to fraud_alerts.log (append mode)
      3. Print formatted terminal alert box
      4. (Optional) Send email/webhook if .env configured

    Returns the alert payload dict.
    """
    payload = _build_alert_payload(transaction, tier, ai_analysis)
    _log_alert_to_file(payload)
    _print_terminal_alert(payload)
    _send_optional_notifications(payload)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# UPGRADE 4 — Main Processing Pipeline
# ─────────────────────────────────────────────────────────────────────────────

def process_transaction(transaction_dict: dict) -> dict:
    """
    Full fraud analysis pipeline.

    1. Classify risk tier via classify_risk_tier()
    2. If risk_score > 0.45 → get_ai_fraud_explanation()
    3. If tier is HIGH_RISK or CRITICAL → send_bank_alert()
    4. Return combined result object

    Args:
        transaction_dict: dict with keys: amount, hour, day, txns_last_24h,
                          amount_last_24h, risk_score

    Returns:
        dict with: transaction, tier, ai_analysis (or None), alert (or None),
                   alert_triggered (bool), timestamp
    """
    # Normalise field names: accept both 'day' and 'dayofweek'
    txn = dict(transaction_dict)
    if "dayofweek" in txn and "day" not in txn:
        txn["day"] = txn["dayofweek"]
    if "day" in txn and "dayofweek" not in txn:
        txn["dayofweek"] = txn["day"]

    risk_score = float(txn.get("risk_score", 0))

    # Step 1 — Classify risk tier
    tier = classify_risk_tier(risk_score)

    # Step 2 — AI explanation (only for suspicious or above)
    ai_analysis = None
    if risk_score > 0.45:
        ai_analysis = get_ai_fraud_explanation(txn)
    
    # Step 3 — Bank alert (only for HIGH_RISK or CRITICAL)
    alert = None
    alert_triggered = False
    if tier["tier"] in ("HIGH_RISK", "CRITICAL"):
        if ai_analysis is None:
            ai_analysis = _rule_based_explanation(txn)
        alert = send_bank_alert(txn, tier, ai_analysis)
        alert_triggered = True

    return {
        "transaction":     txn,
        "tier":            tier,
        "ai_analysis":     ai_analysis,
        "alert":           alert,
        "alert_triggered": alert_triggered,
        "timestamp":       datetime.datetime.utcnow().isoformat() + "Z",
    }
