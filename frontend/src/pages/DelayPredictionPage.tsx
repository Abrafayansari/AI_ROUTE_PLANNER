import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  CheckCircle2,
  Clock,
  Database,
  ExternalLink,
  HelpCircle,
  Info,
  RefreshCw,
  Save,
  Search,
  ShieldAlert,
  Sparkles,
  Table as TableIcon,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../services/api';
import type {
  BayesianModelInfo,
  BayesianPrediction,
  CptRow,
  DatabaseHealth,
  RoutePlanSummary,
} from '../types';

interface DelayPredictionPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
  dbHealth: DatabaseHealth | null;
}

export const DelayPredictionPage: React.FC<DelayPredictionPageProps> = ({
  onNotify,
  dbHealth,
}) => {
  const [plans, setPlans] = useState<RoutePlanSummary[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string>('');
  const [predictions, setPredictions] = useState<BayesianPrediction[]>([]);
  const [selectedPrediction, setSelectedPrediction] = useState<BayesianPrediction | null>(null);

  const [modelInfo, setModelInfo] = useState<BayesianModelInfo | null>(null);
  const [cptRows, setCptRows] = useState<CptRow[]>([]);
  const [showCptModal, setShowCptModal] = useState(false);
  const [cptFilter, setCptFilter] = useState('');

  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [history, setHistory] = useState<BayesianPrediction[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // What-If Simulator state (supports 'Unobserved' for Bayesian marginalization)
  const [simDistance, setSimDistance] = useState<'Near' | 'Medium' | 'Far' | 'Unobserved'>('Far');
  const [simDuration, setSimDuration] = useState<'Short' | 'Medium' | 'Long' | 'Unobserved'>('Long');
  const [simTimeSlot, setSimTimeSlot] = useState<'Morning' | 'Afternoon' | 'Unobserved'>('Afternoon');
  const [simPriority, setSimPriority] = useState<'Low' | 'Medium' | 'High' | 'Unobserved'>('High');
  const [simResult, setSimResult] = useState<BayesianPrediction | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [savingSim, setSavingSim] = useState(false);

  const loadHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await api.getPredictionHistory({ limit: 20 });
      setHistory(res.data.items);
    } catch {
      // ignore if DB not yet ready
    } finally {
      setLoadingHistory(false);
    }
  };

  // Load plans, model metadata, and saved history on mount
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        const [plansRes, infoRes, histRes] = await Promise.all([
          api.getRoutePlans(1, 50).catch(() => ({ data: { items: [] } })),
          api.getModelInfo().catch(() => ({ data: null })),
          api.getPredictionHistory({ limit: 20 }).catch(() => ({ data: { items: [] } })),
        ]);

        if (plansRes.data?.items) {
          setPlans(plansRes.data.items);
          if (plansRes.data.items.length > 0) {
            setSelectedPlanId(plansRes.data.items[0].id);
          }
        }
        if (infoRes.data) {
          setModelInfo(infoRes.data);
        }
        if (histRes.data?.items) {
          setHistory(histRes.data.items);
        }
      } catch (err) {
        onNotify('error', err instanceof Error ? err.message : 'Failed to load initial data');
      } finally {
        setLoading(false);
      }
    };
    void init();
  }, []);

  // Evaluate route plan delays whenever selectedPlanId changes
  const evaluateRoutePlan = async (planId: string) => {
    if (!planId) return;
    setEvaluating(true);
    try {
      const res = await api.predictRouteDelay({ routePlanId: planId, saveToDb: true });
      setPredictions(res.data.predictions);
      if (res.data.predictions.length > 0) {
        setSelectedPrediction(res.data.predictions[0]);
      } else {
        setSelectedPrediction(null);
      }
      void loadHistory();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Evaluation failed');
    } finally {
      setEvaluating(false);
    }
  };

  useEffect(() => {
    if (selectedPlanId) {
      void evaluateRoutePlan(selectedPlanId);
    }
  }, [selectedPlanId]);

  const observedSimCount = [simDistance, simDuration, simTimeSlot, simPriority].filter(
    (v) => v !== 'Unobserved'
  ).length;

  const buildSimulationPayload = (saveToDb = false) => {
    const payload: Record<string, unknown> = {
      distributorName: 'What-If Simulation Stop',
      allowPartial: true,
      saveToDb,
    };
    if (simDistance !== 'Unobserved') payload.distanceCategory = simDistance;
    if (simDuration !== 'Unobserved') payload.visitDurationCategory = simDuration;
    if (simTimeSlot !== 'Unobserved') payload.timeSlot = simTimeSlot;
    if (simPriority !== 'Unobserved') payload.priorityCategory = simPriority;
    return payload;
  };

  // Run What-If simulation
  const runSimulation = async () => {
    if (observedSimCount === 0) {
      setSimResult(null);
      return;
    }
    setSimulating(true);
    try {
      const res = await api.predictVisitDelay(buildSimulationPayload(false));
      setSimResult(res.data);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Simulation failed');
    } finally {
      setSimulating(false);
    }
  };

  const handleSaveSimulation = async () => {
    if (observedSimCount === 0) return;
    setSavingSim(true);
    try {
      const res = await api.predictVisitDelay(buildSimulationPayload(true));
      setSimResult(res.data);
      onNotify('success', 'What-If prediction saved to prediction history.');
      await loadHistory();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to save simulation');
    } finally {
      setSavingSim(false);
    }
  };

  useEffect(() => {
    void runSimulation();
  }, [simDistance, simDuration, simTimeSlot, simPriority]);

  // Load CPT on demand
  const handleOpenCpt = async () => {
    setShowCptModal(true);
    if (cptRows.length === 0) {
      try {
        const res = await api.getCptTable();
        setCptRows(res.data.rows);
      } catch (err) {
        onNotify('error', err instanceof Error ? err.message : 'Failed to load CPT');
      }
    }
  };

  const filteredCpt = useMemo(() => {
    if (!cptFilter.trim()) return cptRows;
    const q = cptFilter.toLowerCase();
    return cptRows.filter(
      (r) =>
        r.distance.toLowerCase().includes(q) ||
        r.visitDuration.toLowerCase().includes(q) ||
        r.timeSlot.toLowerCase().includes(q) ||
        r.priority.toLowerCase().includes(q) ||
        r.mostLikely.toLowerCase().includes(q)
    );
  }, [cptRows, cptFilter]);

  // Summary counts
  const summary = useMemo(() => {
    const total = predictions.length;
    const low = predictions.filter((p) => p.predictedRisk === 'Low').length;
    const medium = predictions.filter((p) => p.predictedRisk === 'Medium').length;
    const high = predictions.filter((p) => p.predictedRisk === 'High').length;
    const avgHighProb =
      total > 0
        ? roundVal(
            (predictions.reduce((acc, p) => acc + p.probabilities.High, 0) / total) * 100,
            1
          )
        : 0;

    return { total, low, medium, high, avgHighProb };
  }, [predictions]);

  // Chart data
  const chartData = useMemo(() => {
    return predictions.map((p, idx) => ({
      name: `#${p.stopOrder ?? idx + 1} ${p.distributorName.length > 14 ? p.distributorName.slice(0, 14) + '…' : p.distributorName}`,
      fullName: p.distributorName,
      'Low Risk': roundVal(p.probabilities.Low * 100, 1),
      'Medium Risk': roundVal(p.probabilities.Medium * 100, 1),
      'High Risk': roundVal(p.probabilities.High * 100, 1),
      predictedRisk: p.predictedRisk,
    }));
  }, [predictions]);

  return (
    <div className="space-y-6">
      {/* Educational Banner */}
      <div className="rounded-lg border border-slate-200 bg-white px-5 py-4 text-xs text-slate-700 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded bg-blue-100 text-blue-700 font-bold text-[11px]">
              BN
            </span>
            <span className="font-semibold text-slate-900">
              Bayesian Network — Distributor Visit Delay Prediction
            </span>
            <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-[11px] text-slate-600">
              Model v{modelInfo?.modelVersion || '1.0.0-illustrative'}
            </span>
          </div>
          <button
            type="button"
            onClick={handleOpenCpt}
            className="inline-flex items-center gap-1.5 font-medium text-blue-600 hover:text-blue-700"
          >
            <TableIcon className="h-3.5 w-3.5" />
            Inspect 54-Row CPT Table
          </button>
        </div>
        <p className="leading-relaxed text-slate-600">
          This module estimates the posterior probability distribution{' '}
          <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">
            P(Delay Risk = Low, Medium, High | Distance, Duration, Time Slot, Priority)
          </code>{' '}
          using formal discrete Bayesian inference. Predictions are advisory and help sales field
          officers allocate buffer times before finalizing schedules.
        </p>
      </div>

      {/* Plan Selector & Action Bar */}
      <div className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium text-slate-700">Select Route Plan:</label>
          <select
            value={selectedPlanId}
            onChange={(e) => setSelectedPlanId(e.target.value)}
            disabled={evaluating || plans.length === 0}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
          >
            {plans.length === 0 && <option value="">No saved route plans in database</option>}
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({String(p.plan_date).slice(0, 10)})
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={() => evaluateRoutePlan(selectedPlanId)}
            disabled={evaluating || !selectedPlanId}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${evaluating ? 'animate-spin' : ''}`} />
            Re-evaluate
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
          <span>Validated Probability Distribution (Sums to 1.0)</span>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium text-slate-500">Evaluated Visits</p>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-slate-900">
            {summary.total}
          </p>
          <p className="mt-1 text-xs text-slate-500">Stops along selected route</p>
        </div>

        <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-emerald-800">Low Delay Risk</p>
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800">
              Green
            </span>
          </div>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-emerald-900">
            {summary.low}
          </p>
          <p className="mt-1 text-xs text-emerald-700">Near distance & short visits</p>
        </div>

        <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-amber-800">Medium Delay Risk</p>
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800">
              Amber
            </span>
          </div>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-amber-900">
            {summary.medium}
          </p>
          <p className="mt-1 text-xs text-amber-700">Moderate transit / duration</p>
        </div>

        <div className="rounded-lg border border-red-200 bg-red-50/50 p-5">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-red-800">High Delay Risk</p>
            <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-800">
              Red
            </span>
          </div>
          <p className="mt-2 font-mono text-2xl font-semibold tabular-nums text-red-900">
            {summary.high}
          </p>
          <p className="mt-1 text-xs text-red-700">
            Avg High Prob: {summary.avgHighProb}%
          </p>
        </div>
      </div>

      {/* Main Grid: Prediction Table & Detail Card */}
      <div className="grid gap-6 lg:grid-cols-12">
        {/* Prediction Table */}
        <div className="rounded-lg border border-slate-200 bg-white lg:col-span-8">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-100 px-5 py-3.5">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Route Stop Delay Risk Table
              </h3>
              <p className="text-xs text-slate-500">
                Select a distributor stop to inspect evidence and Bayesian inference calculation
              </p>
            </div>
            <span className="text-xs text-slate-500">{predictions.length} stops evaluated</span>
          </div>

          {predictions.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500">
              {evaluating
                ? 'Running Bayesian inference on route stops...'
                : 'No evaluated stops found for this route plan. Select a route plan with stops.'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-3.5 py-2.5">Stop</th>
                    <th className="px-3.5 py-2.5">Distributor</th>
                    <th className="px-3 py-2.5">Distance</th>
                    <th className="px-3 py-2.5">Duration</th>
                    <th className="px-3 py-2.5">Time Slot</th>
                    <th className="px-3 py-2.5">Priority</th>
                    <th className="px-3 py-2.5 text-right">P(Low)</th>
                    <th className="px-3 py-2.5 text-right">P(Med)</th>
                    <th className="px-3 py-2.5 text-right">P(High)</th>
                    <th className="px-3.5 py-2.5">Predicted Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {predictions.map((p, idx) => {
                    const isSelected =
                      selectedPrediction?.distributorId === p.distributorId ||
                      (selectedPrediction?.stopOrder === p.stopOrder && p.stopOrder !== undefined);
                    const evidence = p.evidence ?? {
                      distanceCategory: p.distanceCategory ?? 'Near',
                      visitDurationCategory: p.visitDurationCategory ?? 'Medium',
                      timeSlot: p.timeSlot ?? 'Morning',
                      priorityCategory: p.priorityCategory ?? 'Medium',
                    };

                    return (
                      <tr
                        key={p.id ?? `${p.distributorId}-${idx}`}
                        onClick={() => setSelectedPrediction(p)}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? 'bg-blue-50/80 font-medium' : 'hover:bg-slate-50'
                        }`}
                      >
                        <td className="px-3.5 py-2.5 font-mono font-semibold text-slate-700">
                          #{p.stopOrder ?? idx + 1}
                        </td>
                        <td className="px-3.5 py-2.5 font-medium text-slate-900">
                          {p.distributorName}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="font-mono text-slate-800">
                            {p.distanceKm !== null && p.distanceKm !== undefined
                              ? `${p.distanceKm} km`
                              : '—'}
                          </span>{' '}
                          <span
                            className={`ml-1 rounded px-1.5 py-0.5 text-[10px] ${
                              evidence.distanceCategory === 'Far'
                                ? 'bg-red-100 text-red-800'
                                : evidence.distanceCategory === 'Medium'
                                  ? 'bg-amber-100 text-amber-800'
                                  : evidence.distanceCategory === 'Unobserved'
                                    ? 'bg-slate-100 text-slate-500'
                                    : 'bg-emerald-100 text-emerald-800'
                            }`}
                          >
                            {evidence.distanceCategory}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="font-mono text-slate-800">
                            {p.visitDurationMinutes ?? 30}m
                          </span>{' '}
                          <span
                            className={`ml-1 rounded px-1.5 py-0.5 text-[10px] ${
                              evidence.visitDurationCategory === 'Long'
                                ? 'bg-red-100 text-red-800'
                                : evidence.visitDurationCategory === 'Medium'
                                  ? 'bg-amber-100 text-amber-800'
                                  : evidence.visitDurationCategory === 'Unobserved'
                                    ? 'bg-slate-100 text-slate-500'
                                    : 'bg-emerald-100 text-emerald-800'
                            }`}
                          >
                            {evidence.visitDurationCategory}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                              evidence.timeSlot === 'Afternoon'
                                ? 'bg-amber-100 text-amber-800'
                                : evidence.timeSlot === 'Unobserved'
                                  ? 'bg-slate-100 text-slate-500'
                                  : 'bg-blue-100 text-blue-800'
                            }`}
                          >
                            {evidence.timeSlot}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700">
                            {evidence.priorityCategory}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums text-emerald-700">
                          {roundVal(p.probabilities.Low * 100, 1)}%
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums text-amber-700">
                          {roundVal(p.probabilities.Medium * 100, 1)}%
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono font-semibold tabular-nums text-red-700">
                          {roundVal(p.probabilities.High * 100, 1)}%
                        </td>
                        <td className="px-3.5 py-2.5">
                          <span
                            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                              p.predictedRisk === 'High'
                                ? 'bg-red-100 text-red-800'
                                : p.predictedRisk === 'Medium'
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-emerald-100 text-emerald-800'
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                p.predictedRisk === 'High'
                                  ? 'bg-red-600'
                                  : p.predictedRisk === 'Medium'
                                    ? 'bg-amber-600'
                                    : 'bg-emerald-600'
                              }`}
                            />
                            {p.predictedRisk}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Selected Stop Details & Directed Graph Panel */}
        <div className="space-y-6 lg:col-span-4">
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <h3 className="text-sm font-semibold text-slate-900 border-b border-slate-100 pb-3">
              Bayesian Evidence & Explanation
            </h3>

            {selectedPrediction ? (
              <div className="mt-4 space-y-4 text-xs">
                <div>
                  <span className="text-slate-500">Selected Distributor</span>
                  <p className="text-sm font-semibold text-slate-900">
                    {selectedPrediction.distributorName}
                  </p>
                  <p className="text-[11px] text-slate-500 font-mono">
                    Stop #{selectedPrediction.stopOrder ?? '1'} · Route Plan Stop
                  </p>
                </div>

                {/* Evidence Variables List */}
                <div className="rounded-md border border-slate-100 bg-slate-50/70 p-3 space-y-2">
                  <p className="font-semibold text-slate-800 text-[11px]">Parent Evidence Nodes:</p>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      <span className="text-slate-500">Distance:</span>
                      <p className="font-medium text-slate-900">
                        {selectedPrediction.evidence?.distanceCategory ??
                          selectedPrediction.distanceCategory}
                        {selectedPrediction.distanceKm !== null &&
                        selectedPrediction.distanceKm !== undefined
                          ? ` (${selectedPrediction.distanceKm} km)`
                          : ''}
                      </p>
                    </div>
                    <div>
                      <span className="text-slate-500">Visit Duration:</span>
                      <p className="font-medium text-slate-900">
                        {selectedPrediction.evidence?.visitDurationCategory ??
                          selectedPrediction.visitDurationCategory}
                        {selectedPrediction.visitDurationMinutes
                          ? ` (${selectedPrediction.visitDurationMinutes} min)`
                          : ''}
                      </p>
                    </div>
                    <div>
                      <span className="text-slate-500">Time Slot:</span>
                      <p className="font-medium text-slate-900">
                        {selectedPrediction.evidence?.timeSlot ?? selectedPrediction.timeSlot}
                      </p>
                    </div>
                    <div>
                      <span className="text-slate-500">Priority:</span>
                      <p className="font-medium text-slate-900">
                        {selectedPrediction.evidence?.priorityCategory ??
                          selectedPrediction.priorityCategory}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Bayesian Network Mini DAG Visualizer */}
                <div className="rounded-md border border-slate-200 bg-white p-3">
                  <p className="font-semibold text-slate-800 text-[11px] mb-2">
                    Network Dependency Structure:
                  </p>
                  <svg viewBox="0 0 280 140" className="w-full h-auto">
                    <defs>
                      <marker
                        id="arrow"
                        viewBox="0 0 10 10"
                        refX="8"
                        refY="5"
                        markerWidth="5"
                        markerHeight="5"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748B" />
                      </marker>
                    </defs>

                    {/* Parent nodes */}
                    <g transform="translate(10, 10)">
                      <rect
                        width="80"
                        height="22"
                        rx="4"
                        fill="#EFF6FF"
                        stroke="#3B82F6"
                        strokeWidth="1.2"
                      />
                      <text x="40" y="14" textAnchor="middle" fontSize="9" fill="#1E3A8A">
                        Distance:{' '}
                        {selectedPrediction.evidence?.distanceCategory ??
                          selectedPrediction.distanceCategory}
                      </text>
                    </g>

                    <g transform="translate(10, 42)">
                      <rect
                        width="80"
                        height="22"
                        rx="4"
                        fill="#EFF6FF"
                        stroke="#3B82F6"
                        strokeWidth="1.2"
                      />
                      <text x="40" y="14" textAnchor="middle" fontSize="9" fill="#1E3A8A">
                        Duration:{' '}
                        {selectedPrediction.evidence?.visitDurationCategory ??
                          selectedPrediction.visitDurationCategory}
                      </text>
                    </g>

                    <g transform="translate(10, 74)">
                      <rect
                        width="80"
                        height="22"
                        rx="4"
                        fill="#EFF6FF"
                        stroke="#3B82F6"
                        strokeWidth="1.2"
                      />
                      <text x="40" y="14" textAnchor="middle" fontSize="9" fill="#1E3A8A">
                        Time:{' '}
                        {selectedPrediction.evidence?.timeSlot ?? selectedPrediction.timeSlot}
                      </text>
                    </g>

                    <g transform="translate(10, 106)">
                      <rect
                        width="80"
                        height="22"
                        rx="4"
                        fill="#EFF6FF"
                        stroke="#3B82F6"
                        strokeWidth="1.2"
                      />
                      <text x="40" y="14" textAnchor="middle" fontSize="9" fill="#1E3A8A">
                        Priority:{' '}
                        {selectedPrediction.evidence?.priorityCategory ??
                          selectedPrediction.priorityCategory}
                      </text>
                    </g>

                    {/* Connecting arrows to DelayRisk */}
                    <line x1="90" y1="21" x2="175" y2="65" stroke="#94A3B8" strokeWidth="1.2" markerEnd="url(#arrow)" />
                    <line x1="90" y1="53" x2="175" y2="68" stroke="#94A3B8" strokeWidth="1.2" markerEnd="url(#arrow)" />
                    <line x1="90" y1="85" x2="175" y2="72" stroke="#94A3B8" strokeWidth="1.2" markerEnd="url(#arrow)" />
                    <line x1="90" y1="117" x2="175" y2="75" stroke="#94A3B8" strokeWidth="1.2" markerEnd="url(#arrow)" />

                    {/* Target Node */}
                    <g transform="translate(180, 50)">
                      <rect
                        width="90"
                        height="40"
                        rx="6"
                        fill={
                          selectedPrediction.predictedRisk === 'High'
                            ? '#FEF2F2'
                            : selectedPrediction.predictedRisk === 'Medium'
                              ? '#FFFBEB'
                              : '#F0FDF4'
                        }
                        stroke={
                          selectedPrediction.predictedRisk === 'High'
                            ? '#EF4444'
                            : selectedPrediction.predictedRisk === 'Medium'
                              ? '#F59E0B'
                              : '#10B981'
                        }
                        strokeWidth="1.5"
                      />
                      <text x="45" y="17" textAnchor="middle" fontSize="10" fontWeight="bold" fill="#0F172A">
                        Delay Risk
                      </text>
                      <text
                        x="45"
                        y="32"
                        textAnchor="middle"
                        fontSize="11"
                        fontWeight="bold"
                        fill={
                          selectedPrediction.predictedRisk === 'High'
                            ? '#B91C1C'
                            : selectedPrediction.predictedRisk === 'Medium'
                              ? '#B45309'
                              : '#047857'
                        }
                      >
                        {selectedPrediction.predictedRisk}
                      </text>
                    </g>
                  </svg>
                </div>

                {/* Posterior Probability Bars */}
                <div className="space-y-2">
                  <p className="font-semibold text-slate-800 text-[11px]">
                    Posterior Probability Distribution:
                  </p>
                  <div>
                    <div className="flex justify-between text-[11px] mb-0.5">
                      <span className="text-emerald-800 font-medium">P(Low Risk)</span>
                      <span className="font-mono tabular-nums">
                        {roundVal(selectedPrediction.probabilities.Low * 100, 1)}%
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full"
                        style={{ width: `${selectedPrediction.probabilities.Low * 100}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-0.5">
                      <span className="text-amber-800 font-medium">P(Medium Risk)</span>
                      <span className="font-mono tabular-nums">
                        {roundVal(selectedPrediction.probabilities.Medium * 100, 1)}%
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full bg-amber-500 rounded-full"
                        style={{ width: `${selectedPrediction.probabilities.Medium * 100}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-[11px] mb-0.5">
                      <span className="text-red-800 font-medium">P(High Risk)</span>
                      <span className="font-mono tabular-nums font-semibold">
                        {roundVal(selectedPrediction.probabilities.High * 100, 1)}%
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className="h-full bg-red-500 rounded-full"
                        style={{ width: `${selectedPrediction.probabilities.High * 100}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* Explanation */}
                {selectedPrediction.explanation && (
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-700">
                    <p className="font-semibold text-slate-900 mb-1">Inference Explanation:</p>
                    <p>{selectedPrediction.explanation}</p>
                  </div>
                )}

                {/* Recommendation */}
                {selectedPrediction.recommendation && (
                  <div
                    className={`rounded-md border p-3 text-[11px] leading-relaxed ${
                      selectedPrediction.predictedRisk === 'High'
                        ? 'border-red-200 bg-red-50 text-red-900'
                        : 'border-amber-200 bg-amber-50 text-amber-900'
                    }`}
                  >
                    <p className="font-semibold mb-0.5">Field Officer Advisory:</p>
                    <p>{selectedPrediction.recommendation}</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-4 text-xs text-slate-500">
                Select a stop in the table to inspect its Bayesian Network calculation.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Probability Chart Across All Route Stops */}
      {chartData.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Posterior Delay Probability Distribution Across Route Stops
              </h3>
              <p className="text-xs text-slate-500">
                Visualizing Bayesian risk breakdown for each scheduled stop along the route
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1 text-emerald-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" /> Low
              </span>
              <span className="flex items-center gap-1 text-amber-700">
                <span className="h-2 w-2 rounded-full bg-amber-500" /> Medium
              </span>
              <span className="flex items-center gap-1 text-red-700">
                <span className="h-2 w-2 rounded-full bg-red-500" /> High
              </span>
            </div>
          </div>
          <div className="mt-4 h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#475569' }} />
                <YAxis unit="%" domain={[0, 100]} tick={{ fontSize: 11, fill: '#475569' }} />
                <Tooltip
                  formatter={(val: unknown) => [`${val}%`, '']}
                  labelFormatter={(label: unknown, payload: readonly any[]) => {
                    const row = payload?.[0]?.payload;
                    return row ? `${row.fullName} (${row.predictedRisk} Risk)` : String(label ?? '');
                  }}
                  contentStyle={{ fontSize: '12px', borderRadius: '6px' }}
                />
                <Bar dataKey="Low Risk" fill="#10B981" stackId="a" />
                <Bar dataKey="Medium Risk" fill="#F59E0B" stackId="a" />
                <Bar dataKey="High Risk" fill="#EF4444" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Interactive What-If Bayesian Scenario Simulator */}
      <div className="rounded-lg border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-blue-600" />
            <h3 className="text-sm font-semibold text-slate-900">
              Interactive What-If Scenario Simulator (Full &amp; Partial Evidence)
            </h3>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">
              Set any variable to Unobserved to marginalize using priors
            </span>
            <button
              type="button"
              onClick={handleSaveSimulation}
              disabled={savingSim || observedSimCount === 0}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              <Save className="h-3.5 w-3.5" />
              {savingSim ? 'Saving...' : 'Save to History'}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-6 md:grid-cols-12">
          {/* Controls */}
          <div className="grid grid-cols-2 gap-3 md:col-span-6">
            <div>
              <label className="block text-xs font-medium text-slate-700">Transit Distance</label>
              <select
                value={simDistance}
                onChange={(e) => setSimDistance(e.target.value as 'Near' | 'Medium' | 'Far' | 'Unobserved')}
                className="mt-1 w-full rounded border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900"
              >
                <option value="Near">Near (&lt; 5 km)</option>
                <option value="Medium">Medium (5–15 km)</option>
                <option value="Far">Far (&gt; 15 km)</option>
                <option value="Unobserved">Unobserved (Marginalize)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700">Expected Duration</label>
              <select
                value={simDuration}
                onChange={(e) => setSimDuration(e.target.value as 'Short' | 'Medium' | 'Long' | 'Unobserved')}
                className="mt-1 w-full rounded border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900"
              >
                <option value="Short">Short (&lt; 30 min)</option>
                <option value="Medium">Medium (30–59 min)</option>
                <option value="Long">Long (&gt;= 60 min)</option>
                <option value="Unobserved">Unobserved (Marginalize)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700">Scheduled Time</label>
              <select
                value={simTimeSlot}
                onChange={(e) => setSimTimeSlot(e.target.value as 'Morning' | 'Afternoon' | 'Unobserved')}
                className="mt-1 w-full rounded border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900"
              >
                <option value="Morning">Morning (&lt; 12:30)</option>
                <option value="Afternoon">Afternoon (&gt;= 12:30)</option>
                <option value="Unobserved">Unobserved (Marginalize)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700">Distributor Priority</label>
              <select
                value={simPriority}
                onChange={(e) => setSimPriority(e.target.value as 'Low' | 'Medium' | 'High' | 'Unobserved')}
                className="mt-1 w-full rounded border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-900"
              >
                <option value="Low">Low (Priority 1–2)</option>
                <option value="Medium">Medium (Priority 3)</option>
                <option value="High">High (Priority 4–5)</option>
                <option value="Unobserved">Unobserved (Marginalize)</option>
              </select>
            </div>
          </div>

          {/* Result Card */}
          <div className="rounded-lg border border-slate-100 bg-slate-50 p-4 md:col-span-6 flex flex-col justify-between">
            {observedSimCount === 0 ? (
              <div className="flex h-full items-center justify-center text-center text-xs text-slate-600">
                Select at least one observed evidence variable (Distance, Duration, Time Slot, or Priority) to compute a posterior probability distribution.
              </div>
            ) : (
              <>
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs text-slate-500 font-medium">
                      {simulating
                        ? 'Computing Posterior...'
                        : simResult?.isPartialEvidence
                          ? `Marginalized over: ${simResult.marginalizedVariables?.join(', ')}`
                          : 'Computed Posterior (Full Evidence)'}
                    </span>
                    {simResult && (
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                          simResult.predictedRisk === 'High'
                            ? 'bg-red-100 text-red-800'
                            : simResult.predictedRisk === 'Medium'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                        }`}
                      >
                        Predicted: {simResult.predictedRisk} Risk
                      </span>
                    )}
                  </div>

                  {simResult && (
                    <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                      <div className="rounded bg-white p-2 border border-slate-200">
                        <p className="text-[10px] text-slate-500 font-medium">P(Low)</p>
                        <p className="mt-1 font-mono text-base font-bold text-emerald-700">
                          {roundVal(simResult.probabilities.Low * 100, 1)}%
                        </p>
                      </div>
                      <div className="rounded bg-white p-2 border border-slate-200">
                        <p className="text-[10px] text-slate-500 font-medium">P(Medium)</p>
                        <p className="mt-1 font-mono text-base font-bold text-amber-700">
                          {roundVal(simResult.probabilities.Medium * 100, 1)}%
                        </p>
                      </div>
                      <div className="rounded bg-white p-2 border border-slate-200">
                        <p className="text-[10px] text-slate-500 font-medium">P(High)</p>
                        <p className="mt-1 font-mono text-base font-bold text-red-700">
                          {roundVal(simResult.probabilities.High * 100, 1)}%
                        </p>
                      </div>
                    </div>
                  )}
                </div>

                {simResult?.recommendation && (
                  <p className="mt-3 text-xs text-slate-600 border-t border-slate-200 pt-2">
                    <strong>Advisory:</strong> {simResult.recommendation}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Saved Prediction History */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Saved Delay Prediction History</h3>
            <p className="text-xs text-slate-500">
              Recent Bayesian evaluations persisted in `visit_delay_predictions`
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadHistory()}
            disabled={loadingHistory}
            className="inline-flex items-center gap-1.5 rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw className={`h-3 w-3 ${loadingHistory ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
        {history.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">
            No saved predictions in history yet. Evaluate a route plan or click &ldquo;Save to History&rdquo; above.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                <tr>
                  <th className="px-4 py-2.5">Target / Stop</th>
                  <th className="px-3 py-2.5">Evidence (Dist / Dur / Time / Prio)</th>
                  <th className="px-3 py-2.5 text-right">P(Low)</th>
                  <th className="px-3 py-2.5 text-right">P(Med)</th>
                  <th className="px-3 py-2.5 text-right">P(High)</th>
                  <th className="px-4 py-2.5">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {history.map((item, idx) => (
                  <tr key={item.id ?? idx} className="hover:bg-slate-50/70">
                    <td className="px-4 py-2 font-medium text-slate-900">
                      {item.distributorName}
                      {item.routePlanName && (
                        <span className="ml-1.5 text-[11px] font-normal text-slate-500">
                          · {item.routePlanName}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-slate-600">
                      {item.distanceCategory ?? '—'} / {item.visitDurationCategory ?? '—'} /{' '}
                      {item.timeSlot ?? '—'} / {item.priorityCategory ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-emerald-700">
                      {roundVal(item.probabilities.Low * 100, 1)}%
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-amber-700">
                      {roundVal(item.probabilities.Medium * 100, 1)}%
                    </td>
                    <td className="px-3 py-2 text-right font-mono font-semibold text-red-700">
                      {roundVal(item.probabilities.High * 100, 1)}%
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                          item.predictedRisk === 'High'
                            ? 'bg-red-100 text-red-800'
                            : item.predictedRisk === 'Medium'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                        }`}
                      >
                        {item.predictedRisk}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* CPT Inspection Modal */}
      {showCptModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40">
          <div className="flex max-h-[85vh] w-full max-w-4xl flex-col rounded-lg border border-slate-200 bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <div>
                <h3 className="text-base font-semibold text-slate-900">
                  Conditional Probability Table (CPT) — Delay Risk
                </h3>
                <p className="text-xs text-slate-500">
                  Total {cptRows.length} Parent Permutations · Every row sums strictly to 1.0
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCptModal(false)}
                className="rounded-md border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <div className="border-b border-slate-100 px-6 py-3">
              <div className="relative">
                <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter by distance, duration, time slot, priority, or risk..."
                  value={cptFilter}
                  onChange={(e) => setCptFilter(e.target.value)}
                  className="w-full rounded-md border border-slate-200 pl-9 pr-3 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-slate-50 border-b border-slate-200 text-slate-600">
                  <tr>
                    <th className="px-3 py-2">#</th>
                    <th className="px-3 py-2">Distance</th>
                    <th className="px-3 py-2">Visit Duration</th>
                    <th className="px-3 py-2">Time Slot</th>
                    <th className="px-3 py-2">Priority</th>
                    <th className="px-3 py-2 text-right">P(Low)</th>
                    <th className="px-3 py-2 text-right">P(Medium)</th>
                    <th className="px-3 py-2 text-right">P(High)</th>
                    <th className="px-3 py-2 text-center">Sum</th>
                    <th className="px-3 py-2">Most Likely</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredCpt.map((row) => (
                    <tr key={row.id} className="hover:bg-slate-50/70">
                      <td className="px-3 py-2 font-mono text-slate-400">{row.id}</td>
                      <td className="px-3 py-2 font-medium text-slate-900">{row.distance}</td>
                      <td className="px-3 py-2 text-slate-700">{row.visitDuration}</td>
                      <td className="px-3 py-2 text-slate-700">{row.timeSlot}</td>
                      <td className="px-3 py-2 text-slate-700">{row.priority}</td>
                      <td className="px-3 py-2 text-right font-mono text-emerald-700 font-medium">
                        {roundVal(row.pLow * 100, 1)}%
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-amber-700 font-medium">
                        {roundVal(row.pMedium * 100, 1)}%
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-red-700 font-semibold">
                        {roundVal(row.pHigh * 100, 1)}%
                      </td>
                      <td className="px-3 py-2 text-center font-mono text-slate-400">
                        {roundVal((row.pLow + row.pMedium + row.pHigh) * 100, 1)}%
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                            row.mostLikely === 'High'
                              ? 'bg-red-100 text-red-800'
                              : row.mostLikely === 'Medium'
                                ? 'bg-amber-100 text-amber-800'
                                : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {row.mostLikely}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="border-t border-slate-100 px-6 py-3 text-right">
              <button
                type="button"
                onClick={() => setShowCptModal(false)}
                className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

function roundVal(num: number, decimals: number): number {
  const factor = Math.pow(10, decimals);
  return Math.round(num * factor) / factor;
}
