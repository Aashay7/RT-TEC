from datetime import timedelta
from feast import FileSource, FeatureView, Field, FeatureService
from feast.types import Float32
from entities import symbol

ms_source = FileSource(
    path="data/microstructure.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
)

microstructure = FeatureView(
    name="microstructure",
    entities=[symbol],
    ttl=timedelta(seconds=120),
    schema=[Field(name="spread_bps", dtype=Float32)],
    online=True,
    source=ms_source,
)

online_service = FeatureService(
    name="trade_eligibility_service",
    features=[microstructure],
)
