import os, time, uuid
from typing import Dict, Any
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from .schemas import FeatureVector
from .guardrails import quick_ood, decide

TRITON_URL = os.getenv("TRITON_URL", "http://triton:8000")
TRITON_INFER = f"{TRITON_URL}/v2/models/trade_eligibility/versions/1/infer"

app = FastAPI(title="Trade Eligibility API", version="0.1.0")

REQS = Counter("requests_total", "Total requests", ["route", "status"])
FALLBACK = Counter("fallback_total", "Fallback/abstain reasons", ["reason"])
E2E = Histogram("e2e_latency_ms", "End-to-end latency (ms)", buckets=(1,2,3,5,8,13,21,34,55,89))
INF = Histogram("inference_latency_ms", "Inference latency (ms)", buckets=(1,2,3,5,8,13,21,34))

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
        # observe E2E latency bucket even on early return to keep histograms continuous
        E2E.observe((time.perf_counter() - t0) * 1000)
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "stale_features"}

    # Simple OOD placeholder
    zscores = [0.0 for _ in payload.features]
    if quick_ood(zscores):
        FALLBACK.labels("ood").inc()
        REQS.labels("/v1/score", "abstain").inc()
        E2E.observe((time.perf_counter() - t0) * 1000)
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "ood"}

    # Triton inference
    infer_req = {
        "inputs": [
            {"name": "input", "shape": [1, len(payload.features)], "datatype": "FP32", "data": [payload.features]}
        ],
        "outputs": [{"name": "prob"}]
    }

    prob_trade = 0.0
    try:
        start_inf = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(0.020, connect=0.005)) as client:
            r = await client.post(TRITON_INFER, json=infer_req)
            r.raise_for_status()
            out = r.json()
            # Triton HTTP JSON response format: outputs[0].data -> list
            data = out["outputs"][0]["data"][0]  # [p_no_trade, p_trade]
            prob_trade = float(data[1])
        INF.observe((time.perf_counter() - start_inf) * 1000)
    except Exception:
        FALLBACK.labels("infer_error").inc()
        REQS.labels("/v1/score", "abstain").inc()
        E2E.observe((time.perf_counter() - t0) * 1000)
        return {"decision": "ABSTAIN", "conf": 0.0, "corr_id": corr_id, "reason": "infer_error"}

    decision, conf, reason = decide(spread_bps=2.0, prob_trade=prob_trade)
    status = decision.lower()
    REQS.labels("/v1/score", status).inc()

    e2e_ms = (time.perf_counter() - t0) * 1000
    E2E.observe(e2e_ms)
    return {"decision": decision, "conf": conf, "corr_id": corr_id, "latency_ms": int(e2e_ms), "reason": reason}
