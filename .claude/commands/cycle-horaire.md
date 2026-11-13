---
description: Cycle de trading horaire autonome (papier ou réel) avec persistance de l'état
---

Cycle horaire du desk. Lis `ai_agents/memory/CONTRAT.md`, puis `ai_agents/config/autopilot.json`.

**Mode papier** (aucun connecteur nécessaire)
1. `git pull` sur la branche courante.
2. Lance l'agent `autopilot-trader` : « exécute un cycle » (il lance `cycle.py run`). N'appelle aucun outil Coinbase.
3. `git add ai_agents/paper && git commit -m "paper: cycle horaire" && git push` (réessaie le push
   après `git pull --rebase` en cas de conflit). Rien d'autre n'est commité.

**Mode réel** (nécessite les connecteurs Google Drive et Coinbase, et le verrou activé)
1. Vérifie que `.claude/settings.json` déclare `.claude/hooks/coinbase_guard.py` ; sinon réponds
   « ⚠️ mode live sans verrou : aucun ordre passé » et arrête-toi.
2. Restaure l'état privé : fichier Google Drive `crypto-desk-state.json` → `/tmp/desk_state.json` →
   `python3 ai_agents/engine/state_io.py unpack < /tmp/desk_state.json` (absent = premier cycle).
3. Lance `autopilot-trader` : « exécute un cycle ».
4. `python3 ai_agents/engine/state_io.py pack > /tmp/desk_state.json` puis crée / mets à jour le
   fichier Drive privé `crypto-desk-state.json`. Ne commite rien de réel.

Réponse : 3 lignes maximum (mode, valeur, ordres). Anomalie ou coupe-circuit → commence par « ⚠️ ».
