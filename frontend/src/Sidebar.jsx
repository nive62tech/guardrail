// Sidebar.jsx — mock alert sidebar.
// NOTE FOR TEAMMATE: this is a placeholder. Replace freely with the real
// design. It only receives `alerts` as a prop and displays them — no
// logic lives here, so swapping this file never touches the backend.

const COLORS = {
  early_warning: "bg-yellow-100 border-yellow-500 text-yellow-800",
  cool_off: "bg-blue-100 border-blue-500 text-blue-800",
  square_off: "bg-red-100 border-red-500 text-red-800",
  revenge_trade: "bg-orange-100 border-orange-500 text-orange-800",
  report_card: "bg-green-100 border-green-500 text-green-800",
};

const ICONS = {
  early_warning: "🟡",
  cool_off: "🔵",
  square_off: "🔴",
  revenge_trade: "🟠",
  report_card: "🟢",
};

export default function Sidebar({ alerts, reportCard }) {
  return (
    <div className="w-96 border-l p-4 h-screen overflow-y-auto">
      <h2 className="font-bold mb-3">Alerts</h2>

      {alerts.length === 0 && !reportCard && (
        <p className="text-gray-400 text-sm">No alerts yet.</p>
      )}

      <div className="space-y-3">
        {alerts.map((alert, i) => (
          <div
            key={i}
            className={`border-l-4 p-3 rounded ${COLORS[alert.type] || "bg-gray-100"}`}
          >
            <div className="text-sm font-semibold mb-1">
              {ICONS[alert.type]} {alert.type.replace("_", " ")}
            </div>
            <div className="text-sm">{alert.message}</div>
          </div>
        ))}

        {reportCard && (
          <div className="border-l-4 p-3 rounded bg-green-100 border-green-500 text-green-800">
            <div className="text-sm font-semibold mb-1">
              🟢 Discipline Score: {reportCard.score}/100
            </div>
            <div className="text-sm">{reportCard.message}</div>
          </div>
        )}
      </div>
    </div>
  );
}