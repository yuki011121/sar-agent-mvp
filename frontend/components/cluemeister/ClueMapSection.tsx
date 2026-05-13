"use client";

import { useState, useMemo } from "react";
import type { ClueMeisterClueMapNode, ClueMeisterClueMapEdge } from "@/app/chat/page";

const TYPE_COLORS: Record<string, string> = {
  clue:     "#FFE66D",
  person:   "#FF6B6B",
  location: "#4ECDC4",
  event:    "#95E1D3",
  area:     "#F38181",
  resource: "#AA96DA",
  weather:  "#87CEEB",
  time:     "#C7CEEA",
  object:   "#FFB6C1",
  terrain:  "#98D8C8",
  unknown:  "#777777",
};

const TYPE_LABEL: Record<string, string> = {
  clue: "Clue", person: "Person", location: "Location", event: "Event",
  area: "Area", resource: "Resource", weather: "Weather", time: "Time",
  object: "Object", terrain: "Terrain",
};

interface GraphProps {
  nodes: ClueMeisterClueMapNode[];
  edges: ClueMeisterClueMapEdge[];
}

function ClueMapGraph({ nodes, edges }: GraphProps) {
  const [hovered, setHovered] = useState<string | null>(null);

  const W = 640;
  const H = 400;
  const CX = W / 2;
  const CY = H / 2;

  // Circular layout — radius scales with node count
  const positions = useMemo(() => {
    const pos: Record<string, { x: number; y: number }> = {};
    const n = nodes.length;
    if (n === 0) return pos;
    if (n === 1) {
      pos[nodes[0].id] = { x: CX, y: CY };
      return pos;
    }
    const r = Math.min(CX - 60, CY - 50, 40 + n * 12);
    nodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i) / n - Math.PI / 2;
      pos[node.id] = {
        x: CX + r * Math.cos(angle),
        y: CY + r * Math.sin(angle),
      };
    });
    return pos;
  }, [nodes]);

  // IDs directly connected to hovered node
  const connectedIds = useMemo(() => {
    if (!hovered) return new Set<string>();
    const ids = new Set<string>();
    edges.forEach((e) => {
      if (e.source === hovered) ids.add(e.target);
      if (e.target === hovered) ids.add(e.source);
    });
    return ids;
  }, [hovered, edges]);

  if (nodes.length === 0) {
    return (
      <p className="text-sar-muted text-xs px-4 py-3">
        No graph data above the confidence threshold.
      </p>
    );
  }

  const [hoveredNode] = nodes.filter((n) => n.id === hovered);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ background: "transparent" }}
      >
        {/* Edges */}
        {edges.map((edge, i) => {
          const src = positions[edge.source];
          const tgt = positions[edge.target];
          if (!src || !tgt) return null;
          const active = hovered && (edge.source === hovered || edge.target === hovered);
          const dimmed = hovered && !active;
          return (
            <line
              key={i}
              x1={src.x} y1={src.y}
              x2={tgt.x} y2={tgt.y}
              stroke={active ? "#f97316" : "#555"}
              strokeWidth={active ? 1.5 : 0.8}
              strokeOpacity={dimmed ? 0.15 : 0.7}
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((node) => {
          const pos = positions[node.id];
          if (!pos) return null;
          const r = 5 + node.confidence * 9;
          const color = TYPE_COLORS[node.type] ?? TYPE_COLORS.unknown;
          const isHovered = hovered === node.id;
          const isConnected = connectedIds.has(node.id);
          const dimmed = hovered && !isHovered && !isConnected;

          return (
            <g
              key={node.id}
              transform={`translate(${pos.x},${pos.y})`}
              onMouseEnter={() => setHovered(node.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: "pointer" }}
            >
              <circle
                r={r}
                fill={color}
                fillOpacity={dimmed ? 0.15 : 0.85}
                stroke={isHovered ? "white" : "transparent"}
                strokeWidth={2}
              />
              <text
                y={r + 11}
                textAnchor="middle"
                fontSize={9}
                fill={dimmed ? "#444" : "#bbb"}
                style={{ userSelect: "none", pointerEvents: "none" }}
              >
                {node.label.length > 18 ? node.label.slice(0, 17) + "…" : node.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Hover tooltip */}
      {hoveredNode && (
        <div className="absolute top-2 right-2 bg-sar-panel border border-sar-border rounded p-2 text-xs max-w-[200px] space-y-0.5 pointer-events-none">
          <div className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full flex-shrink-0"
              style={{ background: TYPE_COLORS[hoveredNode.type] ?? TYPE_COLORS.unknown }}
            />
            <span className="text-sar-muted uppercase tracking-wide text-[10px]">
              {TYPE_LABEL[hoveredNode.type] ?? hoveredNode.type}
            </span>
          </div>
          <p className="text-sar-text font-medium">{hoveredNode.label}</p>
          <p className="text-sar-muted">
            Confidence: {Math.round(hoveredNode.confidence * 100)}%
          </p>
          {hoveredNode.sources?.length > 0 && (
            <p className="text-sar-muted">
              Source: {hoveredNode.sources.join(", ")}
            </p>
          )}
          <p className="text-sar-muted">
            Connections: {connectedIds.size}
          </p>
        </div>
      )}

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 px-4 pb-2">
        {Array.from(new Set(nodes.map((n) => n.type))).map((type) => (
          <span key={type} className="flex items-center gap-1 text-[10px] text-sar-muted">
            <span
              className="w-2 h-2 rounded-full"
              style={{ background: TYPE_COLORS[type] ?? TYPE_COLORS.unknown }}
            />
            {TYPE_LABEL[type] ?? type}
          </span>
        ))}
      </div>
    </div>
  );
}

interface Props {
  nodes: ClueMeisterClueMapNode[];
  edges: ClueMeisterClueMapEdge[];
}

export default function ClueMapSection({ nodes, edges }: Props) {
  const [open, setOpen] = useState(false);

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
        </span>
        <span>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-sar-border">
          <ClueMapGraph nodes={nodes} edges={edges} />
        </div>
      )}
    </div>
  );
}
