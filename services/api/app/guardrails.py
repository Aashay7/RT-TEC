from typing import List
CONF_THRESH = 0.62
Z_MAX = 3.5

def quick_ood(zscores: List[float]) -> bool:
    return any(abs(z) > Z_MAX for z in zscores)

def decide(spread_bps: float, prob_trade: float):
    if prob_trade < CONF_THRESH:
        return "ABSTAIN", prob_trade, "low_conf"
    if spread_bps > 5:
        return "NO_TRADE", prob_trade, "wide_spread"
    return "TRADE", prob_trade, "ok"
