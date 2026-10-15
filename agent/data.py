"""Data sources: live fetchers or synthetic generators. Engineers own this file."""
import random


def get_inputs(tick: int, seed: int = 42) -> dict:
    """Return the world's inputs for this tick.

    Synthetic by default so the demo is reproducible. Swap in real fetchers
    (e.g. FRED, price APIs) behind this same signature.
    """
    rng = random.Random(seed + tick)
    return {"tick": tick, "value": 100 + rng.uniform(-5, 5)}
