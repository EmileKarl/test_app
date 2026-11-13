---
description: Briefing crypto complet (news, marché, stats quant, risque) sur une liste d'actifs
argument-hint: [actifs, ex. BTC ETH SOL]
---

Prépare un briefing de desk crypto sur : $ARGUMENTS (par défaut : BTC ETH SOL).

1. Lance **en parallèle** les agents `crypto-news-sentinel` et `market-data-analyst`.
   Demande à `market-data-analyst` d'écrire les séries 30 j et 90 j de chaque actif dans `ai_agents/data/`.
2. Une fois les données écrites, lance **en parallèle** `quant-mathematician` (stats 30 j / 90 j,
   matrice de corrélation) et `risk-probabilist` (VaR/CVaR 1 j et 7 j, Monte Carlo 30 j sans dérive
   avec objectif +10 % et stop −10 % sur chaque actif).
3. Synthétise en une page :
   - Contexte de marché (chiffres datés)
   - Alertes de la veille (titres exacts + liens)
   - Tableau risque par actif
   - Points de vigilance / événements à venir
   Pas de recommandation d'achat ou de vente : présente les données et les risques.
