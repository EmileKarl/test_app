#!/usr/bin/env python3
"""Hook PreToolUse : verrou sur la création d'ordres Coinbase (fichier PROTÉGÉ, niveau ROUGE).

Inactif tant que l'utilisateur ne l'a pas déclaré dans .claude/settings.json (voir
ai_agents/README.md, section « Activer le pilote automatique »).

- Ordre conforme à pending_orders.json (émis par cycle.py il y a < 15 min) ET aux limites
  -> autorisé (pilote automatique).
- Ordre hors pending_orders mais dans les limites -> "ask" : l'humain approuve dans l'interface.
- Ordre hors limites (produit, montant, volume du jour, KILL, dérivés) -> refusé, sans exception.
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "ai_agents"


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                      "permissionDecision": decision, "permissionDecisionReason": reason}}))
    sys.exit(0)


def load(p, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def main():
    ev = json.load(sys.stdin)
    o = ev.get("tool_input", {}) or {}
    limits = load(ROOT / "config" / "risk_limits.json")
    if not limits:
        decide("deny", "risk_limits.json illisible : ordre refusé par sécurité")
    if (ROOT / "state" / "KILL").exists() or (ROOT / "paper" / "KILL").exists():
        decide("deny", "coupe-circuit actif (fichier KILL)")
    pid, side = o.get("product_id"), o.get("side")
    if pid not in limits["allowed_products"]:
        decide("deny", f"produit {pid} hors liste autorisée")
    if o.get("product_type") not in (None, "SPOT"):
        decide("deny", "seul le SPOT est autorisé")
    pend = load(ROOT / "state" / "pending_orders.json", {}) or {}
    match = next((x for x in pend.get("orders", [])
                  if x["product_id"] == pid and x["side"] == side), None)
    px = float(o.get("limit_price") or (match or {}).get("price") or 0)
    if o.get("quote_size"):
        notional = float(o["quote_size"])
    elif o.get("base_size") and px:
        notional = float(o["base_size"]) * px
    else:
        decide("deny", "montant impossible à vérifier (donner limit_price ou quote_size)")
    if not notional > 0:
        decide("deny", "montant invalide")
    if notional > limits["max_order_usd"] * 1.02:
        decide("deny", f"montant {notional:.2f} > max_order_usd {limits['max_order_usd']}")
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    vol = 0.0
    j = ROOT / "state" / "journal.jsonl"
    if j.exists():
        for line in j.read_text().splitlines():
            e = json.loads(line)
            if e.get("type") == "fill" and e.get("mode") == "live" and e.get("ts", "").startswith(day):
                vol += float(e.get("notional_usd", 0))
    if vol + notional > limits["max_daily_volume_usd"] * 1.02:
        decide("deny", "volume journalier maximal atteint")
    fresh = False
    if pend.get("created"):
        age = (dt.datetime.now(dt.timezone.utc)
               - dt.datetime.fromisoformat(pend["created"])).total_seconds()
        fresh = age < 900
    if match and fresh and notional <= match["notional_usd"] * 1.02:
        decide("allow", "ordre approuvé par cycle.py / risk_gate.py")
    decide("ask", "ordre manuel (hors pilote automatique) : confirmation humaine requise")


if __name__ == "__main__":
    main()
