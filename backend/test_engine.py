import asyncio
from engine import RiskEngine
from models import RiskLimits
from mock_feed import price_tick_stream, START_PRICE


async def main():
    # cool_off_duration_seconds=10 : TEST-ONLY speed-up so we don't wait
    # 3 real minutes. Production (main.py) always uses the real default (180s).
    engine = RiskEngine(cool_off_duration_seconds=10)
    engine.start_session(RiskLimits(max_daily_loss=500, max_position_size=5000, max_margin_usage_pct=80))
    engine.open_position(quantity=10, entry_price=START_PRICE)

    tick = 0
    async for price in price_tick_stream(interval_seconds=1/12):  # sped up 12x
        snapshot, alerts = engine.process_tick(price)
        for a in alerts:
            print(f"[tick {tick}] ALERT: {a.type.value} -> {a.message}")
        if tick % 30 == 0:
            print(f"[tick {tick}] pnl={snapshot.pnl} status={snapshot.status.value}")
        if engine.state.status.value == "stopped":
            print("Hard stop reached. Ending session.")
            score, summary = engine.end_session()
            print("SCORE:", score)
            print("SUMMARY:", summary)
            break
        tick += 1


asyncio.run(main())