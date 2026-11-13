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
