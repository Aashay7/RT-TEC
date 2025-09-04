import os
import json
import time
from kafka import KafkaConsumer
import redis

BROKERS = os.getenv("KAFKA_BROKERS", "redpanda:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "ticks")
GROUP = os.getenv("KAFKA_GROUP", "ingest-1")
REDIS_URL = os.getenv("REDIS_URL", "redis://:redispassword@redis:6379/0")
TTL = int(os.getenv("SPREAD_TTL_SEC", "180"))

r = redis.from_url(REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0)


def write_spread(symbol: str, spread: float):
    key = f"te:spread_bps:{symbol}"
    pipe = r.pipeline()
    pipe.set(key, spread, ex=TTL)
    pipe.execute()


def main():
    # Auto-create topics is on by default in Redpanda in dev
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=[BROKERS],
        group_id=GROUP,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        api_version_auto_timeout_ms=5000,
    )
    print(
        f"[ingest] consuming {TOPIC} from {BROKERS}; writing spreads with TTL={TTL}s")
    for msg in consumer:
        try:
            v = msg.value
            symbol = v["symbol"]
            spread = float(v["spread_bps"])
            write_spread(symbol, spread)
            print(f"[ingest] {symbol} spread_bps={spread}")
        except Exception as e:
            print(f"[ingest] error: {e} value={getattr(msg,'value',None)}")


if __name__ == "__main__":
    main()
