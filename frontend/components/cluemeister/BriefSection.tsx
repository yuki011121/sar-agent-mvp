"use client";

import type { ClueMeisterBrief } from "@/app/chat/page";

const PRIORITY_STYLES: Record<string, string> = {
  CRITICAL: "border-red-500 bg-red-950/40 text-red-300",
  HIGH:     "border-orange-500 bg-orange-950/30 text-orange-300",
  MEDIUM:   "border-yellow-600 bg-yellow-950/30 text-yellow-300",
  LOW:      "border-sar-border bg-sar-panel text-sar-muted",
  UNKNOWN:  "border-sar-border bg-sar-panel text-sar-muted",
};

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? "bg-green-500" : pct >= 45 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-sar-border overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-sar-muted font-mono w-8 text-right">{pct}%</span>
    </div>
  );
}

interface Props {
  brief: ClueMeisterBrief;
}

export default function BriefSection({ brief }: Props) {
  const hasAreas     = brief.top_search_areas.length > 0;
  const hasConflicts = brief.urgent_conflicts.length > 0;

  return (
    <div className="space-y-3 px-4 py-3">
      {/* Headline + confidence */}
      {brief.headline && (
        <div className="space-y-1.5">
          <p className="text-sar-text font-semibold text-sm leading-snug">
            {brief.headline}
          </p>
          <ConfidenceBar value={brief.confidence} />
        </div>
      )}

      {/* Blocking conflicts — shown before areas */}
      {hasConflicts && (
        <div className="space-y-1.5">
          {brief.urgent_conflicts.map((c, i) => (
            <div
              key={i}
              className={`rounded border px-3 py-2 text-xs leading-relaxed ${
                c.blocking
                  ? "border-red-500 bg-red-950/50 text-red-300"
                  : "border-yellow-600 bg-yellow-950/30 text-yellow-300"
              }`}
            >
              <span className="font-semibold mr-1">
                {c.blocking ? "⛔ BLOCKING:" : "⚠ CONFLICT:"}
              </span>
              {c.description}
              {c.agent && (
                <span className="ml-1 text-yellow-500/70">({c.agent})</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Top search areas */}
      {hasAreas && (
        <div className="space-y-2">
          <p className="text-xs text-sar-muted uppercase tracking-wide font-semibold">
            Top Search Areas
          </p>
          <div className="space-y-1.5">
            {brief.top_search_areas.map((area, i) => {
              const style = PRIORITY_STYLES[area.priority] ?? PRIORITY_STYLES.UNKNOWN;
              return (
                <div key={i} className={`rounded border px-3 py-2 ${style}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-sm">{area.name}</span>
                    <span className="text-xs font-semibold opacity-80 uppercase">
                      {area.priority}
                    </span>
                  </div>
                  {area.rationale && (
                    <p className="text-xs opacity-70 mt-0.5 leading-relaxed">
                      {area.rationale}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* LLM summary bullets */}
      {brief.llm_summary && (
        <div className="text-xs text-sar-muted leading-relaxed border-t border-sar-border pt-3 whitespace-pre-line">
          {brief.llm_summary}
        </div>
      )}
    </div>
  );
}
