import React, { useState } from 'react';
import { CheckCircle2, Database, RefreshCw, Trash2, XCircle } from 'lucide-react';
import { api } from '../services/api';
import { ConfirmDialog } from '../components/ConfirmDialog';
import type { DatabaseHealth } from '../types';

interface SettingsPageProps {
  dbHealth: DatabaseHealth | null;
  onRefreshHealth: () => Promise<void>;
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  dbHealth,
  onRefreshHealth,
  onNotify,
}) => {
  const [busyInit, setBusyInit] = useState(false);
  const [busyDemo, setBusyDemo] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  const handleInitSchema = async () => {
    setBusyInit(true);
    try {
      const res = await api.initDatabase();
      onNotify('success', res.message || 'Schema verified and initialized.');
      await onRefreshHealth();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Schema initialization failed');
    } finally {
      setBusyInit(false);
    }
  };

  const handleLoadDemo = async () => {
    setBusyDemo(true);
    try {
      const res = await api.loadDemoData();
      onNotify('success', res.message || 'Demo data loaded.');
      await onRefreshHealth();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to load demo data');
    } finally {
      setBusyDemo(false);
    }
  };

  const handleClearDemo = async () => {
    setBusyDemo(true);
    try {
      const res = await api.clearDemoData();
      onNotify('success', res.message || 'Cleared demo records.');
      setConfirmClearOpen(false);
      await onRefreshHealth();
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to clear demo data');
    } finally {
      setBusyDemo(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <Database className="h-5 w-5 text-slate-700" />
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                Neon PostgreSQL Connection & Schema Status
              </h3>
              <p className="text-xs text-slate-500">
                Verified by Flask + SQLAlchemy via GET /api/health · Credentials never leave the server
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void onRefreshHealth()}
            className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Re-check Health
          </button>
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-xs text-slate-500">DATABASE_URL Secret</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
              {dbHealth?.configured ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span className="text-emerald-700">Configured</span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-red-600" />
                  <span className="text-red-700">Not Configured</span>
                </>
              )}
            </p>
          </div>

          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-xs text-slate-500">Database Connectivity</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
              {dbHealth?.connected ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span className="text-emerald-700">
                    Connected ({dbHealth.latencyMs ?? 0} ms)
                  </span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-amber-600" />
                  <span className="text-amber-700">Disconnected</span>
                </>
              )}
            </p>
          </div>

          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-xs text-slate-500">Schema Tables (9 Required)</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
              {dbHealth?.schemaReady ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span className="text-emerald-700">All 9 Ready</span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-amber-600" />
                  <span className="text-amber-700">
                    {dbHealth?.existingTables.length ?? 0} / 9 Present
                  </span>
                </>
              )}
            </p>
          </div>
        </div>

        <p className="mt-4 text-sm text-slate-700">{dbHealth?.message}</p>

        {dbHealth?.missingTables && dbHealth.missingTables.length > 0 && (
          <p className="mt-2 font-mono text-xs text-amber-800">
            Missing tables: {dbHealth.missingTables.join(', ')}
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={!dbHealth?.connected || busyInit}
            onClick={handleInitSchema}
            className="whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busyInit ? 'Applying Migrations...' : 'Verify / Initialize Schema (Idempotent)'}
          </button>
          <button
            type="button"
            disabled={!dbHealth?.schemaReady || busyDemo}
            onClick={handleLoadDemo}
            className="whitespace-nowrap shrink-0 rounded-md border border-slate-200 bg-white px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Load Demo Data
          </button>
          <button
            type="button"
            disabled={!dbHealth?.schemaReady || busyDemo}
            onClick={() => setConfirmClearOpen(true)}
            className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 rounded-md border border-red-200 bg-white px-4 py-2 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear Demo Data Only
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
        <h3 className="text-base font-semibold text-slate-900">
          Neon PostgreSQL Setup & Security Guide
        </h3>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-700">
          <li>
            Open Neon Console and select your project. If a database password was previously shared in chat, reset/rotate the role password in Neon before proceeding.
          </li>
          <li>
            Schema alignment is handled non-destructively via SQLAlchemy &amp; Alembic migrations (<code className="font-mono text-xs">backend/migrations/</code>) and <code className="font-mono text-xs">db/schema.sql</code>.
          </li>
          <li>
            Copy the <strong>pooled</strong> PostgreSQL connection string from Neon (recommended for serverless environments).
          </li>
          <li>
            Add it in AI Studio&apos;s server-side <strong>Secrets</strong> panel as <code className="font-mono text-xs">DATABASE_URL</code>. Never use a <code className="font-mono text-xs">VITE_</code> prefix and never commit credentials to Git.
          </li>
          <li>
            Restart the dev server if needed and click <strong>Re-check Health</strong> to verify <code className="font-mono text-xs">GET /api/health</code>.
          </li>
        </ol>
        <p className="border-t border-slate-100 pt-3 text-xs text-slate-500">
          Workspace access note: This app operates as a single-user/demo operations workspace with no fake login wall. No external map API keys or third-party mapping services are used.
        </p>
      </div>

      <ConfirmDialog
        open={confirmClearOpen}
        title="Clear Demo Records"
        description="This removes only records tagged with is_demo = TRUE. Any distributors, offices, schedules, or route plans you created manually will be preserved."
        confirmLabel="Clear Demo Data"
        destructive
        busy={busyDemo}
        onConfirm={handleClearDemo}
        onCancel={() => setConfirmClearOpen(false)}
      />
    </div>
  );
};
