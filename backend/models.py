"""
models.py — Data structures for GuardRail

ARCHITECTURAL NOTE:
Everything in this file is pure state. There is NO AI/LLM anywhere here.
GuardRail's core differentiator is that it is a STATEFUL BACKEND ENGINE —
it holds live position + session data in memory across an entire trading
session, the same way a real risk desk system would. A chatbot wrapper
around an LLM cannot do this: it has no persistent memory of ticks,
no running P&L, and no ability to act between messages. The classes below
are what make GuardRail fundamentally different from "a GPT wrapper".
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SessionStatus(str, Enum):
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COOLING_OFF = "cooling_off"
    STOPPED = "stopped"          # hard stop / square-off has occurred
    ENDED = "ended"               # trader manually ended the session


class AlertType(str, Enum):
    EARLY_WARNING = "early_warning"      # yellow
    COOL_OFF = "cool_off"                # blue
    SQUARE_OFF = "square_off"            # red
    REVENGE_TRADE = "revenge_trade"      # orange
    REPORT_CARD = "report_card"          # green


class TradeAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    SQUARE_OFF = "square_off"   # engine-initiated close


# ---------------------------------------------------------------------------
# Trader-configured limits (Feature 1)
# ---------------------------------------------------------------------------

@dataclass
class RiskLimits:
    max_daily_loss: float          # e.g. 500  (in rupees)
    max_position_size: float       # e.g. 5000 (in rupees, notional value)
    max_margin_usage_pct: float    # e.g. 80   (percentage, 0-100)

    def validate(self) -> None:
        if self.max_daily_loss <= 0:
            raise ValueError("max_daily_loss must be > 0")
        if self.max_position_size <= 0:
            raise ValueError("max_position_size must be > 0")
        if not (0 < self.max_margin_usage_pct <= 100):
            raise ValueError("max_margin_usage_pct must be between 0 and 100")


# ---------------------------------------------------------------------------
# A single trade / position event
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = "NIFTY50"
    action: TradeAction = TradeAction.BUY
    quantity: int = 0
    entry_price: float = 0.0
    position_value: float = 0.0     # quantity * entry_price, notional size
    timestamp: datetime = field(default_factory=datetime.utcnow)
    closed: bool = False
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None


# ---------------------------------------------------------------------------
# Alert sent to frontend over WebSocket
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    type: AlertType
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data: dict = field(default_factory=dict)   # extra structured payload (e.g. score)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }


# ---------------------------------------------------------------------------
# Live tick-level risk snapshot (sent every second)
# ---------------------------------------------------------------------------

@dataclass
class RiskSnapshot:
    current_price: float
    pnl: float
    margin_used_pct: float
    total_exposure: float
    loss_speed_per_min: float       # rupees lost per minute, negative if gaining
    status: SessionStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "current_price": round(self.current_price, 2),
            "pnl": round(self.pnl, 2),
            "margin_used_pct": round(self.margin_used_pct, 2),
            "total_exposure": round(self.total_exposure, 2),
            "loss_speed_per_min": round(self.loss_speed_per_min, 2),
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Full session state — the "stateful memory" GuardRail keeps for the
# entire session. Lives in RAM on the backend, mutated by engine.py.
# ---------------------------------------------------------------------------

@dataclass
class SessionState:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    limits: Optional[RiskLimits] = None
    status: SessionStatus = SessionStatus.NOT_STARTED

    # position tracking
    trades: List[Trade] = field(default_factory=list)
    open_trade: Optional[Trade] = None

    # price / pnl history (for loss-speed calculation + charts)
    price_history: List[float] = field(default_factory=list)
    pnl_history: List[float] = field(default_factory=list)
    tick_timestamps: List[datetime] = field(default_factory=list)

    # alert bookkeeping
    alerts: List[Alert] = field(default_factory=list)
    early_warning_fired: bool = False        # true once per breach cycle
    early_warning_ignored_count: int = 0
    cool_off_breach_count: int = 0
    hard_stop_triggered: bool = False
    revenge_trade_count: int = 0

    # cool-off timing
    cool_off_started_at: Optional[datetime] = None
    cool_off_used_once: bool = False   # first breach = cool-off, second = hard stop

    # revenge-trade detection window
    last_loss_event_at: Optional[datetime] = None
    last_trade_size: Optional[float] = None

    session_started_at: Optional[datetime] = None
    session_ended_at: Optional[datetime] = None

    def add_alert(self, alert: Alert) -> None:
        self.alerts.append(alert)

    def compute_discipline_score(self) -> int:
        """
        Score starts at 100.
        - Each ignored early warning: -10
        - Each cool-off breach: -20
        - Hard stop triggered: -30
        - Each revenge trade flagged: -15
        Minimum: 0
        """
        score = 100
        score -= 10 * self.early_warning_ignored_count
        score -= 20 * self.cool_off_breach_count
        score -= 30 if self.hard_stop_triggered else 0
        score -= 15 * self.revenge_trade_count
        return max(score, 0)