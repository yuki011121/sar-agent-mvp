"use client";

import { useState } from "react";
import type { ClueMeisterClueMapNode, ClueMeisterClueMapEdge } from "@/app/chat/page";
import ClueMapGraph, { TYPE_COLORS, TYPE_LABEL } from "./ClueMapGraph";

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
          {/* React Flow needs an explicit height */}
          <div className="h-[420px]">
            <ClueMapGraph nodes={nodes} edges={edges} />
          </div>
          {nodes.length <= 1 && (
            <div className="px-4 py-2 border-t border-sar-border text-[11px] text-sar-muted">
              Limited session graph: ClueMeister only found {nodes.length} structured node
              {nodes.length === 1 ? "" : "s"} and {edges.length} edge{edges.length === 1 ? "" : "s"}.
              Check whether the specialist agents returned session-scoped payloads.
            </div>
          )}

          {/* Legend */}
          <div className="flex flex-wrap gap-x-3 gap-y-1 px-4 pb-2 pt-1 border-t border-sar-border">
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
      )}
    </div>
  );
}
