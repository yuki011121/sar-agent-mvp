"use client";

import { useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, Marker, Tooltip, useMap } from "react-leaflet";
import type { PathData } from "@/app/chat/page";
import "leaflet/dist/leaflet.css";
import L from "leaflet";

// Fix default marker icon broken by webpack
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// Orange LKP icon
const lkpIcon = L.divIcon({
  className: "",
  html: `<div style="width:14px;height:14px;background:#f97316;border:2px solid #fff;border-radius:50%;box-shadow:0 0 6px rgba(249,115,22,0.8)"></div>`,
  iconSize: [14, 14],
  iconAnchor: [7, 7],
});

function interpolateColor(prob: number, maxProb: number): string {
  // High probability → orange (#f97316), low → yellow (#fde047)
  const t = maxProb > 0 ? prob / maxProb : 0;
  const r = Math.round(253 + (249 - 253) * t);
  const g = Math.round(224 + (115 - 224) * t);
  const b = Math.round(71 + (22 - 71) * t);
  return `rgb(${r},${g},${b})`;
}

function FitBounds({ data }: { data: PathData }) {
  const map = useMap();
  useEffect(() => {
    const pts = data.probability_points.map((p) => [p.lat, p.lon] as [number, number]);
    if (data.lkp) pts.push([data.lkp.lat, data.lkp.lon]);
    if (pts.length) {
      map.fitBounds(L.latLngBounds(pts), { padding: [24, 24] });
    }
  }, [map, data]);
  return null;
}

interface Props {
  data: PathData;
}

export default function PathMapInner({ data }: Props) {
  const { lkp, probability_points } = data;
  const center: [number, number] = lkp
    ? [lkp.lat, lkp.lon]
    : [probability_points[0].lat, probability_points[0].lon];

  const maxProb = Math.max(...probability_points.map((p) => p.endpoint_probability));

  return (
    <MapContainer
      center={center}
      zoom={13}
      style={{ height: 340, width: "100%" }}
      zoomControl={true}
      scrollWheelZoom={false}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds data={data} />

      {/* Probability points as scaled circles */}
      {probability_points.map((pt) => {
        const radius = 6 + pt.endpoint_probability / maxProb * 18;
        const opacity = 0.3 + pt.endpoint_probability / maxProb * 0.55;
        const color = interpolateColor(pt.endpoint_probability, maxProb);
        return (
          <CircleMarker
            key={pt.rank}
            center={[pt.lat, pt.lon]}
            radius={radius}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: opacity,
              weight: 0,
            }}
          >
            <Tooltip>
              <div className="text-xs">
                <div className="font-semibold">Rank #{pt.rank}</div>
                <div>Endpoint prob: {(pt.endpoint_probability * 100).toFixed(1)}%</div>
                <div>Visit density: {(pt.visit_density * 100).toFixed(1)}%</div>
              </div>
            </Tooltip>
          </CircleMarker>
        );
      })}

      {/* LKP marker */}
      {lkp && (
        <Marker position={[lkp.lat, lkp.lon]} icon={lkpIcon}>
          <Tooltip permanent direction="top" offset={[0, -10]}>
            <span className="text-xs font-semibold">LKP</span>
          </Tooltip>
        </Marker>
      )}
    </MapContainer>
  );
}
