from feast import Entity
from feast.types import ValueType

symbol = Entity(name="symbol", join_keys=[
                "symbol"], value_type=ValueType.STRING)
