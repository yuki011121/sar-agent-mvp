"use client";

import dynamic from "next/dynamic";
import type { PathData } from "@/app/chat/page";

// Leaflet must be loaded client-side only (no SSR)
const PathMapInner = dynamic(() => import("./PathMapInner"), { ssr: false });

interface Props {
  data: PathData;
}

export default function PathMapBubble({ data }: Props) {
  if (!data.probability_points?.length) return null;

  const profile = [data.person_class, data.person_profile].filter(Boolean).join(" · ");
  const r = data.search_radius_km;
  const radiusLabel = r ? `p50 ${r.p50} km · p95 ${r.p95} km` : null;

  return (
    <div className="rounded-lg border border-sar-border bg-sar-panel overflow-hidden mt-2">
      <div className="px-4 py-2 border-b border-sar-border flex items-center gap-3">
        <span className="text-sar-orange text-sm font-semibold">Probability Heatmap</span>
        {profile && (
          <span className="text-sar-muted text-xs">{profile}</span>
        )}
        {radiusLabel && (
          <span className="text-sar-muted text-xs ml-auto">{radiusLabel}</span>
        )}
      </div>
      <PathMapInner data={data} />
    </div>
  );
}
