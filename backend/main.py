"""
main.py — FastAPI app: REST endpoints + WebSocket for GuardRail.

ARCHITECTURAL NOTE:
This file is PLUMBING ONLY. It never makes a risk decision itself —
every decision (warn/pause/stop/flag) comes from engine.py. This file's
job is to: receive the trader's limits, run the tick loop, hand each
price to the engine, and push whatever the engine decides out over the
WebSocket. It also calls llm.py, but only AFTER the engine has already
finalized a decision — the LLM is invoked to explain, never to decide.

This is also the file that proves GuardRail is NOT a chatbot: the
WebSocket connection here stays open and the engine keeps running and
making decisions on its own, tick by tick, with no user prompting it.
"""

import asyncio
import uuid
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine import RiskEngine
from models import RiskLimits, AlertType
from mock_feed import price_tick_stream, START_PRICE
from llm import explain_square_off, generate_report_card

app = FastAPI(title="GuardRail Risk Engine")

# Allow the mock React frontend (localhost:3000) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store: session_id -> RiskEngine instance.
# This IS the "stateful memory" — lives in RAM for as long as the
# backend process runs. No database needed for the hackathon prototype.
sessions: Dict[str, RiskEngine] = {}


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------

class StartSessionRequest(BaseModel):
    max_daily_loss: float
    max_position_size: float
    max_margin_usage_pct: float
    quantity: int = 10          # units for the demo position
    entry_price: float = START_PRICE


class StartSessionResponse(BaseModel):
    session_id: str


class NewTradeRequest(BaseModel):
    position_value: float


# ---------------------------------------------------------------------------
# Mock square-off execution (Feature 5)
# Stands in for a real Stoxra paper-trading API call.
# ---------------------------------------------------------------------------

def mock_square_off_order(session_id: str, quantity: int, price: float) -> dict:
    """
    Simulates calling Stoxra's paper trading API to close a position.
    Replace this with a real API call once Stoxra's endpoint is available —
    everything else in the app is unaffected since engine.py never calls
    this directly; only main.py does, after the engine flags a hard stop.
    """
    print(f"[mock_square_off_order] session={session_id} closing {quantity} units @ {price}")
    return {"status": "confirmed", "session_id": session_id, "quantity": quantity, "price": price}


# ---------------------------------------------------------------------------
# REST: start a session (Feature 1)
# ---------------------------------------------------------------------------

@app.post("/api/session/start", response_model=StartSessionResponse)
def start_session(req: StartSessionRequest):
    limits = RiskLimits(
        max_daily_loss=req.max_daily_loss,
        max_position_size=req.max_position_size,
        max_margin_usage_pct=req.max_margin_usage_pct,
    )
    try:
        limits.validate()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    engine = RiskEngine()
    engine.start_session(limits)
    engine.open_position(quantity=req.quantity, entry_price=req.entry_price)

    session_id = engine.state.session_id
    sessions[session_id] = engine
    return StartSessionResponse(session_id=session_id)


# ---------------------------------------------------------------------------
# REST: place a new trade — used to trigger revenge-trade detection (Feature 6)
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/trade")
def place_trade(session_id: str, req: NewTradeRequest):
    engine = sessions.get(session_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Session not found")

    alert = engine.register_new_trade(req.position_value)
    return {"alert": alert.to_dict() if alert else None}


# ---------------------------------------------------------------------------
# REST: manually end a session (Feature 7, when trader clicks "End Session")
# ---------------------------------------------------------------------------

@app.post("/api/session/{session_id}/end")
def end_session(session_id: str):
    engine = sessions.get(session_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Session not found")

    score, summary = engine.end_session()
    paragraph = generate_report_card(summary)
    return {
        "score": score,
        "summary": summary,
        "message": paragraph,
    }


# ---------------------------------------------------------------------------
# WebSocket: the live tick loop (Feature 2, 3, 4, 5)
# Runs continuously, pushing a snapshot + any new alerts every second.
# ---------------------------------------------------------------------------

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()

    engine = sessions.get(session_id)
    if engine is None:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return

    try:
        async for price in price_tick_stream(interval_seconds=1.0):
            snapshot, alerts = engine.process_tick(price)

            # If a hard stop just happened, resolve the LLM explanation
            # before sending — the engine only marked intent, main.py
            # does the actual square-off + LLM call.
            for alert in alerts:
                if alert.type == AlertType.SQUARE_OFF and alert.data.get("needs_llm_explanation"):
                    mock_square_off_order(
                        session_id,
                        engine.state.open_trade.quantity,
                        price,
                    )
                    explanation = explain_square_off(
                        daily_loss_limit=engine.state.limits.max_daily_loss,
                        total_loss=snapshot.pnl,
                        warnings_count=engine.state.early_warning_ignored_count,
                    )
                    alert.message = explanation

            await websocket.send_json({
                "snapshot": snapshot.to_dict(),
                "alerts": [a.to_dict() for a in alerts],
            })

            # After a hard stop, automatically generate and send the
            # report card (Feature 7: "...or after square-off"), then
            # close the connection — the session is over.
            if engine.state.status.value == "stopped":
                score, summary = engine.end_session()
                paragraph = generate_report_card(summary)
                await websocket.send_json({
                    "report_card": {
                        "score": score,
                        "summary": summary,
                        "message": paragraph,
                    }
                })
                break

    except WebSocketDisconnect:
        print(f"[main.py] WebSocket disconnected for session {session_id}")
    finally:
        await websocket.close()


# ---------------------------------------------------------------------------
# Health check — quick way to confirm the server is up
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}