CREATE SCHEMA IF NOT EXISTS audit;
CREATE TABLE IF NOT EXISTS audit.decisions (
  id BIGSERIAL PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  corr_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('TRADE','NO_TRADE','ABSTAIN')),
  confidence DOUBLE PRECISION,
  latency_ms INTEGER,
  reason TEXT,
  model_tag TEXT,
  feature_ms INTEGER,
  inference_ms INTEGER,
  policy_ms INTEGER
);
