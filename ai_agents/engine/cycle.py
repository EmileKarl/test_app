#!/usr/bin/env python3
"""Cycle de trading autonome (appelé toutes les heures par la tâche planifiée).

    python3 ai_agents/engine/cycle.py run            # calcule et (papier) exécute
    python3 ai_agents/engine/cycle.py record FILE    # (réel) journalise les exécutions Coinbase
    python3 ai_agents/engine/cycle.py status         # état du portefeuille géré
    python3 ai_agents/engine/cycle.py kill "raison"  # coupe-circuit manuel

Mode papier : portefeuille fictif dans ai_agents/paper/portfolio.json (commité).
Mode réel   : lit ai_agents/state/live_balances.json (écrit par l'agent depuis le
MCP Coinbase) et écrit les ordres APPROUVÉS dans ai_agents/state/pending_orders.json ;
l'agent les exécute (aperçu puis création) puis appelle `record`.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import market  # noqa: E402
import risk_gate  # noqa: E402
from strategies import DEFAULT_PARAMS, clamp_params, target_exposure  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
STATE = ROOT / "state"          # privé (réel) : ignoré par git
PAPER = ROOT / "paper"          # fictif (papier) : commité, ne révèle rien de réel
MEMORY = ROOT / "memory"        # paramètres de stratégie et historique d'évolution : commités
for d in (STATE, PAPER):
    d.mkdir(exist_ok=True)


def sdir(mode: str) -> Path:
    return PAPER if mode == "paper" else STATE
BARS_PER_YEAR = {"ONE_HOUR": 8760, "TWO_HOUR": 4380, "SIX_HOUR": 1460, "ONE_DAY": 365}


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def save(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def journal(entry: dict) -> None:
    entry = {"ts": now().isoformat(timespec="seconds"), **entry}
    with (sdir(entry.get("mode", "paper")) / "journal.jsonl").open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def today_entries(mode: str) -> list[dict]:
    p = sdir(mode) / "journal.jsonl"
    if not p.exists():
        return []
    day = now().date().isoformat()
    out = []
    for line in p.read_text().splitlines():
        e = json.loads(line)
        if e.get("ts", "").startswith(day) and e.get("mode") == mode and e.get("type") == "fill":
            out.append(e)
    return out


def champion() -> dict:
    s = load(MEMORY / "strategies.json")
    if not s:
        s = {"champion": {**DEFAULT_PARAMS, "granularity": "SIX_HOUR"}, "history": []}
        save(MEMORY / "strategies.json", s)
    return clamp_params(s["champion"]) | {"granularity": s["champion"].get("granularity", "SIX_HOUR"),
                                          "name": s["champion"].get("name", "champion")}


def holdings(mode: str, cfg: dict) -> dict[str, float]:
    if mode == "paper":
        pf = load(PAPER / "portfolio.json")
        if not pf:
            pf = {cfg["quote"]: float(cfg["paper_start_usd"]), "_started": now().isoformat(timespec="seconds")}
            save(PAPER / "portfolio.json", pf)
        return pf
    live = load(STATE / "live_balances.json")
    if not live:
        raise SystemExit("live_balances.json manquant : lire les soldes via le MCP Coinbase d'abord.")
    age = (now() - dt.datetime.fromisoformat(live["as_of"])).total_seconds()
    if age > 900:
        raise SystemExit("live_balances.json a plus de 15 min : relire les soldes.")
    return {k: float(v) for k, v in live["balances"].items()}


def cmd_run() -> dict:
    cfg = load(CONFIG / "autopilot.json")
    limits = load(CONFIG / "risk_limits.json")
    mode = cfg["mode"]
    if mode not in ("paper", "live"):
        raise SystemExit("mode doit être 'paper' ou 'live'")
    p = champion()
    gran = p["granularity"]
    bpy = BARS_PER_YEAR[gran]
    quote = cfg["quote"]
    hold = holdings(mode, cfg)

    prices, targets = {}, {}
    for asset in cfg["universe"]:
        pid = f"{asset}-{quote}"
        rows = market.candles(pid, gran, bars=max(300, p["ema_slow"] * 3 + 10))
        closes = [r["close"] for r in rows]
        prices[asset] = market.price(pid)
        targets[asset] = target_exposure(closes + [prices[asset]], p, bpy) / len(cfg["universe"])

    managed = {a: hold.get(a, 0.0) * prices[a] for a in cfg["universe"]}
    cash = hold.get(quote, 0.0)
    equity = cash + sum(managed.values())

    st = load(sdir(mode) / "risk_state.json", {}) or {}
    day = now().date().isoformat()
    if st.get("day") != day:
        st["day"], st["day_start_equity"] = day, equity
    st["high_water"] = max(st.get("high_water", equity), equity)
    dd = (1 - equity / st["high_water"]) * 100 if st["high_water"] else 0
    fills = today_entries(mode)
    ctx_base = {
        "killed": (STATE / "KILL").exists() or (PAPER / "KILL").exists(),
        "daily_volume_usd": sum(f["notional_usd"] for f in fills),
        "daily_pnl_usd": equity - st["day_start_equity"],
        "drawdown_pct": dd,
        "equity_usd": equity,
    }
    if dd >= limits["max_drawdown_pct"] and not ctx_base["killed"]:
        (sdir(mode) / "KILL").write_text(f"drawdown {dd:.1f}% le {now().isoformat()}\n")
        ctx_base["killed"] = True
    save(sdir(mode) / "risk_state.json", st)

    # Ventes d'abord (libèrent du cash), puis achats.
    proposals = []
    for a in cfg["universe"]:
        cur_w = managed[a] / equity if equity else 0
        delta = (targets[a] - cur_w) * equity
        if abs(targets[a] - cur_w) < p["rebalance_threshold"] / len(cfg["universe"]):
            continue
        side = "BUY" if delta > 0 else "SELL"
        notional = min(abs(delta), limits["max_order_usd"])
        if side == "SELL":
            notional = min(notional, managed[a])
        if notional < cfg["min_order_usd"]:
            continue
        proposals.append({"asset": a, "product_id": f"{a}-{quote}", "side": side,
                          "notional_usd": round(notional, 2), "price": prices[a],
                          "target_weight": round(targets[a], 4), "current_weight": round(cur_w, 4)})
    proposals.sort(key=lambda o: o["side"] != "SELL")

    approved, rejected = [], []
    vol_used = 0.0
    for o in proposals:
        if o["side"] == "BUY":
            o["notional_usd"] = round(min(o["notional_usd"], cash / (1 + cfg["maker_fee"])), 2)
            if o["notional_usd"] < cfg["min_order_usd"]:
                rejected.append({**o, "reasons": ["cash insuffisant"]})
                continue
        ctx = dict(ctx_base, daily_volume_usd=ctx_base["daily_volume_usd"] + vol_used,
                   asset_value_after_usd=managed[o["asset"]] + (o["notional_usd"] if o["side"] == "BUY" else -o["notional_usd"]))
        ok, why = risk_gate.check(o, ctx, limits)
        if not ok:
            rejected.append({**o, "reasons": why})
            continue
        vol_used += o["notional_usd"]
        approved.append(o)
        if mode == "paper":
            _paper_fill(hold, o, cfg, quote, p["name"])
            cash = hold.get(quote, 0.0)
            managed[o["asset"]] = hold.get(o["asset"], 0.0) * prices[o["asset"]]

    if mode == "paper":
        save(PAPER / "portfolio.json", hold)
    else:
        save(STATE / "pending_orders.json", {"created": now().isoformat(), "orders": approved,
                                              "order_type": limits.get("preferred_order_type", "limit")})
    equity_after = hold.get(quote, 0.0) + sum(hold.get(a, 0.0) * prices[a] for a in cfg["universe"]) if mode == "paper" else equity
    summary = {"mode": mode, "strategy": p["name"], "granularity": gran,
               "equity_usd": round(equity_after, 2), "drawdown_pct": round(dd, 2),
               "daily_pnl_usd": round(equity_after - st["day_start_equity"], 2),
               "killed": ctx_base["killed"], "targets": targets, "prices": prices,
               "approved": approved, "rejected": rejected}
    journal({"type": "cycle", "mode": mode, "equity_usd": summary["equity_usd"],
             "n_approved": len(approved), "n_rejected": len(rejected), "strategy": p["name"]})
    return summary


def _paper_fill(hold, o, cfg, quote, strat) -> None:
    fee_rate = cfg["maker_fee"] + cfg.get("paper_slippage", 0.0005)
    n, px = o["notional_usd"], o["price"]
    if o["side"] == "BUY":
        hold[quote] = hold.get(quote, 0.0) - n * (1 + fee_rate)
        hold[o["asset"]] = hold.get(o["asset"], 0.0) + n / px
    else:
        hold[o["asset"]] = max(0.0, hold.get(o["asset"], 0.0) - n / px)
        hold[quote] = hold.get(quote, 0.0) + n * (1 - fee_rate)
    journal({"type": "fill", "mode": "paper", "product_id": o["product_id"], "side": o["side"],
             "notional_usd": n, "price": px, "fee_usd": round(n * fee_rate, 4), "strategy": strat})


def cmd_record(path: str) -> dict:
    """Journalise les exécutions réelles : [{order_id, product_id, side, notional_usd, price, fee_usd}]"""
    fills = json.loads(Path(path).read_text())
    for f in fills:
        journal({"type": "fill", "mode": "live", **f})
    (STATE / "pending_orders.json").unlink(missing_ok=True)
    return {"recorded": len(fills)}


def cmd_status() -> dict:
    cfg = load(CONFIG / "autopilot.json")
    return {"mode": cfg["mode"], "killed": (STATE / "KILL").exists() or (PAPER / "KILL").exists(),
            "paper_portfolio": load(PAPER / "portfolio.json"),
            "champion": load(MEMORY / "strategies.json", {}).get("champion")}


if __name__ == "__main__":
    args = sys.argv[1:] or ["run"]
    if args[0] == "run":
        out = cmd_run()
    elif args[0] == "record":
        out = cmd_record(args[1])
    elif args[0] == "status":
        out = cmd_status()
    elif args[0] == "kill":
        mode = load(CONFIG / "autopilot.json")["mode"]
        (sdir(mode) / "KILL").write_text(" ".join(args[1:]) or "manuel")
        out = {"killed": True}
    else:
        raise SystemExit(__doc__)
    print(json.dumps(out, indent=2, ensure_ascii=False))
