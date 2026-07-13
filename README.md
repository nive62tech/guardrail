# GuardRail — Real-Time Risk Coaching Engine for Paper Traders

Built for StoxraHack 2026 (Stoxra × IIMT University).

## What it is

GuardRail is a stateful, real-time risk engine that runs alongside a trader's
live paper trading session. It watches positions tick by tick, warns before a
daily loss limit is hit, pauses trading on a first breach, automatically
closes the position on a hard breach, detects revenge-trading patterns, and
gives a plain-English report card at the end of the session.

**It is not a chatbot.** It does not wait to be asked — it acts on its own.
The LLM is only used at the end of a decision, to explain that decision in
plain English. All risk detection (`backend/engine.py`) is pure Python
state-machine logic with zero AI involved. This is the core architectural
distinction that makes GuardRail different from a GPT wrapper: it holds live
position data in memory for the entire session, maintains a persistent
WebSocket connection, and can act (pause/stop a trade) without being prompted.

## Architecture

backend/
├── main.py        FastAPI app — REST + WebSocket, wires everything together
├── engine.py       Core risk logic — early warning, cool-off, hard stop,
│                   revenge detection, discipline scoring. NO AI here.
├── llm.py          Groq API calls — only ever explains a decision already made
├── models.py       Data structures — session state, trades, alerts
├── mock_feed.py    Simulated live price ticks (stands in for a real feed)
└── requirements.txt
frontend/
└── src/
├── App.jsx         Main layout + WebSocket connection
├── SetLimits.jsx   Form to set the 3 risk limits before starting
├── TradePanel.jsx  Mock trading screen (placeholder — teammate's
│                   design replaces this)
└── Sidebar.jsx     Mock alert sidebar (placeholder — teammate's
design replaces this)

## Features

1. **Set Your Limits** — trader sets max daily loss, max position size, max margin usage before starting
2. **Live Risk Engine** — recalculates P&L, margin, exposure, and loss speed every second
3. **Early Warning** — fires once per breach cycle if on track to hit the limit within ~10 minutes
4. **Cool-Off Pause** — first breach pauses trading for 3 minutes instead of an immediate hard stop
5. **Auto Square-Off** — second breach closes the position automatically and explains why via LLM
6. **Revenge Trade Detector** — flags oversized trades placed within 2 minutes of a loss
7. **Daily Report Card** — discipline score (0-100) plus an encouraging, plain-English LLM summary with one actionable tip

## Discipline score formula

Starts at 100. `-10` per ignored early warning, `-20` per cool-off breach,
`-30` for a hard stop, `-15` per revenge trade flagged. Minimum 0.

## Tech stack

- **Backend**: Python, FastAPI, WebSocket
- **Frontend (mock)**: React (Vite) + Tailwind CSS v4
- **LLM**: Groq API (`llama-3.3-70b-versatile`) — used only for generating plain-language explanations, never for risk decisions

## How to run

### Backend
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux
pip install -r requirements.txt

Create `backend/.env`:
GROQ_API_KEY=your_key_here

Then:
uvicorn main:app --reload --port 8000

### Frontend
cd frontend
npm install
npm run dev

Open `http://localhost:5173`.

## Notes

- `TradePanel.jsx` and `Sidebar.jsx` are intentionally plain — they only
  receive data as props and display it, with zero logic inside, so a
  teammate's real UI design can replace them without touching any backend
  or logic code.
- If the Groq API call fails for any reason (rate limit, network issue,
  missing key), `llm.py` falls back to plain hardcoded text so the demo
  never breaks.