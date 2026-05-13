"use client";

import { useState } from "react";
import type { ClueMeisterClaim } from "@/app/chat/page";

interface VerificationSummary {
  total_claims: number;
  tier_distribution: Record<string, number>;
  agents_analyzed: string[];
  grounding_rate?: number;
}

interface Props {
  summary: VerificationSummary;
  claims: ClueMeisterClaim[];
}

// Tier → visual style (P5: unverified=grey, conflict=orange-red, reject=red)
const TIER_STYLES: Record<string, string> = {
  accept:     "bg-green-900/40 text-green-300 border-green-700",
  flag:       "bg-yellow-900/40 text-yellow-300 border-yellow-700",
  candidate:  "bg-blue-900/40 text-blue-300 border-blue-700",
  conflict:   "bg-orange-900/50 text-orange-300 border-orange-600",
  reject:     "bg-red-900/40 text-red-300 border-red-700",
  unverified: "bg-zinc-800/60 text-zinc-400 border-zinc-600",
  unknown:    "bg-sar-border text-sar-muted border-sar-border",
};

function TierBadge({ tier }: { tier: string }) {
  const style = TIER_STYLES[tier.toLowerCase()] ?? TIER_STYLES.unknown;
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded border uppercase ${style}`}>
      {tier}
    </span>
  );
}

export default function VerificationSection({ summary, claims }: Props) {
  const [open, setOpen]           = useState(false);
  const [hideUnverified, setHideUnverified] = useState(true);

  const tierDist       = summary.tier_distribution ?? {};
  const agents         = summary.agents_analyzed ?? [];
  const groundingRate  = summary.grounding_rate;

  const visibleClaims = claims.filter((c) => {
    const tier = c.decision?.tier?.toLowerCase() ?? "";
    if (hideUnverified && tier === "unverified") return false;
    return true;
  });

  return (
    <div className="border-t border-sar-border">
      {/* Collapsible toggle */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs text-sar-muted hover:text-sar-text transition-colors"
      >
        <span className="flex items-center gap-2">
          <span className="font-semibold uppercase tracking-wide">ISRID Verification</span>
          <span>·</span>
          <span>{summary.total_claims ?? 0} claims</span>
          {agents.length > 0 && (
            <>
              <span>·</span>
              <span>{agents.join(", ")}</span>
            </>
          )}
          {groundingRate != null && (
            <>
              <span>·</span>
              <span>{Math.round(groundingRate * 100)}% grounded</span>
            </>
          )}
        </span>
        <span>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div>
          {/* Tier summary badges */}
          {Object.keys(tierDist).length > 0 && (
            <div className="px-4 py-2 border-t border-sar-border flex flex-wrap gap-2">
              {Object.entries(tierDist).map(([tier, count]) => (
                <span key={tier} className="flex items-center gap-1">
                  <TierBadge tier={tier} />
                  <span className="text-sar-muted text-xs">×{count}</span>
                </span>
              ))}
            </div>
          )}

          {/* Filter controls */}
          <div className="px-4 py-2 border-t border-sar-border flex gap-4 text-xs text-sar-muted">
            <label className="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={hideUnverified}
                onChange={(e) => setHideUnverified(e.target.checked)}
                className="accent-sar-accent"
              />
              Hide unverified
            </label>
          </div>

          {/* Claims list */}
          <div className="divide-y divide-sar-border border-t border-sar-border">
            {visibleClaims.length === 0 ? (
              <p className="px-4 py-3 text-xs text-sar-muted">No claims to display.</p>
            ) : (
              visibleClaims.map((claim) => (
                <div key={claim.claim_id} className="px-4 py-3 space-y-1.5">
                  {/* Row 1: agent · prediction → tier */}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-sar-muted font-mono">{claim.agent}</span>
                    <span className="text-sar-muted text-xs">·</span>
                    <span className="text-sar-text text-sm">
                      {claim.claim_type}:{" "}
                      <span className="font-medium">{claim.predicted_value}</span>
                    </span>
                    <span className="ml-auto">
                      <TierBadge tier={claim.decision?.tier ?? "unknown"} />
                    </span>
                  </div>

                  {/* Row 2: evidence summary */}
                  {claim.decision?.evidence_summary && (
                    <p className="text-xs text-sar-muted leading-relaxed">
                      {claim.decision.evidence_summary}
                    </p>
                  )}

                  {/* Row 3: ISRID probability + sample count */}
                  {claim.grounding?.is_grounded && (
                    <div className="flex gap-3 text-xs text-sar-muted">
                      {claim.grounding.kg_probability != null && (
                        <span>
                          ISRID prob:{" "}
                          <span className="text-sar-text font-mono">
                            {(claim.grounding.kg_probability * 100).toFixed(1)}%
                          </span>
                        </span>
                      )}
                      {claim.grounding.sample_count > 0 && (
                        <span>
                          n={" "}
                          <span className="text-sar-text font-mono">
                            {claim.grounding.sample_count.toLocaleString()}
                          </span>
                        </span>
                      )}
                    </div>
                  )}

                  {/* Row 4: contradiction / conflict warning */}
                  {claim.contradiction?.has_contradiction && (
                    <div className="text-xs text-yellow-400 flex items-start gap-1">
                      <span>⚠</span>
                      <span>{claim.contradiction.explanation}</span>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
