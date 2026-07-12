"""
mock_feed.py — Simulated live price ticks for the demo/paper-trading session.

ARCHITECTURAL NOTE:
This file exists ONLY to fake what a real Stoxra market-data WebSocket would
send. In production this would be replaced by a live feed subscription.
Nothing here touches risk logic — engine.py is the only place decisions
get made. This keeps the demo deterministic-ish and swappable later.
"""

import asyncio
import random
import time

# Starting price for the demo instrument
START_PRICE = 19800.0

# Per-tick % move range (slightly biased downward so a demo session
# reliably drifts toward the loss limit within ~7-8 minutes).
# Tuned so avg price move per tick ≈ -0.15 rupees, which on a 10-unit
# position (~₹1.5/min avg loss) crosses ₹500 loss around tick 300-350
# (5-6 min), matching the Early Warning(3min)/Cool-Off(5min)/Hard-Stop(7min)
# timeline. Randomness means exact timing will vary run to run — that's fine.
MOVE_MIN_PCT = -0.004   # -0.004%
MOVE_MAX_PCT = 0.0025   # +0.0025%


def _next_price(current_price: float) -> float:
    """Compute the next tick price from a random % move within the biased range."""
    move_pct = random.uniform(MOVE_MIN_PCT, MOVE_MAX_PCT) / 100.0
    return round(current_price * (1 + move_pct), 2)


async def price_tick_stream(start_price: float = START_PRICE, interval_seconds: float = 1.0):
    """
    Async generator that yields one new price every `interval_seconds`.
    Used by main.py inside the WebSocket loop:

        async for price in price_tick_stream():
            ...feed price into engine.py...

    This runs forever until the caller stops iterating (e.g. session ends).
    """
    price = start_price
    while True:
        price = _next_price(price)
        yield price
        await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# Standalone test — run this file directly to sanity check the drift
# BEFORE wiring it into the engine or WebSocket. Prints one line per
# simulated second, compressed in real time via speed_multiplier.
# ---------------------------------------------------------------------------

async def _test_run(duration_seconds: int = 480, speed_multiplier: float = 12.0):
    """
    speed_multiplier compresses the wait time for FAST TESTING ONLY.
    e.g. speed_multiplier=12 means an 8-minute (480s) simulated session
    runs in about 40 real seconds, so you can verify the full trajectory
    quickly. Real usage (via main.py) always uses interval_seconds=1.0,
    untouched by this multiplier.
    """
    print(f"Starting price: {START_PRICE}")
    price = START_PRICE
    tick = 0
    while tick < duration_seconds:
        price = _next_price(price)
        pnl_on_10_units = round((price - START_PRICE) * 10, 2)
        print(f"[{tick:4d}s] price={price}  pnl(10 units)={pnl_on_10_units}")
        tick += 1
        await asyncio.sleep(1.0 / speed_multiplier)


if __name__ == "__main__":
    asyncio.run(_test_run(duration_seconds=480, speed_multiplier=12.0))