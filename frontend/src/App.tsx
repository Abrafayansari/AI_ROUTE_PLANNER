import { useCallback, useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { fetchHealth } from './services/api';
import type { DatabaseHealth } from './types';
import { MainLayout } from './layouts/MainLayout';
import { DashboardPage } from './pages/DashboardPage';
import { DistributorsPage } from './pages/DistributorsPage';
import { SchedulingPage } from './pages/SchedulingPage';
import { OptimizerPage } from './pages/OptimizerPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { SettingsPage } from './pages/SettingsPage';
import { SavedPlansPage } from './pages/SavedPlansPage';

export default function App() {
  const [dbHealth, setDbHealth] = useState<DatabaseHealth | null>(null);
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      const payload = await fetchHealth();
      setDbHealth(payload.database);
      return true;
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Unable to reach /api/health endpoint.';
      setDbHealth({
        configured: false,
        connected: false,
        dialect: null,
        activeDatabase: 'Disconnected',
        neonReachable: false,
        neonTablesVerified: false,
        fallbackActive: false,
        fallbackReason: null,
        schemaReady: false,
        missingTables: [],
        existingTables: [],
        latencyMs: null,
        message,
      });
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    const check = async (attempt: number) => {
      const reachable = await refreshHealth();
      if (!reachable && !cancelled && attempt < 25) {
        retryTimer = setTimeout(() => {
          void check(attempt + 1);
        }, 2500);
      }
    };

    void check(0);
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [refreshHealth]);

  const notify = useCallback((kind: 'success' | 'error', text: string) => {
    setNotice({ kind, text });
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(timer);
  }, [notice]);

  return (
    <Routes>
      <Route
        element={
          <MainLayout
            dbHealth={dbHealth}
            notice={notice}
            onDismissNotice={() => setNotice(null)}
          />
        }
      >
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="/dashboard"
          element={
            <DashboardPage
              dbHealth={dbHealth}
              onNotify={notify}
              onRefreshHealth={() => void refreshHealth()}
            />
          }
        />
        <Route path="/distributors" element={<DistributorsPage onNotify={notify} />} />
        <Route path="/scheduling" element={<SchedulingPage onNotify={notify} />} />
        <Route path="/optimizer" element={<OptimizerPage onNotify={notify} />} />
        <Route path="/saved-plans" element={<Navigate to="/optimizer?tab=saved" replace />} />
        <Route path="/saved-plans/:planId" element={<SavedPlansPage onNotify={notify} />} />
        <Route
          path="/delay-prediction"
          element={<Navigate to="/analytics?tab=prediction" replace />}
        />
        <Route path="/clustering" element={<Navigate to="/distributors?tab=clusters" replace />} />
        <Route path="/office" element={<Navigate to="/settings?tab=office" replace />} />
        <Route
          path="/analytics"
          element={<AnalyticsPage onNotify={notify} dbHealth={dbHealth} />}
        />
        <Route path="/ai-concepts" element={<Navigate to="/analytics" replace />} />
        <Route
          path="/settings"
          element={
            <SettingsPage
              dbHealth={dbHealth}
              onRefreshHealth={refreshHealth}
              onNotify={notify}
            />
          }
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
