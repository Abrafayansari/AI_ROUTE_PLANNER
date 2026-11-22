import React, { useEffect, useMemo, useState } from 'react';
import {
  BarChart,
  Bar,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  Award,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Compass,
  FileText,
  FolderKanban,
  Globe,
  Info,
  Layers,
  Map as MapIcon,
  Play,
  RefreshCw,
  Route,
  Save,
  ShieldAlert,
  Sparkles,
  Zap,
} from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../services/api';
import { SchematicMap, type SchematicPoint } from '../components/SchematicMap';
import { LeafletRouteMap } from '../components/LeafletRouteMap';
import { GoogleKarachiMap } from '../components/GoogleKarachiMap';
import { SavedPlansPage } from './SavedPlansPage';
import type {
  AlgorithmComparisonItem,
  AlgorithmName,
  Distributor,
  MapsStatusPayload,
  OfficeLocation,
  OptimizationObjective,
  OptimizePreviewResponse,
  TravelMode,
} from '../types';

interface OptimizerPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

const DEFAULT_DISTANCE_MULTIPLIER = 1.0;
const DEFAULT_GRAPH_SEED = 42;
const DEFAULT_GA_POPULATION_SIZE = 80;
const DEFAULT_GA_GENERATIONS = 150;
const DEFAULT_GA_MUTATION_RATE = 0.18;

const ALGO_DESCRIPTIONS: Record<string, { category: string; description: string; complexity: string; guarantee: string }> = {
  BFS: {
    category: 'Uninformed Graph Search',
    description: 'Explores routes level-by-level in FIFO order. Strictly minimizes the number of edges/hops, ignoring distance and travel time.',
    complexity: 'O(V + E) per state; up to O(n · 2^n)',
    guarantee: 'Guarantees minimum edge count, NOT shortest road distance or fastest time.',
  },
  UCS: {
    category: 'Uninformed Cost-Based Search',
    description: 'Dijkstra-style frontier expansion ordered strictly by cumulative path cost g(n) without any guiding heuristic.',
    complexity: 'O(b^(1 + C*/ε)) in branch-and-bound',
    guarantee: 'Guarantees the mathematically optimal tour under the chosen objective function.',
  },
  'A*': {
    category: 'Informed Heuristic Search',
    description: 'Guides exploration using f(n) = g(n) + h(n), where h(n) is an admissible Minimum Spanning Tree (MST) lower bound.',
    complexity: 'O(b^d) with significant state pruning',
    guarantee: 'Guarantees the optimal tour while expanding significantly fewer nodes than UCS.',
  },
  GENETIC_ALGORITHM: {
    category: 'Evolutionary Metaheuristic',
    description: 'Maintains a population of permutation chromosomes with Order Crossover (OX1), 2-opt/inversion mutation, and elitism.',
    complexity: 'O(Generations · PopulationSize · TourLength)',
    guarantee: 'Stochastic heuristic; scales seamlessly to larger distributor counts without exponential state explosion.',
  },
};

