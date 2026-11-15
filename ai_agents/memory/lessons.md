# Leçons apprises (mémoire partagée, lue par tous les agents)

Format : `- [date] [agent] leçon — preuve (mesure, test ou source)`. Pas de montants en dollars ici (dépôt public).
L'agent-improver ajoute, fusionne et retire les leçons ; l'agent-auditor vérifie qu'elles sont prouvées.

- [2026-11-13] [evolve] La stratégie initiale (rééquilibrage fréquent) faisait ~224 trades sur ~4 mois et payait ~7,7 % du capital en frais ; le challenger promu, plus lent (seuil de rééquilibrage ~24 %), en faisait 15 avec ~1 % de frais — preuve : evolution_log du 2026-11-13. Sur un petit capital, la fréquence de trading est l'ennemi n°1.
- [2026-11-13] [market] Les données CoinGecko 90 j ont ~120 points (pas ≈ 18 h), pas 1 point/jour : toujours laisser quant.py déduire le pas — preuve : startTs/endTs.
- [2026-11-13] [coinbase] Aucune paire BTC-CAD sur Advanced Trade : la monnaie de cotation est USDC — preuve : API produits publique (NOT_FOUND).
- [2026-11-13] [coinbase] Plusieurs petits jetons du compte (NOICE, B3, KARRAT, VARA…) ne sont probablement pas échangeables via l'API (DEX uniquement) : hors univers, ne pas y toucher.
- [2026-11-13] [coinbase] BNB-USDC est refusé par le connecteur (« not supported for trading on this domain ») : actif retiré de la grille — preuve : coinbase_orders_preview.
- [2026-11-13] [coinbase] `coinbase_orders_list` ne renvoie pas `client_order_id` : la grille gère tous les ordres ouverts de ses paires — preuve : réponse orders_list.
- [2026-11-13] [coinbase] Le connecteur n'a ni outil de déstaking ni conversion CAD→USDC (USD↔USDC seulement) : le staking et les CAD se gèrent dans l'app Coinbase — preuve : liste des outils.
- [2026-11-14] [audit] Après l'annulation d'une vente, `available_balance` exclut encore la quantité bloquée : le nouvel ordre doit se dimensionner sur la position TOTALE (disponible + bloqué), sinon la règle « petite position » vend une part énorme — preuve : test_grid.test_resize_after_cancel_uses_total_position.
- [2026-11-14] [audit] La photo du compte doit être relue à chaque réarmement ; réutiliser une ancienne photo masque les exécutions — preuve : audit du 2026-11-14.
- [2026-11-14] [utilisateur] SUI déstaké par l'utilisateur puis ajouté à la grille (SUI-USDC) à sa demande.
- [2026-11-14] [signals] Sur ~2 ans de bougies journalières (8 cryptos, ~4 000 observations), AUCUN des 10 indicateurs techniques classiques (RSI, MACD, Bollinger, EMA, momentum, Donchian, volume, chandeliers, divergence RSI, z-score), ni Fear & Greed, ni le financement OKX n'a de pouvoir prédictif significatif à 1, 3 ou 7 jours : |IC| < 0,06, taux de réussite 48–52 % — preuve : memory/signal_weights.json. Les poids restent à 0 ; la grille n'est pas modulée tant qu'aucun signal n'est prouvé.
- [2026-11-14] [signals] Un seul résultat « significatif » (volume à 1 j, t = −2,07) sur 36 tests est compatible avec le hasard : seuil d'adoption relevé à |t| ≥ 3.
- [2026-11-15] [utilisateur] Sans prix de revient connu, vendre les avoirs existants peut réaliser une perte : l'utilisateur a choisi le mode « acheter d'abord » (sell_existing_holdings=false), toutes les ventes annulées — preuve : test_grid.test_buy_first_mode_never_sells_holdings.
