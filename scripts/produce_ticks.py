import os
import json
import time
import random
from kafka import KafkaProducer

BROKERS = os.getenv("KAFKA_BROKERS", "redpanda:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "ticks")

p = KafkaProducer(bootstrap_servers=[
                  BROKERS], value_serializer=lambda v: json.dumps(v).encode("utf-8"))
print(f"[producer] sending ticks to {TOPIC} on {BROKERS}. CTRL+C to stop.")
try:
    i = 0
    while True:
        # vary spread a bit
        spread = 3.5 + random.random() * 4.0
        msg = {"symbol": "BTC", "spread_bps": round(
            spread, 3), "ts": int(time.time()*1000)}
        p.send(TOPIC, msg)
        p.flush()
        print(f"[producer] {msg}")
        time.sleep(1.0)
        i += 1
except KeyboardInterrupt:
    print("bye")
