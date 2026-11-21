import React, { useEffect, useMemo, useState } from 'react';
import {
  APIProvider,
  AdvancedMarker,
  InfoWindow,
  Map as GoogleMap,
  Pin,
  useMap,
  useMapsLibrary,
} from '@vis.gl/react-google-maps';
import type { SchematicPoint } from './SchematicMap';
import type { DataSourceType } from '../types';
import { decodeEncodedPolyline } from '../utils/polyline';

interface GoogleKarachiMapProps {
  points: SchematicPoint[];
  routeOrderIds?: string[];
  encodedPolyline?: string | null;
  dataSource?: DataSourceType;
  height?: number;
  title?: string;
  onSwitchToLeaflet?: () => void;
}

const KARACHI_CENTER = { lat: 24.8607, lng: 67.0644 };
const MAP_ID = 'DEMO_MAP_ID';
const ATTRIBUTION_ID = 'gmp_mcp_codeassist_v1_aistudio';

interface RouteOverlayProps {
  points: SchematicPoint[];
  routeOrderIds: string[];
  encodedPolyline?: string | null;
  showTraffic: boolean;
}

const GoogleRouteOverlays: React.FC<RouteOverlayProps> = ({
  points,
  routeOrderIds,
  encodedPolyline,
  showTraffic,
}) => {
  const map = useMap();
  const mapsLib = useMapsLibrary('maps');
  const coreLib = useMapsLibrary('core');

  const fallbackPath = useMemo(() => {
    const pointMap = new Map(points.map((p) => [p.id, p]));
    return routeOrderIds
      .map((id) => pointMap.get(id))
      .filter((p): p is SchematicPoint => Boolean(p))
      .map((p) => ({ lat: p.latitude, lng: p.longitude }));
  }, [points, routeOrderIds]);

  const routePath = useMemo(() => {
    if (encodedPolyline) {
      const decoded = decodeEncodedPolyline(encodedPolyline);
      if (decoded.length >= 2) return decoded;
    }
    return fallbackPath;
  }, [encodedPolyline, fallbackPath]);

  // Fit bounds around points or polyline
  useEffect(() => {
    if (!map || !coreLib || points.length === 0) return;
    const bounds = new coreLib.LatLngBounds();
    points.forEach((p) => bounds.extend({ lat: p.latitude, lng: p.longitude }));
    routePath.forEach((pt) => bounds.extend(pt));
    map.fitBounds(bounds, 48);
  }, [map, coreLib, points, routePath]);

  // Render road polyline (or dashed fallback polyline)
  useEffect(() => {
    if (!map || !mapsLib || routePath.length < 2) return;

    const isRoadPolyline = Boolean(encodedPolyline && decodeEncodedPolyline(encodedPolyline).length >= 2);
    const polyline = new mapsLib.Polyline({
      path: routePath,
      strokeColor: '#2563EB',
      strokeOpacity: isRoadPolyline ? 0.9 : 0.75,
      strokeWeight: isRoadPolyline ? 5 : 3,
      icons: isRoadPolyline
        ? undefined
        : [
            {
              icon: { path: 'M 0,-1 0,1', strokeOpacity: 1, scale: 3 },
              offset: '0',
              repeat: '16px',
            },
          ],
    });
    polyline.setMap(map);
    return () => {
      polyline.setMap(null);
    };
  }, [map, mapsLib, routePath, encodedPolyline]);

  // Optional TrafficLayer overlay
  useEffect(() => {
    if (!map || !mapsLib || !showTraffic) return;
    const layer = new mapsLib.TrafficLayer();
    layer.setMap(map);
    return () => {
      layer.setMap(null);
    };
  }, [map, mapsLib, showTraffic]);

  return null;
};

