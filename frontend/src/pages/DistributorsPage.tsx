import React, { useEffect, useState } from 'react';
import { Download, Edit3, Map as MapIcon, Plus, Search, Store, Trash2, Upload, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { api, distributorsExportUrl } from '../services/api';
import { ConfirmDialog } from '../components/ConfirmDialog';
import type { Distributor, PaginationMeta } from '../types';
import { ClusteringPage } from './ClusteringPage';
import { formatTime12Hour } from '../utils/time';

interface DistributorsPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

interface DistributorFormState {
  name: string;
  contact_person: string;
  phone: string;
  email: string;
  address: string;
  latitude: string;
  longitude: string;
  priority: string;
  visit_duration_minutes: string;
  opening_time: string;
  closing_time: string;
  is_active: boolean;
  notes: string;
}

const EMPTY_FORM: DistributorFormState = {
  name: '',
  contact_person: '',
  phone: '',
  email: '',
  address: '',
  latitude: '',
  longitude: '',
  priority: '3',
  visit_duration_minutes: '30',
  opening_time: '09:00',
  closing_time: '17:00',
  is_active: true,
  notes: '',
};

export const DistributorsPage: React.FC<DistributorsPageProps> = ({ onNotify }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTab = searchParams.get('tab') === 'clusters' ? 'clusters' : 'directory';

  const [items, setItems] = useState<Distributor[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta>({
    page: 1,
    pageSize: 15,
    total: 0,
    totalPages: 1,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState<'all' | 'true' | 'false'>('all');
  const [sortBy, setSortBy] = useState('priority');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<DistributorFormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Distributor | null>(null);
  const [deleting, setDeleting] = useState(false);

  const [csvOpen, setCsvOpen] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [csvImporting, setCsvImporting] = useState(false);

  const loadList = async (targetPage = page) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getDistributors({
        search,
        active: activeFilter,
        sortBy,
        sortDir,
        page: targetPage,
        pageSize: 15,
      });
      setItems(res.data.items);
      setPagination(res.data.pagination);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load distributors');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadList(page);
  }, [search, activeFilter, sortBy, sortDir, page]);

  const openCreate = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  };

  const openEdit = (d: Distributor) => {
    setEditingId(d.id);
    setForm({
      name: d.name,
      contact_person: d.contact_person,
      phone: d.phone,
      email: d.email || '',
      address: d.address,
      latitude: String(d.latitude),
      longitude: String(d.longitude),
      priority: String(d.priority),
      visit_duration_minutes: String(d.visit_duration_minutes),
      opening_time: d.opening_time,
      closing_time: d.closing_time,
      is_active: d.is_active,
      notes: d.notes || '',
    });
    setFormError(null);
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const lat = Number(form.latitude);
    const lng = Number(form.longitude);
    const priority = Number(form.priority);
    const duration = Number(form.visit_duration_minutes);

    if (Number.isNaN(lat) || lat < -90 || lat > 90) {
      setFormError('Latitude must be a number between -90 and 90.');
      return;
    }
    if (Number.isNaN(lng) || lng < -180 || lng > 180) {
      setFormError('Longitude must be a number between -180 and 180.');
      return;
    }
    if (form.closing_time <= form.opening_time) {
      setFormError('Closing time must be strictly after opening time.');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        contact_person: form.contact_person.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        address: form.address.trim(),
        latitude: lat,
        longitude: lng,
        priority,
        visit_duration_minutes: duration,
        opening_time: form.opening_time,
        closing_time: form.closing_time,
        is_active: form.is_active,
        notes: form.notes.trim(),
      };

      if (editingId) {
        await api.updateDistributor(editingId, payload);
        onNotify('success', 'Distributor updated in database.');
      } else {
        await api.createDistributor(payload);
        onNotify('success', 'Distributor created in database.');
      }
      setModalOpen(false);
      await loadList(1);
      setPage(1);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Failed to save distributor');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.deleteDistributor(deleteTarget.id);
      onNotify('success', `Deleted "${deleteTarget.name}".`);
      setDeleteTarget(null);
      await loadList(page);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to delete distributor');
    } finally {
      setDeleting(false);
    }
  };

  const handleLoadDemo = async () => {
    try {
      const res = await api.loadDemoData();
      onNotify('success', res.message || 'Demo data loaded.');
      await loadList(1);
      setPage(1);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to load demo data');
    }
  };

  const handleCsvImport = async (e: React.FormEvent) => {
    e.preventDefault();
    setCsvImporting(true);
    try {
      const res = await api.importDistributorsCsv(csvText);
      onNotify('success', res.message || `Imported ${res.data.importedCount} distributors.`);
      setCsvOpen(false);
      setCsvText('');
      await loadList(1);
      setPage(1);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'CSV import failed');
    } finally {
      setCsvImporting(false);
    }
  };

  const handleCsvFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setCsvText(String(reader.result || ''));
    reader.readAsText(file);
  };

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <div className="flex border-b border-slate-200 bg-white px-6 pt-3">
        <button
          type="button"
          onClick={() => setSearchParams({ tab: 'directory' })}
          className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
            currentTab === 'directory'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Store className="h-4 w-4" />
          Distributor Directory
        </button>
        <button
          type="button"
          onClick={() => setSearchParams({ tab: 'clusters' })}
          className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
            currentTab === 'clusters'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <MapIcon className="h-4 w-4" />
          Map & K-Means Clusters
        </button>
      </div>

      {currentTab === 'clusters' ? (
        <ClusteringPage onNotify={onNotify} />
      ) : (
        <div className="space-y-6">
      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search name, contact, address..."
              className="w-64 rounded-md border border-slate-200 py-1.5 pl-9 pr-3 text-sm text-slate-900 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-1 rounded-md bg-slate-100 p-1">
            {(['all', 'true', 'false'] as const).map((val) => (
              <button
                key={val}
                type="button"
                onClick={() => {
                  setActiveFilter(val);
                  setPage(1);
                }}
                className={`whitespace-nowrap shrink-0 rounded px-2.5 py-1 text-xs font-medium ${
                  activeFilter === val
                    ? 'bg-white text-slate-900 shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {val === 'all' ? 'All' : val === 'true' ? 'Active' : 'Inactive'}
              </button>
            ))}
          </div>

          <select
            value={`${sortBy}:${sortDir}`}
            onChange={(e) => {
              const [col, dir] = e.target.value.split(':');
              setSortBy(col);
              setSortDir(dir as 'asc' | 'desc');
              setPage(1);
            }}
            aria-label="Sort distributors"
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700"
          >
            <option value="priority:desc">Priority (High → Low)</option>
            <option value="priority:asc">Priority (Low → High)</option>
            <option value="name:asc">Name (A → Z)</option>
            <option value="visit_duration_minutes:desc">Duration (Longest)</option>
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setCsvOpen(true)}
            className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <Upload className="h-3.5 w-3.5" />
            Import CSV
          </button>
          <a
            href={distributorsExportUrl}
            className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </a>
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Distributor
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        {loading ? (
          <div className="space-y-2 p-6">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-slate-100" />
            ))}
          </div>
        ) : error ? (
          <div className="p-6 text-sm text-red-700">{error}</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center">
            <p className="text-base font-semibold text-slate-900">No distributors found</p>
            <p className="mt-1 max-w-md text-sm text-slate-600">
              Add distributor records manually with coordinates, import a CSV, or insert the fictional 9-distributor demo dataset.
            </p>
            <div className="mt-4 flex items-center gap-3">
              <button
                type="button"
                onClick={handleLoadDemo}
                className="whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                Load Demo Data
              </button>
              <button
                type="button"
                onClick={openCreate}
                className="whitespace-nowrap shrink-0 rounded-md border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Add Distributor
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
                  <tr>
                    <th className="px-5 py-3">Distributor</th>
                    <th className="px-4 py-3">Contact</th>
                    <th className="px-4 py-3">Coordinates (Lat / Lng)</th>
                    <th className="px-4 py-3 text-right">Priority</th>
                    <th className="px-4 py-3 text-right">Duration</th>
                    <th className="px-4 py-3">Hours</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-5 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((d) => (
                    <tr key={d.id} className="hover:bg-slate-50/70">
                      <td className="px-5 py-3">
                        <div className="font-medium text-slate-900">
                          {d.name}
                          {d.is_demo && (
                            <span className="ml-1.5 text-xs font-normal text-slate-400">· Demo</span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500">{d.address}</div>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-700">
                        <div className="font-medium text-slate-900">{d.contact_person}</div>
                        <div className="font-mono text-slate-500">{d.phone}</div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs tabular-nums text-slate-700">
                        {d.latitude.toFixed(4)}, {d.longitude.toFixed(4)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-slate-900">
                        {d.priority} / 5
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs tabular-nums text-slate-700">
                        {d.visit_duration_minutes} min
                      </td>
                      <td className="px-4 py-3 font-mono text-xs tabular-nums text-slate-700">
                        {formatTime12Hour(d.opening_time)} – {formatTime12Hour(d.closing_time)}
                      </td>
                      <td className="px-4 py-3 text-xs font-medium">
                        <span className={d.is_active ? 'text-emerald-700' : 'text-slate-400'}>
                          {d.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <div className="inline-flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => openEdit(d)}
                            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                            aria-label={`Edit ${d.name}`}
                          >
                            <Edit3 className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget(d)}
                            className="rounded p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600"
                            aria-label={`Delete ${d.name}`}
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
                Showing page {pagination.page} of {pagination.totalPages} ({pagination.total} records)
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={pagination.page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded border border-slate-200 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={pagination.page >= pagination.totalPages}
                  onClick={() => setPage((p) => p + 1)}
                  className="rounded border border-slate-200 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-slate-200 bg-white p-6 shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-900">
                {editingId ? 'Edit Distributor' : 'Add Distributor'}
              </h3>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="mt-4 space-y-4">
              {formError && (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                  {formError}
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs font-medium text-slate-700">Distributor Name *</label>
                  <input
                    required
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">Contact Person *</label>
                  <input
                    required
                    value={form.contact_person}
                    onChange={(e) => setForm({ ...form, contact_person: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">Phone (7–25 chars) *</label>
                  <input
                    required
                    minLength={7}
                    maxLength={25}
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">Email</label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-slate-700">Street Address *</label>
                  <input
                    required
                    value={form.address}
                    onChange={(e) => setForm({ ...form, address: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">
                    Latitude (-90 to 90) *
                  </label>
                  <input
                    type="number"
                    step="any"
                    required
                    placeholder="e.g. 24.8138"
                    value={form.latitude}
                    onChange={(e) => setForm({ ...form, latitude: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">
                    Longitude (-180 to 180) *
                  </label>
                  <input
                    type="number"
                    step="any"
                    required
                    placeholder="e.g. 67.0299"
                    value={form.longitude}
                    onChange={(e) => setForm({ ...form, longitude: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">Priority (1–5)</label>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    required
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">
                    Visit Duration (minutes)
                  </label>
                  <input
                    type="number"
                    min={5}
                    max={480}
                    required
                    value={form.visit_duration_minutes}
                    onChange={(e) => setForm({ ...form, visit_duration_minutes: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">Opening Time</label>
                  <input
                    type="time"
                    required
                    value={form.opening_time}
                    onChange={(e) => setForm({ ...form, opening_time: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700">Closing Time</label>
                  <input
                    type="time"
                    required
                    value={form.closing_time}
                    onChange={(e) => setForm({ ...form, closing_time: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-slate-700">Notes</label>
                  <textarea
                    rows={2}
                    value={form.notes}
                    onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm"
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={form.is_active}
                      onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                      className="rounded border-slate-300"
                    />
                    Active distributor (eligible for clustering, scheduling, and routing)
                  </label>
                </div>
              </div>

              <p className="text-xs text-slate-500">
                Coordinates are entered manually; no external geocoding service is used.
              </p>

              <div className="flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="whitespace-nowrap shrink-0 rounded-md border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : editingId ? 'Save Changes' : 'Create Distributor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

        </div>
      )}

      {csvOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-xl rounded-lg border border-slate-200 bg-white p-6 shadow-lg">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-900">Import Distributors CSV</h3>
              <button
                type="button"
                onClick={() => setCsvOpen(false)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleCsvImport} className="mt-4 space-y-4">
              <p className="text-xs text-slate-600">
                Required columns: <code className="font-mono">name, contact_person, phone, address, latitude, longitude</code>. Optional: <code className="font-mono">email, priority, visit_duration_minutes, opening_time, closing_time, is_active, notes</code>.
              </p>
              <input type="file" accept=".csv,text/csv" onChange={handleCsvFile} className="text-xs" />
              <textarea
                rows={7}
                required
                value={csvText}
                onChange={(e) => setCsvText(e.target.value)}
                placeholder="name,contact_person,phone,email,address,latitude,longitude,priority,visit_duration_minutes,opening_time,closing_time"
                className="w-full rounded-md border border-slate-200 p-3 font-mono text-xs"
              />
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setCsvOpen(false)}
                  className="rounded-md border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={csvImporting}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {csvImporting ? 'Importing...' : 'Import Rows'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete Distributor"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? Associated route stops and schedule entries referencing this distributor will also be removed.`}
        confirmLabel="Delete Distributor"
        destructive
        busy={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
};
