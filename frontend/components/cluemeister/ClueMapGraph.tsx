"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ReactFlow as ReactFlowBase,
  Background,
  Controls,
  Handle,
  Position,
  NodeProps,
  EdgeProps,
  getBezierPath,
  EdgeLabelRenderer,
  BaseEdge,
  ReactFlowProvider,
  Node,
  Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

// Type cast to work around a moduleResolution:"bundler" inference bug with @xyflow/react
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ReactFlow = ReactFlowBase as any;
import type {
  ClueMeisterClueMapNode,
  ClueMeisterClueMapEdge,
  ClueMeisterEvidenceSource,
} from "@/app/chat/page";

// ── Shared constants ──────────────────────────────────────────────────────────

export const TYPE_COLORS: Record<string, string> = {
  search_area: "#4ECDC4",
  person:      "#FF6B6B",
  location:    "#95E1D3",
  evidence:    "#FFE66D",
  event:       "#AA96DA",
  weather:     "#87CEEB",
  clue:        "#FFB6C1",
  unknown:     "#777777",
};

export const ROLE_COLORS: Record<string, string> = {
  incident:    "#AA96DA",
  subject:     "#FF6B6B",
  lkp:         "#95E1D3",
  search_area: "#4ECDC4",
  risk:        "#F38181",
  evidence:    "#FFE66D",
  history:     "#AA96DA",
  context:     "#87CEEB",
};

export const TYPE_LABEL: Record<string, string> = {
  search_area: "Search Area",
  person:      "Person",
  location:    "Location",
  evidence:    "Evidence",
  event:       "Event",
  weather:     "Weather",
  clue:        "Clue",
};

export const ROLE_LABEL: Record<string, string> = {
  incident: "Incident",
  subject: "Subject",
  lkp: "LKP",
  search_area: "Search Area",
  risk: "Risk",
  evidence: "Evidence",
  history: "History",
  context: "Context",
};

export const EDGE_COLORS: Record<string, string> = {
  predicted_at:            "#4ECDC4",
  corroborates:            "#95E1D3",
  similar_outcome:         "#AA96DA",
  historically_found_near: "#AA96DA",
  last_seen:               "#FFB6C1",
  affects:                 "#87CEEB",
  exacerbates:             "#F38181",
  evidence_of:             "#FFE66D",
  found_at:                "#FFE66D",
  associated_with:         "#FF6B6B",
  reported_at:             "#FF9A9A",
  has_risk:                "#F38181",
  supports_risk:           "#F38181",
  matched_by_profile:      "#AA96DA",
  involves:                "#95E1D3",
  reported:                "#FF9A9A",
  originates_from:         "#95E1D3",
  projects_to:             "#4ECDC4",
  includes:                "#87CEEB",
  conflicts_with:          "#F38181",
};

export const TIER_BORDER: Record<string, string> = {
  critical: "#FF4D5E",
  high: "#FFB000",
  medium: "#FFE66D",
  low: "rgba(255,255,255,0.34)",
  support: "rgba(255,255,255,0.22)",
};

// ── Node radius based on confidence + type ────────────────────────────────────

function nodeRadius(confidence: number, type: string): number {
  return Math.round((type === "search_area" ? 18 : 14) + confidence * 12);
}

function evidenceCount(node: ClueMeisterClueMapNode): number {
  return Math.max(1, node.sources?.length ?? 1);
}

function nodeSize(node: ClueMeisterClueMapNode): number {
  const r = nodeRadius(node.confidence, node.type);
  const priorityBoost = Math.min(10, Math.max(0, (node.priority_score ?? 0) - 45) / 8);
  return Math.round(r * 2 + Math.min(18, evidenceCount(node) * 3) + priorityBoost);
}

// ── Custom node component ─────────────────────────────────────────────────────

interface ClueNodeData extends ClueMeisterClueMapNode {
  onSelect: (id: string) => void;
  selected?: boolean;
}

