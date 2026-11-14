# Journal des améliorations des agents

- 2026-11-13 · création du desk v2 : moteur déterministe, évolution champion/challenger, auditeur, améliorateur, chercheur, contrat maître.
- 2026-11-14 · engine/grid.py · audit : redimensionnement après annulation faux (cas DOGE), budget d'achat inéquitable, quote_min manquant à l'achat, garde-fou non appelé, daily_vol fragile · corrections + passage de chaque ordre par risk_gate.check + plan vide si KILL · preuve : engine/test_grid.py (9 tests), 19/19 verts.
- 2026-11-14 · commands/rearmer-grille.md, agents/autopilot-trader.md · photo du compte toujours fraîche + base_size ; actifs de la grille autorisés explicitement.
- 2026-11-14 · engine/grid.py · demande utilisateur : engager toute la position SUI · ajout des échelles de vente (`grid.ladder`, N paliers à k × écart, chaque ordre ≤ auto_max_order_usd, recentrage au-delà du dernier palier) · preuve : test_grid.test_sell_ladder_uses_whole_position_within_limits, 20/20 verts.
