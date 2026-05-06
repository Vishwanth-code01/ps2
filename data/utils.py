"""
Smart Delivery Dispatch System - Utility Functions
"""

from typing import List


def _percentile(data: List[float], pct: float) -> float:
    """Calculate percentile from a list of values."""
    if not data:
        return float("nan")
    s = sorted(data)
    k = (len(s) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (k - lo) * (s[hi] - s[lo])


def _gini(values: List[float]) -> float:
    """Calculate Gini coefficient for inequality measurement."""
    n = len(values)
    if n == 0 or sum(values) == 0:
        return 0.0
    s = sorted(values)
    cum = sum((i + 1) * v for i, v in enumerate(s))
    return (2 * cum) / (n * sum(s)) - (n + 1) / n


def _banner(msg: str) -> None:
    """Print a formatted banner message."""
    w = 72
    print("\n" + "═" * w)
    print(f"{msg:^{w}}")
    print("═" * w)</content>
<parameter name="filePath">c:\Users\91636\Documents\GitHub\ps2\data\utils.py