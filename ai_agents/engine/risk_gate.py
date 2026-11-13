"""Garde-fou de risque déterministe. Chaque ordre passe ici, en papier comme en réel.

Aucun agent ne peut l'outrepasser : cycle.py n'émet que les ordres approuvés.
"""

from __future__ import annotations


def check(order: dict, ctx: dict, limits: dict) -> tuple[bool, list[str]]:
    """order: {product_id, side, notional_usd}
    ctx: {killed, daily_volume_usd, daily_pnl_usd, drawdown_pct, equity_usd,
          asset_value_after_usd, has_stop}
    """
    reasons = []
    if ctx.get("killed"):
        reasons.append("coupe-circuit actif (fichier KILL)")
    if order["product_id"] not in limits["allowed_products"]:
        reasons.append(f"produit non autorisé: {order['product_id']}")
    if order["side"] not in ("BUY", "SELL"):
        reasons.append("sens invalide")
    n = order.get("notional_usd", 0)
    if not (n > 0):
        reasons.append("montant invalide")
    if n > limits["max_order_usd"]:
        reasons.append(f"montant {n:.2f} > max_order_usd {limits['max_order_usd']}")
    if ctx.get("daily_volume_usd", 0) + n > limits["max_daily_volume_usd"]:
        reasons.append("volume journalier dépassé")
    is_buy = order["side"] == "BUY"
    # Les ventes qui réduisent le risque restent permises après une perte.
    if is_buy and ctx.get("daily_pnl_usd", 0) <= -abs(limits["max_daily_loss_usd"]):
        reasons.append("perte journalière max atteinte: achats bloqués")
    if is_buy and ctx.get("drawdown_pct", 0) >= limits["max_drawdown_pct"]:
        reasons.append("drawdown max atteint: achats bloqués")
    eq = ctx.get("equity_usd", 0)
    if is_buy and eq > 0:
        share = ctx.get("asset_value_after_usd", 0) / eq * 100
        if share > limits["max_asset_pct_of_portfolio"]:
            reasons.append(f"concentration {share:.1f}% > {limits['max_asset_pct_of_portfolio']}%")
    if order.get("derivative") and not limits.get("allow_derivatives"):
        reasons.append("dérivés interdits")
    if order.get("withdrawal"):
        reasons.append("retraits interdits")
    return (not reasons, reasons)
