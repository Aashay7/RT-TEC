import json, os, requests, jsonschema

API = os.getenv("API_URL", "http://localhost:8080")

def test_health():
    r = requests.get(f"{API}/healthz", timeout=2)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"

def test_score_golden():
    payload = json.load(open(os.path.join(os.path.dirname(__file__), "golden", "request.json"), "r"))
    r = requests.post(f"{API}/v1/score", json=payload, timeout=5)
    assert r.status_code == 200
    body = r.json()
    schema = json.load(open(os.path.join(os.path.dirname(__file__), "golden", "response.schema.json"), "r"))
    jsonschema.validate(body, schema)
    assert body["decision"] in {"ABSTAIN","TRADE","NO_TRADE"}
