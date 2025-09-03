from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent
PARQUET = OUT_DIR / "microstructure.parquet"
CSV = OUT_DIR / "microstructure.csv"

now = datetime.now(timezone.utc)
rows = []
# make a few recent rows (spread over a few seconds)
for i in range(20):
    rows.append({
        "symbol": "BTC",
        "event_timestamp": now - timedelta(seconds=i % 3),  # tz-aware datetime
        "created": now,                                     # tz-aware datetime
        "spread_bps": 2.0
    })

df = pd.DataFrame(rows)
# ensure dtype is tz-aware in pandas
df["event_timestamp"] = pd.to_datetime(df["event_timestamp"], utc=True)
df["created"] = pd.to_datetime(df["created"], utc=True)

OUT_DIR.mkdir(parents=True, exist_ok=True)
df.to_parquet(PARQUET, index=False)
df.to_csv(CSV, index=False)
print(f"Wrote {PARQUET}")
print(f"Wrote {CSV}")
