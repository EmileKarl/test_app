#!/usr/bin/env python3
"""Grille « achat sur baisse / vente sur rebond » en ordres limite qui restent sur Coinbase.

Les ordres vivent sur le carnet de Coinbase et s'exécutent SEULS, 24 h/24, même quand aucun
agent ne tourne. Un agent repasse régulièrement (« réarmement ») pour reposer les ordres
exécutés et recentrer ceux que le marché a trop distancés.

Pour chaque actif de la grille, on maintient au plus :
  - 1 VENTE limite au-dessus du marché (une tranche de la position) ;
  - 1 ACHAT limite sous le marché avec prise de bénéfice attachée (revente auto au rebond).

    python3 ai_agents/engine/grid.py plan SNAPSHOT.json   -> actions JSON (annulations, ordres)

SNAPSHOT : {"balances": {"BTC": 0.0005, "USDC": 3.1, ...},           # available_balance
            "open_orders": [{"order_id", "product_id", "side", "limit_price", "client_order_id"}]}
Coinbase ne renvoie pas client_order_id dans la liste des ordres : TOUT ordre ouvert sur une
paire de la grille est considéré comme géré par la grille (ne pas y placer d'ordres manuels).
"""

from __future__ import annotations

import json
import math
import sys
import time
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import market  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def load(p):
    return json.loads(Path(p).read_text())


def floor_to(x: float, inc: str) -> str:
    q = Decimal(inc)
    return str((Decimal(str(x)) / q).to_integral_value(rounding=ROUND_DOWN) * q)


def daily_vol(pid: str) -> float:
    rows = market.candles(pid, "ONE_DAY", bars=31)
    c = [r["close"] for r in rows]
    r = [math.log(b / a) for a, b in zip(c, c[1:])]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def spacing(vol: float, g: dict) -> float:
    # Écart = k × volatilité journalière, borné : jamais sous le seuil qui couvre les frais.
    return min(g["max_spacing"], max(g["min_spacing"], g["vol_multiplier"] * vol))


def plan(snapshot: dict) -> dict:
    cfg = load(ROOT / "config" / "autopilot.json")
    limits = load(ROOT / "config" / "risk_limits.json")
    g = cfg["grid"]
    quote = cfg["quote"]
    bal = snapshot["balances"]
    grid_products = {f"{a}-{quote}" for a in g["assets"]}
    desk = [o for o in snapshot.get("open_orders", []) if o.get("product_id") in grid_products]
    cash = float(bal.get(quote, 0.0))
    actions = {"cancel": [], "place": [], "skipped": [], "generated_at": int(time.time())}
    assets = g["assets"]
    need_bid = []
    stamp = time.strftime("%Y%m%d%H%M", time.gmtime())

    for a in assets:
        pid = f"{a}-{quote}"
        if pid not in limits["allowed_products"]:
            actions["skipped"].append({"asset": a, "reason": "produit non autorisé"})
            continue
        prod = market.product(pid)
        px = float(prod["price"])
        s = spacing(daily_vol(pid), g)
        mine = [o for o in desk if o["product_id"] == pid]
        # Recentrage : un ordre trop loin du marché (> 2,5 écarts) est annulé puis reposé.
        keep = []
        for o in mine:
            lp = float(o["limit_price"])
            if abs(lp / px - 1) > 2.5 * s:
                actions["cancel"].append({"order_id": o["order_id"], "product_id": pid,
                                          "reason": f"trop loin du marché ({lp / px - 1:+.1%})"})
            else:
                keep.append(o)
        has_sell = any(o["side"] == "SELL" for o in keep)
        has_buy = any(o["side"] == "BUY" for o in keep)

        held_value = float(bal.get(a, 0.0)) * px
        if not has_sell and held_value >= g["min_order_usd"]:
            chunk = min(g["order_usd"], max(g["min_order_usd"], held_value * g["max_sell_fraction"]))
            if held_value - chunk < g["min_order_usd"] and held_value <= g["order_usd"] * 1.5:
                chunk = held_value * 0.999  # petite position : on la vend en entier
            sell_px = px * (1 + s)
            size = floor_to(min(chunk, held_value * 0.999) / sell_px, prod["base_increment"])
            if Decimal(size) > 0 and float(size) * sell_px >= float(prod["quote_min_size"]):
                actions["place"].append({
                    "product_id": pid, "side": "SELL", "type": "limit", "post_only": True,
                    "time_in_force": "GTC", "base_size": size,
                    "limit_price": floor_to(sell_px, prod["price_increment"]),
                    "client_order_id": f"desk-s-{a}-{stamp}",
                    "notional_usd": round(float(size) * sell_px, 2), "spacing": round(s, 4)})
        if not has_buy:
            need_bid.append((a, pid, prod, px, s))

    # Les achats se partagent le cash disponible, au plus order_usd chacun.
    budget = cash * (1 - g["cash_reserve_fraction"])
    for a, pid, prod, px, s in need_bid:
        n_left = len(need_bid)
        amount = min(g["order_usd"], budget / max(1, n_left))
        if amount < g["min_order_usd"]:
            actions["skipped"].append({"asset": a, "reason": "pas assez de cash pour un achat"})
            continue
        buy_px = px * (1 - s)
        size = floor_to(amount / buy_px, prod["base_increment"])
        if Decimal(size) <= 0:
            continue
        tp_px = buy_px * (1 + g["take_profit_multiple"] * s)
        actions["place"].append({
            "product_id": pid, "side": "BUY", "type": "limit", "post_only": True,
            "time_in_force": "GTC", "base_size": size,
            "limit_price": floor_to(buy_px, prod["price_increment"]),
            "attached_take_profit_price": floor_to(tp_px, prod["price_increment"]),
            "client_order_id": f"desk-b-{a}-{stamp}",
            "notional_usd": round(float(size) * buy_px, 2), "spacing": round(s, 4)})
        budget -= amount

    # Garde-fou : tout ordre au-dessus du seuil d'autonomie doit être confirmé par l'utilisateur.
    for o in actions["place"]:
        o["needs_user_approval"] = o["notional_usd"] > limits["auto_max_order_usd"]
    return actions


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "plan":
        print(json.dumps(plan(load(sys.argv[2])), indent=2, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)
