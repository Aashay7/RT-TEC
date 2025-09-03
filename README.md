# Trade Eligibility — Phase 1.2 (Feast + Redis)

## Quick start (fresh)

1. Build API image

```
docker compose build --no-cache api
```

2. Export dummy model to Triton repo

```
docker compose run --rm -w /app api python scripts/export_dummy_model.py
```

3. Start Postgres, Redis, Triton, API

```
docker compose up -d postgres redis triton api
```

4. Smoke checks

- Health: `curl localhost:8080/healthz`
- Triton ready: `curl localhost:8000/v2/health/ready`
- Model status: `curl localhost:8000/v2/models/trade_eligibility`

5. Score request

```
curl -X POST localhost:8080/v1/score   -H 'Content-Type: application/json'   -d '{"symbol":"BTC","ts_ns":1,"features":[0.1,0.2,0.0,0.3,0.1,0.0,0.2,0.1],"freshness_ms":10}'
```

## Phase 1.1 recap

- API writes to Postgres `audit.decisions` (schema in `sql/create_audit_schema.sql`)
- Triton warmup on startup; timeouts relaxed for dev
- Triton polls the model repo and reloads changes

## Phase 1.2 — Feast + Redis features

We now fetch `spread_bps` from a Feast online store (Redis).

### One-time bootstrap

```
# 1) Build new API image (Feast + pandas + pyarrow)
docker compose build --no-cache api

# 2) Generate offline data (Parquet) – creates feast_repo/data/microstructure.parquet
docker compose run --rm -w /app/feast_repo api python data/generate_microstructure.py

# 3) Register Feast repo and materialize to online (Redis)
docker compose run --rm -w /app/feast_repo api feast apply
docker compose run --rm -w /app/feast_repo api feast materialize-incremental $(date -u +%Y-%m-%dT%H:%M:%S)
```

### Run the stack & test

```
docker compose up -d redis postgres triton api

curl -X POST localhost:8080/v1/score -H 'Content-Type: application/json'   -d '{"symbol":"BTC","ts_ns":1,"features":[0.1,0.2,0.0,0.3,0.1,0.0,0.2,0.1],"freshness_ms":10}'
```

If features are fresh, the API uses `spread_bps` from Feast; otherwise it **abstains** with `"stale_features"`.
