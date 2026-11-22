import React, { useEffect, useState } from 'react';
import { Map as MapIcon, Play } from 'lucide-react';
import { api } from '../services/api';
import { LeafletRouteMap } from '../components/LeafletRouteMap';
import { SchematicMap, type SchematicPoint } from '../components/SchematicMap';
import type { Distributor, KMeansRunResult, OfficeLocation } from '../types';

interface ClusteringPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

export const ClusteringPage: React.FC<ClusteringPageProps> = ({ onNotify }) => {
  const [office, setOffice] = useState<OfficeLocation | null>(null);
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [k, setK] = useState(3);
  const [seed, setSeed] = useState(42);
  const [initMethod, setInitMethod] = useState<'kmeans++' | 'random'>('kmeans++');
  const [maxIterations, setMaxIterations] = useState(100);

  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<KMeansRunResult | null>(null);
  const [mapViewMode, setMapViewMode] = useState<'leaflet' | 'schematic'>('leaflet');

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        const [offRes, distRes, latestRes] = await Promise.all([
          api.getOffices(),
          api.getDistributors({ active: 'true', pageSize: 100 }),
          api.getLatestClusters(),
        ]);
        setOffice(offRes.data.defaultOffice);
        setDistributors(distRes.data.items);
        setSelectedIds(distRes.data.items.map((d) => d.id));
        if (distRes.data.items.length > 0 && distRes.data.items.length < 3) {
          setK(distRes.data.items.length);
        }

        if (latestRes.data && latestRes.data.centroids.length > 0) {
          setResult({
            routePlanId: latestRes.data.routePlanId,
            k: latestRes.data.k,
            seed: 42,
            initMethod: 'kmeans++',
            maxIterations: 100,
            iterations: 0,
            converged: true,
            totalWcss: 0,
            centroids: latestRes.data.centroids,
            assignments: latestRes.data.assignments,
            iterationHistory: [],
          });
        }
      } catch (err) {
        onNotify('error', err instanceof Error ? err.message : 'Unable to load clustering workspace');
      } finally {
        setLoading(false);
      }
    };
    void init();
  }, []);

  const toggleDistributor = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleRunKMeans = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedIds.length === 0) {
      onNotify('error', 'Select at least 1 distributor to cluster.');
      return;
    }
    if (k < 1 || k > selectedIds.length) {
      onNotify('error', `K must be between 1 and ${selectedIds.length} (number of selected distributors).`);
      return;
    }
    setRunning(true);
    try {
      const res = await api.runClustering({
        distributorIds: selectedIds,
        k,
        seed,
        maxIterations,
        initMethod,
      });
      setResult(res.data);
      onNotify('success', `K-Means converged in ${res.data.iterations} iteration(s) and saved to database.`);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'K-Means clustering failed');
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />;
  }

  const assignmentMap = new Map(
    (result?.assignments || []).map((a) => [a.distributorId, a])
  );

  const mapPoints: SchematicPoint[] = [
    ...(office
      ? [
          {
            id: office.id,
            name: office.name,
            latitude: office.latitude,
            longitude: office.longitude,
            isOffice: true,
          },
        ]
      : []),
    ...distributors
      .filter((d) => selectedIds.includes(d.id))
      .map((d) => {
        const assigned = assignmentMap.get(d.id);
        return {
          id: d.id,
          name: d.name,
          latitude: d.latitude,
          longitude: d.longitude,
          priority: d.priority,
          clusterIndex: assigned?.clusterIndex,
          clusterLabel: assigned?.clusterLabel,
        };
      }),
  ];

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white px-5 py-3.5 text-xs text-slate-600">
        <span className="font-semibold text-slate-900">Geographic Territory Clustering:</span>{' '}
        Partitions nearby distributors into balanced sales territories using spatial coordinate clustering for efficient regional coverage.
      </div>

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-4">
          <form onSubmit={handleRunKMeans} className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
            <h3 className="text-base font-semibold text-slate-900">K-Means Parameters</h3>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700">
                  Clusters (K)
                </label>
                <input
                  type="number"
                  min={1}
                  max={Math.max(1, selectedIds.length)}
                  value={k}
                  onChange={(e) => setK(Number(e.target.value))}
                  className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                />
                <p className="mt-0.5 text-[11px] text-slate-500">
                  1 to {selectedIds.length} max
                </p>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700">Random Seed</label>
                <input
                  type="number"
                  min={0}
                  max={1000000}
                  value={seed}
                  onChange={(e) => setSeed(Number(e.target.value))}
                  className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700">Initialization</label>
                <select
                  value={initMethod}
                  onChange={(e) => setInitMethod(e.target.value as 'kmeans++' | 'random')}
                  className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-sm"
                >
                  <option value="kmeans++">K-Means++</option>
                  <option value="random">Random Seeded</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700">Max Iterations</label>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={maxIterations}
                  onChange={(e) => setMaxIterations(Number(e.target.value))}
                  className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-slate-700">
                  Selected Distributors ({selectedIds.length}/{distributors.length})
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
                  {selectedIds.length === distributors.length ? 'Clear' : 'Select All'}
                </button>
              </div>
              <div className="mt-2 max-h-52 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200">
                {distributors.length === 0 ? (
                  <p className="p-3 text-xs text-slate-500">No active distributors available.</p>
                ) : (
                  distributors.map((d) => (
                    <label
                      key={d.id}
                      className="flex cursor-pointer items-center justify-between px-3 py-2 text-xs hover:bg-slate-50"
                    >
                      <span className="flex items-center gap-2 font-medium text-slate-800">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(d.id)}
                          onChange={() => toggleDistributor(d.id)}
                        />
                        {d.name}
                      </span>
                      <span className="font-mono tabular-nums text-slate-400">
                        {d.latitude.toFixed(2)}, {d.longitude.toFixed(2)}
                      </span>
                    </label>
                  ))
                )}
              </div>
            </div>

            <button
              type="submit"
              disabled={running || selectedIds.length === 0}
              className="inline-flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {running ? 'Running K-Means...' : 'Run & Save K-Means Clusters'}
            </button>
          </form>
        </div>

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
              centroids={result?.centroids || []}
              height={420}
              title="Interactive Leaflet Geographic Clusters"
            />
          ) : (
            <SchematicMap
              points={mapPoints}
              centroids={result?.centroids || []}
              showClusterLinks
              height={420}
              title="Schematic Coordinate Map & Geographic Clusters"
            />
          )}

          {result && (
            <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <h3 className="text-base font-semibold text-slate-900">Clustering Output Summary</h3>
                <span className="font-mono text-xs tabular-nums text-slate-600">
                  K={result.k} · Seed {result.seed} · {result.iterations} iteration(s) ·{' '}
                  {result.converged ? 'Converged' : 'Max iterations reached'}
                  {result.totalWcss > 0 ? ` · WCSS ${result.totalWcss}` : ''}
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                {result.centroids.map((c) => (
                  <div key={c.clusterIndex} className="rounded-md border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-slate-900">{c.clusterLabel}</span>
                      <span className="font-mono text-xs tabular-nums text-slate-600">
                        {c.count} stop{c.count === 1 ? '' : 's'}
                      </span>
                    </div>
                    <p className="mt-1 font-mono text-xs tabular-nums text-slate-500">
                      Centroid: {c.centroidLat.toFixed(4)}, {c.centroidLng.toFixed(4)}
                    </p>
                  </div>
                ))}
              </div>

              {result.iterationHistory.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-700">Iteration Trace</h4>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs font-mono tabular-nums text-slate-600">
                    {result.iterationHistory.map((step) => (
                      <span key={step.iteration} className="border-b border-slate-200 pb-0.5">
                        Iter {step.iteration}: inertia {step.inertia} ({step.reassignedCount} moved)
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Distributor</th>
                      <th className="px-3 py-2">Assigned Cluster</th>
                      <th className="px-3 py-2 text-right">Coordinates</th>
                      <th className="px-3 py-2 text-right">Dist. to Centroid</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {result.assignments.map((a) => (
                      <tr key={a.distributorId}>
                        <td className="px-3 py-2 font-medium text-slate-900">{a.distributorName}</td>
                        <td className="px-3 py-2 text-slate-700">{a.clusterLabel}</td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-600">
                          {a.latitude.toFixed(4)}, {a.longitude.toFixed(4)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono tabular-nums text-slate-700">
                          {a.distanceToCentroidKm > 0 ? `${a.distanceToCentroidKm} km` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
