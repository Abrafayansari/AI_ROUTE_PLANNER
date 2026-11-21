import React, { useState } from 'react';
import {
  BarChart3,
  BookOpen,
  Building2,
  CalendarClock,
  CheckCircle2,
  Database,
  FolderKanban,
  LayoutDashboard,
  Map as MapIcon,
  Menu,
  Plus,
  Route,
  ShieldAlert,
  Store,
  X,
} from 'lucide-react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import type { DatabaseHealth } from '../types';

export const NAV_ITEMS: Array<{
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/distributors', label: 'Distributors', icon: Store },
  { path: '/office', label: 'Office Location', icon: Building2 },
  { path: '/clustering', label: 'Map & Clusters', icon: MapIcon },
  { path: '/scheduling', label: 'Visit Scheduling', icon: CalendarClock },
  { path: '/optimizer', label: 'Route Optimizer', icon: Route },
  { path: '/saved-plans', label: 'Saved Plans', icon: FolderKanban },
  { path: '/delay-prediction', label: 'Visit Delay Prediction', icon: ShieldAlert },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/ai-concepts', label: 'AI Lab Concepts', icon: BookOpen },
  { path: '/settings', label: 'Settings / Database', icon: Database },
];

interface MainLayoutProps {
  dbHealth: DatabaseHealth | null;
  notice: { kind: 'success' | 'error'; text: string } | null;
  onDismissNotice: () => void;
}

export const MainLayout: React.FC<MainLayoutProps> = ({
  dbHealth,
  notice,
  onDismissNotice,
}) => {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const currentNav =
    NAV_ITEMS.find((item) => location.pathname.startsWith(item.path)) || NAV_ITEMS[0];

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      {/* Desktop Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="flex h-14 items-center border-b border-slate-200 px-5">
          <span className="text-sm font-bold tracking-tight text-slate-900">
            Smart Route Planner
          </span>
        </div>

        <nav className="flex-1 space-y-1 p-3" aria-label="Primary Navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setMobileNavOpen(false)}
                className={({ isActive }) =>
                  `flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-slate-200 p-4 text-xs text-slate-500">
          <p className="font-medium text-slate-700">Python Flask + React Stack</p>
          <p className="mt-0.5">Local coordinates · OSM Leaflet / Simulated routing</p>
        </div>
      </aside>

      {/* Mobile Drawer */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-slate-950/40"
            onClick={() => setMobileNavOpen(false)}
          />
          <aside className="relative z-10 flex w-64 flex-col bg-white shadow-xl">
            <div className="flex h-14 items-center justify-between border-b border-slate-200 px-5">
              <span className="text-sm font-bold text-slate-900">Smart Route Planner</span>
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                className="rounded p-1 text-slate-500"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="flex-1 space-y-1 p-3">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    onClick={() => setMobileNavOpen(false)}
                    className={({ isActive }) =>
                      `flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm font-medium ${
                        isActive ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-100'
                      }`
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </aside>
        </div>
      )}

      {/* Main Content */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-4 border-b border-slate-200 bg-white px-4 lg:px-8">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileNavOpen(true)}
              className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden"
              aria-label="Open navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="truncate text-sm font-semibold text-slate-900">
              Field Operations / {currentNav.label}
            </h1>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <button
              type="button"
              onClick={() => navigate('/settings')}
              className="hidden items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 sm:inline-flex"
            >
              <Database
                className={`h-3.5 w-3.5 ${
                  dbHealth?.connected && dbHealth?.schemaReady
                    ? 'text-emerald-600'
                    : dbHealth?.connected
                      ? 'text-amber-600'
                      : 'text-red-600'
                }`}
              />
              {dbHealth?.connected && dbHealth?.schemaReady
                ? 'DB Connected'
                : dbHealth?.connected
                  ? 'Schema Needed'
                  : 'DB Disconnected'}
            </button>

            <button
              type="button"
              onClick={() => navigate('/optimizer')}
              className="inline-flex items-center gap-1.5 whitespace-nowrap shrink-0 rounded-md bg-blue-600 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
            >
              <Plus className="h-3.5 w-3.5" />
              New Route Plan
            </button>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1360px] flex-1 p-4 lg:p-8">
          {notice && (
            <div
              role="status"
              className={`mb-5 flex items-center justify-between gap-4 rounded-md border px-4 py-3 text-sm ${
                notice.kind === 'success'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                  : 'border-red-200 bg-red-50 text-red-900'
              }`}
            >
              <span className="flex items-center gap-2">
                {notice.kind === 'success' && <CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                {notice.text}
              </span>
              <button
                type="button"
                onClick={onDismissNotice}
                className="text-xs font-medium opacity-70 hover:opacity-100"
              >
                Dismiss
              </button>
            </div>
          )}

          <Outlet />
        </main>
      </div>
    </div>
  );
};
