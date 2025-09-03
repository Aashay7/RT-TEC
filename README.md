# 🚀 Real-Time Trade-Eligibility Classifier

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen.svg)]()

> **Finance-flavored, latency-critical trading system** that streams market data and makes trade/no-trade decisions under strict P99 latency budgets with safe fallbacks and shadow/canary rollouts.

## 📖 Overview

Stream market data + your features, decide "trade / no trade" under a strict P99 latency budget, with safe fallbacks and shadow/canary rollout.

## 🏗️ Core Architecture

### 📊 Data Pipeline

- **Data Feed**: Historical L2/L3 crypto (Binance/Kraken) replayed as Kafka topics
- **Features**: Rolling microstructure features (spread, imbalance, OFI, short-horizon volatility)
- **Alt Data**: News sentiment from Quiver/alt-data pipeline (optional)

### 🤖 Machine Learning

- **Model Variants**:
  - 🌳 Fast tree model (XGBoost/LightGBM)
  - 🔥 Tiny Torch model (CPU/GPU)
- **Serving**: NVIDIA Triton or TorchServe
- **Gateway**: FastAPI with JSON schema validation & timeouts

### 🗄️ Storage & Streaming

- **Feature Store**: Feast
  - Offline: Parquet files
  - Online: Redis with TTLs
- **Streaming**: Kafka (or Redpanda)
- **Storage**:
  - PostgreSQL (audit logs)
  - S3/Parquet (cold storage)

### ☸️ Infrastructure

- **Orchestration**: Kubernetes with multi-replica deployment
- **Scaling**: HPA based on P99 latency & queue depth
- **Observability**: Prometheus + Grafana (SLOs, burn rate)
- **Tracing**: OpenTelemetry with correlation IDs

### 🔄 CI/CD & DevOps

- **Pipeline**: GitHub Actions
- **Security**: Image signing with Cosign
- **Infrastructure**: Terraform (IaC)
- **Experiments**: Feature flags (OpenFeature/ConfigCat/LaunchDarkly)

## 🛡️ Tier-0 Guardrails

### ✅ Request Validation

- Pydantic schema validation
- Hard timeouts with jitter
- Single retry to secondary replica

### 🔄 Fallback Chain

```
Primary Model → Cached Score → Rules Baseline → Abstain
```

### 🎯 Deployment Safety

- **Shadow Mode**: Test without affecting production
- **Canary Deployments**: Gradual rollout with automatic rollback
- **SLO Breach Detection**: Automatic rollback on performance degradation

### 📈 Health Monitoring

- **Drift Detection**: PSI on key features
- **Model Health**: Calibration drift monitoring
- **Data Quality**: Missingness heatmap
- **Alerting**: Real-time on-call notifications

### 📋 Audit Trail

Complete audit packet for every decision:

- Feature snapshot
- Model version hash
- Decision timestamp
- Performance metrics

## 🚀 Development Phases

### Phase 1: MVP 🎯

```
Kafka Replay → Feast Features → Triton Service → FastAPI → Dashboards
```

**Metrics**: P50/P95/P99 latency + error rates

### Phase 2: Reliability 🛡️

- Canary deployments + blue/green
- Circuit breaker patterns
- Multi-replica with failover

### Phase 3: Scale & Polish 🌟

- Multi-region active-active deployment
- Chaos engineering (node/zone failures)
- Dynamic autoscaling on concurrency

## 🛠️ Technology Stack

| Component          | Technology                |
| ------------------ | ------------------------- |
| **ML Serving**     | NVIDIA Triton, TorchServe |
| **API Gateway**    | FastAPI                   |
| **Feature Store**  | Feast                     |
| **Streaming**      | Kafka/Redpanda            |
| **Database**       | PostgreSQL, Redis         |
| **Storage**        | S3, Parquet               |
| **Orchestration**  | Kubernetes                |
| **Monitoring**     | Prometheus, Grafana       |
| **Tracing**        | OpenTelemetry             |
| **CI/CD**          | GitHub Actions            |
| **Infrastructure** | Terraform                 |
| **Security**       | Cosign                    |

## 📊 Performance Targets

- **Latency**: P99 < 10ms
- **Throughput**: 10k+ requests/second
- **Availability**: 99.99% uptime
- **Accuracy**: >95% model precision

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
