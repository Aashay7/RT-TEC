import os
from typing import Optional
from feast import FeatureStore

FEAST_REPO = os.getenv("FEAST_REPO", "/app/feast_repo")
_store: Optional[FeatureStore] = None

def _get_store() -> FeatureStore:
    global _store
    if _store is None:
        _store = FeatureStore(repo_path=FEAST_REPO)
    return _store

def get_spread_bps(symbol: str) -> Optional[float]:
    store = _get_store()
    resp = store.get_online_features(
        entity_rows=[{"symbol": symbol}],
        features=["microstructure:spread_bps"],
    ).to_dict()
    for key in ("microstructure__spread_bps", "spread_bps", "microstructure:spread_bps"):
        if key in resp:
            vals = resp[key]
            if isinstance(vals, list):
                return vals[0] if vals else None
            return vals
    return None


# Optional streaming fallback via simple Redis key populated by ingest service
import redis as _redis
import functools

@functools.lru_cache(maxsize=1)
def _r() -> _redis.Redis:
    url = os.getenv("REDIS_URL","redis://:redispassword@redis:6379/0")
    return _redis.from_url(url, socket_connect_timeout=0.3, socket_timeout=0.5)

def get_spread_bps_stream(symbol: str):
    try:
        val = _r().get(f"te:spread_bps:{symbol}")
        if val is None:
            return None
        return float(val)
    except Exception:
        return None
