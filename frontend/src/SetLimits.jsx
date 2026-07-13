// SetLimits.jsx — Feature 1: the form for the trader's 3 limits.
// This is pure UI + a callback; no risk logic lives here.

import { useState } from "react";

export default function SetLimits({ onStart }) {
  const [maxDailyLoss, setMaxDailyLoss] = useState(500);
  const [maxPositionSize, setMaxPositionSize] = useState(5000);
  const [maxMarginUsagePct, setMaxMarginUsagePct] = useState(80);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch("http://localhost:8000/api/session/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          max_daily_loss: Number(maxDailyLoss),
          max_position_size: Number(maxPositionSize),
          max_margin_usage_pct: Number(maxMarginUsagePct),
          quantity: 10,
          entry_price: 19800,
        }),
      });
      if (!res.ok) {
        const detail = await res.json();
        throw new Error(detail.detail || "Failed to start session");
      }
      const data = await res.json();
      onStart(data.session_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md mx-auto mt-16 p-6 border rounded">
      <h1 className="text-xl font-bold mb-4">GuardRail — Set Your Limits</h1>

      <label className="block mb-2">
        Max Daily Loss (₹)
        <input
          type="number"
          className="w-full border p-2 mt-1"
          value={maxDailyLoss}
          onChange={(e) => setMaxDailyLoss(e.target.value)}
        />
      </label>

      <label className="block mb-2">
        Max Single Position Size (₹)
        <input
          type="number"
          className="w-full border p-2 mt-1"
          value={maxPositionSize}
          onChange={(e) => setMaxPositionSize(e.target.value)}
        />
      </label>

      <label className="block mb-4">
        Max Margin Usage (%)
        <input
          type="number"
          className="w-full border p-2 mt-1"
          value={maxMarginUsagePct}
          onChange={(e) => setMaxMarginUsagePct(e.target.value)}
        />
      </label>

      {error && <p className="text-red-600 mb-2">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="w-full bg-blue-600 text-white py-2 rounded disabled:opacity-50"
      >
        {loading ? "Starting..." : "Start Session"}
      </button>
    </div>
  );
}