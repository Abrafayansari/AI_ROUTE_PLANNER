import React, { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ArrowRight, Database, Plus, RefreshCw } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import type { AnalyticsSummary, DatabaseHealth } from '../types';

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);

  const loadSummary = async () => {
    if (!dbHealth?.connected || !dbHealth?.schemaReady) {
      setLoading(false);
      setSummary(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.getAnalyticsSummary();
      setSummary(res.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load dashboard summary');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSummary();
  }, [dbHealth?.connected, dbHealth?.schemaReady]);

  const handleLoadDemo = async () => {
    setDemoBusy(true);
    try {
      const res = await api.loadDemoData();
      onNotify('success', res.message || 'Demo dataset loaded.');
      await loadSummary();
      onRefreshHealth();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to load demo data');
    } finally {
      setDemoBusy(false);
    }
  };

  if (!dbHealth?.connected || !dbHealth?.schemaReady) {
    return (
      <div className="space-y-6">
        <div className="rounded-lg border border-amber-200 bg-white p-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1.5">
              <h2 className="text-lg font-semibold text-slate-900">
                Neon PostgreSQL Connection Required
              </h2>
              <p className="max-w-2xl text-sm text-slate-600">
                {dbHealth?.message ||
                  'Configure your rotated Neon pooled PostgreSQL connection string as DATABASE_URL in server-side Secrets, then verify the schema.'}
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
          <h3 className="text-base font-semibold text-slate-900">Workspace Capabilities</h3>
          <p className="mt-1 text-sm text-slate-600">
            Once connected to PostgreSQL, the Python Flask backend runs all search, clustering, scheduling, and Bayesian inference algorithms server-side with zero external routing APIs.
          </p>
          <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="border-t border-slate-100 pt-3">
              <p className="text-sm font-semibold text-slate-900">Week 3 & 4 · Search & Routing</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Compare unweighted BFS, uninformed Uniform Cost Search (UCS), and informed A* with an admissible MST lower-bound heuristic.
              </p>
            </div>
            <div className="border-t border-slate-100 pt-3">
              <p className="text-sm font-semibold text-slate-900">Week 5 & 7 · CSP & Genetic Search</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Schedule time-windowed visits via backtracking CSP and search larger distributor permutations via an elitist Genetic Algorithm.
              </p>
            </div>
            <div className="border-t border-slate-100 pt-3">
              <p className="text-sm font-semibold text-slate-900">Week 12 & 14 · K-Means & Bayesian Net</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                Partition distributor coordinates into geographic clusters on Leaflet/SVG maps and estimate visit delay risk via exact Bayesian inference.
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
        <div className="h-72 animate-pulse rounded-lg border border-slate-200 bg-white p-6" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-white p-6">
        <p className="text-sm font-semibold text-red-700">Failed to load dashboard metrics</p>
        <p className="mt-1 text-sm text-slate-600">{error}</p>
        <button
          type="button"
          onClick={() => void loadSummary()}
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
                Empty Workspace — Start With Sample Data or Your Own Records
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                Your database is connected and initialized with zero rows. Load the Karachi 9-distributor demo dataset or create your own office and distributors.
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

      {/* 4-Column KPI Strip */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium text-slate-500">Active Distributors</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-slate-900">
            {counts.activeDistributors}
          </p>
          <p className="mt-1 text-xs text-slate-500 tabular-nums">
            {counts.totalDistributors} total · {counts.totalOffices ?? 0} office(s) · {counts.demoDistributors} demo
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium text-slate-500">Route Plans Created</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-slate-900">
            {counts.totalRoutePlans}
          </p>
          <p className="mt-1 text-xs text-slate-500 tabular-nums">
            {counts.scheduledOrCompletedPlans} optimized · {counts.totalScheduledVisits ?? 0} scheduled visits
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium text-slate-500">Avg. Route Distance</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-slate-900">
            {counts.avgDistanceKm !== null ? `${counts.avgDistanceKm} km` : '—'}
          </p>
          <p className="mt-1 text-xs text-slate-500">Saved route plan average</p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium text-slate-500">Delay Risk Predictions</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-slate-900">
            {summary?.delayPredictionSummary?.totalPredictions ?? 0}
          </p>
          <p className="mt-1 text-xs text-slate-500 tabular-nums">
            {summary?.delayPredictionSummary
              ? `${summary.delayPredictionSummary.lowRiskCount} Low · ${summary.delayPredictionSummary.mediumRiskCount} Med · ${summary.delayPredictionSummary.highRiskCount} High`
              : counts.avgDurationMinutes !== null
                ? `${counts.avgDurationMinutes} min avg travel`
                : 'No evaluations yet'}
          </p>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-12">
        <div className="rounded-lg border border-slate-200 bg-white p-6 lg:col-span-5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <h3 className="text-base font-semibold text-slate-900">Latest Route Plan</h3>
            <button
              type="button"
              onClick={() => navigate('/optimizer')}
              className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 text-xs font-medium text-blue-600 hover:text-blue-700"
            >
              <Plus className="h-3.5 w-3.5" />
              Create Route Plan
            </button>
          </div>

          {summary?.latestRoutePlan ? (
            <div className="mt-4 space-y-4">
              <div>
                <p className="text-base font-semibold text-slate-900">
                  {summary.latestRoutePlan.name}
                </p>
                <p className="mt-1 text-xs text-slate-500 tabular-nums">
                  {String(summary.latestRoutePlan.plan_date).slice(0, 10)} · Base:{' '}
                  {summary.latestRoutePlan.office_name} · Status: {summary.latestRoutePlan.status}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4 border-t border-slate-100 pt-4 text-sm">
                <div>
                  <p className="text-xs text-slate-500">Selected Algorithm</p>
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
                  <p className="text-xs text-slate-500">Return to Office</p>
                  <p className="mt-0.5 font-medium text-slate-900">
                    {summary.latestRoutePlan.return_to_office ? 'Yes (Closed Tour)' : 'No (One-Way)'}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => navigate(`/saved-plans/${summary.latestRoutePlan!.id}`)}
                className="inline-flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100"
              >
                Inspect Route Details
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <div className="flex h-48 flex-col items-center justify-center text-center">
              <p className="text-sm text-slate-600">No route plans saved in database yet.</p>
              <button
                type="button"
                onClick={() => navigate('/optimizer')}
                className="mt-3 whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                Create Route Plan
              </button>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6 lg:col-span-7">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                Algorithm Average Distance Comparison
              </h3>
              <p className="text-xs text-slate-500">
                Aggregated across stored runs (lower road km is better; BFS minimizes hops, not km)
              </p>
            </div>
            <button
              type="button"
              onClick={() => navigate('/analytics')}
              className="whitespace-nowrap shrink-0 text-xs font-medium text-blue-600 hover:text-blue-700"
            >
              Full Report
            </button>
          </div>

          {summary && summary.algorithmAverages.length > 0 ? (
            <div className="mt-4 h-60 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary.algorithmAverages} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="algorithmName" tick={{ fontSize: 12, fill: '#475569' }} />
                  <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit=" km" />
                  <Tooltip
                    formatter={(val: unknown) => [`${val} km`, 'Avg Route Distance']}
                    contentStyle={{ fontSize: '12px', borderRadius: '6px', borderColor: '#CBD5E1' }}
                  />
                  <Bar dataKey="avgDistanceKm" fill="#2563EB" radius={[4, 4, 0, 0]} maxBarSize={52} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-60 flex-col items-center justify-center text-center">
              <p className="text-sm text-slate-600">
                Run BFS, UCS, A*, and Genetic Algorithm on a route plan to view stored performance comparisons.
              </p>
              <button
                type="button"
                onClick={() => navigate('/optimizer')}
                className="mt-3 whitespace-nowrap shrink-0 rounded-md border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Open Route Optimizer
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Recent Algorithm Runs Table */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h3 className="text-base font-semibold text-slate-900">Recent Algorithm Comparisons</h3>
          <span className="text-xs text-slate-500">Stored in `algorithm_runs`</span>
        </div>
        {summary && summary.recentAlgorithmRuns.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
                <tr>
                  <th className="px-6 py-3">Route Plan</th>
                  <th className="px-4 py-3">Algorithm</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3 text-right">Route Dist.</th>
                  <th className="px-4 py-3 text-right">Nodes Expanded</th>
                  <th className="px-6 py-3 text-right">Exec Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {summary.recentAlgorithmRuns.slice(0, 8).map((run) => (
                  <tr key={run.id} className="hover:bg-slate-50/70">
                    <td className="px-6 py-2.5 font-medium text-slate-900">
                      {run.route_plan_name}
                      {run.result_details?.isRecommended && (
                        <span className="ml-2 text-xs font-medium text-emerald-700">
                          · Recommended
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs font-semibold text-slate-800">
                      {run.algorithm_name}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-600">
                      {run.algorithm_name === 'A*'
                        ? 'Informed (MST heuristic)'
                        : run.algorithm_name === 'GENETIC_ALGORITHM'
                          ? 'Evolutionary heuristic'
                          : run.algorithm_name === 'UCS'
                            ? 'Uninformed (least cost)'
                            : 'Uninformed (edge count)'}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-900">
                      {run.total_distance_km ?? 0} km
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-700">
                      {(run.nodes_expanded ?? 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-2.5 text-right font-mono tabular-nums text-slate-700">
                      {run.execution_time_ms ?? 0} ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6 text-sm text-slate-500">
            No algorithm runs saved yet.
          </div>
        )}
      </div>
    </div>
  );
};