function ClueNodeInner({ data }: NodeProps) {
  const nodeData = data as unknown as ClueNodeData;
  const role = nodeData.role ?? nodeData.type;
  const color = ROLE_COLORS[role] ?? TYPE_COLORS[nodeData.type] ?? TYPE_COLORS.unknown;
  const circleSize = Math.min(58, Math.max(42, nodeSize(nodeData) * 0.72));
  const shellWidth = 118;
  const tier = nodeData.decision_tier ?? nodeData.priority_tier ?? "support";
  const borderColor = TIER_BORDER[tier] ?? TIER_BORDER.low;
  const borderWidth = tier === "critical" ? 4 : tier === "high" ? 3 : tier === "medium" ? 2 : 1;
  const label = nodeData.display_label || nodeData.label;
  const glyph = role === "incident" ? "IC" :
    role === "subject" ? "S" :
    role === "lkp" ? "LKP" :
    role === "search_area" ? "SA" :
    role === "risk" ? "R" :
    role === "history" ? "H" :
    role === "evidence" ? "E" : "C";

  return (
    <div
      className="clue-map-node"
      style={{ width: shellWidth, height: 86, cursor: "pointer" }}
      onClick={(e) => {
        e.stopPropagation();
        nodeData.onSelect?.(nodeData.id);
      }}
    >
      <Handle id="target-left" type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: "none", top: 28 }} />
      <Handle id="source-left" type="source" position={Position.Left} style={{ opacity: 0, pointerEvents: "none", top: 28 }} />
      <Handle id="target-right" type="target" position={Position.Right} style={{ opacity: 0, pointerEvents: "none", top: 28 }} />
      <Handle id="source-right" type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: "none", top: 28 }} />
      <Handle id="target-top" type="target" position={Position.Top} style={{ opacity: 0, pointerEvents: "none", left: shellWidth / 2 }} />
      <Handle id="source-top" type="source" position={Position.Top} style={{ opacity: 0, pointerEvents: "none", left: shellWidth / 2 }} />
      <Handle id="target-bottom" type="target" position={Position.Bottom} style={{ opacity: 0, pointerEvents: "none", left: shellWidth / 2, top: 56 }} />
      <Handle id="source-bottom" type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: "none", left: shellWidth / 2, top: 56 }} />
      <div
        style={{
          width: shellWidth,
          height: 86,
          opacity: 0.9,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 5,
          boxSizing: "border-box",
          position: "relative",
        }}
      >
        <div
          style={{
            width: circleSize,
            height: circleSize,
            borderRadius: "50%",
            background: color,
            border: `${borderWidth}px solid ${borderColor}`,
            boxShadow: nodeData.selected ? `0 0 0 4px rgba(255,255,255,0.16), 0 0 18px ${borderColor}` : "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxSizing: "border-box",
            color: "#fff",
            fontSize: glyph.length > 2 ? 9 : 13,
            fontWeight: 800,
          }}
        >
          {glyph}
        </div>
        {nodeData.priority_rank && nodeData.priority_rank <= 3 ? (
          <span
            style={{
              position: "absolute",
              top: 3,
              right: 24,
              minWidth: 18,
              height: 18,
              borderRadius: 999,
              background: borderColor,
              color: "#111827",
              fontSize: 8,
              fontWeight: 700,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              border: "1px solid rgba(255,255,255,0.55)",
            }}
          >
            #{nodeData.priority_rank}
          </span>
        ) : null}
        <span
          style={{
            fontSize: 10,
            color: nodeData.selected ? "#F8FAFC" : "#CBD5E1",
            fontWeight: 650,
            textAlign: "center",
            lineHeight: 1.15,
            wordBreak: "break-word",
            maxWidth: shellWidth,
            minHeight: 24,
          }}
        >
          {label.length > 36 ? label.slice(0, 35) + "..." : label}
        </span>
      </div>
    </div>
  );
}

const nodeTypes = { clue: ClueNodeInner };

interface ClueEdgeData extends ClueMeisterClueMapEdge {
  dimmed?: boolean;
  highlighted?: boolean;
  mode?: "command" | "analyze";
}

// ── Custom edge component ─────────────────────────────────────────────────────

