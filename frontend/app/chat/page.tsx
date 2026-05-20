"use client";

import { useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import ChatWindow from "@/components/ChatWindow";
import InputBar from "@/components/InputBar";
import AgentStatusBar from "@/components/AgentStatusBar";

export type MessageRole = "user" | "assistant" | "system";

export interface AttachedFile {
  file: File;
  preview?: string; // data URL for images
}

export interface ClueMeisterClaim {
  claim_id: string;
  agent: string;
  claim_type: string;
  subject_type: string;
  predicted_value: string;
  stated_confidence: number;
  decision: { tier: string; final_confidence: number; recommendation: string; evidence_summary: string };
  contradiction: { has_contradiction: boolean; explanation: string };
  grounding: { is_grounded: boolean; kg_probability: number | null; hop_type: string; sample_count: number };
}

export interface ClueMeisterSearchArea {
  name: string;
  priority: string;
  rationale: string;
  confidence: number;
}

export interface ClueMeisterConflict {
  type: string;
  description: string;
  agent?: string;
  blocking: boolean;
}

export interface ClueMeisterBrief {
  headline: string;
  confidence: number;
  top_search_areas: ClueMeisterSearchArea[];
  urgent_conflicts: ClueMeisterConflict[];
  llm_summary: string;
  debug?: Record<string, unknown>;
}

export interface ClueMeisterEvidenceSource {
  agent: string;
  stream: string;
  session_id?: string;
  turn_id?: string;
  field_path?: string;
  excerpt?: string;
  timestamp?: string;
}

export interface ClueMeisterClueMapNode {
  id: string;
  type: string;
  label: string;
  canonical_key?: string;
  confidence: number;
  sources: Array<string | ClueMeisterEvidenceSource>;
  agent?: string;
  details?: Record<string, string | number | boolean | null>;
  created_at?: string;
  updated_at?: string;
}

export interface ClueMeisterClueMapEdge {
  source: string;
  target: string;
  type: string;
  confidence: number;
  sources?: Array<string | ClueMeisterEvidenceSource>;
  details?: Record<string, string | number | boolean | null>;
}

export interface ClueMeisterResult {
  session_id: string;
  status: string;
  // Layer 1 — incident commander brief
  brief?: ClueMeisterBrief;
  // Layer 2 — graph data
  clue_map?: { nodes: ClueMeisterClueMapNode[]; edges: ClueMeisterClueMapEdge[] };
  // Layer 3 — per-claim ISRID verification
  verification?: {
    summary: {
      total_claims: number;
      tier_distribution: Record<string, number>;
      agents_analyzed: string[];
      grounding_rate?: number;
    };
    claims: ClueMeisterClaim[];
  };
}

export interface PathPoint {
  lat: number;
  lon: number;
  endpoint_probability: number;
  visit_density: number;
  rank: number;
}

export interface PathData {
  lkp: { lat: number; lon: number } | null;
  probability_points: PathPoint[];
  person_class?: string;
  person_profile?: string;
  search_radius_km?: { p25: number; p50: number; p75: number; p95: number };
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  agents?: string[]; // which agents contributed
  streaming?: boolean;
  isClueMeister?: boolean;
  clueMeisterData?: ClueMeisterResult;
  pathData?: PathData;
}

const SESSION_KEY = "sar_session_id";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Welcome to **SAR Command Center**. I can help with search and rescue operations — ask about weather conditions, medical risks, historical cases, or upload photos and documents for analysis.",
    },
  ]);
  const [sessionId, setSessionId] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [hasAgentResponse, setHasAgentResponse] = useState(false);
  const [isClueMeisterLoading, setIsClueMeisterLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(SESSION_KEY) || uuidv4();
    setSessionId(stored);
    localStorage.setItem(SESSION_KEY, stored);
  }, []);

  const handleNewSession = () => {
    const newId = uuidv4();
    setSessionId(newId);
    setMessages([
      {
        id: "welcome-new",
        role: "assistant",
        content: "New session started. How can I assist with your SAR operation?",
      },
    ]);
  };

  const handleSend = async (text: string, files: AttachedFile[]) => {
    if (!text.trim() && files.length === 0) return;

    // Add user message
    const userMsg: ChatMessage = {
      id: uuidv4(),
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);

    // Placeholder assistant message (streaming)
    const assistantId = uuidv4();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      streaming: true,
      agents: [],
    };
    setMessages((prev) => [...prev, assistantMsg]);
    setIsStreaming(true);

    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

    try {
      const formData = new FormData();
      formData.append("message", text || "(files attached)");
      formData.append("session_id", sessionId);
      for (const af of files) {
        formData.append("files", af.file);
      }

      abortRef.current = new AbortController();
      const res = await fetch(`${apiBase}/chat`, {
        method: "POST",
        body: formData,
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }

      const contentType = res.headers.get("content-type") || "";

      if (contentType.includes("text/event-stream")) {
        // ── SSE streaming path ────────────────────────────────────────────
        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalContent = "";
        let agentsContributed: string[] = [];
        let pendingPathData: PathData | null = null;
        // SSE state: track current event type across lines
        let currentEvent = "message";
        let currentDataLines: string[] = [];

        const processSSEMessage = (eventType: string, dataLines: string[]) => {
          const data = dataLines.join("\n").trim();
          if (!data || data === "[DONE]") return;

          if (eventType === "agent_start") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, agents: [...(m.agents ?? []), data] }
                  : m
              )
            );
          } else if (eventType === "agent_result") {
            setHasAgentResponse(true);
            const match = data.match(/^\*\*(.+?)\*\*/);
            if (match) agentsContributed.push(match[1]);
          } else if (eventType === "path_data") {
            try {
              pendingPathData = JSON.parse(data) as PathData;
            } catch {
              // ignore malformed path_data
            }
          } else if (eventType === "final") {
            finalContent = data;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: finalContent,
                      streaming: false,
                      agents: agentsContributed,
                      ...(pendingPathData ? { pathData: pendingPathData } : {}),
                    }
                  : m
              )
            );
          } else if (eventType === "done") {
            if (data && data !== sessionId) {
              setSessionId(data);
            }
          } else if (eventType === "error") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: `Error: ${data}`, streaming: false }
                  : m
              )
            );
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              currentDataLines.push(line.slice(5).trimStart());
            } else if (line === "") {
              // Empty line = end of SSE message, dispatch it
              if (currentDataLines.length > 0) {
                processSSEMessage(currentEvent, currentDataLines);
              }
              currentEvent = "message";
              currentDataLines = [];
            }
            // ignore comment lines (":") and other prefixes
          }
        }

        // If no final event was received (e.g. empty stream), show fallback
        if (!finalContent) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: "No response received from agents. Make sure the backend services are running.", streaming: false }
                : m
            )
          );
        }
      } else {
        // ── Non-streaming JSON fallback ───────────────────────────────────
        const json = await res.json();
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: json.response || "No response", streaming: false }
              : m
          )
        );
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") return;
      const msg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: `Connection error: ${msg}`, streaming: false }
            : m
        )
      );
    } finally {
      setIsStreaming(false);
    }
  };

  const handleClueMeisterAnalysis = async () => {
    if (!sessionId || isClueMeisterLoading) return;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
    const loadingId = uuidv4();

    setIsClueMeisterLoading(true);
    setMessages((prev) => [
      ...prev,
      {
        id: loadingId,
        role: "assistant",
        content: "Analyzing…",
        isClueMeister: true,
        streaming: true,
      },
    ]);

    try {
      const res = await fetch(`${apiBase}/clue-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(json.detail || "ClueMeister request failed");
      }
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingId
            ? {
                ...m,
                content: "",
                streaming: false,
                clueMeisterData: json.result ?? null,
              }
            : m
        )
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingId
            ? { ...m, content: `ClueMeister error: ${msg}`, streaming: false }
            : m
        )
      );
    } finally {
      setIsClueMeisterLoading(false);
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setMessages((prev) =>
      prev.map((m) => (m.streaming ? { ...m, streaming: false } : m))
    );
  };

  return (
    <div className="flex flex-col h-screen bg-sar-dark">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-sar-border bg-sar-panel shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🔍</span>
          <div>
            <h1 className="font-bold text-sar-text text-lg leading-tight">SAR Command Center</h1>
            <p className="text-sar-muted text-xs">Search & Rescue AI Assistant</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <AgentStatusBar />
          {hasAgentResponse && !isStreaming && (
            <button
              onClick={handleClueMeisterAnalysis}
              disabled={isClueMeisterLoading}
              className="text-xs px-3 py-1.5 rounded border border-sar-orange text-sar-orange hover:bg-sar-orange/20 disabled:opacity-50 disabled:cursor-wait transition-colors"
            >
              {isClueMeisterLoading ? "Analyzing…" : "Run ClueMeister Analysis"}
            </button>
          )}
          <button
            onClick={handleNewSession}
            className="text-xs px-3 py-1.5 rounded border border-sar-border text-sar-muted hover:text-sar-text hover:border-sar-orange transition-colors"
          >
            New Session
          </button>
          <span className="text-xs text-sar-muted font-mono hidden sm:block">
            {sessionId.slice(0, 8)}
          </span>
        </div>
      </header>

      {/* Chat area */}
      <main className="flex-1 overflow-hidden">
        <ChatWindow messages={messages} isStreaming={isStreaming} />
      </main>

      {/* Input */}
      <footer className="shrink-0 border-t border-sar-border bg-sar-panel">
        <InputBar onSend={handleSend} onStop={handleStop} isStreaming={isStreaming} />
      </footer>
    </div>
  );
}
