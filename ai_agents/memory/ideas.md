# Idées de stratégies à tester (strategy-researcher)

Format : hypothèse · source · test proposé (backtest.py / composante) · statut (à tester / rejetée / adoptée + mesure).

- Filtre de régime BTC : n'exposer les altcoins que si BTC est au-dessus de sa moyenne longue · TradingAgents / littérature momentum crypto · ajouter une composante `regime_btc` · à tester
- Ordres post-only (maker 0,25 %) au lieu de taker (0,5 %) : divise les frais par 2 · grille de frais Coinbase · déjà appliqué en papier ; à vérifier en réel (taux de remplissage) · à tester en réel
