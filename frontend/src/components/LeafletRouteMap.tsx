import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { SchematicCentroid, SchematicPoint } from './SchematicMap';
import type { DataSourceType, RoutingProvider } from '../types';
import { decodeEncodedPolyline } from '../utils/polyline';

interface LeafletRouteMapProps {
  points: SchematicPoint[];
  centroids?: SchematicCentroid[];
  routeOrderIds?: string[];
  encodedPolyline?: string | null;
  provider?: RoutingProvider;
  providerLabel?: string;
  isLiveTraffic?: boolean;
  durationLabel?: string;
  dataSource?: DataSourceType;
  height?: number;
  title?: string;
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

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export const LeafletRouteMap: React.FC<LeafletRouteMapProps> = ({
  points,
  centroids = [],
  routeOrderIds = [],
  encodedPolyline = null,
  providerLabel,
  isLiveTraffic = false,
  durationLabel,
  dataSource = 'osrm_osm',
  height = 420,
  title = 'Interactive Leaflet Route Map',
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);

  const validPoints = points.filter(
    (p) =>
      typeof p.latitude === 'number' &&
      typeof p.longitude === 'number' &&
      !Number.isNaN(p.latitude) &&
      !Number.isNaN(p.longitude)
  );

  useEffect(() => {
    if (!containerRef.current || validPoints.length === 0) {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
      return;
    }

    if (mapRef.current) {
      mapRef.current.remove();
      mapRef.current = null;
    }

    const defaultLat = validPoints[0].latitude;
    const defaultLng = validPoints[0].longitude;

    const map = L.map(containerRef.current, {
      center: [defaultLat, defaultLng],
      zoom: 12,
      attributionControl: true,
      zoomControl: true,
    });
    mapRef.current = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    const pointMap = new Map(validPoints.map((p) => [p.id, p]));
    const bounds = L.latLngBounds([]);

    const decodedRoad = encodedPolyline ? decodeEncodedPolyline(encodedPolyline) : [];
    if (decodedRoad.length >= 2) {
      const roadLatLngs: L.LatLngExpression[] = decodedRoad.map((pt) => {
        bounds.extend([pt.lat, pt.lng]);
        return [pt.lat, pt.lng];
      });
      L.polyline(roadLatLngs, {
        color: '#2563EB',
        weight: 4,
        opacity: 0.9,
        lineJoin: 'round',
      }).addTo(map);
    } else if (routeOrderIds.length > 1) {
      const latlngs: L.LatLngExpression[] = [];
      routeOrderIds.forEach((id) => {
        const pt = pointMap.get(id);
        if (pt) {
          latlngs.push([pt.latitude, pt.longitude]);
        }
      });

      if (latlngs.length > 1) {
        L.polyline(latlngs, {
          color: '#2563EB',
          weight: 3.5,
          opacity: 0.85,
          dashArray: '6, 6',
          lineJoin: 'round',
        }).addTo(map);
      }
    }

    centroids.forEach((c) => {
      bounds.extend([c.centroidLat, c.centroidLng]);
      const color = CLUSTER_COLORS[c.clusterIndex % CLUSTER_COLORS.length];
      const centroidIcon = L.divIcon({
        className: 'custom-centroid-marker',
        html: `<div style="background-color: ${color}; width: 22px; height: 22px; border: 2px solid white; border-radius: 4px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-size: 10px; font-weight: bold; color: white;">C${c.clusterIndex + 1}</div>`,
        iconSize: [22, 22],
        iconAnchor: [11, 11],
      });

      L.marker([c.centroidLat, c.centroidLng], { icon: centroidIcon })
        .addTo(map)
        .bindPopup(
          `<strong>${escapeHtml(c.clusterLabel)}</strong><br/>Centroid: ${c.centroidLat.toFixed(4)}, ${c.centroidLng.toFixed(4)}`
        );
    });

    validPoints.forEach((p) => {
      bounds.extend([p.latitude, p.longitude]);

      const stopNumbers: number[] = [];
      routeOrderIds.forEach((id, idx) => {
        if (id === p.id && idx > 0 && !(p.isOffice && idx === routeOrderIds.length - 1)) {
          stopNumbers.push(idx);
        }
      });

      let markerIcon: L.DivIcon;
      if (p.isOffice) {
        markerIcon = L.divIcon({
          className: 'custom-office-marker',
          html: `<div style="background-color: #0F172A; width: 28px; height: 28px; border: 2px solid white; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(0,0,0,0.3); color: white; font-size: 11px; font-weight: bold;">HQ</div>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });
      } else {
        const clusterColor =
          p.clusterIndex !== undefined
            ? CLUSTER_COLORS[p.clusterIndex % CLUSTER_COLORS.length]
            : '#2563EB';

        const stopLabel = stopNumbers.length > 0 ? `#${stopNumbers.join(',')}` : `P${p.priority || 3}`;

        markerIcon = L.divIcon({
          className: 'custom-distributor-marker',
          html: `<div style="background-color: ${clusterColor}; width: 26px; height: 26px; border: 2px solid white; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 6px rgba(0,0,0,0.3); color: white; font-size: 10px; font-weight: bold; font-family: monospace;">${escapeHtml(stopLabel)}</div>`,
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        });
      }

      const safeName = escapeHtml(p.name);
      const safeStatus = p.status ? escapeHtml(p.status) : '';
      const popupHtml = `
        <div style="font-size: 12px; line-height: 1.4;">
          <strong>${safeName}</strong> ${p.isOffice ? '<span style="color: #64748B;">(Base Office)</span>' : ''}<br/>
          <span>Coordinates: ${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)}</span><br/>
          ${p.priority ? `<span>Priority: ${p.priority}/5</span><br/>` : ''}
          ${safeStatus ? `<span>Status: <strong style="text-transform: capitalize;">${safeStatus}</strong></span><br/>` : ''}
          ${stopNumbers.length > 0 ? `<span style="color: #2563EB; font-weight: 600;">Stop Sequence: #${stopNumbers.join(', ')}</span>` : ''}
        </div>
      `;

      L.marker([p.latitude, p.longitude], { icon: markerIcon })
        .addTo(map)
        .bindPopup(popupHtml);
    });

    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });

    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, [points, centroids, routeOrderIds, encodedPolyline]);

  if (validPoints.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <span className="text-xs text-slate-500">OpenStreetMap Leaflet</span>
        </div>
        <div className="flex h-64 items-center justify-center text-sm text-slate-500">
          Add an office or distributor coordinates to render the interactive Leaflet map.
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          <p className="text-xs text-slate-500">
            {encodedPolyline
              ? `Real road geometry (${providerLabel || dataSource.replace(/_/g, ' ')}) · ${
                  durationLabel ||
                  (isLiveTraffic
                    ? 'Live traffic durations'
                    : 'Estimated normal road durations (no live traffic)')
                }`
              : routeOrderIds.length > 1
                ? 'Route stop order plotted on OpenStreetMap Leaflet · Click pins for stop details'
                : 'OpenStreetMap Leaflet · Click Optimize to fetch road-following polyline'}
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-600">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full bg-slate-900" />
            Base Office
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-full bg-blue-600" />
            Distributor Stop
          </span>
        </div>
      </div>
      <div
        ref={containerRef}
        style={{ height: `${height}px`, width: '100%' }}
        className="z-0 rounded-b-lg"
      />
    </div>
  );
};
