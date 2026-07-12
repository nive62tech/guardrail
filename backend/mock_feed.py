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
# reliably drifts toward the loss limit within a few minutes)
MOVE_MIN_PCT = -0.05   # -0.05%
MOVE_MAX_PCT = 0.03    # +0.03%


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
# BEFORE wiring it into the engine or WebSocket. Prints one line per second.
# ---------------------------------------------------------------------------

async def _test_run(duration_seconds: int = 60):
    print(f"Starting price: {START_PRICE}")
    start_time = time.time()
    async for price in price_tick_stream():
        elapsed = time.time() - start_time
        pnl_on_10_units = round((price - START_PRICE) * 10, 2)
        print(f"[{elapsed:5.1f}s] price={price}  pnl(10 units)={pnl_on_10_units}")
        if elapsed >= duration_seconds:
            break


if __name__ == "__main__":
    asyncio.run(_test_run(duration_seconds=60))