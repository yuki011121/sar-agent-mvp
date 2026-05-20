"use client";

import { useEffect, useState, useCallback } from "react";
import {
  ReactFlow as ReactFlowBase,
  Background,
  Controls,
  MiniMap,
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
import ELK from "elkjs/lib/elk.bundled.js";
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

export const TYPE_LABEL: Record<string, string> = {
  search_area: "Search Area",
  person:      "Person",
  location:    "Location",
  evidence:    "Evidence",
  event:       "Event",
  weather:     "Weather",
  clue:        "Clue",
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
  includes:                "#87CEEB",
  conflicts_with:          "#F38181",
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
  return Math.round(r * 2 + Math.min(18, evidenceCount(node) * 3));
}

// ── Custom node component ─────────────────────────────────────────────────────

interface ClueNodeData extends ClueMeisterClueMapNode {
  onHover: (id: string | null, x: number, y: number) => void;
}

function ClueNodeInner({ data }: NodeProps) {
  const nodeData = data as unknown as ClueNodeData;
  const r = nodeSize(nodeData) / 2;
  const color = TYPE_COLORS[nodeData.type] ?? TYPE_COLORS.unknown;
  const size = r * 2;

  return (
    <div
      style={{ width: size, height: size }}
      onMouseEnter={(e) => nodeData.onHover?.(nodeData.id, e.clientX, e.clientY)}
      onMouseLeave={() => nodeData.onHover?.(null, 0, 0)}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0, pointerEvents: "none" }} />
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, pointerEvents: "none" }} />
      <div
        style={{
          width: size,
          height: size,
          borderRadius: "50%",
          background: color,
          opacity: 0.88,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxSizing: "border-box",
        }}
      >
        <span
          style={{
            fontSize: Math.max(7, r * 0.32) + "px",
            color: "#fff",
            fontWeight: 500,
            textAlign: "center",
            padding: "2px 4px",
            lineHeight: 1.2,
            wordBreak: "break-word",
            maxWidth: size - 8,
          }}
        >
          {nodeData.label.length > 22
            ? nodeData.label.slice(0, 21) + "…"
            : nodeData.label}
        </span>
      </div>
    </div>
  );
}

const nodeTypes = { clue: ClueNodeInner };

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
  const edgeData = data as unknown as ClueMeisterClueMapEdge;
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
  });
  const color = EDGE_COLORS[edgeData?.type] ?? "#555";
  const label = (edgeData?.type ?? "").replace(/_/g, " ");

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{ stroke: color, strokeWidth: 1.5, strokeOpacity: 0.7 }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            fontSize: 9,
            color: "#8a8aaa",
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
    </>
  );
}

const edgeTypes = { clue: ClueEdgeInner };

function sourceAgent(source: string | ClueMeisterEvidenceSource): string {
  return typeof source === "string" ? source : source.agent || source.stream || "source";
}

// ── ELK layout hook ───────────────────────────────────────────────────────────

const elk = new ELK();

