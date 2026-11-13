---
description: Réarme la grille d'ordres limite Coinbase (achat sur baisse / vente sur rebond), petits montants en autonomie
---

Réarmement de la grille. Lis `ai_agents/memory/CONTRAT.md`, `ai_agents/config/autopilot.json`
(section `grid`) et `ai_agents/config/risk_limits.json`. Portefeuille Coinbase : celui que
renvoie `coinbase_portfolios_list` (Default).

1. Si `ai_agents/state/KILL` ou `ai_agents/paper/KILL` existe : n'ouvre aucun ordre, signale-le.
2. **Photo du compte** : `coinbase_balance` (available_balance exactes) et
   `coinbase_orders_list` status=OPEN. Écris `ai_agents/state/grid_snapshot.json` :
   `{"balances": {"BTC": …, "USDC": …}, "open_orders": [{"order_id","product_id","side","limit_price"}]}`
   (limit_price lu dans `order_configuration`).
3. **Exécutions depuis le dernier passage** : `coinbase_orders_fills` (24 h) ; ajoute chaque nouveau
   fill dans `ai_agents/state/journal.jsonl` (`{"ts","type":"fill","mode":"live","order_id","product_id","side","notional_usd","price","fee_usd"}`),
   sans doublon d'order_id+trade.
4. **Plan** : `python3 ai_agents/engine/grid.py plan ai_agents/state/grid_snapshot.json`.
5. **Annulations** du plan via `coinbase_orders_cancel`, puis relis les soldes si des fonds ont été libérés
   et relance le plan.
6. **Ordres** : pour chaque ordre du plan, `coinbase_orders_preview` puis `coinbase_orders_create` avec
   exactement les champs du plan (limit, post_only, GTC, base_size, limit_price,
   attached_take_profit_price pour les achats, portfolio_id).
   - `needs_user_approval: true` (montant > `auto_max_order_usd`) → ne pas créer ; le lister pour
     l'utilisateur. Au-delà de `ask_user_above_usd`, toujours demander.
   - Rejet post-only (prix traversé) : recalculer une seule fois au prochain passage, pas de boucle.
   - Produit refusé (« not supported for trading on this domain ») : ajouter une leçon et ne plus réessayer.
7. Vérifie le volume du jour (journal) contre `max_daily_volume_usd` avant de créer ; au-delà, stop.
8. Rapport (5 lignes max) : ordres ouverts par actif, exécutions depuis le dernier passage
   (gain brut estimé de chaque aller-retour terminé), USDC disponible, anomalies.
   Rien de réel n'est commité (dépôt public) ; seules les leçons génériques le sont.
