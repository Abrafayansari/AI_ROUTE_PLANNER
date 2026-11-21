import React, { useEffect, useState } from 'react';
import { Map as MapIcon, Trash2 } from 'lucide-react';
import { api } from '../services/api';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { LeafletRouteMap } from '../components/LeafletRouteMap';
import { SchematicMap } from '../components/SchematicMap';
import type { Distributor, OfficeLocation } from '../types';

interface OfficePageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

export const OfficePage: React.FC<OfficePageProps> = ({ onNotify }) => {
  const [offices, setOffices] = useState<OfficeLocation[]>([]);
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [selectedOfficeId, setSelectedOfficeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState('');
  const [address, setAddress] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [isDefault, setIsDefault] = useState(true);

  const [mapViewMode, setMapViewMode] = useState<'leaflet' | 'schematic'>('leaflet');
  const [deleteTarget, setDeleteTarget] = useState<OfficeLocation | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [offRes, distRes] = await Promise.all([
        api.getOffices(),
        api.getDistributors({ active: 'true', pageSize: 100 }),
      ]);
      setOffices(offRes.data.offices);
      setDistributors(distRes.data.items);
      const def = offRes.data.defaultOffice || offRes.data.offices[0];
      if (def) {
        setSelectedOfficeId(def.id);
        setName(def.name);
        setAddress(def.address);
        setLatitude(String(def.latitude));
        setLongitude(String(def.longitude));
        setIsDefault(def.is_default);
      } else {
        setSelectedOfficeId(null);
        setName('');
        setAddress('');
        setLatitude('');
        setLongitude('');
        setIsDefault(true);
      }
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Unable to load office data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const handleSelectOffice = (off: OfficeLocation) => {
    setSelectedOfficeId(off.id);
    setName(off.name);
    setAddress(off.address);
    setLatitude(String(off.latitude));
    setLongitude(String(off.longitude));
    setIsDefault(off.is_default);
  };

  const handleNewOffice = () => {
    setSelectedOfficeId(null);
    setName('');
    setAddress('');
    setLatitude('');
    setLongitude('');
    setIsDefault(offices.length === 0);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const lat = Number(latitude);
    const lng = Number(longitude);
    if (
      latitude.trim() === '' ||
      longitude.trim() === '' ||
      Number.isNaN(lat) ||
      lat < -90 ||
      lat > 90 ||
      Number.isNaN(lng) ||
      lng < -180 ||
      lng > 180
    ) {
      onNotify('error', 'Coordinates must be valid latitude (-90..90) and longitude (-180..180).');
      return;
    }

    setSaving(true);
    try {
      if (selectedOfficeId) {
        await api.updateOffice(selectedOfficeId, {
          name: name.trim(),
          address: address.trim(),
          latitude: lat,
          longitude: lng,
          is_default: isDefault,
        });
        onNotify('success', 'Office location updated.');
      } else {
        await api.createOffice({
          name: name.trim(),
          address: address.trim(),
          latitude: lat,
          longitude: lng,
          is_default: isDefault,
        });
        onNotify('success', 'Office location created.');
      }
      await loadData();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to save office location');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteOffice = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteOffice(deleteTarget.id);
      onNotify('success', `Deleted office "${deleteTarget.name}".`);
      setDeleteTarget(null);
      await loadData();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to delete office');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return <div className="h-64 animate-pulse rounded-lg border border-slate-200 bg-white" />;
  }

  const previewLat = Number(latitude);
  const previewLng = Number(longitude);
  const validPreview =
    latitude.trim() !== '' &&
    longitude.trim() !== '' &&
    !Number.isNaN(previewLat) &&
    !Number.isNaN(previewLng);

  const mapPoints = [
    ...(validPreview
      ? [
          {
            id: selectedOfficeId || 'preview-office',
            name: name || 'Base Office',
            latitude: previewLat,
            longitude: previewLng,
            isOffice: true,
          },
        ]
      : []),
    ...distributors.map((d) => ({
      id: d.id,
      name: d.name,
      latitude: d.latitude,
      longitude: d.longitude,
      priority: d.priority,
    })),
  ];

  return (
    <div className="space-y-4">
      {offices.length === 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-5 py-3 text-xs text-amber-900">
          No base office is configured yet. Create an office location below (or load demo data on the Settings / Dashboard page) before running route optimization.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="space-y-4 lg:col-span-5">
          <div className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-900">
                {selectedOfficeId ? 'Edit Base Office Location' : 'Create Base Office Location'}
              </h3>
              {offices.length > 0 && (
                <button
                  type="button"
                  onClick={handleNewOffice}
                  className="whitespace-nowrap shrink-0 text-xs font-medium text-blue-600 hover:text-blue-700"
                >
                  + New Office
                </button>
              )}
            </div>

            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700">Office / Depot Name *</label>
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Karachi Central Hub"
                  className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700">Address *</label>
                <input
                  required
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="Shahrah-e-Faisal, PECHS Block 6, Karachi"
                  className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700">Latitude *</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={latitude}
                    onChange={(e) => setLatitude(e.target.value)}
                    placeholder="e.g. 24.8607"
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">Longitude *</label>
                  <input
                    type="number"
                    step="any"
                    required
                    value={longitude}
                    onChange={(e) => setLongitude(e.target.value)}
                    placeholder="e.g. 67.0644"
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
              </div>

              <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="rounded border-slate-300"
                />
                Set as default route start/end base
              </label>

              <p className="text-xs text-slate-500">
                The base office acts as the initial state (start node) and optional terminal goal state when return-to-office is enabled. Enter coordinates manually (no external geocoding API).
              </p>

              <button
                type="submit"
                disabled={saving}
                className="w-full whitespace-nowrap rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : selectedOfficeId ? 'Update Office Location' : 'Create Office Location'}
              </button>
            </form>
          </div>

          {offices.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-5">
              <h4 className="text-sm font-semibold text-slate-900">Saved Office Locations</h4>
              <div className="mt-3 divide-y divide-slate-100">
                {offices.map((off) => (
                  <div
                    key={off.id}
                    className="flex items-center justify-between gap-2 py-2.5"
                  >
                    <button
                      type="button"
                      onClick={() => handleSelectOffice(off)}
                      className={`flex flex-1 items-center justify-between text-left text-sm ${
                        selectedOfficeId === off.id ? 'font-semibold text-blue-700' : 'text-slate-700'
                      }`}
                    >
                      <span>
                        {off.name}
                        {off.is_default && <span className="ml-1.5 text-xs text-emerald-700">· Default</span>}
                      </span>
                      <span className="font-mono text-xs tabular-nums text-slate-500">
                        {off.latitude.toFixed(3)}, {off.longitude.toFixed(3)}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(off)}
                      aria-label={`Delete ${off.name}`}
                      className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-4 lg:col-span-7">
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
              height={460}
              title="Base Office & Active Distributors Map"
            />
          ) : (
            <SchematicMap
              points={mapPoints}
              height={460}
              title="Base Office & Active Distributors Coordinate Preview"
            />
          )}
        </div>
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete Office Location"
        description={`Delete "${deleteTarget?.name}"? Offices referenced by saved route plans cannot be removed while those plans exist.`}
        confirmLabel="Delete Office"
        destructive
        busy={deleting}
        onConfirm={handleDeleteOffice}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};
