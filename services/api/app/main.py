from prometheus_client import Counter, Histogram
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
from .features import get_spread_bps, get_spread_bps_stream

TRITON_URL = os.getenv("TRITON_URL", "http://triton:8000")
TRITON_INFER = f"{TRITON_URL}/v2/models/trade_eligibility/versions/1/infer"

CANARY_ENABLED = os.getenv(
    "CANARY_ENABLED", "false").lower() in ("1", "true", "yes")
CANARY_VERSION = os.getenv("CANARY_VERSION", "2")
TRITON_INFER_CANARY = f"{TRITON_URL}/v2/models/trade_eligibility/versions/{CANARY_VERSION}/infer"


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
    try:
        ensure_schema()
        log.info("Audit schema ensured")
    except Exception:
        log.exception("ensure_schema_failed")
    try:
        infer_req = {
            "inputs": [{"name": "input", "shape": [1, 8], "datatype": "FP32", "data": [[0.0]*8]}],
            "outputs": [{"name": "prob", "parameters": {"binary_data": False}}],
        }
        with httpx.Client(timeout=httpx.Timeout(connect=0.3, read=2.0, write=0.5, pool=0.5)) as client:
            r = client.post(TRITON_INFER, json=infer_req)
            r.raise_for_status()
        log.info("Triton warmup succeeded")
    except Exception:
        log.warning("Triton warmup failed (continuing)")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/score")
async def score(payload: FeatureVector, request: Request):
    corr_id = request.headers.get("x-corr-id", str(uuid.uuid4()))
    t0 = time.perf_counter()

    now_ns = time.time_ns()
    age_ms = max(0, int((now_ns - int(payload.ts_ns)) / 1_000_000))
    log.debug(f"event_age_ms={age_ms} freshness_ms={payload.freshness_ms}")
    if age_ms > int(payload.freshness_ms):
        FALLBACK.labels("stale_features").inc()
        REQS.labels("/v1/score", "abstain").inc()
        E2E.observe((time.perf_counter() - t0) * 1000)
        try:
            write_decision({
                "corr_id": corr_id, "symbol": payload.symbol, "decision": "ABSTAIN",
                "confidence": 0.0, "latency_ms": int((time.perf_counter() - t0)*1000),
                "reason": f"stale_event(age_ms={age_ms})", "model_tag": "trade_eligibility@1",
                "feature_ms": 0, "inference_ms": 0, "policy_ms": 0
            })
        except Exception:
            pass
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "stale_event"}

    # Feast
    # t_feat = time.perf_counter()
    # spread = None
    # try:
    #     spread = get_spread_bps(payload.symbol)
    # except Exception:
    #     spread = None
    # FEAT.observe((time.perf_counter() - t_feat) * 1000)
    # # streaming fallback
    # if spread is None:
    #     spread = get_spread_bps_stream(payload.symbol)
    #     if spread is None:
    #         FALLBACK.labels("stale_features").inc()
    #         REQS.labels("/v1/score", "abstain").inc()
    #         E2E.observe((time.perf_counter() - t0) * 1000)
    #         return {"decision": "ABSTAIN", "conf": -0.1, "corr_id": corr_id, "reason": "stale_features_2"}
    # spread_bps = float(spread)

    t_feat = time.perf_counter()
    feast_spread = None
    try:
        feast_spread = get_spread_bps(payload.symbol)  # Feast online
    except Exception:
        feast_spread = None
    stream_spread = get_spread_bps_stream(payload.symbol)  # Redis stream
    FEAT.observe((time.perf_counter() - t_feat) * 1000)

    # Prefer streaming when available; else fall back to Feast
    source = None
    if stream_spread is not None:
        spread_bps = float(stream_spread)
        source = "stream"
    elif feast_spread is not None:
        spread_bps = float(feast_spread)
        source = "feast"
    else:
        FALLBACK.labels("stale_features").inc()
        REQS.labels("/v1/score", "abstain").inc()
        E2E.observe((time.perf_counter() - t0) * 1000)
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "stale_features"}

    log.debug(
        f"Symbol {payload.symbol} spread_bps={spread_bps} source={source}")

    # Triton infer
    infer_req = {
        "inputs": [{"name": "input", "shape": [1, len(payload.features)], "datatype": "FP32", "data": [payload.features]}],
        "outputs": [{"name": "prob", "parameters": {"binary_data": False}}]
    }
    prob_trade, inf_ms = 0.0, 0
    try:
        t_inf = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=0.3, read=2.0, write=0.5, pool=0.5)) as client:
            r = await client.post(TRITON_INFER, json=infer_req)
            r.raise_for_status()
            out = r.json()
        outputs = out.get("outputs", [])
        vals = outputs[0].get("data") if outputs else None
        if vals is None:
            raise RuntimeError("Triton JSON missing 'data'")
        vec = vals[0] if (isinstance(vals, list)
                          and vals and isinstance(vals[0], list)) else vals
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

    # Canary (non-blocking for decision; but we await here to record metrics)
    if CANARY_ENABLED:
        log.debug("Canary enabled, invoking")
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=0.3, read=2.0, write=0.5, pool=0.5)) as client:
                cr = await client.post(TRITON_INFER_CANARY, json=infer_req)
                if cr.status_code == 200:
                    cout = cr.json()
                    cvals = cout.get("outputs", [])[0].get("data")
                    cvec = cvals[0] if (isinstance(
                        cvals, list) and cvals and isinstance(cvals[0], list)) else cvals
                    canary_prob = float(cvec[1])
                    from math import fabs
                    CANARY_DELTA.observe(abs(prob_trade - canary_prob))
                    # decision disagreement?
                    from .guardrails import decide as dec2
                    cdec, _, _ = dec2(spread_bps=spread_bps,
                                      prob_trade=canary_prob)
                    if cdec != decision:
                        CANARY_DISAGREE.inc()
                else:
                    pass
        except Exception:
            pass

    # Policy
    t_pol = time.perf_counter()
    decision, conf, reason = decide(
        spread_bps=spread_bps, prob_trade=prob_trade)
    log.debug(f"Decision {decision} conf {conf} reason {reason}")
    pol_ms = int((time.perf_counter() - t_pol) * 1000)
    POL.observe(pol_ms)

    REQS.labels("/v1/score", decision.lower()).inc()
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

    return {"decision": decision, "conf": conf, "corr_id": corr_id, "spread_bps": spread_bps, "latency_ms": e2e_ms, "reason": reason}

