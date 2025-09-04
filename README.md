# Trade Eligibility — Phase 0.3

## What’s in this phase

- Feast online feature (Redis) with dev TTL.
- `/debug/features` and `/debug/triton` endpoints.
- Prometheus + example Grafana dashboard.
- Golden test scaffolding and k6 smoke.

## Quick start

```bash
# Build API image (Feast + deps)
docker compose build --no-cache api

# Export model to Triton repo
docker compose run --rm -w /app api python scripts/export_dummy_model.py

# Generate Feast data, apply & materialize
docker compose run --rm -w /app/feast_repo api python data/generate_microstructure.py
docker compose run --rm -w /app/feast_repo api feast apply
docker compose run --rm -w /app/feast_repo api feast materialize-incremental "$(date -u +"%Y-%m-%dT%H:%M:%S")"

# Start core services
docker compose up -d redis postgres triton api

# Sanity
curl -s http://localhost:8080/healthz
curl -s "http://localhost:8080/debug/features?symbol=BTC"
curl -s "http://localhost:8080/debug/triton?n=8"
curl -s -X POST http://localhost:8080/v1/score -H 'Content-Type: application/json'   -d '{"symbol":"BTC","ts_ns":1,"features":[0.1,0.2,0.0,0.3,0.1,0.0,0.2,0.1],"freshness_ms":10}'
```

## Phase 0.4 — Streaming & Canary

### New services

- **redpanda** (Kafka-compatible broker) + **redpanda-console** at http://localhost:8081
- **ingest** consumer: reads `ticks` topic and writes `te:spread_bps:{symbol}` to Redis (TTL env `SPREAD_TTL_SEC`).
- **pytools** helper container.

### API updates

- **Streaming fallback**: if Feast has no feature, API reads `te:spread_bps:{symbol}` from Redis.
- **Canary inference**: enable with `CANARY_ENABLED=true` (defaults to version `2`). Metrics:
  - `canary_abs_delta` histogram
  - `canary_disagree_total` counter

### Try it

```bash
# build & start new services
docker compose build ingest
docker compose up -d redpanda redpanda-console ingest

# export primary (v1) and canary (v2) models
docker compose run --rm -w /app api python scripts/export_dummy_model.py
docker compose restart triton

# (optional) keep Feast materialized too
docker compose run --rm -w /app/feast_repo api feast apply
docker compose run --rm -w /app/feast_repo api feast materialize-incremental "$(date -u +"%Y-%m-%dT%H:%M:%S")"

# enable canary and restart API
export CANARY_ENABLED=true && export CANARY_VERSION=2
# or set in docker-compose.yml env for api before bringing it up
docker compose restart api

# send streaming ticks (from tools container)
docker compose run --rm pytools bash -lc "pip install -q kafka-python && python scripts/produce_ticks.py"
# in another terminal, hit the API while ingest updates Redis
curl -s -X POST http://localhost:8080/v1/score -H 'Content-Type: application/json'   -d '{"symbol":"BTC","ts_ns":1,"features":[0.1,0.2,0.0,0.3,0.1,0.0,0.2,0.1],"freshness_ms":10}'

# debug helpers
curl -s "http://localhost:8080/debug/triton?n=8" | jq
curl -s "http://localhost:8080/debug/features?symbol=BTC" | jq
```

### Notes

- Redis key format for streaming is simple: `te:spread_bps:{SYMBOL}`. TTL is `SPREAD_TTL_SEC` (default 180s).
- Redpanda auto-creates the `ticks` topic on first publish.
- Grafana dashboard (Phase 0.3) will also chart canary metrics if you add them.
