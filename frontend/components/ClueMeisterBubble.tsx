"use client";

import type { ClueMeisterResult } from "@/app/chat/page";
import BriefSection from "./cluemeister/BriefSection";
import ClueMapSection from "./cluemeister/ClueMapSection";
import VerificationSection from "./cluemeister/VerificationSection";

interface Props {
  data: ClueMeisterResult;
}

export default function ClueMeisterBubble({ data }: Props) {
  const { status, brief, verification } = data;

  if (status === "unavailable") {
    return (
      <div className="rounded-lg border border-sar-border bg-sar-panel px-4 py-3 text-sar-muted text-sm">
        ClueMeister verification engine is unavailable.
      </div>
    );
  }

  if (status === "no_data") {
    return (
      <div className="rounded-lg border border-sar-border bg-sar-panel px-4 py-3 text-sar-muted text-sm">
        No buffered agent outputs found for this session.
      </div>
    );
  }

  const hasBrief       = brief && (brief.headline || brief.top_search_areas.length > 0 || brief.llm_summary);
  const hasVerification = verification && (verification.claims.length > 0 || verification.summary.total_claims > 0);

  return (
    <div className="rounded-lg border border-sar-border bg-sar-panel overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-sar-border flex items-center gap-2">
        <span className="font-semibold text-sar-text text-sm">ClueMeister Analysis</span>
        {brief?.confidence != null && brief.confidence > 0 && (
          <>
            <span className="text-sar-muted text-xs">·</span>
            <span className="text-sar-muted text-xs">
              {Math.round(brief.confidence * 100)}% search area confidence
            </span>
          </>
        )}
      </div>

      {/* Layer 1 — Brief (primary view) */}
      {hasBrief ? (
        <BriefSection brief={brief!} />
      ) : (
        <div className="px-4 py-3 space-y-1">
          <p className="text-sar-muted text-sm">
            {status === "no_claims"
              ? "No verifiable claims found in agent responses."
              : "Not enough cross-agent data to generate a search brief."}
          </p>
          <p className="text-sar-muted text-xs">
            Tip: describe the subject profile, last known location, and timeline in your messages,
            then run the analysis again after the agents have responded.
          </p>
        </div>
      )}

      {/* Layer 2 — Clue Map graph (collapsed by default) */}
      {data.clue_map && (data.clue_map.nodes.length > 0 || data.clue_map.edges.length > 0) && (
        <ClueMapSection nodes={data.clue_map.nodes} edges={data.clue_map.edges} />
      )}

      {/* Layer 3 — Verification (collapsed by default) */}
      {hasVerification && (
        <VerificationSection
          summary={verification!.summary}
          claims={verification!.claims}
        />
      )}
    </div>
  );
}