# Debug endpoints


@app.get("/debug/features")
async def debug_features(symbol: str = Query(..., pattern=r"^[A-Z.]{1,15}$")):
    from feast import FeatureStore
    import redis as _redis
    feast_repo = os.getenv("FEAST_REPO", "/app/feast_repo")
    store = FeatureStore(repo_path=feast_repo)
    online = store.get_online_features(
        entity_rows=[{"symbol": symbol}],
        features=["microstructure:spread_bps"],
    ).to_dict()
    ttl_seconds = None
    try:
        fv = store.get_feature_view("microstructure")
        if getattr(fv, "ttl", None):
            ttl_seconds = int(fv.ttl.total_seconds())
    except Exception:
        pass
    redis_url = os.getenv("REDIS_URL", "redis://:redispassword@redis:6379/0")
    try:
        r = _redis.from_url(
            redis_url, socket_connect_timeout=0.2, socket_timeout=0.5)
        redis_ok = (r.ping() is True)
        redis_error = None
    except Exception as e:
        redis_ok = False
        redis_error = str(e)
    return {"symbol": symbol, "feast_repo": feast_repo, "online_result": online, "ttl_seconds": ttl_seconds, "redis": {"url": redis_url, "ok": redis_ok, "error": redis_error}}


@app.get("/debug/triton")
async def debug_triton(n: int = Query(8, ge=1, le=64)):
    import time
    t0 = time.perf_counter()
    payload = {
        "inputs": [{"name": "input", "shape": [1, n], "datatype": "FP32", "data": [[0.0]*n]}],
        "outputs": [{"name": "prob", "parameters": {"binary_data": False}}],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=0.3, read=2.0, write=0.5, pool=0.5)) as client:
            r = await client.post(TRITON_INFER, json=payload)
            body = r.json() if r.headers.get("content-type",
                                             "").startswith("application/json") else r.text
            ok = r.status_code == 200
    except Exception as e:
        ok, body = False, {"error": str(e)}
    return {"ok": ok, "elapsed_ms": int((time.perf_counter()-t0)*1000), "infer_url": TRITON_INFER, "response": body}

CANARY_DELTA = Histogram("canary_abs_delta", "Abs difference between primary and canary prob", buckets=(
    0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0))
CANARY_DISAGREE = Counter("canary_disagree_total",
                          "Count of decision disagreement between primary and canary")
