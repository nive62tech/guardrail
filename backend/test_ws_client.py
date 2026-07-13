import asyncio
import websockets
import json
import sys

async def main(session_id: str):
    uri = f"ws://localhost:8000/ws/{session_id}"
    async with websockets.connect(uri) as ws:
        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)

                if "error" in data:
                    print(f"SERVER ERROR: {data['error']}")
                    break

                if "snapshot" in data:
                    print(f"pnl={data['snapshot']['pnl']} status={data['snapshot']['status']}")
                    for alert in data.get("alerts", []):
                        print(f"  ALERT [{alert['type']}]: {alert['message']}")

                if "report_card" in data:
                    print("\n=== REPORT CARD ===")
                    print(json.dumps(data["report_card"], indent=2))
                    break

            except websockets.exceptions.ConnectionClosed:
                print("Connection closed.")
                break

if __name__ == "__main__":
    session_id = sys.argv[1]
    asyncio.run(main(session_id))