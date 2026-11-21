import React, { useMemo, useState } from 'react';

export interface SchematicPoint {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  isOffice?: boolean;
  clusterIndex?: number;
  clusterLabel?: string;
  priority?: number;
  status?: 'pending' | 'visited' | 'skipped';
}

export interface SchematicCentroid {
  clusterIndex: number;
  clusterLabel: string;
  centroidLat: number;
  centroidLng: number;
}

interface SchematicMapProps {
  points: SchematicPoint[];
  centroids?: SchematicCentroid[];
  routeOrderIds?: string[];
  height?: number;
  title?: string;
  showClusterLinks?: boolean;
}

const CLUSTER_COLORS = [
  '#2563EB',
  '#0D9488',
  '#D97706',
  '#7C3AED',
  '#DB2777',
  '#16A34A',
  '#EA580C',
  '#4F46E5',
];

function approxKmPerDegLat(): number {
  return 111.32;
}

export const SchematicMap: React.FC<SchematicMapProps> = ({
  points,
  centroids = [],
  routeOrderIds = [],
  height = 420,
  title = 'Schematic Coordinate Plot',
  showClusterLinks = false,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const width = 760;
  const padLeft = 64;
  const padRight = 32;
  const padTop = 30;
  const padBottom = 46;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const projection = useMemo(() => {
    const allLats = [
      ...points.map((p) => p.latitude),
      ...centroids.map((c) => c.centroidLat),
    ];
    const allLngs = [
      ...points.map((p) => p.longitude),
      ...centroids.map((c) => c.centroidLng),
    ];

    if (allLats.length === 0) {
      return null;
    }

    let minLat = Math.min(...allLats);
    let maxLat = Math.max(...allLats);
    let minLng = Math.min(...allLngs);
    let maxLng = Math.max(...allLngs);

    const meanLatRad = (((minLat + maxLat) / 2) * Math.PI) / 180;
    const cosLat = Math.max(0.2, Math.cos(meanLatRad));

    const rawLatSpan = Math.max(0.01, maxLat - minLat);
    const rawLngSpan = Math.max(0.01, maxLng - minLng);
    minLat -= rawLatSpan * 0.14;
    maxLat += rawLatSpan * 0.14;
    minLng -= rawLngSpan * 0.14;
    maxLng += rawLngSpan * 0.14;

    const latSpan = maxLat - minLat;
    const lngSpanScaled = (maxLng - minLng) * cosLat;

    const scale = Math.min(plotW / lngSpanScaled, plotH / latSpan);
    const usedW = lngSpanScaled * scale;
    const usedH = latSpan * scale;
    const offsetX = padLeft + (plotW - usedW) / 2;
    const offsetY = padTop + (plotH - usedH) / 2;

    const toXY = (lat: number, lng: number) => ({
      x: offsetX + (lng - minLng) * cosLat * scale,
      y: offsetY + (maxLat - lat) * scale,
    });

    const kmPerPixel = approxKmPerDegLat() / scale;
    const targetKm = kmPerPixel * 100;
    const niceSteps = [0.5, 1, 2, 5, 10, 20, 50, 100, 250];
    const scaleKm = niceSteps.find((s) => s >= targetKm * 0.6) ?? Math.round(targetKm);
    const scaleBarPx = scaleKm / kmPerPixel;

    return {
      minLat,
      maxLat,
      minLng,
      maxLng,
      toXY,
      scaleKm,
      scaleBarPx: Math.min(150, Math.max(36, scaleBarPx)),
    };
  }, [points, centroids, plotW, plotH]);

  const pointMap = useMemo(() => new Map(points.map((p) => [p.id, p])), [points]);

  if (!projection || points.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <span className="text-xs text-slate-500">Locally generated SVG · No external map API</span>
        </div>
        <div className="flex h-64 items-center justify-center text-sm text-slate-500">
          Add an office or distributor coordinates to view the schematic coordinate plot.
        </div>
      </div>
    );
  }

  const routeCoords = routeOrderIds
    .map((id, orderIdx) => {
      const pt = pointMap.get(id);
      if (!pt) return null;
      return { pt, orderIdx, ...projection.toXY(pt.latitude, pt.longitude) };
    })
    .filter((v): v is NonNullable<typeof v> => v !== null);

  const hoveredPoint = hoveredId ? pointMap.get(hoveredId) : null;
  const gridSteps = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <p className="text-xs text-slate-500">
            Schematic coordinate visualization from stored latitude/longitude · Not a street map or road navigation display
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rotate-45 border border-slate-900 bg-slate-900" />
            Office / Base
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full border border-blue-700 bg-blue-600" />
            Distributor
          </span>
          {centroids.length > 0 && (
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm border-2 border-slate-700 bg-white" />
              Cluster Centroid
            </span>
          )}
        </div>
      </div>

      <div className="relative overflow-hidden bg-slate-50/60 p-2">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto w-full select-none"
          role="img"
          aria-label={title}
        >
          <defs>
            <marker
              id="route-arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#2563EB" />
            </marker>
          </defs>

          <rect
            x={padLeft}
            y={padTop}
            width={plotW}
            height={plotH}
            fill="#FFFFFF"
            stroke="#CBD5E1"
            strokeWidth={1}
            rx={4}
          />

          {gridSteps.map((t) => {
            const x = padLeft + t * plotW;
            const y = padTop + t * plotH;
            const latVal = projection.maxLat - t * (projection.maxLat - projection.minLat);
            const lngVal = projection.minLng + t * (projection.maxLng - projection.minLng);
            return (
              <g key={t}>
                <line
                  x1={x}
                  y1={padTop}
                  x2={x}
                  y2={padTop + plotH}
                  stroke="#F1F5F9"
                  strokeWidth={1}
                />
                <line
                  x1={padLeft}
                  y1={y}
                  x2={padLeft + plotW}
                  y2={y}
                  stroke="#F1F5F9"
                  strokeWidth={1}
                />
                <text
                  x={x}
                  y={padTop + plotH + 16}
                  textAnchor="middle"
                  className="fill-slate-400 font-mono text-[10px]"
                >
                  {lngVal.toFixed(3)}°
                </text>
                <text
                  x={padLeft - 8}
                  y={y + 3}
                  textAnchor="end"
                  className="fill-slate-400 font-mono text-[10px]"
                >
                  {latVal.toFixed(3)}°
                </text>
              </g>
            );
          })}

          <text
            x={padLeft + plotW / 2}
            y={height - 6}
            textAnchor="middle"
            className="fill-slate-500 text-[10px] font-medium"
          >
            Longitude (Aspect-corrected East–West)
          </text>

          {showClusterLinks &&
            centroids.length > 0 &&
            points.map((p) => {
              if (p.isOffice || p.clusterIndex === undefined) return null;
              const centroid = centroids.find((c) => c.clusterIndex === p.clusterIndex);
              if (!centroid) return null;
              const pXY = projection.toXY(p.latitude, p.longitude);
              const cXY = projection.toXY(centroid.centroidLat, centroid.centroidLng);
              const color = CLUSTER_COLORS[p.clusterIndex % CLUSTER_COLORS.length];
              return (
                <line
                  key={`link-${p.id}`}
                  x1={pXY.x}
                  y1={pXY.y}
                  x2={cXY.x}
                  y2={cXY.y}
                  stroke={color}
                  strokeOpacity={0.35}
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                />
              );
            })}

          {routeCoords.length > 1 &&
            routeCoords.slice(0, -1).map((from, idx) => {
              const to = routeCoords[idx + 1];
              const midX = (from.x + to.x) / 2;
              const midY = (from.y + to.y) / 2;
              return (
                <g key={`seg-${idx}`}>
                  <line
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke="#2563EB"
                    strokeWidth={2.2}
                    strokeOpacity={0.85}
                    markerEnd="url(#route-arrow)"
                  />
                  <circle cx={midX} cy={midY} r={8} fill="#EFF6FF" stroke="#BFDBFE" strokeWidth={1} />
                  <text
                    x={midX}
                    y={midY + 3}
                    textAnchor="middle"
                    className="fill-blue-700 font-mono text-[9px] font-semibold"
                  >
                    {idx + 1}
                  </text>
                </g>
              );
            })}

          {centroids.map((c) => {
            const { x, y } = projection.toXY(c.centroidLat, c.centroidLng);
            const color = CLUSTER_COLORS[c.clusterIndex % CLUSTER_COLORS.length];
            return (
              <g key={`centroid-${c.clusterIndex}`}>
                <circle
                  cx={x}
                  cy={y}
                  r={14}
                  fill={color}
                  fillOpacity={0.1}
                  stroke={color}
                  strokeWidth={1.2}
                  strokeDasharray="3 2"
                />
                <rect
                  x={x - 5}
                  y={y - 5}
                  width={10}
                  height={10}
                  fill="#FFFFFF"
                  stroke={color}
                  strokeWidth={2.2}
                  rx={2}
                />
                <text
                  x={x}
                  y={y - 11}
                  textAnchor="middle"
                  fill={color}
                  className="text-[10px] font-semibold"
                >
                  {c.clusterLabel}
                </text>
              </g>
            );
          })}

          {points.map((p) => {
            const { x, y } = projection.toXY(p.latitude, p.longitude);
            const isHovered = hoveredId === p.id;
            const clusterColor =
              p.clusterIndex !== undefined
                ? CLUSTER_COLORS[p.clusterIndex % CLUSTER_COLORS.length]
                : '#2563EB';
            const statusStroke =
              p.status === 'visited'
                ? '#16A34A'
                : p.status === 'skipped'
                  ? '#D97706'
                  : '#FFFFFF';

            const stopNumbers: number[] = [];
            routeOrderIds.forEach((id, idx) => {
              if (id === p.id && idx > 0 && !(p.isOffice && idx === routeOrderIds.length - 1)) {
                stopNumbers.push(idx);
              }
            });

            return (
              <g
                key={p.id}
                className="cursor-pointer"
                onMouseEnter={() => setHoveredId(p.id)}
                onMouseLeave={() => setHoveredId(null)}
              >
                {p.isOffice ? (
                  <g transform={`translate(${x}, ${y})`}>
                    <polygon
                      points="0,-9 9,0 0,9 -9,0"
                      fill="#0F172A"
                      stroke="#FFFFFF"
                      strokeWidth={2}
                    />
                    <text
                      x={12}
                      y={3}
                      className="fill-slate-900 text-[11px] font-semibold"
                    >
                      {p.name.length > 22 ? `${p.name.slice(0, 22)}…` : p.name}
                    </text>
                  </g>
                ) : (
                  <g>
                    <circle
                      cx={x}
                      cy={y}
                      r={isHovered ? 8.5 : 6.5}
                      fill={clusterColor}
                      stroke={statusStroke}
                      strokeWidth={2}
                    />
                    {stopNumbers.length > 0 && (
                      <text
                        x={x}
                        y={y - 10}
                        textAnchor="middle"
                        className="fill-slate-800 font-mono text-[10px] font-semibold"
                      >
                        #{stopNumbers.join(',')}
                      </text>
                    )}
                    <text
                      x={x + 10}
                      y={y + 3}
                      className="fill-slate-700 text-[10px] font-medium"
                    >
                      {p.name.length > 20 ? `${p.name.slice(0, 20)}…` : p.name}
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          <g transform={`translate(${padLeft + 14}, ${padTop + 18})`}>
            <line
              x1={0}
              y1={0}
              x2={projection.scaleBarPx}
              y2={0}
              stroke="#475569"
              strokeWidth={2}
            />
            <line x1={0} y1={-4} x2={0} y2={4} stroke="#475569" strokeWidth={1.5} />
            <line
              x1={projection.scaleBarPx}
              y1={-4}
              x2={projection.scaleBarPx}
              y2={4}
              stroke="#475569"
              strokeWidth={1.5}
            />
            <text x={0} y={13} className="fill-slate-600 font-mono text-[10px]">
              ~{projection.scaleKm} km (straight-line)
            </text>
          </g>

          <g transform={`translate(${padLeft + plotW - 24}, ${padTop + 26})`}>
            <circle cx={0} cy={0} r={14} fill="#F8FAFC" stroke="#CBD5E1" strokeWidth={1} />
            <path d="M 0 -10 L 4 2 L 0 -1 L -4 2 Z" fill="#0F172A" />
            <text x={0} y={11} textAnchor="middle" className="fill-slate-600 text-[8px] font-bold">
              N
            </text>
          </g>
        </svg>

        {hoveredPoint && (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700">
            <span className="font-semibold text-slate-900">
              {hoveredPoint.name} {hoveredPoint.isOffice ? '(Base Office)' : ''}
            </span>
            <span className="font-mono tabular-nums text-slate-600">
              Lat {hoveredPoint.latitude.toFixed(5)} · Lng {hoveredPoint.longitude.toFixed(5)}
              {hoveredPoint.clusterLabel ? ` · ${hoveredPoint.clusterLabel}` : ''}
              {hoveredPoint.priority ? ` · Priority ${hoveredPoint.priority}/5` : ''}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