function ClueEdgeInner({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const edgeData = data as unknown as ClueEdgeData;
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
  });
  const color = EDGE_COLORS[edgeData?.type] ?? "#555";
  const label = edgeData?.display_label || (edgeData?.type ?? "").replace(/_/g, " ");
  const importance = edgeData?.importance ?? "context";
  const showLabel = edgeData?.mode === "analyze" || importance === "primary" || edgeData.highlighted;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: edgeData.highlighted ? 2.8 : importance === "primary" ? 1.8 : 1.15,
          strokeOpacity: edgeData.dimmed ? 0.16 : importance === "context" ? 0.35 : 0.72,
          strokeDasharray: importance === "context" ? "5 5" : undefined,
        }}
      />
      {showLabel ? (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              fontSize: 9,
              color: "#8a8aaa",
              opacity: edgeData.dimmed ? 0.25 : 1,
              pointerEvents: "none",
              whiteSpace: "nowrap",
              background: "rgba(20,20,30,0.75)",
              padding: "1px 4px",
              borderRadius: 3,
            }}
            className="nodrag nopan"
          >
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const edgeTypes = { clue: ClueEdgeInner };

function sourceAgent(source: string | ClueMeisterEvidenceSource): string {
  return typeof source === "string" ? source : source.agent || source.stream || "source";
}

function sourceExcerpt(source: string | ClueMeisterEvidenceSource): string {
  return typeof source === "string" ? "" : source.excerpt || "";
}

// ── SAR lane layout hook ─────────────────────────────────────────────────────

const COMMAND_LANES: Record<string, { x: number; order: number }> = {
  incident: { x: 0, order: 0 },
  subject: { x: 180, order: 1 },
  lkp: { x: 360, order: 2 },
  search_area: { x: 540, order: 3 },
  risk: { x: 720, order: 4 },
  evidence: { x: 900, order: 5 },
  history: { x: 900, order: 6 },
  context: { x: 900, order: 7 },
};

const ANALYZE_LANES: Record<string, { x: number; order: number }> = {
  incident: { x: 0, order: 0 },
  subject: { x: 170, order: 1 },
  lkp: { x: 340, order: 2 },
  search_area: { x: 510, order: 3 },
  risk: { x: 680, order: 4 },
  evidence: { x: 850, order: 5 },
  history: { x: 1020, order: 6 },
  context: { x: 1190, order: 7 },
};

function sortNode(a: ClueMeisterClueMapNode, b: ClueMeisterClueMapNode): number {
  const ar = a.priority_rank ?? a.rank ?? 999;
  const br = b.priority_rank ?? b.rank ?? 999;
  if (ar !== br) return ar - br;
  return (b.priority_score ?? 0) - (a.priority_score ?? 0);
}

function edgeHandles(
  source: { x: number; y: number } | undefined,
  target: { x: number; y: number } | undefined,
): { sourceHandle: string; targetHandle: string } {
  if (!source || !target) {
    return { sourceHandle: "source-right", targetHandle: "target-left" };
  }
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  if (Math.abs(dx) < 80 && Math.abs(dy) > 20) {
    return dy > 0
      ? { sourceHandle: "source-bottom", targetHandle: "target-top" }
      : { sourceHandle: "source-top", targetHandle: "target-bottom" };
  }
  return dx >= 0
    ? { sourceHandle: "source-right", targetHandle: "target-left" }
    : { sourceHandle: "source-left", targetHandle: "target-right" };
}

