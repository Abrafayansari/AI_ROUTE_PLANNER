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
import { BarChart3, ShieldAlert } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import type { AnalyticsSummary, DatabaseHealth } from '../types';
import { DelayPredictionPage } from './DelayPredictionPage';

interface AnalyticsPageProps {
  onNotify?: (kind: 'success' | 'error', text: string) => void;
  dbHealth?: DatabaseHealth | null;
}

export const AnalyticsPage: React.FC<AnalyticsPageProps> = ({
  onNotify = () => {},
  dbHealth = null,
}) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = searchParams.get('tab') === 'prediction' ? 'prediction' : 'overview';

  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (currentTab !== 'overview') return;
    const load = async () => {
      setLoading(true);
      try {
        const res = await api.getAnalyticsSummary();
        setSummary(res.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to load analytics');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [currentTab]);

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <div className="flex border-b border-slate-200 bg-white px-6 pt-3">
        <button
          type="button"
          onClick={() => setSearchParams({ tab: 'overview' })}
          className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
            currentTab === 'overview'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <BarChart3 className="h-4 w-4" />
          Analytics & Performance Summary
        </button>
        <button
          type="button"
          onClick={() => setSearchParams({ tab: 'prediction' })}
          className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
            currentTab === 'prediction'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <ShieldAlert className="h-4 w-4" />
          Visit Delay Prediction (Bayesian Network)
        </button>
      </div>

      {currentTab === 'prediction' ? (
        <DelayPredictionPage onNotify={onNotify} dbHealth={dbHealth} />
      ) : loading ? (
        <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />
      ) : error || !summary ? (
        <div className="rounded-lg border border-red-200 bg-white p-6 text-sm text-red-700">
          {error || 'No analytics available.'}
        </div>
      ) : (
        <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h3 className="text-base font-semibold text-slate-900">
          Automated Performance Analysis
        </h3>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-slate-700">
          {summary.plainLanguageSummary.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h3 className="text-base font-semibold text-slate-900">
            Average Simulated Route Distance by Algorithm
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            BFS minimizes edges; UCS and A* minimize simulated km; GA searches heuristically.
          </p>
          {summary.algorithmAverages.length > 0 ? (
            <div className="mt-4 h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary.algorithmAverages}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="algorithmName" tick={{ fontSize: 12, fill: '#475569' }} />
                  <YAxis tick={{ fontSize: 12, fill: '#475569' }} unit=" km" />
                  <Tooltip formatter={(v: unknown) => [`${v} km`, 'Avg Sim. Distance']} />
                  <Bar dataKey="avgDistanceKm" fill="#2563EB" radius={[4, 4, 0, 0]} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-10 text-center text-sm text-slate-500">No stored algorithm runs yet.</p>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h3 className="text-base font-semibold text-slate-900">
            Average Nodes Expanded / Evaluated
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            Demonstrates how A*&apos;s admissible heuristic prunes search states compared to UCS.
          </p>
          {summary.algorithmAverages.length > 0 ? (
            <div className="mt-4 h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary.algorithmAverages}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="algorithmName" tick={{ fontSize: 12, fill: '#475569' }} />
                  <YAxis tick={{ fontSize: 12, fill: '#475569' }} />
                  <Tooltip formatter={(v: unknown) => [`${v}`, 'Avg Nodes Expanded']} />
                  <Bar dataKey="avgNodesExpanded" fill="#0D9488" radius={[4, 4, 0, 0]} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-10 text-center text-sm text-slate-500">No stored algorithm runs yet.</p>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h3 className="text-base font-semibold text-slate-900">Latest K-Means Cluster Sizes</h3>
          {summary.latestClusters.length > 0 ? (
            <div className="mt-4 h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={summary.latestClusters}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="clusterLabel" tick={{ fontSize: 12, fill: '#475569' }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#475569' }} />
                  <Tooltip formatter={(v: unknown) => [`${v} distributors`, 'Cluster Size']} />
                  <Bar dataKey="size" fill="#4F46E5" radius={[4, 4, 0, 0]} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="mt-6 text-sm text-slate-500">
              No K-Means clustering results saved yet.
            </p>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h3 className="text-base font-semibold text-slate-900">
            Latest CSP Schedule Coverage
          </h3>
          {summary.scheduleSummary.hasRun ? (
            <div className="mt-4 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-md border border-slate-200 p-4">
                  <p className="text-xs text-slate-500">Scheduled Visits</p>
                  <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-emerald-700">
                    {summary.scheduleSummary.scheduledCount}
                  </p>
                </div>
                <div className="rounded-md border border-slate-200 p-4">
                  <p className="text-xs text-slate-500">Remaining Unscheduled Active</p>
                  <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-amber-700">
                    {summary.scheduleSummary.remainingActiveCount}
                  </p>
                </div>
              </div>
              <p className="text-xs text-slate-600">
                Schedule date: <span className="font-mono">{summary.scheduleSummary.scheduleDate}</span>
              </p>
            </div>
          ) : (
            <p className="mt-6 text-sm text-slate-500">
              No CSP schedule saved yet. Run the Visit Scheduling page to generate one.
            </p>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h3 className="text-base font-semibold text-slate-900">
          Bayesian Delay Risk Prediction Summary
        </h3>
        {summary.delayPredictionSummary && summary.delayPredictionSummary.totalPredictions > 0 ? (
          <div className="mt-4 grid gap-4 sm:grid-cols-4">
            <div className="rounded-md border border-slate-200 p-4">
              <p className="text-xs text-slate-500">Saved Evaluations</p>
              <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-slate-900">
                {summary.delayPredictionSummary.totalPredictions}
              </p>
            </div>
            <div className="rounded-md border border-emerald-200 bg-emerald-50/40 p-4">
              <p className="text-xs text-emerald-800">Low Risk</p>
              <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-emerald-700">
                {summary.delayPredictionSummary.lowRiskCount}
              </p>
            </div>
            <div className="rounded-md border border-amber-200 bg-amber-50/40 p-4">
              <p className="text-xs text-amber-800">Medium Risk</p>
              <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-amber-700">
                {summary.delayPredictionSummary.mediumRiskCount}
              </p>
            </div>
            <div className="rounded-md border border-red-200 bg-red-50/40 p-4">
              <p className="text-xs text-red-800">High Risk</p>
              <p className="mt-1 font-mono text-2xl font-semibold tabular-nums text-red-700">
                {summary.delayPredictionSummary.highRiskCount}
              </p>
            </div>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            No Bayesian delay predictions saved yet. Evaluate a route plan on Visit Delay Prediction or save an optimized route plan.
          </p>
        )}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-6 py-4">
          <h3 className="text-base font-semibold text-slate-900">Algorithm Performance Breakdown</h3>
        </div>
        {summary.algorithmAverages.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
                <tr>
                  <th className="px-6 py-3">Algorithm</th>
                  <th className="px-4 py-3 text-right">Runs</th>
                  <th className="px-4 py-3 text-right">Avg Sim. Distance</th>
                  <th className="px-4 py-3 text-right">Avg Sim. Travel</th>
                  <th className="px-4 py-3 text-right">Avg Nodes Expanded</th>
                  <th className="px-6 py-3 text-right">Avg Exec Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {summary.algorithmAverages.map((row) => (
                  <tr key={row.algorithmName}>
                    <td className="px-6 py-3 font-mono font-semibold text-slate-900">
                      {row.algorithmName}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700">
                      {row.runCount}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-900">
                      {row.avgDistanceKm} km
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700">
                      {row.avgDurationMinutes} min
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-slate-700">
                      {row.avgNodesExpanded.toLocaleString()}
                    </td>
                    <td className="px-6 py-3 text-right font-mono tabular-nums text-slate-700">
                      {row.avgExecutionMs} ms
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-6 text-sm text-slate-500">No stored algorithm data yet.</div>
        )}
      </div>
        </div>
      )}
    </div>
  );
};
