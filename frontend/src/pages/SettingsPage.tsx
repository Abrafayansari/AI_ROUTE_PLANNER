import React, { useState } from 'react';
import { CheckCircle2, Database, RefreshCw, Trash2, XCircle } from 'lucide-react';
import { api } from '../services/api';
import { ConfirmDialog } from '../components/ConfirmDialog';
import type { DatabaseHealth } from '../types';

interface SettingsPageProps {
  dbHealth: DatabaseHealth | null;
  onRefreshHealth: () => Promise<boolean | void>;
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  dbHealth,
  onRefreshHealth,
  onNotify,
}) => {
  const [busyInit, setBusyInit] = useState(false);
  const [busyDemo, setBusyDemo] = useState(false);
  const [checkingHealth, setCheckingHealth] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  const handleRecheckHealth = async () => {
    setCheckingHealth(true);
    try {
      const ok = await onRefreshHealth();
      if (ok === false) {
        onNotify('error', 'Health check failed — see database status details below.');
      }
    } finally {
      setCheckingHealth(false);
    }
  };

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

  const existingCount = dbHealth?.existingTables.length ?? 0;
  const missingCount = dbHealth?.missingTables.length ?? 0;
  const requiredCount = dbHealth ? existingCount + missingCount : 10;

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <Database className="h-5 w-5 text-slate-700" />
            <div>
              <h3 className="text-base font-semibold text-slate-900">
                Database Connection &amp; Schema Audit ({dbHealth?.activeDatabase || 'Checking...'})
              </h3>
              <p className="text-xs text-slate-500">
                Verified by Flask + SQLAlchemy via GET /api/health · Dialect:{' '}
                <code className="font-mono">{dbHealth?.dialect ?? 'unknown'}</code> · Fallback:{' '}
                <code className="font-mono">
                  {dbHealth ? (dbHealth.fallbackActive ? 'active' : 'inactive') : 'unknown'}
                </code>{' '}
                · Credentials never leave the server
              </p>
            </div>
          </div>

          <button
            type="button"
            disabled={checkingHealth}
            onClick={() => void handleRecheckHealth()}
            className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${checkingHealth ? 'animate-spin' : ''}`} />
            {checkingHealth ? 'Checking...' : 'Re-check Health'}
          </button>
        </div>

        {dbHealth && !dbHealth.connected && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 text-xs text-red-900">
            <p className="font-semibold">Database Health Check Error</p>
            <p className="mt-1">{dbHealth.message || 'Unable to verify database health.'}</p>
          </div>
        )}

        {dbHealth?.fallbackActive && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
            <p className="font-semibold">
              SQLite Fallback Active — Not Connected to Neon PostgreSQL
            </p>
            <p className="mt-1">
              {dbHealth.fallbackReason ||
                'Neon PostgreSQL is unreachable or unconfigured; local SQLite fallback is active.'}
            </p>
          </div>
        )}

        <div className="mt-4 grid gap-4 sm:grid-cols-4">
          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-xs text-slate-500">Active Dialect</p>
            <p className="mt-1 flex items-center gap-1.5 font-mono text-sm font-semibold text-slate-900">
              {dbHealth?.activeDatabase && dbHealth.dialect === 'postgresql'
                ? `${dbHealth.activeDatabase} (${dbHealth.dialect})`
                : (dbHealth?.dialect ?? 'unknown')}
            </p>
          </div>

          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-xs text-slate-500">Neon PostgreSQL</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
              {dbHealth?.neonReachable ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span className="text-emerald-700">Neon Connected</span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-amber-600" />
                  <span className="text-amber-700">Not Connected</span>
                </>
              )}
            </p>
          </div>

          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-xs text-slate-500">Active Engine</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
              {dbHealth?.connected ? (
                <>
                  <CheckCircle2
                    className={`h-4 w-4 ${dbHealth.fallbackActive ? 'text-amber-600' : 'text-emerald-600'}`}
                  />
                  <span className={dbHealth.fallbackActive ? 'text-amber-700' : 'text-emerald-700'}>
                    {dbHealth.fallbackActive ? 'SQLite Fallback' : 'Connected'} ({dbHealth.latencyMs ?? 0} ms)
                  </span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-red-600" />
                  <span className="text-red-700">Disconnected</span>
                </>
              )}
            </p>
          </div>

          <div className="rounded-md border border-slate-200 p-4">
            <p className="text-xs text-slate-500">
              Schema Tables ({requiredCount || 10} Required)
            </p>
            <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
              {dbHealth?.schemaReady ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  <span className="text-emerald-700">
                    {existingCount} / {requiredCount || 10} Verified
                  </span>
                </>
              ) : (
                <>
                  <XCircle className="h-4 w-4 text-amber-600" />
                  <span className="text-amber-700">
                    {existingCount} / {requiredCount || 10} Present
                  </span>
                </>
              )}
            </p>
          </div>
        </div>

        <p className="mt-4 text-sm text-slate-700">{dbHealth?.message}</p>

        {dbHealth?.existingTables && dbHealth.existingTables.length > 0 && (
          <div className="mt-3 rounded-md border border-slate-100 bg-slate-50 p-3">
            <p className="text-xs font-medium text-slate-600">
              Verified Tables ({dbHealth.existingTables.length}):
            </p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {dbHealth.existingTables.map((table) => (
                <span
                  key={table}
                  className="rounded border border-slate-200 bg-white px-2 py-0.5 font-mono text-[11px] text-slate-700"
                >
                  {table}
                </span>
              ))}
            </div>
          </div>
        )}

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
          Workspace access note: This app operates as a single-user/demo operations workspace with no fake login wall. No external routing or geocoding API keys are required (Leaflet loads free OpenStreetMap basemap tiles client-side).
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
