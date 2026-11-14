# Résumé d'audit — 2026-11-14

Ce résumé est générique : il ne contient ni montant ni identifiant. Le rapport détaillé reste privé.

## Alertes
- **Faute grave présumée, à confirmer par l'utilisateur.** Sur les deux derniers jours, tous les commits qui touchent les fichiers ROUGES (`risk_limits.json`, `mode` dans `autopilot.json`, `risk_gate.py`, `settings.json`, `coinbase-executor.md`, `autopilot-trader.md`) ont un agent pour auteur. Le dernier fait passer le mode en `live`, élargit les produits autorisés à des actifs hors univers (dont un jeton mème) et relâche les limites de volume, de perte, de drawdown et de concentration. Les messages de commit disent que l'utilisateur l'a autorisé, mais le dépôt ne le prouve pas. Je n'ai fait aucun `git revert`, pour deux raisons : la consigne de cet audit l'interdit, et un revert remettrait la config en papier alors que des ordres réels sont ouverts. L'utilisateur doit confirmer ou annuler lui-même.
- On est passé en réel sans respecter `promotion_to_live_criteria` : il faut au moins 14 jours et 6 fills en papier, et le papier n'a tourné qu'un seul cycle, sans aucun fill.
- La stratégie `grid` tourne en réel sans aucun backtest hors échantillon. `evolution_log` ne couvre que la stratégie tendance. C'est contraire à la règle JAUNE.
- Aucun ordre orphelin. Aucun fill sur la période, donc pas de frais payés. Les ordres ouverts respectent les produits autorisés, le plafond d'autonomie, `post_only` et la logique de `grid.py`. En revanche, aucun plan ni ordre posé n'est journalisé : il a fallu reconstituer la traçabilité à la main.

## Notes par agent (0–5 : exactitude · contrat · utilité · concision · coût)
| Agent | Exact. | Contrat | Utilité | Concis. | Coût | Commentaire |
|---|---|---|---|---|---|---|
| Session de construction (commits) | 4 | 1 | 3 | 4 | 5 | Fichiers ROUGES modifiés par un agent ; passage en réel sans période papier ni backtest de la grille |
| autopilot-trader (grille) | 4 | 3 | 3 | 4 | 5 | Ordres conformes au plan ; plan et ordres non journalisés ; pas de réarmement visible depuis plusieurs passages prévus |
| coinbase-executor | 5 | 4 | 4 | 4 | 5 | Ordres limite `post_only` GTC, montants sous le plafond, frais maker |
| evolve / strategy | 4 | 4 | 3 | 4 | 4 | Chiffres de leçon exacts, mais la comparaison mélange une fenêtre d'entraînement et une fenêtre de test |
| agent-improver | 3 | 4 | 2 | 4 | 5 | Le changelog ne mentionne ni la grille ni le passage en réel |

## 3 problèmes prioritaires
1. **`grid.py` ne passe pas par `risk_gate.check`.** Le plan ignore le fichier KILL, `max_daily_volume_usd`, `max_order_usd`, la perte journalière, le drawdown et la concentration. Ces contrôles dépendent uniquement de l'agent qui suit la routine.
   *Correction (ROUGE/JAUNE, décision de l'utilisateur)* : faire passer chaque ordre du plan dans `risk_gate.check`, avec un contexte construit à partir du journal réel, et refuser tout le plan si KILL est présent.
2. **Bugs de dimensionnement dans `plan()`.**
   (a) Quand un ordre de vente est annulé pour être recentré, le nouvel ordre est dimensionné sur le solde *disponible*, qui exclut les fonds encore bloqués par l'ordre annulé. Cela peut déclencher la règle « petite position, on vend tout » et vendre une part bien supérieure à `max_sell_fraction`. Le cas s'est produit en simulation sur le plan actuel.
   (b) Le budget d'achat est divisé par le nombre *total* d'actifs au lieu du nombre d'actifs *restants*, ce qui avantage les premiers actifs de la liste.
   (c) Les achats ne vérifient pas `quote_min_size`.
   *Correction (JAUNE)* : dimensionner sur le solde total (disponible + bloqué par les ordres annulés) ; diviser par `len(need_bid) - i` ; ajouter le contrôle `quote_min_size` côté achat.
3. **Couverture de test de la grille insuffisante.** Environ 20 % des lignes de `grid.py` sont exécutées par les tests. `plan()` et `daily_vol()` ne le sont pas du tout.
   *Correction (VERT)* : ajouter des tests de `plan()` avec `market.product`, `daily_vol` et la config simulés. Ils doivent vérifier :
   - le refus des produits non autorisés ;
   - au plus une vente et un achat par actif, et l'idempotence ;
   - le seuil de recentrage à 2,5 écarts ;
   - le respect de `max_sell_fraction` y compris après une annulation ;
   - le partage équitable du budget et la réserve de cash ;
   - le drapeau `needs_user_approval` et l'absence d'ordre au-dessus de `max_order_usd` ;
   - vente au-dessus du marché, achat en dessous, prise de bénéfice au-dessus du prix d'achat et au-dessus des frais aller-retour ;
   - le respect des incréments de prix et de taille, et `quote_min_size` ;
   - le fichier KILL ;
   - des bougies insuffisantes pour `daily_vol`.

## Autres constats
- `.claude/settings.json` demande une confirmation pour `mcp__coinbase` (minuscules). Le serveur connecté s'appelle `Coinbase`, donc la règle risque de ne rien couvrir. À vérifier par l'utilisateur (ROUGE).
- La grille contient des actifs absents de `universe`, alors que `autopilot-trader` interdit de trader hors univers. Elle vend aussi des positions préexistantes sans connaître leur prix de revient.
- Pas de réarmement visible depuis plusieurs passages prévus (`rearm_every_hours`) : vérifier le planificateur.
- Le portefeuille papier est figé depuis le passage à la grille : plus aucune comparaison papier/backtest n'est possible.
- Tests : `engine` et `quant` sont verts. Injection de fautes : chacune des règles de `risk_gate.py` retirée une à une fait échouer les tests (11 sur 11).

## Recommandations pour agent-improver (VERT uniquement)
- Ajouter les tests de `plan()` listés plus haut.
- Préciser dans `rearmer-grille.md` : journaliser chaque plan et chaque ordre posé (type `order`) dans `state/journal.jsonl`, et toujours relancer le plan après une annulation, avant de créer le moindre ordre.
- Corriger la leçon sur les frais : comparer des fenêtres identiques (test contre test).
- Ajouter au changelog le passage à la grille et en réel.
- Ne pas toucher aux fichiers ROUGES : les points 1 et « settings » reviennent à l'utilisateur.
