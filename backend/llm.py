"""
llm.py — LLM API calls for GuardRail.

Using Groq (free tier, OpenAI-compatible SDK, very fast inference —
important for a live demo where we don't want judges waiting on API calls).
Model: llama-3.3-70b-versatile (good quality, free, fast).

ARCHITECTURAL NOTE:
This file is ONLY ever called AFTER engine.py has already made a decision
(hard stop happened, session ended). The LLM does not decide anything —
it only explains a decision in plain English. If this file failed entirely,
GuardRail would still correctly protect the trader; the alerts would just
show a fallback plain-text message instead of AI-generated coaching text.
That fallback is built in below, so a demo never breaks because of an
API hiccup.
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 300

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not found. Add it to backend/.env"
            )
        _client = Groq(api_key=api_key)
    return _client


def _call_llm(prompt: str, fallback: str) -> str:
    """
    Shared call wrapper. Always returns usable text — falls back to a
    plain hardcoded message if the API call fails for any reason
    (no key, network issue, rate limit), so a demo never breaks.
    """
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content.strip()
        return text if text else fallback
    except Exception as e:
        print(f"[llm.py] LLM call failed, using fallback. Error: {e}")
        return fallback


# ---------------------------------------------------------------------------
# Feature 5: Square-Off explanation
# ---------------------------------------------------------------------------

def explain_square_off(daily_loss_limit: float, total_loss: float, warnings_count: int) -> str:
    prompt = (
        f"You are a friendly trading coach speaking to a beginner. The trader just had "
        f"their position automatically closed because they hit their daily loss limit of "
        f"₹{daily_loss_limit:.0f}. Their total loss today was ₹{abs(total_loss):.0f}. "
        f"They had {warnings_count} warnings before this happened. Explain what happened "
        f"in 2-3 plain sentences. No jargon. Be kind but honest."
    )
    fallback = (
        f"Your position was automatically closed after your loss reached ₹{abs(total_loss):.0f}, "
        f"past your ₹{daily_loss_limit:.0f} daily limit. This limit exists to protect you from "
        f"bigger losses on a tough day. Take a break and come back with a clear head next session."
    )
    return _call_llm(prompt, fallback)


# ---------------------------------------------------------------------------
# Feature 7: Daily Report Card paragraph
# ---------------------------------------------------------------------------

def generate_report_card(summary: dict) -> str:
    """
    summary is the dict returned by engine.end_session(), shaped like:
        {
          "total_trades": int,
          "total_pnl": float,
          "early_warnings_ignored": int,
          "cool_off_breaches": int,
          "hard_stop_triggered": bool,
          "revenge_trades": int,
          "discipline_score": int,
        }
    """
    pnl = summary["total_pnl"]
    pnl_label = "profit" if pnl >= 0 else "loss"

    prompt = (
        "You are a friendly trading coach giving end-of-day feedback to a beginner trader. "
        "Here is their session summary:\n"
        f"- Total trades placed: {summary['total_trades']}\n"
        f"- Total P&L: ₹{abs(pnl):.0f} ({pnl_label})\n"
        f"- Early warnings received: {summary['early_warnings_ignored']}, "
        f"ignored: {summary['early_warnings_ignored']}\n"
        f"- Cool-off pauses triggered: {summary['cool_off_breaches']}\n"
        f"- Hard stop triggered: {'yes' if summary['hard_stop_triggered'] else 'no'}\n"
        f"- Revenge trades flagged: {summary['revenge_trades']}\n"
        f"- Discipline score: {summary['discipline_score']}/100\n\n"
        "Write a 3-4 sentence plain-English summary of their session. Be encouraging even "
        "if the score is low. Always end with one specific actionable tip for their next "
        "session. No jargon. Talk like a human coach, not a machine."
    )
    fallback = (
        f"You ended today with a discipline score of {summary['discipline_score']}/100. "
        f"You had {summary['cool_off_breaches']} cool-off pause(s) and "
        f"{summary['revenge_trades']} bigger-than-usual trade(s) after a loss. "
        f"Every session is a chance to build better habits — for next time, try setting a "
        f"tighter cool-off rule so you step away sooner after a tough trade."
    )
    return _call_llm(prompt, fallback)