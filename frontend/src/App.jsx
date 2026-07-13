// App.jsx — main layout + WebSocket connection.
// Holds session state and passes data down as props to TradePanel/Sidebar.
// No risk logic here — purely wiring UI to what the backend sends.

import { useState, useRef } from "react";
import SetLimits from "./SetLimits";
import TradePanel from "./TradePanel";
import Sidebar from "./Sidebar";

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [snapshot, setSnapshot] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [reportCard, setReportCard] = useState(null);
  const wsRef = useRef(null);

  const handleStart = (id) => {
    setSessionId(id);

    const ws = new WebSocket(`ws://localhost:8000/ws/${id}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.snapshot) {
        setSnapshot(data.snapshot);
      }
      if (data.alerts && data.alerts.length > 0) {
        setAlerts((prev) => [...prev, ...data.alerts]);
      }
      if (data.report_card) {
        setReportCard(data.report_card);
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };
  };

  if (!sessionId) {
    return <SetLimits onStart={handleStart} />;
  }

  const handleEndSession = async () => {
    const res = await fetch(`http://localhost:8000/api/session/${sessionId}/end`, {
      method: "POST",
    });
    const data = await res.json();
    setReportCard(data);
    if (wsRef.current) wsRef.current.close();
  };

  return (
    <div className="flex">
      <TradePanel snapshot={snapshot} onEndSession={handleEndSession} />
      <Sidebar alerts={alerts} reportCard={reportCard} />
    </div>
  );
}