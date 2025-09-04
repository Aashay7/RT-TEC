import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = { vus: 2, duration: '20s' };

export default function () {
  const url = 'http://localhost:8080/v1/score';
  const payload = JSON.stringify({
    symbol: 'BTC',
    ts_ns: 1,
    features: [0.1,0.2,0.0,0.3,0.1,0.0,0.2,0.1],
    freshness_ms: 10
  });
  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(url, payload, params);
  check(res, { 'status is 200': (r) => r.status === 200, 'has decision': (r) => !!r.json('decision') });
  sleep(0.2);
}
