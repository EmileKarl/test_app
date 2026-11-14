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
            "open_orders": [{"order_id", "product_id", "side", "limit_price", "base_size"}]}
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
import risk_gate  # noqa: E402
import signals  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def load(p):
    return json.loads(Path(p).read_text())


def floor_to(x: float, inc: str) -> str:
    q = Decimal(inc)
    return str((Decimal(str(x)) / q).to_integral_value(rounding=ROUND_DOWN) * q)


def daily_vol(pid: str) -> float:
    rows = market.candles(pid, "ONE_DAY", bars=31)
    c = [r["close"] for r in rows]
    if len(c) < 3:
        return 0.04  # historique insuffisant : hypothèse prudente (écart plus large)
    r = [math.log(b / a) for a, b in zip(c, c[1:])]
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def asset_score(asset: str, g: dict) -> float:
    if not g.get("use_signals", True):
        return 0.0
    try:
        return float(signals.compute(asset)["score"])
    except Exception:
        return 0.0  # données indisponibles : neutre, jamais bloquant


def live_volume_today() -> float:
    j = ROOT / "state" / "journal.jsonl"
    if not j.exists():
        return 0.0
    day = time.strftime("%Y-%m-%d", time.gmtime())
    vol = 0.0
    for line in j.read_text().splitlines():
        e = json.loads(line)
        if e.get("type") == "fill" and e.get("mode") == "live" and e.get("ts", "").startswith(day):
            vol += float(e.get("notional_usd", 0))
    return vol


def spacing(vol: float, g: dict) -> float:
    # Écart = k × volatilité journalière, borné : jamais sous le seuil qui couvre les frais.
    return min(g["max_spacing"], max(g["min_spacing"], g["vol_multiplier"] * vol))


