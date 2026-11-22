import React, { useState, useEffect } from 'react';
import { ArrowLeft, CheckCircle2, Clock, Globe, Map as MapIcon, RefreshCw, Route, ShieldAlert, SkipForward, Trash2 } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../services/api';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { SchematicMap, type SchematicPoint } from '../components/SchematicMap';
import { LeafletRouteMap } from '../components/LeafletRouteMap';
import { GoogleKarachiMap } from '../components/GoogleKarachiMap';
import { formatTime12Hour } from '../utils/time';
import type {
  AlgorithmName,
  OptimizationObjective,
  PaginationMeta,
  RoutePlanDetailPayload,
  RoutePlanSummary,
} from '../types';

interface SavedPlansPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

export const SavedPlansPage: React.FC<SavedPlansPageProps> = ({ onNotify }) => {
  const { planId: selectedPlanId = null } = useParams<{ planId?: string }>();
  const navigate = useNavigate();
  const hasGoogleBrowserKey = Boolean((import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '').trim());

  const [plans, setPlans] = useState<RoutePlanSummary[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta>({
    page: 1,
    pageSize: 15,
    total: 0,
    totalPages: 1,
  });
  const [page, setPage] = useState(1);
  const [loadingList, setLoadingList] = useState(true);

  const [detail, setDetail] = useState<RoutePlanDetailPayload | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RoutePlanSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [switchingObjective, setSwitchingObjective] = useState(false);
  const [mapViewMode, setMapViewMode] = useState<'leaflet' | 'schematic'>('leaflet');
  const [evaluatingDelays, setEvaluatingDelays] = useState(false);

  const loadPlans = async (targetPage = page) => {
    setLoadingList(true);
    try {
      const res = await api.getRoutePlans(targetPage, 15);
      setPlans(res.data.items);
      setPagination(res.data.pagination);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Unable to load route plans');
    } finally {
      setLoadingList(false);
    }
  };

  const loadDetail = async (id: string) => {
    setLoadingDetail(true);
    try {
      const res = await api.getRoutePlanDetail(id);
      setDetail(res.data);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Unable to load route plan details');
      navigate('/saved-plans');
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    void loadPlans(page);
  }, [page]);

  useEffect(() => {
    if (selectedPlanId) {
      void loadDetail(selectedPlanId);
    } else {
      setDetail(null);
    }
  }, [selectedPlanId]);

  const handleStopStatus = async (stopId: string, status: 'pending' | 'visited' | 'skipped') => {
    try {
      await api.updateStopStatus(stopId, status);
      onNotify('success', `Stop marked as ${status}.`);
      if (selectedPlanId) await loadDetail(selectedPlanId);
      await loadPlans(page);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to update stop status');
    }
  };

  const handleSwitchAlgorithm = async (algo: AlgorithmName) => {
    if (!selectedPlanId) return;
    try {
      await api.updateRoutePlan(selectedPlanId, { selectedAlgorithm: algo });
      onNotify('success', `Applied ${algo} route order to plan stops.`);
      await loadDetail(selectedPlanId);
      await loadPlans(page);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to switch algorithm');
    }
  };

  const handleSwitchObjective = async (nextObjective: OptimizationObjective) => {
    if (!selectedPlanId || !detail || detail.plan.optimization_objective === nextObjective) return;
    setSwitchingObjective(true);
    try {
      await api.updateRoutePlan(selectedPlanId, { optimizationObjective: nextObjective });
      onNotify(
        'success',
        `Re-optimized route plan for ${nextObjective === 'FASTEST_TIME' ? 'Fastest Time' : 'Shortest Distance'}.`
      );
      await loadDetail(selectedPlanId);
      await loadPlans(page);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to switch optimization objective');
    } finally {
      setSwitchingObjective(false);
    }
  };

  const handleDeletePlan = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteRoutePlan(deleteTarget.id);
      onNotify('success', `Deleted route plan "${deleteTarget.name}".`);
      if (selectedPlanId === deleteTarget.id) {
        navigate('/saved-plans');
      }
      setDeleteTarget(null);
      await loadPlans(page);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to delete route plan');
    } finally {
      setDeleting(false);
    }
  };

  const handleEvaluateDelays = async () => {
    if (!selectedPlanId) return;
    setEvaluatingDelays(true);
    try {
      await api.predictRouteDelay({ routePlanId: selectedPlanId });
      onNotify('success', 'Bayesian delay risk evaluated and saved.');
      await loadDetail(selectedPlanId);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to evaluate delay risks');
    } finally {
      setEvaluatingDelays(false);
    }
  };

  if (selectedPlanId) {
    if (loadingDetail || !detail) {
      return <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />;
    }

    const { plan, stops, algorithms } = detail;
    const planObjective: OptimizationObjective = plan.optimization_objective || 'FASTEST_TIME';
    const planDataSource = plan.data_source || 'osrm_osm';
    const planProviderLabel =
      plan.provider_label ||
      (planDataSource === 'osrm_osm'
        ? 'OSRM / OpenStreetMap'
        : planDataSource === 'openrouteservice'
          ? 'OpenRouteService'
          : planDataSource.startsWith('google_')
            ? 'Google Maps'
            : planDataSource);
    const planDurationLabel =
      plan.duration_label ||
      (plan.is_live_traffic || planDataSource === 'google_live_traffic'
        ? 'Live traffic travel duration'
        : 'Estimated road travel duration (no live traffic)');

    const pointMap = new Map<string, SchematicPoint>();
    if (plan.office_latitude !== undefined && plan.office_longitude !== undefined) {
      pointMap.set(plan.office_id, {
        id: plan.office_id,
        name: plan.office_name || 'Office',
        latitude: plan.office_latitude,
        longitude: plan.office_longitude,
        isOffice: true,
      });
    }
    for (const s of stops) {
      if (s.stop_type === 'distributor' && s.distributor_id) {
        pointMap.set(s.distributor_id, {
          id: s.distributor_id,
          name: s.stop_name || 'Distributor',
          latitude: s.latitude,
          longitude: s.longitude,
          priority: s.distributor_priority ?? undefined,
          status: s.status,
        });
      }
    }
    const routeOrderIds = stops.map((s) =>
      s.stop_type === 'distributor' && s.distributor_id ? s.distributor_id : plan.office_id
    );

    return (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-5 py-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate('/saved-plans')}
              className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              All Plans
            </button>
            <div>
              <h2 className="text-base font-semibold text-slate-900">{plan.name}</h2>
              <p className="text-xs text-slate-500 tabular-nums">
                {String(plan.plan_date).slice(0, 10)} · Base: {plan.office_name} · Algorithm:{' '}
                <span className="font-mono font-semibold text-slate-800">
                  {plan.selected_algorithm || 'Draft'}
                </span>{' '}
                · Provider: <span className="font-medium text-slate-700">{planProviderLabel}</span> · Status: {plan.status}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-5 font-mono text-xs tabular-nums">
            <div>
              <span className="text-slate-500">Distance: </span>
              <span className="font-semibold text-slate-900">{plan.total_distance_km} km</span>
            </div>
            <div>
              <span className="text-slate-500">Travel Time: </span>
              <span className="font-semibold text-slate-900">{plan.total_duration_minutes} min</span>
              {(plan.traffic_delay_minutes ?? 0) > 0 && (
                <span className="ml-1.5 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">
                  +{plan.traffic_delay_minutes}m traffic
                </span>
              )}
            </div>
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 font-sans">
              <button
                type="button"
                disabled={switchingObjective}
                onClick={() => void handleSwitchObjective('FASTEST_TIME')}
                className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium ${
                  planObjective === 'FASTEST_TIME'
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Clock className="h-3 w-3" />
                Fastest Time
              </button>
              <button
                type="button"
                disabled={switchingObjective}
                onClick={() => void handleSwitchObjective('SHORTEST_DISTANCE')}
                className={`inline-flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium ${
                  planObjective === 'SHORTEST_DISTANCE'
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Route className="h-3 w-3" />
                Shortest Dist
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setMapViewMode('leaflet')}
              className={`inline-flex items-center gap-1.5 rounded px-3 py-1 font-medium transition-colors ${
                mapViewMode === 'leaflet'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <MapIcon className="h-3 w-3" />
              Leaflet Map
            </button>
            <button
              type="button"
              onClick={() => setMapViewMode('schematic')}
              className={`rounded px-3 py-1 font-medium transition-colors ${
                mapViewMode === 'schematic'
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Schematic Plot
            </button>
          </div>

          <button
            type="button"
            disabled={evaluatingDelays}
            onClick={handleEvaluateDelays}
            className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:opacity-50"
          >
            <ShieldAlert className="h-3.5 w-3.5" />
            {evaluatingDelays ? 'Evaluating...' : 'Evaluate Delay Risks (BN)'}
          </button>
        </div>

        {mapViewMode === 'leaflet' ? (
          <LeafletRouteMap
            points={Array.from(pointMap.values())}
            routeOrderIds={routeOrderIds}
            encodedPolyline={plan.encoded_polyline}
            providerLabel={planProviderLabel}
            isLiveTraffic={Boolean(plan.is_live_traffic || planDataSource === 'google_live_traffic')}
            durationLabel={planDurationLabel}
            dataSource={planDataSource}
            height={380}
            title={`Saved Route (Leaflet Map) · ${plan.selected_algorithm || 'Draft'} (${plan.total_duration_minutes} min · ${plan.total_distance_km} km)`}
          />
        ) : (
          <SchematicMap
            points={Array.from(pointMap.values())}
            routeOrderIds={routeOrderIds}
            height={380}
            title={`Saved Route Schematic · ${plan.selected_algorithm || 'Draft'} (${plan.total_distance_km} km)`}
          />
        )}

        {detail.delayPredictions && detail.delayPredictions.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-gradient-to-r from-slate-50 to-indigo-50/40 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-900">
                  Bayesian Delay Risk Analysis Summary
                </h4>
                <p className="text-xs text-slate-600">
                  Exact Bayesian inference computed for {detail.delayPredictions.length} distributor stops using distance, duration, time slot, and priority.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-red-600" />
                  {detail.delayPredictions.filter((p) => p.predictedRisk === 'High').length} High Risk
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-600" />
                  {detail.delayPredictions.filter((p) => p.predictedRisk === 'Medium').length} Medium
                </span>
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-600" />
                  {detail.delayPredictions.filter((p) => p.predictedRisk === 'Low').length} Low
                </span>
              </div>
            </div>
          </div>
        )}

        <div className="rounded-lg border border-slate-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3.5">
            <h3 className="text-base font-semibold text-slate-900">Ordered Route Stops</h3>
            <span className="text-xs text-slate-500">
              {planProviderLabel} · {planDurationLabel}
              {plan.traffic_calculated_at &&
                ` · Calculated ${new Date(plan.traffic_calculated_at).toLocaleString()}`}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
                <tr>
                  <th className="px-4 py-2.5">#</th>
                  <th className="px-4 py-2.5">Location</th>
                  <th className="px-4 py-2.5 text-right">Leg Dist.</th>
                  <th className="px-4 py-2.5 text-right">Leg Travel</th>
                  <th className="px-4 py-2.5 text-right">Est. Arrival / Dep.</th>
                  <th className="px-4 py-2.5 text-center">Delay Risk (BN)</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">Update</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {stops.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50/70">
                    <td className="px-4 py-2.5 font-mono text-xs tabular-nums text-slate-500">
                      {s.stop_order}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="font-medium text-slate-900">{s.stop_name}</div>
                      <div className="text-xs text-slate-500">
                        {s.stop_type === 'distributor' ? s.distributor_address : plan.office_address}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-700">
                      {s.distance_from_previous_km ?? 0} km
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-700">
                      {s.travel_from_previous_minutes ?? 0} min
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-600">
                      {s.estimated_arrival_hhmm ? formatTime12Hour(s.estimated_arrival_hhmm) : '—'} → {s.estimated_departure_hhmm ? formatTime12Hour(s.estimated_departure_hhmm) : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {(() => {
                        const pred = (detail.delayPredictions || []).find(
                          (dp) => dp.distributorId === s.distributor_id || dp.stopOrder === s.stop_order
                        );
                        if (!pred) return <span className="text-xs text-slate-400">—</span>;
                        return (
                          <span
                            title={pred.recommendation || `Predicted risk: ${pred.predictedRisk}`}
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                              pred.predictedRisk === 'High'
                                ? 'bg-red-100 text-red-800'
                                : pred.predictedRisk === 'Medium'
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-emerald-100 text-emerald-800'
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                pred.predictedRisk === 'High'
                                  ? 'bg-red-600'
                                  : pred.predictedRisk === 'Medium'
                                    ? 'bg-amber-600'
                                    : 'bg-emerald-600'
                              }`}
                            />
                            {pred.predictedRisk}
                          </span>
                        );
                      })()}
                    </td>
                    <td className="px-4 py-2.5 text-xs font-medium">
                      <span
                        className={
                          s.status === 'visited'
                            ? 'text-emerald-700'
                            : s.status === 'skipped'
                              ? 'text-amber-700'
                              : 'text-slate-600'
                        }
                      >
                        {s.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {s.stop_type === 'distributor' ? (
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleStopStatus(s.id, 'visited')}
                            title="Mark Visited"
                            className="inline-flex items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700 hover:bg-emerald-100"
                          >
                            <CheckCircle2 className="h-3 w-3" />
                            Visited
                          </button>
                          <button
                            type="button"
                            onClick={() => handleStopStatus(s.id, 'skipped')}
                            title="Mark Skipped"
                            className="inline-flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700 hover:bg-amber-100"
                          >
                            <SkipForward className="h-3 w-3" />
                            Skip
                          </button>
                          {s.status !== 'pending' && (
                            <button
                              type="button"
                              onClick={() => handleStopStatus(s.id, 'pending')}
                              title="Reset Pending"
                              className="rounded border border-slate-200 p-1 text-slate-500 hover:bg-slate-100"
                            >
                              <RefreshCw className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-slate-400">Base</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {algorithms.length > 0 && (
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <h3 className="text-base font-semibold text-slate-900">
              Stored Algorithm Comparison for This Plan
            </h3>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-3 py-2">Algorithm</th>
                    <th className="px-3 py-2">Objective</th>
                    <th className="px-3 py-2 text-right">Distance</th>
                    <th className="px-3 py-2 text-right">Travel Time</th>
                    <th className="px-3 py-2 text-right">Nodes Expanded</th>
                    <th className="px-3 py-2 text-right">Exec Time</th>
                    <th className="px-3 py-2 text-right">Apply</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {algorithms.map((a) => (
                    <tr key={a.id}>
                      <td className="px-3 py-2 font-mono font-semibold text-slate-900">
                        {a.algorithm_name}
                        {a.result_details?.isRecommended && (
                          <span className="ml-1.5 font-sans text-emerald-700">· Recommended</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {a.result_details?.objectiveDescription || 'Route comparison run'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-900">
                        {a.total_distance_km ?? 0} km
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-900">
                        {a.estimated_duration_minutes ?? 0} min
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-700">
                        {(a.nodes_expanded ?? 0).toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-700">
                        {a.execution_time_ms ?? 0} ms
                      </td>
                      <td className="px-3 py-2 text-right">
                        {plan.selected_algorithm === a.algorithm_name ? (
                          <span className="font-medium text-blue-700">Active</span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleSwitchAlgorithm(a.algorithm_name)}
                            className="rounded border border-slate-200 px-2.5 py-1 font-medium text-slate-700 hover:bg-slate-50"
                          >
                            Use Route
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Saved Route Plans</h3>
            <p className="text-xs text-slate-500">
              Persisted in SQLite database across refreshes
            </p>
          </div>
          <button
            type="button"
            onClick={() => navigate('/optimizer')}
            className="whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
          >
            New Route Plan
          </button>
        </div>

        {loadingList ? (
          <div className="space-y-2 p-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-slate-100" />
            ))}
          </div>
        ) : plans.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-base font-semibold text-slate-900">No route plans saved yet</p>
            <p className="mt-1 text-sm text-slate-600">
              Use the Route Optimizer to compare BFS, UCS, A*, and GA and save a route plan.
            </p>
            <button
              type="button"
              onClick={() => navigate('/optimizer')}
              className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Open Route Optimizer
            </button>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
                  <tr>
                    <th className="px-5 py-3">Plan Name</th>
                    <th className="px-4 py-3">Date</th>
                    <th className="px-4 py-3">Algorithm &amp; Objective</th>
                    <th className="px-4 py-3 text-right">Stops Done</th>
                    <th className="px-4 py-3 text-right">Distance</th>
                    <th className="px-4 py-3 text-right">Travel</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {plans.map((p) => (
                    <tr key={p.id} className="hover:bg-slate-50/70">
                      <td className="px-5 py-3">
                        <button
                          type="button"
                          onClick={() => navigate(`/saved-plans/${p.id}`)}
                          className="font-medium text-blue-600 hover:text-blue-800 hover:underline"
                        >
                          {p.name}
                        </button>
                        <div className="text-xs text-slate-500">{p.office_name}</div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs tabular-nums text-slate-700">
                        {String(p.plan_date).slice(0, 10)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-800">
                        <span className="font-semibold">{p.selected_algorithm || 'Draft'}</span>
                        <div className="text-[11px] font-sans text-slate-500">
                          {p.optimization_objective === 'SHORTEST_DISTANCE'
                            ? 'Shortest Distance'
                            : 'Fastest Time'}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-slate-700">
                        {p.visited_count ?? 0} / {p.stop_count ?? 0}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-slate-900">
                        {p.total_distance_km} km
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-slate-700">
                        {p.total_duration_minutes} min
                      </td>
                      <td className="px-4 py-3 text-xs font-medium text-slate-700">{p.status}</td>
                      <td className="px-5 py-3 text-right">
                        <div className="inline-flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => navigate(`/saved-plans/${p.id}`)}
                            className="rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            View
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget(p)}
                            className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                            aria-label={`Delete ${p.name}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between border-t border-slate-100 px-5 py-3 text-xs text-slate-600">
              <span className="tabular-nums">
                Page {pagination.page} of {pagination.totalPages} ({pagination.total} plans)
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={pagination.page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded border border-slate-200 px-2.5 py-1 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={pagination.page >= pagination.totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="rounded border border-slate-200 px-2.5 py-1 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete Route Plan"
        description={`Delete "${deleteTarget?.name}" and its associated route stops and algorithm comparison runs?`}
        confirmLabel="Delete Plan"
        destructive
        busy={deleting}
        onConfirm={handleDeletePlan}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};
