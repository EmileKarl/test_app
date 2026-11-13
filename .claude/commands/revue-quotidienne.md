---
description: Revue quotidienne - audit de tous les agents puis amélioration continue
---

Revue quotidienne du desk. Lis `ai_agents/memory/CONTRAT.md`.

1. Restaure l'état comme dans `/cycle-horaire` (étape 1).
2. Lance `crypto-news-sentinel` (dernières 24 h, actifs de `ai_agents/config/autopilot.json`).
   Si une alerte de sécurité grave touche un actif de l'univers (hack d'exchange, dépeg USDC,
   faille du protocole), écris `python3 ai_agents/engine/cycle.py kill "<raison>"`.
3. Lance `agent-auditor` (contrôles quotidiens complets). Attends son rapport.
4. Lance `agent-improver` avec le résumé d'audit : au plus 3 améliorations VERTES prouvées.
5. Lance les tests : `cd ai_agents/engine && python3 -m unittest test_engine` et
   `cd ai_agents/quant && python3 -m unittest test_quant`. S'ils échouent, annule les changements
   de l'améliorateur (`git checkout -- .claude/agents ai_agents/memory ai_agents/engine ai_agents/quant`).
6. Sauvegarde l'état (étape 3 de `/cycle-horaire`). Commite et pousse **uniquement**
   `.claude/agents ai_agents/memory ai_agents/engine ai_agents/quant` (jamais `ai_agents/state` ni
   `ai_agents/config`) sur la branche courante.
7. Résumé pour l'utilisateur (10 lignes max) : performance nette vs cash et buy-and-hold, notes
   des agents, améliorations faites, alertes. Envoie-le aussi par Gmail en **brouillon** à
   l'utilisateur (ne pas envoyer automatiquement).