function useClueMapLayout(
  rawNodes: ClueMeisterClueMapNode[],
  rawEdges: ClueMeisterClueMapEdge[],
  onHover: (id: string | null, x: number, y: number) => void,
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

    const run = async () => {
      const graph = {
        id: "cluemeister",
        layoutOptions: {
          "elk.algorithm": "layered",
          "elk.direction": "RIGHT",
          "elk.spacing.nodeNode": "56",
          "elk.layered.spacing.nodeNodeBetweenLayers": "80",
          "elk.edgeRouting": "SPLINES",
        },
        children: rawNodes.map((n) => {
          const size = nodeSize(n) + 18;
          return { id: n.id, width: size, height: size };
        }),
        edges: validEdges.map((e, i) => ({
          id: `elk-${i}-${e.source}-${e.target}`,
          sources: [e.source],
          targets: [e.target],
        })),
      };

      try {
        const result = await elk.layout(graph);
        if (cancelled) return;
        const positions = new Map(
          (result.children ?? []).map((n) => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]),
        );
        setLayouted({
          nodes: rawNodes.map((n, index) => {
            const pos = positions.get(n.id) ?? { x: index * 90, y: index * 40 };
            return {
              id: n.id,
              type: "clue",
              position: pos,
              data: { ...n, onHover },
              draggable: true,
            };
          }),
          edges: validEdges.map((e, i) => ({
            id: `e-${i}-${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            type: "clue",
            data: e as unknown as Record<string, unknown>,
            animated: e.confidence > 0.75,
          })),
        });
      } catch {
        if (cancelled) return;
        setLayouted({
          nodes: rawNodes.map((n, index) => ({
            id: n.id,
            type: "clue",
            position: {
              x: Math.cos(index * 1.7) * 160 + 220,
              y: Math.sin(index * 1.7) * 120 + 160,
            },
            data: { ...n, onHover },
            draggable: true,
          })),
          edges: validEdges.map((e, i) => ({
            id: `e-${i}-${e.source}-${e.target}`,
            source: e.source,
            target: e.target,
            type: "clue",
            data: e as unknown as Record<string, unknown>,
            animated: e.confidence > 0.75,
          })),
        });
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [rawNodes, rawEdges, onHover]);

  return layouted;
}

// ── Hover tooltip ─────────────────────────────────────────────────────────────

interface TooltipProps {
  node: ClueMeisterClueMapNode | null;
  x: number;
  y: number;
  edges: ClueMeisterClueMapEdge[];
  allNodes: ClueMeisterClueMapNode[];
}

function NodeTooltip({ node, x, y, edges, allNodes }: TooltipProps) {
  if (!node) return null;
  const color = TYPE_COLORS[node.type] ?? TYPE_COLORS.unknown;
  const connections = edges.filter(
    (e) => e.source === node.id || e.target === node.id,
  );

  return (
    <div
      style={{
        position: "fixed",
        left: x + 14,
        top: y - 8,
        zIndex: 9999,
        pointerEvents: "none",
        maxWidth: 240,
      }}
    >
      <div className="bg-sar-panel border border-sar-border rounded p-2.5 text-xs space-y-1 shadow-lg">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
          <span className="text-sar-muted uppercase tracking-wide text-[10px] font-semibold">
            {TYPE_LABEL[node.type] ?? node.type}
          </span>
        </div>
        <p className="text-sar-text font-medium leading-snug">{node.label}</p>
        <p className="text-sar-muted">
          Confidence:{" "}
          <span className="text-sar-text">{Math.round(node.confidence * 100)}%</span>
        </p>
        {node.details && Object.entries(node.details).some(([, v]) => v) && (
          <div className="border-t border-sar-border pt-1 space-y-0.5">
            {Object.entries(node.details)
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <div key={k} className="flex justify-between gap-2 min-w-0">
                  <span className="text-sar-muted shrink-0">{k}:</span>
                  <span className="text-sar-text text-right truncate">{String(v)}</span>
                </div>
              ))}
          </div>
        )}
        {node.sources?.length > 0 && (
          <div className="border-t border-sar-border pt-1 space-y-0.5">
            <p className="text-sar-muted text-[10px] uppercase tracking-wide font-semibold">
              Sources ({node.sources.length})
            </p>
            {node.sources.slice(0, 4).map((source, i) => (
              <p key={i} className="text-sar-muted text-[10px] truncate">
                <span className="text-sar-text">{sourceAgent(source)}</span>
                {typeof source !== "string" && source.field_path ? (
                  <span className="opacity-60"> · {source.field_path}</span>
                ) : null}
              </p>
            ))}
          </div>
        )}
        {connections.length > 0 && (
          <div className="border-t border-sar-border pt-1 space-y-0.5">
            <p className="text-sar-muted text-[10px] uppercase tracking-wide font-semibold">
              Connections ({connections.length})
            </p>
            {connections.slice(0, 4).map((e, i) => {
              const otherId = e.source === node.id ? e.target : e.source;
              const other = allNodes.find((n) => n.id === otherId);
              const dir = e.source === node.id ? "→" : "←";
              return other ? (
                <p key={i} className="text-sar-muted text-[10px] truncate">
                  {dir} <span className="text-sar-text">{other.label}</span>
                  <span className="opacity-60"> · {e.type.replace(/_/g, " ")}</span>
                </p>
              ) : null;
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main graph (inner — needs ReactFlowProvider context) ──────────────────────

interface GraphInnerProps {
  nodes: ClueMeisterClueMapNode[];
  edges: ClueMeisterClueMapEdge[];
}

function GraphInner({ nodes: rawNodes, edges: rawEdges }: GraphInnerProps) {
  const [hovered, setHovered] = useState<{
    node: ClueMeisterClueMapNode | null;
    x: number;
    y: number;
  }>({ node: null, x: 0, y: 0 });

  const handleHover = useCallback(
    (id: string | null, x: number, y: number) => {
      if (!id) {
        setHovered({ node: null, x: 0, y: 0 });
      } else {
        const node = rawNodes.find((n) => n.id === id) ?? null;
        setHovered({ node, x, y });
      }
    },
    [rawNodes],
  );

  const { nodes, edges } = useClueMapLayout(rawNodes, rawEdges, handleHover);

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
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#2a2a3a" gap={20} size={1} />
        <Controls
          className="[&>button]:bg-sar-panel [&>button]:border-sar-border [&>button]:text-sar-text"
          showInteractive={false}
        />
        <MiniMap
          nodeColor={(n) => {
            const t = (n.data as unknown as ClueMeisterClueMapNode)?.type ?? "unknown";
            return TYPE_COLORS[t] ?? TYPE_COLORS.unknown;
          }}
          style={{ background: "#1a1a2e" }}
          maskColor="rgba(0,0,0,0.4)"
        />
      </ReactFlow>
      <NodeTooltip
        node={hovered.node}
        x={hovered.x}
        y={hovered.y}
        edges={rawEdges}
        allNodes={rawNodes}
      />
    </div>
  );
}

// ── Public export ─────────────────────────────────────────────────────────────

export default function ClueMapGraph({ nodes, edges }: GraphInnerProps) {
  return (
    <ReactFlowProvider>
      <GraphInner nodes={nodes} edges={edges} />
    </ReactFlowProvider>
  );
}