function useClueMapLayout(
  rawNodes: ClueMeisterClueMapNode[],
  rawEdges: ClueMeisterClueMapEdge[],
  onSelect: (id: string) => void,
  selectedId: string | null,
  mode: "command" | "analyze",
): { nodes: Node[]; edges: Edge[] } {
  const [layouted, setLayouted] = useState<{ nodes: Node[]; edges: Edge[] }>({
    nodes: [],
    edges: [],
  });

  useEffect(() => {
    let cancelled = false;
    if (rawNodes.length === 0) {
      setLayouted({ nodes: [], edges: [] });
      return;
    }

    const validNodeIds = new Set(rawNodes.map((n) => n.id));
    const validEdges = rawEdges.filter(
      (e) => validNodeIds.has(e.source) && validNodeIds.has(e.target),
    );

    const lanes = mode === "command" ? COMMAND_LANES : ANALYZE_LANES;
    const byLane = new Map<string, ClueMeisterClueMapNode[]>();
    rawNodes.forEach((node) => {
      const role = node.role ?? node.type ?? "context";
      const key = lanes[role] ? role : "context";
      byLane.set(key, [...(byLane.get(key) ?? []), node]);
    });
    byLane.forEach((items) => items.sort(sortNode));
    const positions = new Map<string, { x: number; y: number }>();
    Array.from(byLane.entries())
      .sort(([a], [b]) => (lanes[a]?.order ?? 99) - (lanes[b]?.order ?? 99))
      .forEach(([role, items]) => {
        const lane = lanes[role] ?? lanes.context;
        const step = mode === "command" ? 112 : 104;
        const startY = Math.max(0, 190 - ((items.length - 1) * step) / 2);
        items.forEach((node, index) => {
          positions.set(node.id, {
            x: lane.x,
            y: startY + index * step,
          });
        });
      });

    if (cancelled) return;
    setLayouted({
      nodes: rawNodes.map((n, index) => ({
        id: n.id,
        type: "clue",
        position: positions.get(n.id) ?? { x: index * 130, y: index * 52 },
        data: { ...n, onSelect, selected: selectedId === n.id },
        draggable: true,
      })),
      edges: validEdges.map((e, i) => {
        const handles = edgeHandles(positions.get(e.source), positions.get(e.target));
        return {
          id: e.id ?? `e-${i}-${e.source}-${e.target}`,
          source: e.source,
          target: e.target,
          sourceHandle: handles.sourceHandle,
          targetHandle: handles.targetHandle,
          type: "clue",
          data: { ...(e as unknown as Record<string, unknown>), mode },
          animated: false,
        };
      }),
    });
    return () => {
      cancelled = true;
    };
  }, [rawNodes, rawEdges, onSelect, selectedId, mode]);

  return layouted;
}

// ── Click details panel ───────────────────────────────────────────────────────

interface DetailsPanelProps {
  node: ClueMeisterClueMapNode | null;
  edges: ClueMeisterClueMapEdge[];
  allNodes: ClueMeisterClueMapNode[];
  onClose: () => void;
}

