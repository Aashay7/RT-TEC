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

    # Handle various Feast versions / naming styles
    for key in ("microstructure__spread_bps", "spread_bps", "microstructure:spread_bps"):
        if key in resp:
            vals = resp[key]
            if isinstance(vals, list) and vals:
                return vals[0]
            return vals
    return None
