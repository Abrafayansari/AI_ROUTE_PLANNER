import React, { useEffect, useState } from 'react';
import { Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Map as MapIcon, Play, Save, ShieldAlert } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { SchematicMap, type SchematicPoint } from '../components/SchematicMap';
import { LeafletRouteMap } from '../components/LeafletRouteMap';
import type {
  AlgorithmComparisonItem,
  Distributor,
  OfficeLocation,
  OptimizePreviewResponse,
} from '../types';

interface OptimizerPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

const FIXED_DISTANCE_MULTIPLIER = 1;
const FIXED_GRAPH_SEED = 42;
const FIXED_GA_POPULATION_SIZE = 80;
const FIXED_GA_GENERATIONS = 150;
const FIXED_GA_MUTATION_RATE = 0.18;

export const OptimizerPage: React.FC<OptimizerPageProps> = ({ onNotify }) => {
  const navigate = useNavigate();
  const [offices, setOffices] = useState<OfficeLocation[]>([]);
  const [officeId, setOfficeId] = useState<string>('');
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const [planName, setPlanName] = useState('Daily Metro Route');
  const [planDate, setPlanDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [travelMode, setTravelMode] = useState<'simulated_vehicle' | 'simulated_van' | 'simulated_walking'>('simulated_vehicle');
  const [returnToOffice, setReturnToOffice] = useState(true);

  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);

  const [preview, setPreview] = useState<OptimizePreviewResponse | null>(null);
  const [activeAlgo, setActiveAlgo] = useState<'BFS' | 'UCS' | 'A*' | 'GENETIC_ALGORITHM'>('A*');
  const [mapViewMode, setMapViewMode] = useState<'schematic' | 'leaflet'>('leaflet');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [offRes, distRes] = await Promise.all([
          api.getOffices(),
          api.getDistributors({ active: 'true', pageSize: 100 }),
        ]);
        setOffices(offRes.data.offices);
        const defOff = offRes.data.defaultOffice || offRes.data.offices[0];
        if (defOff) setOfficeId(defOff.id);
        setDistributors(distRes.data.items);
        setSelectedIds(distRes.data.items.slice(0, 9).map((d) => d.id));
      } catch (err) {
        onNotify('error', err instanceof Error ? err.message : 'Unable to load optimizer inputs');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const handleRunComparison = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!officeId) {
      onNotify('error', 'Create or select an office location first.');
      return;
    }
    if (selectedIds.length === 0) {
      onNotify('error', 'Select at least 1 distributor.');
      return;
    }
    setRunning(true);
    try {
      const res = await api.previewOptimization({
        officeId,
        distributorIds: selectedIds,
        seed: FIXED_GRAPH_SEED,
        distanceMultiplier: FIXED_DISTANCE_MULTIPLIER,
        travelMode,
        returnToOffice,
        gaPopulationSize: FIXED_GA_POPULATION_SIZE,
        gaGenerations: FIXED_GA_GENERATIONS,
        gaMutationRate: FIXED_GA_MUTATION_RATE,
      });
      setPreview(res.data);
      if (res.data.recommendedAlgorithm) {
        setActiveAlgo(res.data.recommendedAlgorithm);
      }
      onNotify(
        'success',
        `Ran BFS, UCS, A*, and GA on the same local cost matrix (${res.data.matrix.cacheHit ? 'cached' : 'generated'}).`
      );
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Optimization failed');
    } finally {
      setRunning(false);
    }
  };

  const handleSavePlan = async () => {
    if (!officeId || selectedIds.length === 0) return;
    setSaving(true);
    try {
      const createRes = await api.createRoutePlan({
        name: planName.trim() || 'Daily Metro Route',
        planDate,
        officeId,
        distributorIds: selectedIds,
        travelMode,
        returnToOffice,
        distanceMultiplier: FIXED_DISTANCE_MULTIPLIER,
        graphSeed: FIXED_GRAPH_SEED,
      });
      const planId = createRes.data.id;
      await api.optimizeRoutePlan(planId, {
        distributorIds: selectedIds,
        selectedAlgorithm: activeAlgo,
        seed: FIXED_GRAPH_SEED,
        distanceMultiplier: FIXED_DISTANCE_MULTIPLIER,
        returnToOffice,
        travelMode,
        gaPopulationSize: FIXED_GA_POPULATION_SIZE,
        gaGenerations: FIXED_GA_GENERATIONS,
        gaMutationRate: FIXED_GA_MUTATION_RATE,
      });
      onNotify('success', 'Route plan, stops, and all 4 algorithm comparisons saved to Neon PostgreSQL.');
      navigate(`/saved-plans/${planId}`);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to save route plan');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />;
  }

  const activeResult: AlgorithmComparisonItem | undefined = preview?.results.find(
    (r) => r.algorithm === activeAlgo
  );

  const gaResult = preview?.results.find((r) => r.algorithm === 'GENETIC_ALGORITHM');

  const selectedOffice = offices.find((o) => o.id === officeId) || null;
  const mapPoints: SchematicPoint[] = preview
    ? preview.nodes.map((n) => ({
        id: n.id,
        name: n.name,
        latitude: n.latitude,
        longitude: n.longitude,
        isOffice: n.isOffice,
      }))
    : [
        ...(selectedOffice
          ? [
              {
                id: selectedOffice.id,
                name: selectedOffice.name,
                latitude: selectedOffice.latitude,
                longitude: selectedOffice.longitude,
                isOffice: true,
              },
            ]
          : []),
        ...distributors
          .filter((d) => selectedIds.includes(d.id))
          .map((d) => ({
            id: d.id,
            name: d.name,
            latitude: d.latitude,
            longitude: d.longitude,
            priority: d.priority,
          })),
      ];

  const routeOrderIds =
    preview && activeResult?.completed
      ? activeResult.routeOrder.map((idx) => preview.nodes[idx]?.id).filter(Boolean)
      : [];

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white px-5 py-3.5 text-xs text-slate-600">
        <span className="font-semibold text-slate-900">
          Weeks 2, 3, 4 & 7 · Agent Environment & Route Search Comparison:
        </span>{' '}
        Models the field officer as an agent starting at the office (<code className="font-mono">state = (location, visitedSet)</code>). Edges use locally calculated Haversine straight-line distances scaled by a simulated multiplier (no external road or routing API). BFS minimizes edge count; UCS (uninformed) and A* (informed MST heuristic) minimize simulated distance; GA searches permutations heuristically.
      </div>

      {selectedIds.length > 12 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-5 py-3 text-xs text-amber-900">
          Warning: Exact state-space search (BFS, UCS, A*) grows as n · 2^n and is capped at 12 distributors to prevent server overload. For {selectedIds.length} stops, Genetic Algorithm (GA) will return a heuristic tour while exact algorithms will report the cap warning.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        <form
          onSubmit={handleRunComparison}
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 lg:col-span-4"
        >
          <h3 className="text-base font-semibold text-slate-900">Route Problem Setup</h3>

          <div>
            <label className="block text-xs font-medium text-slate-700">Plan Name</label>
            <input
              required
              value={planName}
              onChange={(e) => setPlanName(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700">Plan Date</label>
              <input
                type="date"
                required
                value={planDate}
                onChange={(e) => setPlanDate(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-xs"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700">Base Office</label>
              <select
                value={officeId}
                onChange={(e) => setOfficeId(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
              >
                {offices.length === 0 && <option value="">No office configured</option>}
                {offices.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700">Simulated Mode</label>
              <select
                value={travelMode}
                onChange={(e) =>
                  setTravelMode(
                    e.target.value as 'simulated_vehicle' | 'simulated_van' | 'simulated_walking'
                  )
                }
                className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
              >
                <option value="simulated_vehicle">Car (35 km/h sim.)</option>
                <option value="simulated_van">Delivery Van (28 km/h sim.)</option>
                <option value="simulated_walking">Walking (5 km/h sim.)</option>
              </select>
            </div>
            <div className="flex items-end pb-1.5">
              <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700">
                <input
                  type="checkbox"
                  checked={returnToOffice}
                  onChange={(e) => setReturnToOffice(e.target.checked)}
                />
                Return to office
              </label>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-700">
                Distributors ({selectedIds.length} selected)
              </label>
              <button
                type="button"
                onClick={() =>
                  setSelectedIds(
                    selectedIds.length === distributors.length ? [] : distributors.map((d) => d.id)
                  )
                }
                className="text-xs font-medium text-blue-600"
              >
                {selectedIds.length === distributors.length ? 'Clear' : 'Select All'}
              </button>
            </div>
            <div className="mt-2 max-h-48 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200">
              {distributors.map((d) => (
                <label
                  key={d.id}
                  className="flex cursor-pointer items-center justify-between px-3 py-1.5 text-xs hover:bg-slate-50"
                >
                  <span className="flex items-center gap-2 font-medium text-slate-800">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(d.id)}
                      onChange={() =>
                        setSelectedIds((prev) =>
                          prev.includes(d.id) ? prev.filter((x) => x !== d.id) : [...prev, d.id]
                        )
                      }
                    />
                    {d.name}
                  </span>
                  <span className="font-mono text-[11px] text-slate-400">P{d.priority}</span>
                </label>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={running || !officeId || selectedIds.length === 0}
            className="inline-flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {running ? 'Running BFS, UCS, A*, GA...' : 'Compare All 4 Algorithms'}
          </button>
        </form>

        <div className="space-y-6 lg:col-span-8">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">Map Visualization Mode:</span>
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setMapViewMode('schematic')}
                className={`rounded px-3 py-1 font-medium transition-colors ${
                  mapViewMode === 'schematic'
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Schematic Coordinate Plot
              </button>
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
                Interactive Leaflet Map
              </button>
            </div>
          </div>

          {mapViewMode === 'leaflet' ? (
            <LeafletRouteMap
              points={mapPoints}
              routeOrderIds={routeOrderIds}
              height={400}
              title={
                activeResult?.completed
                  ? `Interactive Leaflet Route — ${activeAlgo} (${activeResult.estimatedDistanceKm} km simulated)`
                  : 'Interactive Leaflet Route Map'
              }
            />
          ) : (
            <SchematicMap
              points={mapPoints}
              routeOrderIds={routeOrderIds}
              height={400}
              title={
                activeResult?.completed
                  ? `Schematic Route Preview — ${activeAlgo} (${activeResult.estimatedDistanceKm} km simulated)`
                  : 'Schematic Coordinate Preview'
              }
            />
          )}

          {preview && (
            <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                <div>
                  <h3 className="text-base font-semibold text-slate-900">
                    Algorithm Comparison Matrix (Same Graph & Seed {preview.matrix.seed})
                  </h3>
                  <p className="text-xs text-slate-500">
                    Recommended: <span className="font-mono font-semibold text-emerald-700">{preview.recommendedAlgorithm}</span> (lowest simulated travel distance among valid completed tours) · Click a row to preview its route
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleSavePlan}
                  disabled={saving}
                  className="inline-flex items-center gap-2 whitespace-nowrap shrink-0 rounded-md bg-slate-900 px-4 py-2 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  <Save className="h-3.5 w-3.5" />
                  {saving ? 'Saving to Neon...' : `Save Plan (${activeAlgo}) to Neon`}
                </button>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-3 py-2.5">Algorithm</th>
                      <th className="px-3 py-2.5">Classification & Objective</th>
                      <th className="px-3 py-2.5 text-right">Edges</th>
                      <th className="px-3 py-2.5 text-right">Simulated Dist.</th>
                      <th className="px-3 py-2.5 text-right">Sim. Travel</th>
                      <th className="px-3 py-2.5 text-right">Nodes Expanded</th>
                      <th className="px-3 py-2.5 text-right">Exec Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {preview.results.map((r) => {
                      const isSelected = activeAlgo === r.algorithm;
                      return (
                        <tr
                          key={r.algorithm}
                          onClick={() => r.completed && setActiveAlgo(r.algorithm)}
                          className={`cursor-pointer ${
                            isSelected ? 'bg-blue-50/70' : 'hover:bg-slate-50'
                          }`}
                        >
                          <td className="px-3 py-2.5 font-mono font-semibold text-slate-900">
                            {r.algorithm}
                            {preview.recommendedAlgorithm === r.algorithm && (
                              <span className="ml-1.5 font-sans text-[11px] font-medium text-emerald-700">
                                · Recommended
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-slate-600">
                            <span className="font-medium text-slate-800">
                              {r.algorithm === 'A*'
                                ? 'Informed (A* MST heuristic)'
                                : r.algorithm === 'UCS'
                                  ? 'Uninformed (cost-based)'
                                  : r.algorithm === 'BFS'
                                    ? 'Uninformed (minimizes edge count, NOT distance)'
                                    : 'Evolutionary heuristic (non-optimal guarantee)'}
                            </span>
                            {r.warning && (
                              <p className="mt-0.5 text-[11px] text-amber-700">{r.warning}</p>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-700">
                            {r.completed ? r.edgeCount : '—'}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono font-semibold tabular-nums text-slate-900">
                            {r.completed ? `${r.estimatedDistanceKm} km` : '—'}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-700">
                            {r.completed ? `${r.estimatedDurationMinutes} min` : '—'}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-700">
                            {r.nodesExpanded.toLocaleString()}
                          </td>
                          <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-700">
                            {r.executionTimeMs} ms
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {activeResult?.completed && (
                <div className="border-t border-slate-100 pt-3">
                  <p className="text-xs font-semibold text-slate-800">
                    {activeResult.algorithm} Visit Sequence:
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-600">
                    {activeResult.routeOrder
                      .map((idx) => preview.nodes[idx]?.name || `Node ${idx}`)
                      .join(' → ')}
                  </p>
                </div>
              )}

              {gaResult?.convergenceHistory && gaResult.convergenceHistory.length > 1 && (
                <div className="border-t border-slate-100 pt-4">
                  <h4 className="text-xs font-semibold text-slate-800">
                    Genetic Algorithm Convergence (Best Tour Distance by Generation)
                  </h4>
                  <div className="mt-2 h-40 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={gaResult.convergenceHistory}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                        <XAxis dataKey="generation" tick={{ fontSize: 11, fill: '#475569' }} />
                        <YAxis tick={{ fontSize: 11, fill: '#475569' }} domain={['auto', 'auto']} />
                        <Tooltip formatter={(val: unknown) => [`${val} km`, 'Best Cost']} />
                        <Line type="monotone" dataKey="bestCost" stroke="#2563EB" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Bayesian Delay Risk Assessment for the Optimized Tour */}
              {preview.delayPredictions && preview.delayPredictions.length > 0 && (
                <div className="border-t border-slate-100 pt-4 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <ShieldAlert className="h-4 w-4 text-blue-600" />
                      <h4 className="text-xs font-semibold text-slate-900">
                        Bayesian Network Delay Risk Report ({activeAlgo} Tour)
                      </h4>
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate('/delay-prediction')}
                      className="text-[11px] font-medium text-blue-600 hover:text-blue-700 underline"
                    >
                      Open Full Bayesian Analyzer →
                    </button>
                  </div>
                  <div className="overflow-x-auto rounded border border-slate-200">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200 text-slate-600">
                        <tr>
                          <th className="px-3 py-2">Stop</th>
                          <th className="px-3 py-2">Distributor</th>
                          <th className="px-3 py-2">Distance</th>
                          <th className="px-3 py-2">Duration</th>
                          <th className="px-3 py-2 text-right">P(Low)</th>
                          <th className="px-3 py-2 text-right">P(Med)</th>
                          <th className="px-3 py-2 text-right">P(High)</th>
                          <th className="px-3 py-2">Predicted Risk</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {preview.delayPredictions.map((pred, i) => (
                          <tr key={i} className="hover:bg-slate-50/70">
                            <td className="px-3 py-1.5 font-mono font-semibold text-slate-700">
                              #{pred.stopOrder ?? i + 1}
                            </td>
                            <td className="px-3 py-1.5 font-medium text-slate-900">
                              {pred.distributorName}
                            </td>
                            <td className="px-3 py-1.5 text-slate-700">
                              {pred.inputs?.distanceKm ?? pred.distanceKm ?? '—'} km
                            </td>
                            <td className="px-3 py-1.5 text-slate-700">
                              {pred.inputs?.visitDurationMinutes ?? pred.visitDurationMinutes ?? 30} min
                            </td>
                            <td className="px-3 py-1.5 text-right font-mono text-emerald-700">
                              {Math.round(pred.probabilities.Low * 100)}%
                            </td>
                            <td className="px-3 py-1.5 text-right font-mono text-amber-700">
                              {Math.round(pred.probabilities.Medium * 100)}%
                            </td>
                            <td className="px-3 py-1.5 text-right font-mono text-red-700 font-semibold">
                              {Math.round(pred.probabilities.High * 100)}%
                            </td>
                            <td className="px-3 py-1.5">
                              <span
                                className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                                  pred.predictedRisk === 'High'
                                    ? 'bg-red-100 text-red-800'
                                    : pred.predictedRisk === 'Medium'
                                      ? 'bg-amber-100 text-amber-800'
                                      : 'bg-emerald-100 text-emerald-800'
                                }`}
                              >
                                {pred.predictedRisk}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
