#!/usr/bin/env python3
"""
FraudGuard Demo Runner — Upgrade 5
====================================
Loads fraudguard_transactions_demo.csv, runs every transaction through
the full AI pipeline, and prints a rich terminal summary table.

Usage:
    python demo_runner.py
    python demo_runner.py --csv path/to/other.csv
"""

import csv
import sys
import os
import argparse
import datetime

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
logging.basicConfig(
    level=logging.WARNING,  # Suppress info noise during demo run
    format="%(levelname)s — %(message)s"
)

from src.fraud_ai_engine import process_transaction, classify_risk_tier

# ── ANSI colours ──────────────────────────────────────────────────────────────
_C = {
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "orange": "\033[38;5;208m",
    "red":    "\033[91m",
    "cyan":   "\033[96m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "reset":  "\033[0m",
}

def _colorize(text: str, color: str) -> str:
    return f"{_C.get(color, '')}{text}{_C['reset']}"

_TIER_COLOR_MAP = {
    "SAFE":      "green",
    "SUSPICIOUS": "yellow",
    "HIGH_RISK": "orange",
    "CRITICAL":  "red",
}

def _tier_badge(tier_name: str) -> str:
    color = _TIER_COLOR_MAP.get(tier_name, "reset")
    return _colorize(f"[{tier_name}]", color)

# ── Banner ─────────────────────────────────────────────────────────────────────
def print_banner():
    banner = r"""
  ╔═══════════════════════════════════════════════════════╗
  ║      🛡️   F R A U D G U A R D   A I   E N G I N E    ║
  ║          Real-Time Bank Fraud Detection Demo          ║
  ╚═══════════════════════════════════════════════════════╝"""
    print(_colorize(banner, "cyan"))
    print(_colorize(f"  Run started: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", "dim"))

# ── Load CSV ───────────────────────────────────────────────────────────────────
def load_csv(path: str) -> list[dict]:
    transactions = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                txn = {
                    "amount":          int(float(row["amount"])),
                    "hour":            int(row["hour"]),
                    "day":             int(row["day"]) if "day" in row else int(row.get("dayofweek", 0)),
                    "txns_last_24h":   int(float(row["txns_last_24h"])),
                    "amount_last_24h": int(float(row["amount_last_24h"])),
                    "risk_score":      float(row["risk_score"]),
                }
                transactions.append(txn)
            except (KeyError, ValueError) as e:
                print(f"  {_colorize('⚠', 'yellow')}  Skipping invalid row: {e}")
    return transactions

# ── Summary Table ──────────────────────────────────────────────────────────────
_COL_WIDTHS = [6, 8, 6, 12, 12, 11, 14, 14]
_HEADERS    = ["#", "Amount", "Hour", "Risk Score", "Tier", "AI Rec.", "Source", "Alert"]

def _fmt_row(*cells) -> str:
    parts = []
    for cell, w in zip(cells, _COL_WIDTHS):
        # Strip ANSI for width calculation
        import re
        plain = re.sub(r'\033\[[0-9;]*m', '', str(cell))
        pad = max(0, w - len(plain))
        parts.append(str(cell) + " " * pad)
    return "  " + "  ".join(parts)

def print_table_header():
    sep = "  " + "─" * (sum(_COL_WIDTHS) + 2 * len(_COL_WIDTHS))
    print(_colorize(_fmt_row(*_HEADERS), "bold"))
    print(_colorize(sep, "dim"))

def print_table_row(idx: int, txn: dict, result: dict):
    tier_name = result["tier"]["tier"]
    ai        = result.get("ai_analysis") or {}
    rec       = ai.get("recommendation", "—")
    source    = "AI" if ai.get("source") == "gemini_ai" else ("Rules" if ai else "—")
    alert_str = _colorize("YES 🔔", "red") if result["alert_triggered"] else _colorize("no", "dim")
    tier_str  = _tier_badge(tier_name)

    print(_fmt_row(
        idx,
        f"₹{txn['amount']:,}",
        f"{txn['hour']:02d}:00",
        f"{txn['risk_score']:.4f}",
        tier_str,
        rec if rec != "—" else _colorize("—", "dim"),
        source,
        alert_str,
    ))

# ── Counts Summary ─────────────────────────────────────────────────────────────
def print_summary(results: list[dict], alerts_triggered: int):
    counts = {"SAFE": 0, "SUSPICIOUS": 0, "HIGH_RISK": 0, "CRITICAL": 0}
    for r in results:
        t = r["tier"]["tier"]
        if t in counts:
            counts[t] += 1

    total = len(results)
    print("\n" + _colorize("  ═" * 30, "dim"))
    print(_colorize("  📊  PIPELINE SUMMARY", "bold"))
    print(_colorize("  ─" * 30, "dim"))
    print(f"  Total transactions processed : {_colorize(str(total), 'bold')}")
    print(f"  ✅  SAFE                      : {_colorize(str(counts['SAFE']), 'green')}")
    print(f"  ⚠️   SUSPICIOUS                : {_colorize(str(counts['SUSPICIOUS']), 'yellow')}")
    print(f"  🔶  HIGH_RISK                  : {_colorize(str(counts['HIGH_RISK']), 'orange')}")
    print(f"  🚨  CRITICAL                   : {_colorize(str(counts['CRITICAL']), 'red')}")
    print(_colorize("  ─" * 30, "dim"))
    print(f"  🔔  Bank alerts triggered      : {_colorize(str(alerts_triggered), 'red' if alerts_triggered else 'green')}")
    print(_colorize("  ═" * 30, "dim"))
    print()

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="FraudGuard Demo Runner")
    parser.add_argument(
        "--csv",
        default="fraudguard_transactions_demo.csv",
        help="Path to demo CSV file (default: fraudguard_transactions_demo.csv)"
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        help="Suppress terminal alert boxes (alerts still logged to file)"
    )
    args = parser.parse_args()

    csv_path = args.csv
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), csv_path)

    if not os.path.exists(csv_path):
        print(f"\n  {_colorize('ERROR', 'red')}: CSV not found: {csv_path}")
        sys.exit(1)

    print_banner()
    print(f"  {_colorize('Loading', 'dim')} {csv_path}")

    transactions = load_csv(csv_path)
    print(f"  {_colorize(str(len(transactions)), 'bold')} transactions loaded\n")

    # Monkey-patch send_bank_alert to suppress terminal boxes if --no-alerts
    if args.no_alerts:
        import src.fraud_ai_engine as engine
        original_print = engine._print_terminal_alert
        engine._print_terminal_alert = lambda _: None

    results = []
    alerts_triggered = 0

    print_table_header()

    for idx, txn in enumerate(transactions, start=1):
        result = process_transaction(txn)
        results.append(result)
        if result["alert_triggered"]:
            alerts_triggered += 1
        print_table_row(idx, txn, result)

    print_summary(results, alerts_triggered)
    print(f"  {_colorize('Alert log', 'dim')} → fraud_alerts.log")
    print()


if __name__ == "__main__":
    main()
