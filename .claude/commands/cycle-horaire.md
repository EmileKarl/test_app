---
description: Cycle de trading horaire autonome (papier ou réel) avec persistance de l'état privé
---

Cycle horaire du desk. Lis `ai_agents/memory/CONTRAT.md`.

1. **Restaurer l'état** : cherche dans Google Drive le fichier `crypto-desk-state.json`
   (`title = 'crypto-desk-state.json'`). S'il existe, lis son contenu, écris-le dans
   `/tmp/desk_state.json` puis `python3 ai_agents/engine/state_io.py unpack < /tmp/desk_state.json`.
   S'il n'existe pas, c'est le premier cycle : continue.
2. Lance l'agent `autopilot-trader` : « exécute un cycle ». Attends son rapport.
3. **Sauvegarder l'état** : `python3 ai_agents/engine/state_io.py pack > /tmp/desk_state.json`, puis
   crée ou mets à jour le fichier Drive `crypto-desk-state.json` avec ce contenu (fichier privé,
   jamais partagé).
4. Ne commite rien (l'état est privé). Réponse : 3 lignes maximum (mode, valeur, ordres).
   Si le coupe-circuit est actif ou si une anomalie apparaît, commence la réponse par « ⚠️ ».