export const OptimizerPage: React.FC<OptimizerPageProps> = ({ onNotify }) => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') === 'saved' ? 'saved' : 'create';

  const hasGoogleBrowserKey = Boolean((import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '').trim());

  // Input Data States
  const [offices, setOffices] = useState<OfficeLocation[]>([]);
  const [officeId, setOfficeId] = useState<string>('');
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Route Configuration States
  const [planName, setPlanName] = useState('Karachi Daily Sales Route');
  const [planDate, setPlanDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [optimizationObjective, setOptimizationObjective] = useState<OptimizationObjective>('FASTEST_TIME');
  const [travelMode, setTravelMode] = useState<TravelMode>('DRIVE');
  const [returnToOffice, setReturnToOffice] = useState(true);

  // Status & Loading States
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);

  // Results & Display Modes
  const [mapsStatus, setMapsStatus] = useState<MapsStatusPayload | null>(null);
  const [preview, setPreview] = useState<OptimizePreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [activeAlgo, setActiveAlgo] = useState<AlgorithmName>('A*');
  const [activePolyline, setActivePolyline] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'default' | 'academic'>('default');
  const [mapViewMode, setMapViewMode] = useState<'leaflet' | 'schematic'>('leaflet');
  const [expandedAlgo, setExpandedAlgo] = useState<string | null>('A*');

  // Load Initial Data: Offices, Distributors, and Routing Status
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [offRes, distRes, statusRes] = await Promise.all([
          api.getOffices(),
          api.getDistributors({ active: 'true', pageSize: 100 }),
          api.getMapsStatus().catch(() => null),
        ]);
        setOffices(offRes.data.offices);
        const defOff = offRes.data.defaultOffice || offRes.data.offices[0];
        if (defOff) setOfficeId(defOff.id);
        const allDists = distRes.data.items;
        setDistributors(allDists);
        // By default, select all active distributors as requested in core workflow
        setSelectedIds(allDists.map((d) => d.id));
        if (statusRes?.data) setMapsStatus(statusRes.data);
      } catch (err) {
        onNotify('error', err instanceof Error ? err.message : 'Unable to load optimizer inputs');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  // Execute Route Optimization across all 4 algorithms
  const executeComparison = async (
    objective: OptimizationObjective,
    mode: TravelMode = travelMode
  ) => {
    if (!officeId) {
      onNotify('error', 'Select or create a base office location first.');
      return;
    }
    if (selectedIds.length === 0) {
      onNotify('error', 'Please select at least 1 distributor to optimize.');
      return;
    }
    setRunning(true);
    setPreviewError(null);
    try {
      const res = await api.previewOptimization({
        officeId,
        distributorIds: selectedIds,
        seed: DEFAULT_GRAPH_SEED,
        distanceMultiplier: DEFAULT_DISTANCE_MULTIPLIER,
        travelMode: mode,
        optimizationObjective: objective,
        returnToOffice,
        gaPopulationSize: DEFAULT_GA_POPULATION_SIZE,
        gaGenerations: DEFAULT_GA_GENERATIONS,
        gaMutationRate: DEFAULT_GA_MUTATION_RATE,
      });
      setPreview(res.data);
      const nextAlgo = res.data.recommendedAlgorithm || 'A*';
      setActiveAlgo(nextAlgo);
      setActivePolyline(res.data.encodedPolyline ?? null);
      const modeLabel =
        objective === 'FASTEST_TIME' ? 'Fastest Travel Time' : 'Shortest Road Distance';
      const provLabel = res.data.providerLabel || res.data.dataSource.replace(/_/g, ' ');
      onNotify(
        'success',
        `Successfully executed BFS, UCS, A*, and Genetic Algorithm using ${modeLabel} (${provLabel}).`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Optimization failed to complete.';
      setPreview(null);
      setActivePolyline(null);
      setPreviewError(msg);
      onNotify('error', msg);
    } finally {
      setRunning(false);
    }
  };

  const handleRunOptimization = async (e: React.FormEvent) => {
    e.preventDefault();
    await executeComparison(optimizationObjective, travelMode);
  };

  const handleObjectiveChange = (nextObjective: OptimizationObjective) => {
    if (nextObjective === optimizationObjective) return;
    setOptimizationObjective(nextObjective);
    if (preview && officeId && selectedIds.length > 0 && !running) {
      void executeComparison(nextObjective, travelMode);
    }
  };

  // Algorithm selection and interactive route map update
  const handleSelectAlgorithm = async (r: AlgorithmComparisonItem) => {
    if (!r.completed || !preview) return;
    setActiveAlgo(r.algorithm);
    const existingGeom = preview.geometryByAlgorithm?.[r.algorithm];
    if (existingGeom !== undefined) {
      setActivePolyline(existingGeom.encodedPolyline ?? null);
      return;
    }
    const waypoints = r.routeOrder
      .map((idx) => preview.nodes[idx])
      .filter(Boolean)
      .map((n) => ({ latitude: n.latitude, longitude: n.longitude }));
    if (waypoints.length >= 2) {
      try {
        const gRes = await api.computeRouteGeometry({
          waypoints,
          travelMode,
          optimizationObjective: preview.optimizationObjective || optimizationObjective,
        });
        setActivePolyline(gRes.data.encodedPolyline ?? null);
      } catch (err) {
        setActivePolyline(null);
        onNotify(
          'error',
          err instanceof Error ? err.message : 'Unable to fetch route geometry for selected algorithm'
        );
      }
    }
  };

  // Save the currently selected plan to database
  const handleSavePlan = async () => {
    if (!officeId || selectedIds.length === 0) return;
    setSaving(true);
    try {
      const activeObj = preview?.optimizationObjective || optimizationObjective;
      const createRes = await api.createRoutePlan({
        name: planName.trim() || 'Karachi Daily Sales Route',
        planDate,
        officeId,
        distributorIds: selectedIds,
        travelMode,
        optimizationObjective: activeObj,
        returnToOffice,
        distanceMultiplier: DEFAULT_DISTANCE_MULTIPLIER,
        graphSeed: DEFAULT_GRAPH_SEED,
      });
      const planId = createRes.data.id;
      await api.optimizeRoutePlan(planId, {
        distributorIds: selectedIds,
        selectedAlgorithm: activeAlgo,
        optimizationObjective: activeObj,
        seed: DEFAULT_GRAPH_SEED,
        distanceMultiplier: DEFAULT_DISTANCE_MULTIPLIER,
        returnToOffice,
        travelMode,
        gaPopulationSize: DEFAULT_GA_POPULATION_SIZE,
        gaGenerations: DEFAULT_GA_GENERATIONS,
        gaMutationRate: DEFAULT_GA_MUTATION_RATE,
      });
      onNotify('success', `Saved plan "${planName}" with ${activeAlgo} route!`);
      setSearchParams({ tab: 'saved' });
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to save route plan');
    } finally {
      setSaving(false);
    }
  };

  // Map points & Route order calculation
  const mapPoints: SchematicPoint[] = useMemo(() => {
    if (preview && preview.nodes.length > 0) {
      return preview.nodes.map((n) => ({
        id: n.id,
        name: n.name,
        latitude: n.latitude,
        longitude: n.longitude,
        isOffice: n.isOffice,
      }));
    }
    const currentOff = offices.find((o) => o.id === officeId) || offices[0];
    const offPoint: SchematicPoint[] = currentOff
      ? [{ id: currentOff.id, name: currentOff.name, latitude: currentOff.latitude, longitude: currentOff.longitude, isOffice: true }]
      : [];
    const distPoints: SchematicPoint[] = distributors
      .filter((d) => selectedIds.includes(d.id))
      .map((d) => ({
        id: d.id,
        name: d.name,
        latitude: d.latitude,
        longitude: d.longitude,
        isOffice: false,
      }));
    return [...offPoint, ...distPoints];
  }, [preview, offices, officeId, distributors, selectedIds]);

  const activeResult = useMemo(
    () => preview?.results.find((r) => r.algorithm === activeAlgo) ?? null,
    [preview, activeAlgo]
  );

  const routeOrderIds = useMemo(() => {
    if (!preview || !activeResult?.completed || activeResult.routeOrder.length === 0) {
      return [];
    }
    return activeResult.routeOrder
      .map((idx) => preview.nodes[idx]?.id)
      .filter((id): id is string => Boolean(id));
  }, [preview, activeResult]);

  // Comparative Standouts & Badges
  const comparisonStats = useMemo(() => {
    if (!preview || preview.results.length === 0) return null;
    const completed = preview.results.filter((r) => r.completed && r.routeOrder.length > 0);
    if (completed.length === 0) return null;

    let bestDist = completed[0];
    let fastestTravel = completed[0];
    let fastestExec = completed[0];

    for (const r of completed) {
      if (r.estimatedDistanceKm < bestDist.estimatedDistanceKm) bestDist = r;
      if (r.estimatedDurationMinutes < fastestTravel.estimatedDurationMinutes) fastestTravel = r;
      if (r.executionTimeMs < fastestExec.executionTimeMs) fastestExec = r;
    }

    return {
      bestDistanceAlgo: bestDist.algorithm,
      bestDistanceKm: bestDist.estimatedDistanceKm,
      fastestTravelAlgo: fastestTravel.algorithm,
      fastestTravelMin: fastestTravel.estimatedDurationMinutes,
      fastestExecAlgo: fastestExec.algorithm,
      fastestExecMs: fastestExec.executionTimeMs,
      recommendedAlgo: preview.recommendedAlgorithm || 'A*',
    };
  }, [preview]);

  const gaResult = useMemo(
    () => preview?.results.find((r) => r.algorithm === 'GENETIC_ALGORITHM') ?? null,
    [preview]
  );

  const completedResultsForCharts = useMemo(
    () => preview?.results.filter((r) => r.completed && r.routeOrder.length > 0) ?? [],
    [preview]
  );

  const activeDelayPredictions = useMemo(
    () => preview?.delayPredictionsByAlgorithm?.[activeAlgo] ?? preview?.delayPredictions ?? [],
    [preview, activeAlgo]
  );

  const dataSource = preview?.dataSource || 'osrm_osm';
  const unitLabel = preview?.optimizationObjective === 'SHORTEST_DISTANCE' ? 'km' : 'min';

  if (activeTab === 'saved') {
    return (
      <div className="space-y-6">
        <div className="flex border-b border-slate-200 bg-white px-6 pt-3">
          <button
            type="button"
            onClick={() => setSearchParams({ tab: 'create' })}
            className="flex items-center gap-2 border-b-2 border-transparent px-4 py-3 text-sm font-medium text-slate-500 hover:text-slate-800"
          >
            <Route className="h-4 w-4" />
            Route Planning &amp; Optimizer
          </button>
          <button
            type="button"
            onClick={() => setSearchParams({ tab: 'saved' })}
            className="flex items-center gap-2 border-b-2 border-blue-600 px-4 py-3 text-sm font-medium text-blue-600"
          >
            <FolderKanban className="h-4 w-4" />
            Saved Route Plans
          </button>
        </div>
        <SavedPlansPage onNotify={onNotify} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Tabs */}
      <div className="flex border-b border-slate-200 bg-white px-6 pt-3">
        <button
          type="button"
          onClick={() => setSearchParams({ tab: 'create' })}
          className="flex items-center gap-2 border-b-2 border-blue-600 px-4 py-3 text-sm font-medium text-blue-600"
        >
          <Route className="h-4 w-4" />
          Route Planning &amp; Optimizer
        </button>
        <button
          type="button"
          onClick={() => setSearchParams({ tab: 'saved' })}
          className="flex items-center gap-2 border-b-2 border-transparent px-4 py-3 text-sm font-medium text-slate-500 hover:text-slate-800"
        >
          <FolderKanban className="h-4 w-4" />
          Saved Route Plans
        </button>
      </div>

      {/* Main Grid */}
      <div className="grid gap-6 lg:grid-cols-12">
        {/* Left Workflow Controls (Step 1-5) */}
        <form
          onSubmit={handleRunOptimization}
          className="space-y-5 rounded-lg border border-slate-200 bg-white p-5 lg:col-span-4"
        >
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div>
              <h2 className="text-base font-semibold text-slate-900">Route Configuration</h2>
              <p className="text-xs text-slate-500">Configure parameters &amp; select distributors</p>
            </div>
            <span className="rounded bg-blue-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-blue-700">
              Karachi Hub
            </span>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700">Plan Name</label>
            <input
              required
              value={planName}
              onChange={(e) => setPlanName(e.target.value)}
              placeholder="e.g., Karachi Central Sales Route"
              className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
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
                className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-xs focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700">Base Office</label>
              <select
                value={officeId}
                onChange={(e) => setOfficeId(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
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

          {/* Objective Switcher */}
          <div>
            <label className="block text-xs font-medium text-slate-700">Optimization Goal</label>
            <div className="mt-1.5 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => handleObjectiveChange('FASTEST_TIME')}
                className={`rounded-md border p-2 text-left text-xs transition-colors ${
                  optimizationObjective === 'FASTEST_TIME'
                    ? 'border-blue-600 bg-blue-50/50 text-blue-800 ring-1 ring-blue-600'
                    : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                <div className="font-semibold">Fastest Time</div>
                <div className="text-[10px] text-slate-500">Minimizes road travel min</div>
              </button>
              <button
                type="button"
                onClick={() => handleObjectiveChange('SHORTEST_DISTANCE')}
                className={`rounded-md border p-2 text-left text-xs transition-colors ${
                  optimizationObjective === 'SHORTEST_DISTANCE'
                    ? 'border-blue-600 bg-blue-50/50 text-blue-800 ring-1 ring-blue-600'
                    : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                <div className="font-semibold">Shortest Distance</div>
                <div className="text-[10px] text-slate-500">Minimizes road distance km</div>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700">Travel Mode</label>
              <select
                value={travelMode}
                onChange={(e) => setTravelMode(e.target.value as TravelMode)}
                className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
              >
                <option value="DRIVE">Car / Van (DRIVE)</option>
                <option value="TWO_WHEELER">Motorcycle (TWO_WHEELER)</option>
                <option value="WALK">Walking (WALK)</option>
              </select>
            </div>
            <div className="flex items-end pb-1.5">
              <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={returnToOffice}
                  onChange={(e) => setReturnToOffice(e.target.checked)}
                  className="rounded text-blue-600"
                />
                Return to Office Tour
              </label>
            </div>
          </div>

          {/* Distributor Selection (All selected by default, option to deselect) */}
          <div>
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-700">
                Select Distributors ({selectedIds.length} of {distributors.length})
              </label>
              <button
                type="button"
                onClick={() =>
                  setSelectedIds(
                    selectedIds.length === distributors.length ? [] : distributors.map((d) => d.id)
                  )
                }
                className="text-xs font-medium text-blue-600 hover:text-blue-700"
              >
                {selectedIds.length === distributors.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>
            <div className="mt-2 max-h-52 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200 bg-slate-50/50">
              {distributors.length === 0 ? (
                <div className="p-3 text-center text-xs text-slate-500">No active distributors found.</div>
              ) : (
                distributors.map((d) => {
                  const isChecked = selectedIds.includes(d.id);
                  return (
                    <label
                      key={d.id}
                      className={`flex cursor-pointer items-center justify-between px-3 py-2 text-xs transition-colors ${
                        isChecked ? 'bg-white' : 'hover:bg-slate-100/60'
                      }`}
                    >
                      <span className="flex items-center gap-2 font-medium text-slate-800">
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() =>
                            setSelectedIds((prev) =>
                              prev.includes(d.id) ? prev.filter((x) => x !== d.id) : [...prev, d.id]
                            )
                          }
                          className="rounded text-blue-600"
                        />
                        <span className="truncate max-w-[190px]">{d.name}</span>
                      </span>
                      <span className="font-mono text-[10px] text-slate-400">P{d.priority}</span>
                    </label>
                  );
                })
              )}
            </div>
          </div>

          {/* Primary Action Button (Step 5) */}
          <button
            type="submit"
            disabled={running || !officeId || selectedIds.length === 0}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {running ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Optimizing (BFS, UCS, A*, GA)...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Optimize Route
              </>
            )}
          </button>
        </form>

        {/* Right Output Section */}
        <div className="space-y-6 lg:col-span-8">
          {/* Map & View Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3">
            {/* View Mode Toggle: Default vs Academic Comparison */}
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setViewMode('default')}
                className={`inline-flex items-center gap-1.5 rounded px-3 py-1 font-semibold transition-colors ${
                  viewMode === 'default'
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Compass className="h-3.5 w-3.5" />
                Default Route View
              </button>
              <button
                type="button"
                onClick={() => setViewMode('academic')}
                className={`inline-flex items-center gap-1.5 rounded px-3 py-1 font-semibold transition-colors ${
                  viewMode === 'academic'
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Award className="h-3.5 w-3.5" />
                Algorithm Comparison (Course Project View)
              </button>
            </div>

            {/* Map Mode Toggle */}
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setMapViewMode('leaflet')}
                className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 font-medium transition-colors ${
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
                className={`rounded px-2.5 py-1 font-medium transition-colors ${
                  mapViewMode === 'schematic'
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Schematic
              </button>
            </div>
          </div>

          {/* Central Map Element (Step 10) */}
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            {mapViewMode === 'leaflet' ? (
              <LeafletRouteMap
                points={mapPoints}
                routeOrderIds={routeOrderIds}
                encodedPolyline={activePolyline}
                provider={preview?.provider}
                providerLabel={preview?.providerLabel || mapsStatus?.providerLabel}
                isLiveTraffic={preview?.isLiveTraffic}
                durationLabel={preview?.durationLabel}
                dataSource={dataSource}
                height={400}
                title={
                  activeResult?.completed
                    ? `Karachi Route — ${activeAlgo} (${activeResult.estimatedDurationMinutes} min · ${activeResult.estimatedDistanceKm} km)`
                    : 'Karachi Interactive Route Map'
                }
              />
            ) : (
              <SchematicMap
                points={mapPoints}
                routeOrderIds={routeOrderIds}
                height={400}
                title={
                  activeResult?.completed
                    ? `Schematic Route Preview — ${activeAlgo} (${activeResult.estimatedDistanceKm} km)`
                    : 'Schematic Coordinate Preview'
                }
              />
            )}
          </div>

          {/* TWO-LEVEL EXPERIENCE */}
          {/* LEVEL 1: DEFAULT FIELD OFFICER VIEW (Steps 7, 8, 9, 10, 11) */}
          {viewMode === 'default' && (
            <div className="space-y-5 rounded-lg border border-slate-200 bg-white p-5">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                      Recommended Route
                    </span>
                    <h3 className="text-base font-semibold text-slate-900">
                      Optimal Tour ({activeAlgo})
                    </h3>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    Determined by backend optimization based on {optimizationObjective === 'FASTEST_TIME' ? 'fastest travel duration' : 'shortest road distance'}.
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={handleSavePlan}
                    disabled={saving || !preview}
                    className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {saving ? 'Saving Route...' : 'Save This Route'}
                  </button>
                </div>
              </div>

              {preview && activeResult ? (
                <div className="space-y-4">
                  {/* KPI Cards Strip */}
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                      <p className="text-[11px] font-medium text-slate-500">Total Distance</p>
                      <p className="mt-1 font-mono text-xl font-bold tabular-nums text-slate-900">
                        {activeResult.completed ? `${activeResult.estimatedDistanceKm} km` : 'N/A — Limit exceeded'}
                      </p>
                    </div>
                    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                      <p className="text-[11px] font-medium text-slate-500">Est. Travel Time</p>
                      <p className="mt-1 font-mono text-xl font-bold tabular-nums text-slate-900">
                        {activeResult.completed ? `${activeResult.estimatedDurationMinutes} min` : 'N/A — Limit exceeded'}
                      </p>
                    </div>
                    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                      <p className="text-[11px] font-medium text-slate-500">Stops Visited</p>
                      <p className="mt-1 font-mono text-xl font-bold tabular-nums text-slate-900">
                        {activeResult.completed
                          ? `${activeResult.routeOrder.filter((idx) => !preview.nodes[idx]?.isOffice).length} stops`
                          : '0 stops'}
                      </p>
                    </div>
                    <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                      <p className="text-[11px] font-medium text-slate-500">Route Type</p>
                      <p className="mt-1 text-sm font-semibold text-slate-900">
                        {returnToOffice ? 'Closed Loop' : 'One-Way Stop'}
                      </p>
                    </div>
                  </div>

                  {/* Warning banner if selected algorithm is capped/incomplete */}
                  {!activeResult.completed && activeResult.warning && (
                    <div className="flex items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
                      <div>
                        <span className="font-semibold">{activeResult.algorithm} Notice: </span>
                        {activeResult.warning}
                      </div>
                    </div>
                  )}

                  {/* Quick Alternate Route Selector (Step 9) */}
                  <div className="rounded-md border border-slate-200 p-3">
                    <p className="text-xs font-semibold text-slate-700">Choose an Alternative Algorithm Route:</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {preview.results.map((r) => {
                        const isSelected = activeAlgo === r.algorithm;
                        return (
                          <button
                            key={r.algorithm}
                            type="button"
                            onClick={() => void handleSelectAlgorithm(r)}
                            className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                              isSelected
                                ? 'bg-blue-600 text-white shadow-sm'
                                : r.completed
                                ? 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                                : 'border border-slate-200 bg-slate-100 text-slate-500 hover:bg-slate-200'
                            }`}
                          >
                            <span>{r.algorithm}</span>
                            <span className="font-mono text-[10px] opacity-80">
                              {r.completed
                                ? `(${r.estimatedDistanceKm} km · ${r.estimatedDurationMinutes} m)`
                                : '(N/A — Limit exceeded)'}
                            </span>
                            {r.completed && preview.recommendedAlgorithm === r.algorithm && (
                              <span className="rounded bg-emerald-500 px-1 py-0.2 text-[9px] text-white">
                                Best
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Visit Sequence */}
                  <div className="rounded-md border border-slate-200 p-3">
                    <p className="text-xs font-semibold text-slate-800">Stop Sequence for Officer:</p>
                    <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-slate-700">
                      {activeResult.routeOrder.map((nodeIdx, order) => {
                        const node = preview.nodes[nodeIdx];
                        return (
                          <li key={order}>
                            <span className="font-semibold text-slate-900">
                              {node?.name || `Node ${nodeIdx}`}
                            </span>
                            {node?.isOffice && (
                              <span className="ml-1.5 text-[10px] font-medium text-blue-600">
                                (Base Office Hub)
                              </span>
                            )}
                          </li>
                        );
                      })}
                    </ol>
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-sm text-slate-500">
                  Select distributors and click <span className="font-semibold text-blue-600">&quot;Optimize Route&quot;</span> to compute the best route and compare all supported search algorithms.
                </div>
              )}
            </div>
          )}

          {/* LEVEL 2: ADVANCED / COURSE PROJECT VIEW (Section 2 & 3) */}
          {viewMode === 'academic' && (
            <div className="space-y-6">
              {preview ? (
                <>
                  {/* Standout Highlights Cards */}
                  {comparisonStats && (
                    <div className="grid gap-3 sm:grid-cols-4">
                      <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-4">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-800">
                          <Award className="h-4 w-4" />
                          Recommended Route
                        </div>
                        <p className="mt-1 font-mono text-lg font-bold text-emerald-900">
                          {comparisonStats.recommendedAlgo}
                        </p>
                        <p className="mt-0.5 text-[11px] text-emerald-700">
                          Top score under {optimizationObjective}
                        </p>
                      </div>

                      <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-800">
                          <Compass className="h-4 w-4" />
                          Best Road Distance
                        </div>
                        <p className="mt-1 font-mono text-lg font-bold text-blue-900">
                          {comparisonStats.bestDistanceKm} km
                        </p>
                        <p className="mt-0.5 text-[11px] text-blue-700">
                          Found by {comparisonStats.bestDistanceAlgo}
                        </p>
                      </div>

                      <div className="rounded-lg border border-indigo-200 bg-indigo-50/50 p-4">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-800">
                          <Clock className="h-4 w-4" />
                          Fastest Travel Time
                        </div>
                        <p className="mt-1 font-mono text-lg font-bold text-indigo-900">
                          {comparisonStats.fastestTravelMin} min
                        </p>
                        <p className="mt-0.5 text-[11px] text-indigo-700">
                          Found by {comparisonStats.fastestTravelAlgo}
                        </p>
                      </div>

                      <div className="rounded-lg border border-purple-200 bg-purple-50/50 p-4">
                        <div className="flex items-center gap-1.5 text-xs font-semibold text-purple-800">
                          <Zap className="h-4 w-4" />
                          Fastest Execution
                        </div>
                        <p className="mt-1 font-mono text-lg font-bold text-purple-900">
                          {comparisonStats.fastestExecMs} ms
                        </p>
                        <p className="mt-0.5 text-[11px] text-purple-700">
                          By {comparisonStats.fastestExecAlgo}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Complete Algorithm Comparison Table */}
                  <div className="rounded-lg border border-slate-200 bg-white p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3">
                      <div>
                        <h3 className="text-base font-semibold text-slate-900">
                          Algorithm Performance &amp; Evaluation Matrix
                        </h3>
                        <p className="text-xs text-slate-500">
                          Ground truth execution results. Click any algorithm row to preview its route on the Karachi map.
                        </p>
                      </div>
                      <span className="rounded bg-slate-100 px-2.5 py-1 text-xs text-slate-700 font-mono">
                        Objective: {optimizationObjective}
                      </span>
                    </div>

                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                          <tr>
                            <th className="px-3 py-2.5">Algorithm</th>
                            <th className="px-3 py-2.5">Search Type &amp; Heuristic</th>
                            <th className="px-3 py-2.5 text-right">Distance (km)</th>
                            <th className="px-3 py-2.5 text-right">Duration (min)</th>
                            <th className="px-3 py-2.5 text-right">Exec Time (ms)</th>
                            <th className="px-3 py-2.5 text-right">Nodes Expanded</th>
                            <th className="px-3 py-2.5 text-right">Generations / Iter.</th>
                            <th className="px-3 py-2.5 text-right">Objective Score</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {preview.results.map((r) => {
                            const isSelected = activeAlgo === r.algorithm;
                            const isRec = preview.recommendedAlgorithm === r.algorithm;
                            return (
                              <tr
                                key={r.algorithm}
                                onClick={() => void handleSelectAlgorithm(r)}
                                className={`cursor-pointer transition-colors ${
                                  isSelected ? 'bg-blue-50/80 font-medium' : 'hover:bg-slate-50'
                                }`}
                              >
                                <td className="px-3 py-2.5 font-mono font-semibold text-slate-900">
                                  <div className="flex items-center gap-1.5">
                                    <span>{r.algorithm}</span>
                                    {r.completed && isRec && (
                                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                                        Best
                                      </span>
                                    )}
                                    {isSelected && (
                                      <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-800">
                                        Viewing
                                      </span>
                                    )}
                                  </div>
                                </td>
                                <td className="px-3 py-2.5 text-slate-600">
                                  <div>{ALGO_DESCRIPTIONS[r.algorithm]?.category || r.objectiveDescription}</div>
                                  {!r.completed && r.warning && (
                                    <div className="mt-0.5 text-[10px] text-amber-700 italic">
                                      {r.warning}
                                    </div>
                                  )}
                                </td>
                                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-900">
                                  {r.completed ? `${r.estimatedDistanceKm} km` : 'N/A — Limit exceeded'}
                                </td>
                                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-900">
                                  {r.completed ? `${r.estimatedDurationMinutes} min` : 'N/A — Limit exceeded'}
                                </td>
                                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-purple-700">
                                  {r.executionTimeMs} ms
                                </td>
                                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-700">
                                  {r.nodesExpanded.toLocaleString()}
                                </td>
                                <td className="px-3 py-2.5 text-right font-mono tabular-nums text-slate-700">
                                  {r.generationsRun !== undefined ? r.generationsRun : 'Not available'}
                                </td>
                                <td className="px-3 py-2.5 text-right font-mono font-semibold tabular-nums text-slate-900">
                                  {r.totalCost ? r.totalCost.toFixed(2) : 'Not available'}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Comparison Visualizations: Bar Charts for Distance, Duration, Execution Time */}
                  <div className="grid gap-6 lg:grid-cols-3">
                    {/* 1. Distance Comparison Bar Chart */}
                    <div className="rounded-lg border border-slate-200 bg-white p-4">
                      <h4 className="text-xs font-semibold text-slate-900">
                        Total Route Distance (km)
                      </h4>
                      <p className="text-[11px] text-slate-500">Lower is better (completed runs)</p>
                      <div className="mt-3 h-48 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={completedResultsForCharts} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                            <XAxis dataKey="algorithm" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 10 }} unit="km" />
                            <Tooltip formatter={(val) => [`${val} km`, 'Distance']} />
                            <Bar dataKey="estimatedDistanceKm" radius={[4, 4, 0, 0]}>
                              {completedResultsForCharts.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={entry.algorithm === activeAlgo ? '#2563EB' : '#94A3B8'}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* 2. Travel Duration Bar Chart */}
                    <div className="rounded-lg border border-slate-200 bg-white p-4">
                      <h4 className="text-xs font-semibold text-slate-900">
                        Estimated Travel Duration (min)
                      </h4>
                      <p className="text-[11px] text-slate-500">Lower is better (completed runs)</p>
                      <div className="mt-3 h-48 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={completedResultsForCharts} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                            <XAxis dataKey="algorithm" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 10 }} unit="m" />
                            <Tooltip formatter={(val) => [`${val} min`, 'Duration']} />
                            <Bar dataKey="estimatedDurationMinutes" radius={[4, 4, 0, 0]}>
                              {completedResultsForCharts.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={entry.algorithm === activeAlgo ? '#0D9488' : '#94A3B8'}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* 3. Execution Time Bar Chart */}
                    <div className="rounded-lg border border-slate-200 bg-white p-4">
                      <h4 className="text-xs font-semibold text-slate-900">
                        Algorithm Execution Time (ms)
                      </h4>
                      <p className="text-[11px] text-slate-500">Computation speed (completed runs)</p>
                      <div className="mt-3 h-48 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={completedResultsForCharts} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                            <XAxis dataKey="algorithm" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 10 }} unit="ms" />
                            <Tooltip formatter={(val) => [`${val} ms`, 'Runtime']} />
                            <Bar dataKey="executionTimeMs" radius={[4, 4, 0, 0]}>
                              {completedResultsForCharts.map((entry, index) => (
                                <Cell
                                  key={`cell-${index}`}
                                  fill={entry.algorithm === activeAlgo ? '#7C3AED' : '#94A3B8'}
                                />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>

                  {/* Genetic Algorithm Convergence Plot */}
                  {gaResult?.convergenceHistory && gaResult.convergenceHistory.length > 1 && (
                    <div className="rounded-lg border border-slate-200 bg-white p-5">
                      <h4 className="text-xs font-semibold text-slate-900">
                        Genetic Algorithm Fitness Convergence (Best Tour Cost across Generations)
                      </h4>
                      <p className="text-[11px] text-slate-500">
                        Shows evolutionary progression with elitism, Order Crossover (OX1), and 2-opt inversion mutation.
                      </p>
                      <div className="mt-3 h-44 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={gaResult.convergenceHistory}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                            <XAxis dataKey="generation" tick={{ fontSize: 11, fill: '#475569' }} />
                            <YAxis tick={{ fontSize: 11, fill: '#475569' }} domain={['auto', 'auto']} />
                            <Tooltip formatter={(val: unknown) => [`${val} ${unitLabel}`, 'Best Cost']} />
                            <Line type="monotone" dataKey="bestCost" stroke="#2563EB" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  {/* Expandable Algorithm Details & Theoretical Explanations */}
                  <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-3">
                    <h3 className="text-sm font-semibold text-slate-900">
                      Algorithm Architecture &amp; Complexity Breakdown
                    </h3>
                    <div className="divide-y divide-slate-100">
                      {preview.results.map((r) => {
                        const info = ALGO_DESCRIPTIONS[r.algorithm];
                        const isExpanded = expandedAlgo === r.algorithm;
                        return (
                          <div key={r.algorithm} className="py-2.5">
                            <button
                              type="button"
                              onClick={() => setExpandedAlgo(isExpanded ? null : r.algorithm)}
                              className="flex w-full items-center justify-between text-left text-xs font-semibold text-slate-800 hover:text-blue-600"
                            >
                              <span>{r.algorithm} — {info?.category || 'Algorithm Details'}</span>
                              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                            </button>
                            {isExpanded && info && (
                              <div className="mt-2 space-y-1.5 pl-2 text-xs text-slate-600">
                                <p>{info.description}</p>
                                <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
                                  <div className="rounded bg-slate-50 p-2">
                                    <span className="font-semibold text-slate-800">Complexity: </span>
                                    {info.complexity}
                                  </div>
                                  <div className="rounded bg-slate-50 p-2">
                                    <span className="font-semibold text-slate-800">Optimality: </span>
                                    {info.guarantee}
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              ) : (
                <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">
                  Execute route optimization to display the complete algorithm performance comparison matrix and charts.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
