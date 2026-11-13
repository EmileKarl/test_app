"""Données de marché publiques Coinbase Advanced Trade (sans clé API).

Endpoints publics : /api/v3/brokerage/market/products/{id}[/candles|/ticker].
Aucune authentification n'est nécessaire ; on ne passe jamais d'ordre ici.
"""

from __future__ import annotations

import json
import time
import urllib.request

BASE = "https://api.coinbase.com/api/v3/brokerage/market/products"
GRANULARITY_SECONDS = {
    "ONE_HOUR": 3600, "TWO_HOUR": 7200, "SIX_HOUR": 21600, "ONE_DAY": 86400,
}
MAX_PER_REQUEST = 300


def _get(url: str, retries: int = 3) -> dict:
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "crypto-desk/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:  # réseau instable : petit backoff
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Échec requête {url}: {last}")


def candles(product_id: str, granularity: str = "SIX_HOUR", bars: int = 300,
            end: int | None = None) -> list[dict]:
    """Bougies OHLCV du plus ancien au plus récent (pagination automatique)."""
    step = GRANULARITY_SECONDS[granularity]
    end = end or int(time.time())
    out: dict[int, dict] = {}
    remaining = bars
    while remaining > 0:
        n = min(MAX_PER_REQUEST, remaining)
        start = end - n * step
        url = (f"{BASE}/{product_id}/candles?granularity={granularity}"
               f"&start={start}&end={end}&limit={n}")
        data = _get(url).get("candles", [])
        if not data:
            break
        for c in data:
            t = int(c["start"])
            out[t] = {"t": t, "open": float(c["open"]), "high": float(c["high"]),
                      "low": float(c["low"]), "close": float(c["close"]),
                      "volume": float(c["volume"])}
        remaining -= n
        end = start
    rows = sorted(out.values(), key=lambda r: r["t"])
    # On retire la bougie en cours (non clôturée) pour éviter tout biais.
    if rows and rows[-1]["t"] + step > time.time():
        rows = rows[:-1]
    return rows[-bars:]


def product(product_id: str) -> dict:
    return _get(f"{BASE}/{product_id}")


def price(product_id: str) -> float:
    return float(product(product_id)["price"])