function NodeDetailsPanel({ node, edges, allNodes, onClose }: DetailsPanelProps) {
  if (!node) return null;
  const role = node.role ?? node.type;
  const color = ROLE_COLORS[role] ?? TYPE_COLORS[node.type] ?? TYPE_COLORS.unknown;
  const connections = edges.filter(
    (e) => e.source === node.id || e.target === node.id,
  );

  return (
    <div className="absolute right-3 top-3 bottom-3 z-20 w-[380px] max-w-[calc(100%-24px)] pointer-events-auto">
      <div className="bg-sar-panel border border-sar-border rounded text-xs shadow-lg h-full flex flex-col overflow-hidden">
        <div className="flex items-start gap-2 px-3 py-2 border-b border-sar-border">
          <span className="w-2 h-2 rounded-full flex-shrink-0 mt-1.5" style={{ background: color }} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sar-muted uppercase tracking-wide text-[10px] font-semibold">
                {ROLE_LABEL[role] ?? TYPE_LABEL[node.type] ?? role}
              </span>
              {(node.decision_tier ?? node.priority_tier) ? (
                <span className="text-[10px] uppercase tracking-wide text-sar-muted">
                  {node.decision_tier ?? node.priority_tier}
                </span>
              ) : null}
            </div>
            <p className="text-sar-text font-medium leading-snug mt-1">
              {node.detail_label || node.label}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-sar-muted hover:text-sar-text px-1 leading-none"
            aria-label="Close node details"
          >
            ×
          </button>
        </div>

        <div className="p-3 space-y-2 overflow-y-auto">
          <div className="grid grid-cols-2 gap-2 text-sar-muted">
            <p>
              Confidence: <span className="text-sar-text">{Math.round(node.confidence * 100)}%</span>
            </p>
            {typeof node.priority_score === "number" ? (
              <p>
                Priority: <span className="text-sar-text">{node.priority_score}</span>
              </p>
            ) : null}
            {node.priority_rank ? (
              <p>
                Rank: <span className="text-sar-text">#{node.priority_rank}</span>
              </p>
            ) : null}
            {node.geo ? (
              <p>
                Geo: <span className="text-sar-text">{node.geo.lat.toFixed(4)}, {node.geo.lon.toFixed(4)}</span>
              </p>
            ) : null}
          </div>
          {node.support_summary ? (
            <p className="text-sar-muted leading-snug border-t border-sar-border pt-2">
              Why it matters: <span className="text-sar-text">{node.support_summary}</span>
            </p>
          ) : null}
          {node.details && Object.entries(node.details).some(([, v]) => v) && (
            <div className="border-t border-sar-border pt-2 space-y-1.5">
              {Object.entries(node.details)
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <div key={k} className="grid grid-cols-[105px_1fr] gap-2 min-w-0">
                    <span className="text-sar-muted">{k}:</span>
                    <span className="text-sar-text whitespace-normal break-words leading-snug">{String(v)}</span>
                  </div>
                ))}
            </div>
          )}
          {node.sources?.length > 0 && (
            <div className="border-t border-sar-border pt-2 space-y-1">
              <p className="text-sar-muted text-[10px] uppercase tracking-wide font-semibold">
                Sources ({node.sources.length})
              </p>
              {node.sources.map((source, i) => (
                <div key={i} className="text-sar-muted text-[10px] leading-snug">
                  <p>
                    <span className="text-sar-text">{sourceAgent(source)}</span>
                    {typeof source !== "string" && source.field_path ? (
                      <span className="opacity-60"> · {source.field_path}</span>
                    ) : null}
                  </p>
                  {sourceExcerpt(source) ? (
                    <p className="whitespace-normal break-words opacity-80">{sourceExcerpt(source)}</p>
                  ) : null}
                </div>
              ))}
            </div>
          )}
          {connections.length > 0 && (
            <div className="border-t border-sar-border pt-2 space-y-1">
              <p className="text-sar-muted text-[10px] uppercase tracking-wide font-semibold">
                Connections ({connections.length})
              </p>
              {connections.map((e, i) => {
                const otherId = e.source === node.id ? e.target : e.source;
                const other = allNodes.find((n) => n.id === otherId);
                const dir = e.source === node.id ? "→" : "←";
                return other ? (
                  <div key={i} className="text-sar-muted text-[10px] leading-snug">
                    <p>
                      {dir} <span className="text-sar-text">{other.display_label || other.label}</span>
                      <span className="opacity-60"> · {e.display_label || e.type.replace(/_/g, " ")}</span>
                      {e.importance ? <span className="opacity-60"> · {e.importance}</span> : null}
                    </p>
                    {e.reason ? (
                      <p className="whitespace-normal break-words opacity-80">Why related: {e.reason}</p>
                    ) : null}
                  </div>
                ) : null;
              })}
            </div>
          )}
          <p className="border-t border-sar-border pt-2 text-[10px] text-sar-muted break-all">
            Node ID: <span className="font-mono">{node.id}</span>
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Main graph (inner — needs ReactFlowProvider context) ──────────────────────

interface GraphInnerProps {
  nodes: ClueMeisterClueMapNode[];
  edges: ClueMeisterClueMapEdge[];
  mode?: "command" | "analyze";
}

function GraphInner({ nodes: rawNodes, edges: rawEdges, mode = "command" }: GraphInnerProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
    },
    [],
  );
  const selectedNode = rawNodes.find((node) => node.id === selectedId) ?? null;

  const { nodes, edges } = useClueMapLayout(rawNodes, rawEdges, handleSelect, selectedId, mode);

  if (rawNodes.length === 0) {
    return (
      <p className="text-sar-muted text-xs px-4 py-3">
        No graph data available for this session.
      </p>
    );
  }

  return (
    <div className="relative w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={3}
        onPaneClick={() => setSelectedId(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2a2a3a" gap={20} size={1} />
        <Controls
          className="[&>button]:bg-sar-panel [&>button]:border-sar-border [&>button]:text-sar-text"
          showInteractive={false}
        />
      </ReactFlow>
      <NodeDetailsPanel
        node={selectedNode}
        edges={rawEdges}
        allNodes={rawNodes}
        onClose={() => setSelectedId(null)}
      />
    </div>
  );
}

// ── Public export ─────────────────────────────────────────────────────────────

export default function ClueMapGraph({ nodes, edges, mode = "command" }: GraphInnerProps) {
  return (
    <ReactFlowProvider>
      <GraphInner nodes={nodes} edges={edges} mode={mode} />
    </ReactFlowProvider>
  );
}