def plan(snapshot: dict) -> dict:
    cfg = load(ROOT / "config" / "autopilot.json")
    limits = load(ROOT / "config" / "risk_limits.json")
    g = cfg["grid"]
    quote = cfg["quote"]
    actions = {"cancel": [], "place": [], "skipped": [], "generated_at": int(time.time())}
    if (ROOT / "state" / "KILL").exists() or (ROOT / "paper" / "KILL").exists():
        actions["skipped"].append({"asset": "*", "reason": "coupe-circuit actif (KILL)"})
        return actions
    bal = {k: float(v) for k, v in snapshot["balances"].items()}
    grid_products = {f"{a}-{quote}" for a in g["assets"]}
    desk = [o for o in snapshot.get("open_orders", []) if o.get("product_id") in grid_products]
    cash = bal.get(quote, 0.0)
    need_bid, info = [], {}
    stamp = time.strftime("%Y%m%d%H%M", time.gmtime())

    for a in g["assets"]:
        pid = f"{a}-{quote}"
        if pid not in limits["allowed_products"]:
            actions["skipped"].append({"asset": a, "reason": "produit non autorisé"})
            continue
        prod = market.product(pid)
        px = float(prod["price"])
        s = spacing(daily_vol(pid), g)
        # Signaux : un score baissier écarte les achats, un score haussier remonte les ventes.
        # Score nul (aucun signal prouvé) = aucun effet.
        score = asset_score(a, g)
        s_buy = s * (1 + g.get("signal_strength", 1.0) * max(0.0, -score))
        s_sell = s * (1 + g.get("signal_strength", 1.0) * max(0.0, score))
        info[a] = (pid, prod, px, s_buy)
        mine = [o for o in desk if o["product_id"] == pid]
        on_hold = sum(float(o.get("base_size", 0)) for o in mine if o["side"] == "SELL")
        total_qty = bal.get(a, 0.0) + on_hold          # position totale, ordres compris
        levels = int(g.get("ladder", {}).get(a, 1))   # nombre de paliers de vente
        keep = []
        for o in mine:
            lp = float(o["limit_price"])
            dev = lp / px - 1
            # Une vente peut aller jusqu'au dernier palier (+ marge) ; un achat reste à 2,5 écarts.
            far = (dev > (levels + 1.5) * s or dev < -2.5 * s) if o["side"] == "SELL" else abs(dev) > 2.5 * s
            if far:
                actions["cancel"].append({"order_id": o["order_id"], "product_id": pid,
                                          "reason": f"trop loin du marché ({dev:+.1%})"})
                # Les fonds de l'ordre annulé redeviennent disponibles pour le nouvel ordre.
                if o["side"] == "SELL":
                    bal[a] = bal.get(a, 0.0) + float(o.get("base_size", 0))
                else:
                    cash += float(o.get("base_size", 0)) * lp
            else:
                keep.append(o)
        sells = [o for o in keep if o["side"] == "SELL"]
        has_buy = any(o["side"] == "BUY" for o in keep)

        avail_value = bal.get(a, 0.0) * px
        total_value = total_qty * px
        if levels == 1 and not sells and avail_value >= g["min_order_usd"]:
            # La tranche se calcule sur la position TOTALE, jamais sur le seul disponible.
            chunk = min(g["order_usd"], max(g["min_order_usd"], total_value * g["max_sell_fraction"]))
            if total_value <= g["order_usd"] * 1.5 and total_value - chunk < g["min_order_usd"]:
                chunk = total_value  # très petite position : vendue en entier
            chunk = min(chunk, avail_value * 0.999)
            sell_px = px * (1 + s_sell)
            size = floor_to(chunk / sell_px, prod["base_increment"])
            if Decimal(size) > 0 and float(size) * sell_px >= float(prod["quote_min_size"]):
                actions["place"].append({
                    "product_id": pid, "side": "SELL", "type": "limit", "post_only": True,
                    "time_in_force": "GTC", "base_size": size,
                    "limit_price": floor_to(sell_px, prod["price_increment"]),
                    "client_order_id": f"desk-s-{a}-{stamp}", "asset": a,
                    "notional_usd": round(float(size) * sell_px, 2), "spacing": round(s, 4)})
        elif levels > 1 and len(sells) < levels and avail_value >= g["min_order_usd"]:
            # Échelle : toute la position disponible est répartie sur les paliers libres
            # (palier k au prix marché × (1 + k × écart)), chaque ordre ≤ seuil d'autonomie.
            taken = {max(1, round((float(o["limit_price"]) / px - 1) / s)) for o in sells}
            free = [k for k in range(1, levels + 1) if k not in taken][: levels - len(sells)]
            qty_each = bal.get(a, 0.0) * 0.999 / len(free)
            for k in free:
                sell_px = px * (1 + k * s_sell)
                q = min(qty_each, limits["auto_max_order_usd"] / sell_px)
                size = floor_to(q, prod["base_increment"])
                if Decimal(size) > 0 and float(size) * sell_px >= max(float(prod["quote_min_size"]), g["min_order_usd"]):
                    actions["place"].append({
                        "product_id": pid, "side": "SELL", "type": "limit", "post_only": True,
                        "time_in_force": "GTC", "base_size": size,
                        "limit_price": floor_to(sell_px, prod["price_increment"]),
                        "client_order_id": f"desk-s{k}-{a}-{stamp}", "asset": a,
                        "notional_usd": round(float(size) * sell_px, 2), "spacing": round(s, 4)})
        if not has_buy:
            if score <= -g.get("pause_buys_below_score", 0.6):
                actions["skipped"].append({"asset": a, "reason": f"signaux fortement baissiers ({score:+.2f}) : achat suspendu"})
            else:
                need_bid.append(a)

    # Les achats se partagent équitablement le cash, au plus order_usd chacun.
    budget = cash * (1 - g["cash_reserve_fraction"])
    for i, a in enumerate(need_bid):
        pid, prod, px, s = info[a]
        amount = min(g["order_usd"], budget / (len(need_bid) - i))
        if amount < max(g["min_order_usd"], float(prod["quote_min_size"])):
            actions["skipped"].append({"asset": a, "reason": "pas assez de cash pour un achat"})
            continue
        buy_px = px * (1 - s)
        size = floor_to(amount / buy_px, prod["base_increment"])
        if Decimal(size) <= 0 or float(size) * buy_px < float(prod["quote_min_size"]):
            continue
        tp_px = buy_px * (1 + g["take_profit_multiple"] * s)
        actions["place"].append({
            "product_id": pid, "side": "BUY", "type": "limit", "post_only": True,
            "time_in_force": "GTC", "base_size": size,
            "limit_price": floor_to(buy_px, prod["price_increment"]),
            "attached_take_profit_price": floor_to(tp_px, prod["price_increment"]),
            "client_order_id": f"desk-b-{a}-{stamp}", "asset": a,
            "notional_usd": round(float(size) * buy_px, 2), "spacing": round(s, 4)})
        budget -= float(size) * buy_px

    # Chaque ordre passe par le garde-fou de risque commun (volume, montant, concentration…).
    equity = cash + sum(bal.get(a, 0.0) * info[a][2] for a in info) + sum(
        float(o.get("base_size", 0)) * info[o["product_id"].split("-")[0]][2]
        for o in desk if o["side"] == "SELL" and o["product_id"].split("-")[0] in info)
    vol_used = live_volume_today()
    approved = []
    for o in actions["place"]:
        a = o["asset"]
        asset_val = (bal.get(a, 0.0) + sum(float(x.get("base_size", 0)) for x in desk
                     if x["product_id"] == o["product_id"] and x["side"] == "SELL")) * info[a][2]
        after = asset_val + (o["notional_usd"] if o["side"] == "BUY" else 0)
        ctx = {"killed": False, "daily_volume_usd": vol_used, "daily_pnl_usd": 0,
               "drawdown_pct": 0, "equity_usd": equity, "asset_value_after_usd": after}
        ok, why = risk_gate.check(o, ctx, limits)
        if not ok:
            actions["skipped"].append({"asset": a, "reason": "; ".join(why)})
            continue
        vol_used += o["notional_usd"]
        o["needs_user_approval"] = o["notional_usd"] > limits["auto_max_order_usd"]
        approved.append(o)
    actions["place"] = approved
    return actions


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "plan":
        print(json.dumps(plan(load(sys.argv[2])), indent=2, ensure_ascii=False))
    else:
        raise SystemExit(__doc__)
