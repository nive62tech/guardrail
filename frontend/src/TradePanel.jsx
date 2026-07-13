// TradePanel.jsx — mock trading screen.
// NOTE FOR TEAMMATE: this is a placeholder. Replace freely with the real
// design. It only receives `snapshot` as a prop and displays it — no
// logic lives here, so swapping this file never touches the backend.

export default function TradePanel({ snapshot, onEndSession }) {
  if (!snapshot) {
    return <div className="flex-1 p-6">Waiting for data...</div>;
  }

  const pnlColor = snapshot.pnl >= 0 ? "text-green-600" : "text-red-600";

  return (
    <div className="flex-1 p-6">
      <h2 className="font-bold text-lg mb-4">Live Paper Trade — NIFTY50</h2>

      <div className="grid grid-cols-2 gap-4 max-w-md">
        <div className="border p-4 rounded">
          <div className="text-sm text-gray-500">Current Price</div>
          <div className="text-xl font-semibold">₹{snapshot.current_price}</div>
        </div>

        <div className="border p-4 rounded">
          <div className="text-sm text-gray-500">P&amp;L</div>
          <div className={`text-xl font-semibold ${pnlColor}`}>₹{snapshot.pnl}</div>
        </div>

        <div className="border p-4 rounded">
          <div className="text-sm text-gray-500">Margin Used</div>
          <div className="text-xl font-semibold">{snapshot.margin_used_pct}%</div>
        </div>

        <div className="border p-4 rounded">
          <div className="text-sm text-gray-500">Exposure</div>
          <div className="text-xl font-semibold">₹{snapshot.total_exposure}</div>
        </div>
      </div>

      <div className="mt-4">
        <span className="text-sm text-gray-500">Session status: </span>
        <span className="font-semibold uppercase">{snapshot.status}</span>
      </div>

      {snapshot.status === "active" && (
        <button
          onClick={onEndSession}
          className="mt-4 bg-gray-700 text-white px-4 py-2 rounded"
        >
          End Session
        </button>
      )}

      {snapshot.status === "active" && (
        <button
          onClick={onEndSession}
          className="mt-4 bg-gray-700 text-white px-4 py-2 rounded"
        >
          End Session
        </button>
      )}
    </div>
  );
}