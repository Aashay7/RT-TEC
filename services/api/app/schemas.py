from typing import List
from pydantic import BaseModel, Field

class FeatureVector(BaseModel):
    symbol: str = Field(..., pattern=r"^[A-Z.]{1,15}$")
    ts_ns: int
    features: List[float] = Field(..., min_length=8, max_length=64)
    freshness_ms: int = 0
