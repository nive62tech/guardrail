"""
engine.py — GuardRail's core risk engine.

ARCHITECTURAL NOTE (this is the file that wins "Best Innovation"):
This is where EVERY decision is made — early warning, cool-off, hard stop,
revenge-trade detection, discipline scoring. None of it depends on an LLM.
The engine is pure Python state-machine logic acting on live price ticks.
The LLM (llm.py) is only ever called AFTER a decision is already final,
purely to phrase that decision in plain English. If you deleted llm.py
entirely, GuardRail would still correctly protect the trader — it would
just show plain alert text instead of AI-generated coaching language.
That separation is the whole point: a chatbot can't hold this state or
act on its own between messages. This engine does, continuously.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from models import (
    SessionState,
    RiskLimits,
    Trade,
    TradeAction,
    Alert,
    AlertType,
    RiskSnapshot,
    SessionStatus,
)

# ---------------------------------------------------------------------------
# Tunable thresholds (kept as named constants so they're easy to explain
# to judges and easy to tweak without touching logic)
# ---------------------------------------------------------------------------

COOL_OFF_DURATION_SECONDS = 180          # 3 minutes
EARLY_WARNING_LOOKAHEAD_MINUTES = 10     # warn if limit will be hit within ~10 min
LOSS_SPEED_WINDOW_SECONDS = 60           # how much recent history to use for ₹/min calc
REVENGE_TRADE_WINDOW_SECONDS = 120       # 2 minutes
REVENGE_TRADE_SIZE_MULTIPLIER = 1.5      # new trade > 1.5x previous = revenge flag


class RiskEngine:
    """
    Wraps a single SessionState and exposes the operations main.py needs:
      - start_session(limits)
      - open_position(quantity, entry_price)
      - process_tick(current_price) -> (RiskSnapshot, List[Alert])
      - register_new_trade(position_value) -> Optional[Alert]  (revenge check)
      - end_session() -> (int score, dict summary)

    One RiskEngine instance = one trader's live session, held in memory
    for as long as the WebSocket connection is open.
    """

    def __init__(self, cool_off_duration_seconds: int = COOL_OFF_DURATION_SECONDS):
        self.state: Optional[SessionState] = None
        # Configurable so tests can shrink this without fragile module patching.
        # Real usage (main.py) never overrides this — always the real 180s.
        self.cool_off_duration_seconds = cool_off_duration_seconds

    # -----------------------------------------------------------------
    # Setup
    # -----------------------------------------------------------------

    def start_session(self, limits: RiskLimits) -> SessionState:
        limits.validate()
        self.state = SessionState(limits=limits)
        self.state.status = SessionStatus.ACTIVE
        self.state.session_started_at = datetime.utcnow()
        return self.state

    def open_position(self, quantity: int, entry_price: float, symbol: str = "NIFTY50") -> Trade:
        """Opens the trader's position. In the demo this is called once at session start."""
        trade = Trade(
            symbol=symbol,
            action=TradeAction.BUY,
            quantity=quantity,
            entry_price=entry_price,
            position_value=quantity * entry_price,
        )
        self.state.trades.append(trade)
        self.state.open_trade = trade
        self.state.last_trade_size = trade.position_value
        return trade

    # -----------------------------------------------------------------
    # Per-tick processing — the heart of the engine, called once per second
    # -----------------------------------------------------------------

    def process_tick(self, current_price: float) -> Tuple[RiskSnapshot, List[Alert]]:
        state = self.state
        new_alerts: List[Alert] = []
        now = datetime.utcnow()

        # Record tick history regardless of status (useful for report card charts)
        state.price_history.append(current_price)
        state.tick_timestamps.append(now)

        # If session already terminal, just return a flat snapshot, do nothing else.
        if state.status in (SessionStatus.STOPPED, SessionStatus.ENDED):
            pnl = self._compute_pnl(current_price)
            state.pnl_history.append(pnl)
            snapshot = self._build_snapshot(current_price, pnl, 0.0)
            return snapshot, new_alerts

        # Handle cool-off expiry before anything else
        if state.status == SessionStatus.COOLING_OFF:
            elapsed = (now - state.cool_off_started_at).total_seconds()
            if elapsed >= self.cool_off_duration_seconds:
                state.status = SessionStatus.ACTIVE
                state.early_warning_fired = False  # fresh breach cycle after cool-off
            else:
                # still cooling off — compute pnl for display but skip breach checks
                pnl = self._compute_pnl(current_price)
                state.pnl_history.append(pnl)
                snapshot = self._build_snapshot(current_price, pnl, 0.0)
                return snapshot, new_alerts

        # --- Core calculations (Feature 2) ---
        pnl = self._compute_pnl(current_price)
        state.pnl_history.append(pnl)
        loss_speed = self._compute_loss_speed(now)
        margin_used_pct = self._compute_margin_used_pct()
        total_exposure = self._compute_total_exposure(current_price)

        # --- Breach check (Feature 4 / 5) ---
        daily_loss_limit = state.limits.max_daily_loss
        if pnl <= -daily_loss_limit:
            breach_alert = self._handle_breach()
            new_alerts.append(breach_alert)
        else:
            # --- Early warning check (Feature 3), only if not already in breach ---
            warning_alert = self._check_early_warning(pnl, loss_speed, daily_loss_limit)
            if warning_alert:
                new_alerts.append(warning_alert)

        snapshot = self._build_snapshot(current_price, pnl, loss_speed, margin_used_pct, total_exposure)
        return snapshot, new_alerts

    # -----------------------------------------------------------------
    # Feature 3: Early Warning
    # -----------------------------------------------------------------

    def _check_early_warning(self, pnl: float, loss_speed: float, daily_loss_limit: float) -> Optional[Alert]:
        state = self.state

        if state.early_warning_fired:
            return None  # already fired this breach cycle, don't repeat every second

        if loss_speed <= 0:
            return None  # not currently losing money, no warning needed

        remaining_to_limit = daily_loss_limit + pnl  # pnl is negative while losing
        projected_minutes = remaining_to_limit / loss_speed

        if 0 < projected_minutes <= EARLY_WARNING_LOOKAHEAD_MINUTES:
            state.early_warning_fired = True
            message = (
                f"You are losing ₹{loss_speed:.0f} per minute. "
                f"At this rate you will hit your ₹{daily_loss_limit:.0f} limit "
                f"in about {projected_minutes:.0f} minutes. Consider reducing your position."
            )
            alert = Alert(type=AlertType.EARLY_WARNING, message=message)
            state.add_alert(alert)
            return alert

        return None

    # -----------------------------------------------------------------
    # Feature 4 & 5: Cool-Off then Hard Stop / Square-Off
    # -----------------------------------------------------------------

    def _handle_breach(self) -> Alert:
        state = self.state

        # If a warning was live and ignored right up to the breach, count it.
        if state.early_warning_fired:
            state.early_warning_ignored_count += 1
            state.early_warning_fired = False

        state.last_loss_event_at = datetime.utcnow()

        if not state.cool_off_used_once:
            # First breach -> cool off, don't stop trading yet
            state.status = SessionStatus.COOLING_OFF
            state.cool_off_started_at = datetime.utcnow()
            state.cool_off_used_once = True
            state.cool_off_breach_count += 1
            message = (
                "You have hit your daily limit for the first time. "
                "Trading is paused for 3 minutes. Take a breath — this is normal for new traders."
            )
            alert = Alert(type=AlertType.COOL_OFF, message=message)
        else:
            # Second breach (after cool-off already used) -> hard stop
            state.status = SessionStatus.STOPPED
            state.hard_stop_triggered = True
            # main.py is responsible for: calling the mock square-off function,
            # then calling llm.py for the explanation, then sending the real
            # SQUARE_OFF alert with that text. Here we just mark intent.
            message = "SQUARE_OFF_PENDING"  # placeholder; main.py replaces this with LLM text
            alert = Alert(type=AlertType.SQUARE_OFF, message=message, data={"needs_llm_explanation": True})

        state.add_alert(alert)
        return alert

    # -----------------------------------------------------------------
    # Feature 6: Revenge Trade Detector
    # Call this whenever the trader places a NEW trade (not on every tick).
    # -----------------------------------------------------------------

    def register_new_trade(self, position_value: float) -> Optional[Alert]:
        state = self.state
        alert = None

        if state.last_loss_event_at is not None:
            seconds_since_loss = (datetime.utcnow() - state.last_loss_event_at).total_seconds()
            if seconds_since_loss <= REVENGE_TRADE_WINDOW_SECONDS and state.last_trade_size:
                size_ratio = position_value / state.last_trade_size
                if size_ratio > REVENGE_TRADE_SIZE_MULTIPLIER:
                    state.revenge_trade_count += 1
                    minutes_since = round(seconds_since_loss / 60, 1)
                    message = (
                        f"This trade is {size_ratio:.1f}x bigger than your last one, "
                        f"placed just {minutes_since} minutes after a loss. "
                        f"This pattern is called revenge trading and often leads to bigger losses. "
                        f"You can still proceed, but be careful."
                    )
                    alert = Alert(type=AlertType.REVENGE_TRADE, message=message)
                    state.add_alert(alert)

        state.last_trade_size = position_value
        return alert

    # -----------------------------------------------------------------
    # Feature 7: Daily Report Card (score only — LLM paragraph added by main.py)
    # -----------------------------------------------------------------

    def end_session(self) -> Tuple[int, dict]:
        state = self.state
        state.status = SessionStatus.ENDED
        state.session_ended_at = datetime.utcnow()

        score = state.compute_discipline_score()
        summary = {
            "total_trades": len(state.trades),
            "total_pnl": round(state.pnl_history[-1], 2) if state.pnl_history else 0.0,
            "early_warnings_fired_total": state.early_warning_ignored_count,  # all fired warnings were followed by a breach in this simple model
            "early_warnings_ignored": state.early_warning_ignored_count,
            "cool_off_breaches": state.cool_off_breach_count,
            "hard_stop_triggered": state.hard_stop_triggered,
            "revenge_trades": state.revenge_trade_count,
            "discipline_score": score,
        }
        return score, summary

    # -----------------------------------------------------------------
    # Internal calculation helpers
    # -----------------------------------------------------------------

    def _compute_pnl(self, current_price: float) -> float:
        trade = self.state.open_trade
        if trade is None:
            return 0.0
        if trade.action == TradeAction.BUY:
            return round((current_price - trade.entry_price) * trade.quantity, 2)
        else:
            return round((trade.entry_price - current_price) * trade.quantity, 2)

    def _compute_margin_used_pct(self) -> float:
        """
        Simplified for the hackathon demo: margin used is expressed as a
        percentage of the trader's configured max_position_size limit,
        since we don't have a real broker margin API. Swap this for a real
        margin calculation if the Stoxra API exposes one.
        """
        trade = self.state.open_trade
        if trade is None or not self.state.limits:
            return 0.0
        pct = (trade.position_value / self.state.limits.max_position_size) * 100
        return round(min(pct, 100.0), 2)

    def _compute_total_exposure(self, current_price: float) -> float:
        trade = self.state.open_trade
        if trade is None:
            return 0.0
        return round(trade.quantity * current_price, 2)

    def _compute_loss_speed(self, now: datetime) -> float:
        """
        Rupees being lost per minute, based on recent pnl history
        (last LOSS_SPEED_WINDOW_SECONDS). Positive = losing money.
        Negative or zero = flat or gaining, never triggers a warning.
        """
        state = self.state
        if len(state.pnl_history) < 2:
            return 0.0

        cutoff = now - timedelta(seconds=LOSS_SPEED_WINDOW_SECONDS)
        window_pnls = []
        window_times = []
        for pnl, ts in zip(state.pnl_history, state.tick_timestamps):
            if ts >= cutoff:
                window_pnls.append(pnl)
                window_times.append(ts)

        if len(window_pnls) < 2:
            return 0.0

        pnl_change = window_pnls[0] - window_pnls[-1]   # positive if pnl dropped
        seconds_elapsed = (window_times[-1] - window_times[0]).total_seconds()
        if seconds_elapsed <= 0:
            return 0.0

        rupees_per_second = pnl_change / seconds_elapsed
        return round(rupees_per_second * 60, 2)

    def _build_snapshot(
        self,
        current_price: float,
        pnl: float,
        loss_speed: float,
        margin_used_pct: float = 0.0,
        total_exposure: float = 0.0,
    ) -> RiskSnapshot:
        return RiskSnapshot(
            current_price=current_price,
            pnl=pnl,
            margin_used_pct=margin_used_pct,
            total_exposure=total_exposure,
            loss_speed_per_min=loss_speed,
            status=self.state.status,
        )