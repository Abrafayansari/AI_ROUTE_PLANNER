import React, { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ArrowRight, Database, Play, Plus, RefreshCw, Route, Store } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { LeafletRouteMap } from '../components/LeafletRouteMap';
import type { SchematicPoint } from '../components/SchematicMap';
import type { AnalyticsSummary, DatabaseHealth, Distributor, OfficeLocation, RoutePlanDetailPayload } from '../types';

interface DashboardPageProps {
  dbHealth: DatabaseHealth | null;
  onNotify: (kind: 'success' | 'error', text: string) => void;
  onRefreshHealth: () => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  dbHealth,
  onNotify,
  onRefreshHealth,
}) => {
  const navigate = useNavigate();
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [office, setOffice] = useState<OfficeLocation | null>(null);
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [latestPlanDetail, setLatestPlanDetail] = useState<RoutePlanDetailPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);

  const loadData = async () => {
    if (!dbHealth?.connected || !dbHealth?.schemaReady) {
      setLoading(false);
      setSummary(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [sumRes, offRes, distRes] = await Promise.all([
        api.getAnalyticsSummary(),
        api.getOffices().catch(() => null),
        api.getDistributors({ active: 'true', pageSize: 100 }).catch(() => null),
      ]);
      setSummary(sumRes.data);
      if (offRes?.data?.defaultOffice) {
        setOffice(offRes.data.defaultOffice);
      }
      if (distRes?.data?.items) {
        setDistributors(distRes.data.items);
      }

      // If there's a latest plan, load its details for the interactive map
      if (sumRes.data.latestRoutePlan?.id) {
        try {
          const planRes = await api.getRoutePlanDetail(sumRes.data.latestRoutePlan.id);
          setLatestPlanDetail(planRes.data);
        } catch {
          // ignore if detail load fails
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [dbHealth?.connected, dbHealth?.schemaReady]);

  const handleLoadDemo = async () => {
    setDemoBusy(true);
    try {
      const res = await api.loadDemoData();
      onNotify('success', res.message || 'Demo dataset loaded.');
      await loadData();
      onRefreshHealth();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to load demo data');
    } finally {
      setDemoBusy(false);
    }
  };

  // Prepare map points and sequence
  const mapPoints: SchematicPoint[] = useMemo(() => {
    if (latestPlanDetail?.stops && latestPlanDetail.stops.length > 0) {
      return latestPlanDetail.stops.map((s) => ({
        id: s.distributor_id || s.id,
        name: s.stop_name,
        latitude: Number(s.latitude),
        longitude: Number(s.longitude),
        isOffice: s.stop_type === 'office_start' || s.stop_type === 'office_end',
      }));
    }
    // Fallback: show office + all distributors
    const points: SchematicPoint[] = [];
    if (office) {
      points.push({
        id: office.id,
        name: office.name,
        latitude: office.latitude,
        longitude: office.longitude,
        isOffice: true,
      });
    }
    for (const d of distributors) {
      points.push({
        id: d.id,
        name: d.name,
        latitude: d.latitude,
        longitude: d.longitude,
        isOffice: false,
      });
    }
    return points;
  }, [latestPlanDetail, office, distributors]);

  const routeOrderIds = useMemo(() => {
    if (latestPlanDetail?.stops && latestPlanDetail.stops.length > 0) {
      return latestPlanDetail.stops.map((s) => s.distributor_id || s.id);
    }
    return [];
  }, [latestPlanDetail]);

  if (!dbHealth?.connected || !dbHealth?.schemaReady) {
    return (
      <div className="space-y-6">
        <div className="rounded-lg border border-amber-200 bg-white p-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1.5">
              <h2 className="text-lg font-semibold text-slate-900">
                Database Initialization Required
              </h2>
              <p className="max-w-2xl text-sm text-slate-600">
                {dbHealth?.message || 'Database connection is not ready. Verify SQLite database configuration.'}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={onRefreshHealth}
                className="inline-flex items-center gap-2 whitespace-nowrap shrink-0 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <RefreshCw className="h-4 w-4" />
                Retry Connection
              </button>
              <button
                type="button"
                onClick={() => navigate('/settings')}
                className="inline-flex items-center gap-2 whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                <Database className="h-4 w-4" />
                Open Database Setup
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h3 className="text-base font-semibold text-slate-900">System Capabilities</h3>
          <p className="mt-1 text-sm text-slate-600">
            Intelligent route planning, constraint-based visit scheduling, and delay prediction for field officers in Karachi.
          </p>
          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="border-t border-slate-100 pt-3">
              <p className="text-sm font-semibold text-slate-900">Route Planning &amp; Optimization</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Compare BFS, Uniform Cost Search (UCS), A* with MST heuristic, and Genetic Algorithm to find the optimal road tour.
              </p>
            </div>
            <div className="border-t border-slate-100 pt-3">
              <p className="text-sm font-semibold text-slate-900">Visit Scheduling</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Automatically schedule distributor visits respecting officer working hours, lunch breaks, and travel buffers.
              </p>
            </div>
            <div className="border-t border-slate-100 pt-3">
              <p className="text-sm font-semibold text-slate-900">Territories &amp; Delay Prediction</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Partition distributors into balanced regional clusters and estimate visit delay probabilities using Bayesian inference.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg border border-slate-200 bg-white p-5" />
          ))}
        </div>
        <div className="h-96 animate-pulse rounded-lg border border-slate-200 bg-white" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-white p-6 text-center">
        <p className="text-sm font-semibold text-red-700">Failed to load dashboard metrics</p>
        <p className="mt-1 text-sm text-slate-600">{error}</p>
        <button
          type="button"
          onClick={() => void loadData()}
          className="mt-4 inline-flex items-center gap-2 whitespace-nowrap shrink-0 rounded-md border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </button>
      </div>
    );
  }

  const counts = summary?.counts ?? {
    totalOffices: 0,
    totalDistributors: 0,
    activeDistributors: 0,
    demoDistributors: 0,
    totalRoutePlans: 0,
    scheduledOrCompletedPlans: 0,
    totalScheduledVisits: 0,
    avgDistanceKm: null,
    avgDurationMinutes: null,
  };

  const isEmptyWorkspace = counts.totalDistributors === 0 && counts.totalRoutePlans === 0;

  return (
    <div className="space-y-6">
      {isEmptyWorkspace && (
        <div className="rounded-lg border border-blue-200 bg-white p-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                Empty Workspace — Load Karachi Sample Data
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Load the Karachi 9-distributor dataset to evaluate route planning, scheduling, and delay prediction.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={handleLoadDemo}
                disabled={demoBusy}
                className="whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {demoBusy ? 'Loading Demo...' : 'Load Demo Data'}
              </button>
              <button
                type="button"
                onClick={() => navigate('/distributors')}
                className="whitespace-nowrap shrink-0 rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Add Distributor
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 4-Column Compact KPI Strip */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-500">Active Distributors</p>
            <Store className="h-4 w-4 text-blue-600" />
          </div>
          <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
            {counts.activeDistributors}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {counts.totalDistributors} total · {counts.totalOffices ?? 0} office hub
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-500">Route Plans</p>
            <Route className="h-4 w-4 text-emerald-600" />
          </div>
          <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
            {counts.totalRoutePlans}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500">
            {counts.scheduledOrCompletedPlans} optimized tours saved
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-500">Avg. Tour Distance</p>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">Road</span>
          </div>
          <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
            {counts.avgDistanceKm !== null ? `${counts.avgDistanceKm} km` : '—'}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500">Across saved plans</p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-slate-500">Scheduled Visits</p>
            <span className="rounded bg-indigo-50 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-indigo-700">CSP</span>
          </div>
          <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
            {counts.totalScheduledVisits ?? 0}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-500">With verified travel buffers</p>
        </div>
      </div>

      {/* Central Map-First Display */}
      <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Karachi Field Operations Map</h2>
            <p className="text-xs text-slate-500">
              {latestPlanDetail
                ? `Showing active route for: ${latestPlanDetail.plan.name} (${latestPlanDetail.plan.total_distance_km} km · ${latestPlanDetail.plan.total_duration_minutes} min)`
                : 'Showing central base office and registered distributor network in Karachi.'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/optimizer')}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-blue-700"
            >
              <Play className="h-3.5 w-3.5" />
              Quick Optimize Route
            </button>
          </div>
        </div>

        <div className="overflow-hidden rounded-md border border-slate-200">
          <LeafletRouteMap
            points={mapPoints}
            routeOrderIds={routeOrderIds}
            encodedPolyline={latestPlanDetail?.plan?.encoded_polyline}
            isLiveTraffic={Boolean(latestPlanDetail?.plan?.is_live_traffic)}
            dataSource={latestPlanDetail?.plan?.data_source}
            height={420}
            title={
              latestPlanDetail
                ? `Active Plan: ${latestPlanDetail.plan.name} (${latestPlanDetail.plan.selected_algorithm || 'A*'})`
                : 'Karachi Distributor Network Map'
            }
          />
        </div>
      </div>

      {/* Main Content Grid: Latest Route Plan & Algorithm Comparison */}
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="rounded-lg border border-slate-200 bg-white p-5 lg:col-span-5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 className="text-base font-semibold text-slate-900">Latest Route Plan</h3>
            <button
              type="button"
              onClick={() => navigate('/optimizer')}
              className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700"
            >
              <Plus className="h-3.5 w-3.5" />
              Create Plan
            </button>
          </div>

          {summary?.latestRoutePlan ? (
            <div className="mt-4 space-y-4">
              <div>
                <p className="text-base font-semibold text-slate-900">
                  {summary.latestRoutePlan.name}
                </p>
                <p className="mt-0.5 text-xs text-slate-500 tabular-nums">
                  {String(summary.latestRoutePlan.plan_date).slice(0, 10)} · Base:{' '}
                  {summary.latestRoutePlan.office_name}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 border-t border-slate-100 pt-3 text-sm">
                <div>
                  <p className="text-xs text-slate-500">Algorithm</p>
                  <p className="mt-0.5 font-mono font-semibold text-slate-900">
                    {summary.latestRoutePlan.selected_algorithm || 'Draft'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Route Distance</p>
                  <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900">
                    {summary.latestRoutePlan.total_distance_km} km
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Est. Road Travel</p>
                  <p className="mt-0.5 font-mono font-semibold tabular-nums text-slate-900">
                    {summary.latestRoutePlan.total_duration_minutes} min
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500">Tour Format</p>
                  <p className="mt-0.5 text-xs font-medium text-slate-900">
                    {summary.latestRoutePlan.return_to_office ? 'Closed Loop' : 'One-Way'}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => navigate('/optimizer?tab=saved')}
                className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium text-slate-800 hover:bg-slate-100"
              >
                Inspect All Saved Plans
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex h-48 flex-col items-center justify-center text-center">
              <p className="text-sm text-slate-600">No route plans saved in database yet.</p>
              <button
                type="button"
                onClick={() => navigate('/optimizer')}
                className="mt-3 rounded-md bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-700"
              >
                Create First Route Plan
              </button>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 lg:col-span-7">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                Algorithm Average Distance Comparison
              </h3>
              <p className="text-xs text-slate-500">
                Performance across recorded algorithm runs (lower km is better)
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate('/analytics')}
              className="text-xs font-medium text-blue-600 hover:text-blue-700"
            >
              Full Insights
            </button>
          </div>

          {summary && summary.algorithmAverages.length > 0 ? (
            <div className="mt-4 h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary.algorithmAverages} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="algorithmName" tick={{ fontSize: 11, fill: '#475569' }} />
                  <YAxis tick={{ fontSize: 11, fill: '#475569' }} unit=" km" />
                  <Tooltip
                    formatter={(val: unknown) => [`${val} km`, 'Avg Distance']}
                    contentStyle={{ fontSize: '12px', borderRadius: '6px', borderColor: '#CBD5E1' }}
                  />
                  <Bar dataKey="avgDistanceKm" fill="#2563EB" radius={[4, 4, 0, 0]} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-56 flex-col items-center justify-center text-center">
              <p className="text-sm text-slate-600">
                Run route optimization to view algorithm comparison metrics.
              </p>
              <button
                type="button"
                onClick={() => navigate('/optimizer')}
                className="mt-3 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
              >
                Open Route Planning
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
