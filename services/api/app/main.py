import os
import time
import uuid
import logging
import httpx
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from .schemas import FeatureVector
from .guardrails import quick_ood, decide
from .db import ensure_schema, write_decision
from .features import get_spread_bps

TRITON_URL = os.getenv("TRITON_URL", "http://triton:8000")
TRITON_INFER = f"{TRITON_URL}/v2/models/trade_eligibility/versions/1/infer"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

app = FastAPI(title="Trade Eligibility API", version="0.3.0")

REQS = Counter("requests_total", "Total requests", ["route", "status"])
FALLBACK = Counter("fallback_total", "Fallback/abstain reasons", ["reason"])
E2E = Histogram("e2e_latency_ms", "End-to-end latency (ms)",
                buckets=(1, 2, 3, 5, 8, 13, 21, 34, 55, 89))
INF = Histogram("inference_latency_ms", "Inference latency (ms)",
                buckets=(1, 2, 3, 5, 8, 13, 21, 34))
FEAT = Histogram("feature_latency_ms", "Feature latency (ms)",
                 buckets=(1, 2, 3, 5, 8, 13, 21, 34))
POL = Histogram("policy_latency_ms", "Policy latency (ms)",
                buckets=(1, 2, 3, 5, 8, 13, 21, 34))


@app.on_event("startup")
def _startup():
    # Ensure audit schema exists
    try:
        ensure_schema()
        log.info("Audit schema ensured")
    except Exception:
        log.exception("ensure_schema_failed")

    # Warmup Triton once to avoid first-request penalty
    try:
        infer_req = {
            "inputs": [{"name": "input", "shape": [1, 8], "datatype": "FP32", "data": [[0.0]*8]}],
            "outputs": [{"name": "prob", "parameters": {"binary_data": False}}],
        }
        # with httpx.Client(timeout=httpx.Timeout(connect=0.1, read=0.5, write=0.5, pool=0.5)) as client:
        with httpx.Client(timeout=httpx.Timeout(connect=0.2, read=1.5, write=0.5, pool=0.5)) as client:
            r = client.post(TRITON_INFER, json=infer_req)
            r.raise_for_status()
        log.info("Triton warmup succeeded")
    except Exception:
        log.warning("Triton warmup failed (continuing)")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/score")
