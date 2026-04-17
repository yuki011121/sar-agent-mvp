"use client";

import { useEffect, useState } from "react";

interface AgentState {
  name: string;
  label: string;
  active: boolean;
  lastSeen?: number; // ms timestamp
}

const AGENT_LABELS: Record<string, string> = {
  photo: "Photo",
  interview: "Interview",
  health: "Health",
  weather: "Weather",
  history: "History",
  cluemeister: "ClueMeister",
  command: "Command",
};

export default function AgentStatusBar() {
  const [agents, setAgents] = useState<AgentState[]>(
    Object.entries(AGENT_LABELS).map(([name, label]) => ({
      name,
      label,
      active: false,
    }))
  );
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const wsUrl = (process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8080") + "/ws";
    let ws: WebSocket;
    let pingInterval: ReturnType<typeof setInterval>;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setConnected(true);
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 20000);
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.event === "agent_update" && msg.agent) {
            const now = Date.now();
            setAgents((prev) =>
              prev.map((a) =>
                a.name === msg.agent ? { ...a, active: true, lastSeen: now } : a
              )
            );
            // Dim after 8 seconds of no activity
            setTimeout(() => {
              setAgents((prev) =>
                prev.map((a) =>
                  a.name === msg.agent && a.lastSeen === now
                    ? { ...a, active: false }
                    : a
                )
              );
            }, 8000);
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        setConnected(false);
        clearInterval(pingInterval);
        // Reconnect after 5 seconds
        reconnectTimeout = setTimeout(connect, 5000);
      };

      ws.onerror = () => ws.close();
    };

    connect();
    return () => {
      clearInterval(pingInterval);
      clearTimeout(reconnectTimeout);
      ws?.close();
    };
  }, []);

  const activeAgents = agents.filter((a) => a.active);

  return (
    <div className="flex items-center gap-2">
      {/* Connection dot */}
      <span
        className={`w-2 h-2 rounded-full ${connected ? "bg-green-400" : "bg-red-500"}`}
        title={connected ? "Connected to backend" : "Disconnected"}
      />

      {/* Active agent pills */}
      {activeAgents.length > 0 ? (
        <div className="flex gap-1">
          {activeAgents.map((a) => (
            <span
              key={a.name}
              className="text-xs px-2 py-0.5 rounded-full bg-sar-orange/20 text-sar-orange border border-sar-orange/30 animate-pulse"
            >
              {a.label}
            </span>
          ))}
        </div>
      ) : (
        <span className="text-xs text-sar-muted hidden sm:block">Agents idle</span>
      )}
    </div>
  );
}