export const GoogleKarachiMap: React.FC<GoogleKarachiMapProps> = ({
  points,
  routeOrderIds = [],
  encodedPolyline = null,
  dataSource = 'simulated_fallback',
  height = 420,
  title = 'Karachi Google Maps View',
  onSwitchToLeaflet,
}) => {
  const browserApiKey = (import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '').trim();
  const [selectedPoint, setSelectedPoint] = useState<{
    point: SchematicPoint;
    stops: number[];
  } | null>(null);
  const [showTraffic, setShowTraffic] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const validPoints = useMemo(
    () =>
      points.filter(
        (p) =>
          typeof p.latitude === 'number' &&
          typeof p.longitude === 'number' &&
          !Number.isNaN(p.latitude) &&
          !Number.isNaN(p.longitude)
      ),
    [points]
  );

  useEffect(() => {
    const win = window as Window & { gm_authFailure?: () => void };
    const prev = win.gm_authFailure;
    win.gm_authFailure = () => {
      setAuthError('Google Maps JavaScript API authentication failed for the current key.');
    };
    return () => {
      win.gm_authFailure = prev;
    };
  }, []);

  if (!browserApiKey || authError) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
            <p className="text-xs text-slate-500">
              Google Maps JavaScript API fallback · Interactive Leaflet &amp; OpenStreetMap remain available
            </p>
          </div>
          {onSwitchToLeaflet && (
            <button
              type="button"
              onClick={onSwitchToLeaflet}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              Switch to Interactive Leaflet Map
            </button>
          )}
        </div>
        <div
          style={{ height: `${Math.max(240, height - 60)}px` }}
          className="flex flex-col items-center justify-center gap-2 bg-slate-50 px-6 text-center"
        >
          <p className="text-sm font-semibold text-slate-800">
            {authError
              ? authError
              : 'Google Maps browser key (VITE_GOOGLE_MAPS_API_KEY) is not configured.'}
          </p>
          <p className="max-w-lg text-xs text-slate-600">
            Configure <code className="font-mono">VITE_GOOGLE_MAPS_API_KEY</code> in environment settings to render live Karachi Google Maps tiles, traffic overlays, and Advanced Markers. All Python route optimization and Leaflet mapping continue to operate cleanly.
          </p>
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
              ? `Real Karachi road geometry rendered on Google Maps (${dataSource.replace(/_/g, ' ')})`
              : 'Karachi Google Maps basemap with straight-line fallback legs · Configure GOOGLE_MAPS_API_KEY on server for road polylines'}
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-600">
          <label className="inline-flex cursor-pointer items-center gap-1.5 font-medium text-slate-700">
            <input
              type="checkbox"
              checked={showTraffic}
              onChange={(e) => setShowTraffic(e.target.checked)}
            />
            Traffic Layer
          </label>
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

      <div style={{ height: `${height}px`, width: '100%' }} className="overflow-hidden rounded-b-lg">
        <APIProvider apiKey={browserApiKey} libraries={['marker']} language="en" region="PK">
          <GoogleMap
            mapId={MAP_ID}
            defaultCenter={KARACHI_CENTER}
            defaultZoom={12}
            gestureHandling="greedy"
            internalUsageAttributionIds={[ATTRIBUTION_ID]}
            style={{ width: '100%', height: '100%' }}
          >
            <GoogleRouteOverlays
              points={validPoints}
              routeOrderIds={routeOrderIds}
              encodedPolyline={encodedPolyline}
              showTraffic={showTraffic}
            />

            {validPoints.map((p) => {
              const stopNumbers: number[] = [];
              routeOrderIds.forEach((id, idx) => {
                if (id === p.id && idx > 0 && !(p.isOffice && idx === routeOrderIds.length - 1)) {
                  stopNumbers.push(idx);
                }
              });

              return (
                <AdvancedMarker
                  key={p.id}
                  position={{ lat: p.latitude, lng: p.longitude }}
                  title={p.name}
                  onClick={() => setSelectedPoint({ point: p, stops: stopNumbers })}
                >
                  <Pin
                    background={p.isOffice ? '#0F172A' : '#2563EB'}
                    borderColor="#FFFFFF"
                    glyphColor="#FFFFFF"
                    glyph={p.isOffice ? 'HQ' : stopNumbers.length > 0 ? `#${stopNumbers[0]}` : 'D'}
                  />
                </AdvancedMarker>
              );
            })}

            {selectedPoint && (
              <InfoWindow
                position={{
                  lat: selectedPoint.point.latitude,
                  lng: selectedPoint.point.longitude,
                }}
                onCloseClick={() => setSelectedPoint(null)}
              >
                <div className="max-w-xs space-y-1 p-1 text-xs text-slate-800">
                  <p className="font-semibold text-slate-900">
                    {selectedPoint.point.name}{' '}
                    {selectedPoint.point.isOffice && (
                      <span className="font-normal text-slate-500">(Base Office)</span>
                    )}
                  </p>
                  <p className="font-mono text-[11px] text-slate-600">
                    {selectedPoint.point.latitude.toFixed(5)}, {selectedPoint.point.longitude.toFixed(5)}
                  </p>
                  {selectedPoint.point.priority !== undefined && (
                    <p>Priority: {selectedPoint.point.priority}/5</p>
                  )}
                  {selectedPoint.point.status && (
                    <p>
                      Status: <strong className="capitalize">{selectedPoint.point.status}</strong>
                    </p>
                  )}
                  {selectedPoint.stops.length > 0 && (
                    <p className="font-semibold text-blue-700">
                      Stop Sequence: #{selectedPoint.stops.join(', ')}
                    </p>
                  )}
                </div>
              </InfoWindow>
            )}
          </GoogleMap>
        </APIProvider>
      </div>
    </div>
  );
};
