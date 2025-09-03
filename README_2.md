# Trade Eligibility — Phase 0 Bootstrap

## Quick start
1) Build API image  
```
docker compose build api
```

2) Export dummy model to Triton repo  
```
docker compose run --rm api python scripts/export_dummy_model.py
```

3) Start the stack  
```
docker compose up -d
```

4) Smoke checks  
- Health: `curl localhost:8080/healthz`  
- Metrics: `http://localhost:8080/metrics` (API), `http://localhost:8002/metrics` (Triton)

5) Score request  
```
curl -X POST localhost:8080/v1/score \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTC","ts_ns":1,"features":[0.1,0.2,0.0,0.3,0.1,0.0,0.2,0.1],"freshness_ms":10}'
```

## Notes
- Feast/Redis features, Postgres audit writes, and load/golden tests come next.
- The OTEL collector is wired for local dev with a logging exporter. Swap to your APM later.