async def score(payload: FeatureVector, request: Request):
    corr_id = request.headers.get("x-corr-id", str(uuid.uuid4()))
    t0 = time.perf_counter()

    # Freshness guard
    if payload.freshness_ms > 1500:
        FALLBACK.labels("stale_features").inc()
        REQS.labels("/v1/score", "abstain").inc()
        E2E.observe((time.perf_counter() - t0) * 1000)
        try:
            write_decision({
                "corr_id": corr_id, "symbol": payload.symbol, "decision": "ABSTAIN",
                "confidence": 0.0, "latency_ms": int((time.perf_counter() - t0)*1000),
                "reason": "stale_features", "model_tag": "trade_eligibility@1",
                "feature_ms": 0, "inference_ms": 0, "policy_ms": 0
            })
        except Exception:
            pass
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "stale_features"}

    # Feature phase (Feast)
    t_feat = time.perf_counter()
    try:
        spread = get_spread_bps(payload.symbol)
    except Exception:
        spread = None
    FEAT.observe((time.perf_counter() - t_feat) * 1000)
    if spread is None:
        FALLBACK.labels("stale_features").inc()
        REQS.labels("/v1/score", "abstain").inc()
        E2E.observe((time.perf_counter() - t0) * 1000)
        try:
            write_decision({
                "corr_id": corr_id, "symbol": payload.symbol, "decision": "ABSTAIN",
                "confidence": 0.0, "latency_ms": int((time.perf_counter() - t0)*1000),
                "reason": "stale_features", "model_tag": "trade_eligibility@1",
                "feature_ms": 0, "inference_ms": 0, "policy_ms": 0
            })
        except Exception:
            pass
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "stale_features"}
    spread_bps = float(spread)

    # Triton inference
    infer_req = {
        "inputs": [
            {"name": "input", "shape": [
                1, len(payload.features)], "datatype": "FP32", "data": [payload.features]}
        ],
        "outputs": [{"name": "prob", "parameters": {"binary_data": False}}]
    }

    prob_trade = 0.0
    inf_ms = 0
    try:
        t_inf = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=0.2, read=1.5, write=0.5, pool=0.5)) as client:
            r = await client.post(TRITON_INFER, json=infer_req)
            r.raise_for_status()
            out = r.json()
        outputs = out.get("outputs", [])
        if not outputs:
            raise RuntimeError("Triton JSON missing 'outputs'")
        vals = outputs[0].get("data", None)
        if vals is None:
            raise RuntimeError("Triton JSON missing 'data' for 'prob'")
        vec = vals[0] if (isinstance(vals, list)
                          and vals and isinstance(vals[0], list)) else vals
        if not (isinstance(vec, list) and len(vec) >= 2):
            raise RuntimeError(f"Unexpected prob vector: {vec!r}")
        prob_trade = float(vec[1])
        inf_ms = int((time.perf_counter() - t_inf) * 1000)
        INF.observe(inf_ms)
    except Exception:
        FALLBACK.labels("infer_error").inc()
        REQS.labels("/v1/score", "abstain").inc()
        E2E.observe((time.perf_counter() - t0) * 1000)
        try:
            write_decision({
                "corr_id": corr_id, "symbol": payload.symbol, "decision": "ABSTAIN",
                "confidence": 0.0, "latency_ms": int((time.perf_counter() - t0)*1000),
                "reason": "infer_error", "model_tag": "trade_eligibility@1",
                "feature_ms": 0, "inference_ms": inf_ms, "policy_ms": 0
            })
        except Exception:
            pass
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "infer_error"}

    # Policy constraints
    t_pol = time.perf_counter()
    decision, conf, reason = decide(
        spread_bps=spread_bps, prob_trade=prob_trade)
    pol_ms = int((time.perf_counter() - t_pol) * 1000)
    POL.observe(pol_ms)

    status = decision.lower()
    REQS.labels("/v1/score", status).inc()

    e2e_ms = int((time.perf_counter() - t0) * 1000)
    E2E.observe(e2e_ms)

    try:
        write_decision({
            "corr_id": corr_id, "symbol": payload.symbol, "decision": decision,
            "confidence": conf, "latency_ms": e2e_ms, "reason": reason,
            "model_tag": "trade_eligibility@1", "feature_ms": 0, "inference_ms": inf_ms, "policy_ms": pol_ms
        })
    except Exception:
        pass

    return {"decision": decision, "conf": conf, "corr_id": corr_id, "latency_ms": e2e_ms, "reason": reason}


@app.get("/debug/features")
async def debug_features(symbol: str = Query(..., pattern=r"^[A-Z.]{1,15}$")):
    """
    Return what the API sees from Feast for a symbol, plus TTL and Redis connectivity.
    """
    import os
    import time
    from feast import FeatureStore
    import redis as _redis

    t0 = time.perf_counter()
    feast_repo = os.getenv("FEAST_REPO", "/app/feast_repo")
    store = FeatureStore(repo_path=feast_repo)

    # Read online features
    online = store.get_online_features(
        entity_rows=[{"symbol": symbol}],
        features=["microstructure:spread_bps"],
    ).to_dict()

    # Try to read TTL from the FeatureView (best effort across Feast versions)
    ttl_seconds = None
    try:
        fv = store.get_feature_view("microstructure")  # works on modern Feast
        if getattr(fv, "ttl", None):
            ttl_seconds = int(fv.ttl.total_seconds())
    except Exception:
        try:
            # Older Feast: via registry
            reg = store.registry
            fv = reg.get_feature_view("trade_eligibility", "microstructure")
            if getattr(fv, "ttl", None):
                ttl_seconds = int(fv.ttl.total_seconds())
        except Exception:
            ttl_seconds = None

    # Redis ping (confirms credentials + reachability)
    redis_url = os.getenv("REDIS_URL", "redis://:redispassword@redis:6379/0")
    try:
        r = _redis.from_url(
            redis_url, socket_connect_timeout=0.2, socket_timeout=0.5)
        redis_ok = (r.ping() is True)
    except Exception as e:
        redis_ok = False
        redis_error = str(e)
    else:
        redis_error = None

    return {
        "symbol": symbol,
        "feast_repo": feast_repo,
        "features": ["microstructure:spread_bps"],
        # e.g. {'symbol':['BTC'], 'spread_bps':[2.0]}
        "online_result": online,
        "ttl_seconds": ttl_seconds,      # from FeatureView if available
        "redis": {"url": redis_url, "ok": redis_ok, "error": redis_error},
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }
