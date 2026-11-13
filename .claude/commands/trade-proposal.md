---
description: Évaluer une idée de trade avec le desk d'agents, puis (optionnel) l'exécuter sur Coinbase après confirmation
argument-hint: [ex. acheter 50 USDC de BTC-USDC, stop 62000, objectif 80000]
---

Idée de trade de l'utilisateur : $ARGUMENTS

1. En parallèle : `crypto-news-sentinel` (news sur l'actif des dernières 48 h) et
   `market-data-analyst` (prix, liquidité, séries 90 j écrites dans `ai_agents/data/`).
2. Puis `risk-probabilist` : vérification contre `ai_agents/config/risk_limits.json`, VaR,
   Monte Carlo objectif/stop, taille de position, avocat du diable. Son verdict prime.
3. Présente le dossier : verdict, chiffres, risques, et ce qu'il faudrait changer si c'est REFUSÉ.
4. **N'exécute rien.** Si le verdict n'est pas REFUSÉ et que l'utilisateur veut exécuter, il doit
   répondre avec une confirmation explicite ; seulement alors, lance `coinbase-executor` qui refera
   l'aperçu d'ordre et redemandera confirmation.
