---
description: Évolution hebdomadaire - recherche d'idées puis compétition champion/challengers hors échantillon
---

Évolution hebdomadaire. Lis `ai_agents/memory/CONTRAT.md`.

1. `git pull`. En mode réel seulement : restaure l'état privé comme dans `/cycle-horaire`.
2. Lance `strategy-researcher` : 1 à 3 nouvelles idées testables dans `ai_agents/memory/ideas.md`.
3. Lance `agent-improver` : s'il existe une idée « à tester » bien spécifiée, l'implémenter comme
   composante (niveau JAUNE, poids 0 par défaut, test unitaire), tests verts obligatoires.
4. `python3 ai_agents/engine/evolve.py --candidates 60 --bars 720` : le champion n'est remplacé que
   s'il est battu hors échantillon (règles dans evolve.py). Ne force jamais une promotion.
5. Mets à jour le statut des idées dans `ideas.md` et ajoute une leçon prouvée dans `lessons.md`
   (sans montants).
6. En mode réel : sauvegarde l'état privé (Drive). Commite et pousse `.claude/agents ai_agents/memory ai_agents/engine ai_agents/quant`.
7. Résumé : champion actuel, résultat de la compétition (train/test, frais, trades), idées testées.
