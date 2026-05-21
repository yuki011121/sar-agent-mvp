"use client";

import { useState } from "react";
import type {
  ClueMeisterClueMapNode,
  ClueMeisterClueMapEdge,
  ClueMeisterClueMapView,
} from "@/app/chat/page";
import ClueMapGraph, { ROLE_COLORS, ROLE_LABEL, TIER_BORDER, TYPE_COLORS, TYPE_LABEL } from "./ClueMapGraph";

interface Props {
  nodes: ClueMeisterClueMapNode[];
  edges: ClueMeisterClueMapEdge[];
  views?: {
    command?: ClueMeisterClueMapView;
    analyze?: ClueMeisterClueMapView;
  };
  debug?: Record<string, unknown>;
}

type ViewMode = "command" | "analyze";

function edgeKey(edge: ClueMeisterClueMapEdge, index: number): string {
  return edge.id ?? `${edge.source}-${edge.target}-${edge.type}-${index}`;
}

export default function ClueMapSection({ nodes, edges, views, debug }: Props) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<ViewMode>("command");
  const historyShape = (debug?.payload_shapes as Record<string, { warning?: string }> | undefined)?.history;
  const topPriority = nodes
    .filter((node) => typeof node.priority_score === "number")
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))[0];
  const activeView = mode === "command" ? views?.command : views?.analyze;
  const nodeIds = activeView ? new Set(activeView.node_ids) : null;
  const edgeIds = activeView ? new Set(activeView.edge_ids) : null;
  const visibleNodes = nodeIds ? nodes.filter((node) => nodeIds.has(node.id)) : nodes;
  const visibleNodeIds = new Set(visibleNodes.map((node) => node.id));
  const visibleEdges = edges.filter((edge, index) => {
    if (!visibleNodeIds.has(edge.source) || !visibleNodeIds.has(edge.target)) return false;
    if (edgeIds) return edgeIds.has(edgeKey(edge, index));
    return mode === "analyze" || edge.show_in_command !== false;
  });
  const hiddenNodes = activeView?.hidden_counts.nodes ?? Math.max(0, nodes.length - visibleNodes.length);
  const hiddenEdges = activeView?.hidden_counts.edges ?? Math.max(0, edges.length - visibleEdges.length);
  const modeLabel = mode === "command" ? "Command" : "Analyze";

  return (
    <div className="border-t border-sar-border">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs text-sar-muted hover:text-sar-text transition-colors"
      >
        <span className="flex items-center gap-2">
          <span className="font-semibold uppercase tracking-wide">Clue Map</span>
          <span>·</span>
          <span>{nodes.length} nodes</span>
          <span>·</span>
          <span>{edges.length} edges</span>
          {topPriority ? (
            <>
              <span>·</span>
              <span>top #{topPriority.rank}: {topPriority.priority_tier}</span>
            </>
          ) : null}
          {views ? (
            <>
              <span>·</span>
              <span>{modeLabel}: {visibleNodes.length} shown · {hiddenNodes} hidden</span>
            </>
          ) : null}
        </span>
        <span>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-sar-border">
          <div className="flex items-center justify-between gap-3 px-4 py-2 border-b border-sar-border">
            <div className="inline-flex rounded border border-sar-border overflow-hidden">
              {(["command", "analyze"] as const).map((viewMode) => (
                <button
                  key={viewMode}
                  type="button"
                  onClick={() => setMode(viewMode)}
                  className={`px-3 py-1 text-[11px] uppercase tracking-wide transition-colors ${
                    mode === viewMode
                      ? "bg-sar-orange/20 text-sar-text"
                      : "text-sar-muted hover:text-sar-text"
                  }`}
                >
                  {viewMode === "command" ? "Command" : "Analyze"}
                </button>
              ))}
            </div>
            <span className="text-[11px] text-sar-muted">
              {modeLabel} view: {visibleNodes.length} shown · {hiddenNodes} nodes hidden · {hiddenEdges} edges hidden
            </span>
          </div>
          {/* React Flow needs an explicit height */}
          <div className="h-[420px]">
            <ClueMapGraph nodes={visibleNodes} edges={visibleEdges} mode={mode} />
          </div>
          {visibleNodes.length <= 1 && (
            <div className="px-4 py-2 border-t border-sar-border text-[11px] text-sar-muted">
              Limited session graph: ClueMeister only found {visibleNodes.length} structured node
              {visibleNodes.length === 1 ? "" : "s"} and {visibleEdges.length} edge{visibleEdges.length === 1 ? "" : "s"} in this view.
              Check whether the specialist agents returned session-scoped payloads.
            </div>
          )}
          {historyShape?.warning && (
            <div className="px-4 py-2 border-t border-sar-border text-[11px] text-sar-muted">
              History note: {historyShape.warning}.
            </div>
          )}

          {/* Legend */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 pb-2 pt-1 border-t border-sar-border">
            <span className="text-[10px] uppercase tracking-wide text-sar-muted">Role</span>
            {Array.from(new Set(visibleNodes.map((n) => n.role ?? n.type))).map((role) => (
              <span key={role} className="flex items-center gap-1 text-[10px] text-sar-muted">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ background: ROLE_COLORS[role] ?? TYPE_COLORS[role] ?? TYPE_COLORS.unknown }}
                />
                {ROLE_LABEL[role] ?? TYPE_LABEL[role] ?? role}
              </span>
            ))}
            <span className="text-[10px] uppercase tracking-wide text-sar-muted">Priority</span>
            {["critical", "high", "medium", "low", "support"].map((tier) => (
              <span key={tier} className="flex items-center gap-1 text-[10px] text-sar-muted">
                <span
                  className="w-2 h-2 rounded-full border"
                  style={{ borderColor: TIER_BORDER[tier], background: "transparent" }}
                />
                {tier}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
