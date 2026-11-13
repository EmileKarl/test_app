#!/usr/bin/env python3
"""Persistance de l'état privé entre deux sessions cloud éphémères.

    python3 ai_agents/engine/state_io.py pack   > /tmp/desk_state.json   # à sauvegarder
    python3 ai_agents/engine/state_io.py unpack < /tmp/desk_state.json   # à restaurer

L'état (portefeuille papier, état de risque, champion, coupe-circuit, fin du journal,
dernières évolutions) tient dans un seul JSON compact, stocké hors du dépôt public
(fichier privé Google Drive « crypto-desk-state.json » par défaut).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

STATE = Path(__file__).resolve().parents[1] / "state"
FILES = ["paper_portfolio.json", "paper_risk_state.json", "live_risk_state.json",
         "strategies.json"]
JOURNAL_KEEP = 150      # lignes de journal conservées
EVOLUTION_KEEP = 20


def tail(path: Path, n: int) -> list[str]:
    return path.read_text().splitlines()[-n:] if path.exists() else []


def pack() -> dict:
    blob = {"version": 1, "files": {}, "kill": None}
    for f in FILES:
        p = STATE / f
        if p.exists():
            blob["files"][f] = json.loads(p.read_text())
    if (STATE / "KILL").exists():
        blob["kill"] = (STATE / "KILL").read_text()
    # On garde tous les fills des 7 derniers jours + les derniers cycles.
    lines = tail(STATE / "journal.jsonl", 5000)
    fills = [l for l in lines if '"type": "fill"' in l][-JOURNAL_KEEP:]
    cycles = [l for l in lines if '"type": "cycle"' in l][-48:]
    blob["journal"] = sorted(set(fills + cycles), key=lambda l: json.loads(l)["ts"])
    blob["evolution"] = tail(STATE / "evolution_log.jsonl", EVOLUTION_KEEP)
    return blob


def unpack(blob: dict) -> dict:
    STATE.mkdir(exist_ok=True)
    for f, data in blob.get("files", {}).items():
        if f in FILES:
            (STATE / f).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    if blob.get("kill"):
        (STATE / "KILL").write_text(blob["kill"])
    if blob.get("journal"):
        (STATE / "journal.jsonl").write_text("\n".join(blob["journal"]) + "\n")
    if blob.get("evolution"):
        (STATE / "evolution_log.jsonl").write_text("\n".join(blob["evolution"]) + "\n")
    return {"restored_files": list(blob.get("files", {})), "journal_lines": len(blob.get("journal", [])),
            "killed": bool(blob.get("kill"))}


if __name__ == "__main__":
    if sys.argv[1:] == ["pack"]:
        print(json.dumps(pack(), separators=(",", ":"), ensure_ascii=False))
    elif sys.argv[1:] == ["unpack"]:
        print(json.dumps(unpack(json.load(sys.stdin))))
    else:
        raise SystemExit(__doc__)
