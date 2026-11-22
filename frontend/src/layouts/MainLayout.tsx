import React, { useState } from 'react';
import {
  BarChart3,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Database,
  LayoutDashboard,
  Menu,
  Route,
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
  { path: '/optimizer', label: 'Route Planning', icon: Route },
  { path: '/scheduling', label: 'Scheduling', icon: CalendarClock },
  { path: '/analytics', label: 'Insights', icon: BarChart3 },
  { path: '/settings', label: 'Settings', icon: Database },
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
  const [isHovered, setIsHovered] = useState(false);
  const [pinnedOpen, setPinnedOpen] = useState(false);

  const location = useLocation();
  const navigate = useNavigate();

  const currentNav =
    NAV_ITEMS.find((item) => location.pathname.startsWith(item.path)) || NAV_ITEMS[0];

  const isExpanded = isHovered || pinnedOpen;

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      {/* Desktop Collapsible Hover Sidebar */}
      <aside
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`hidden lg:flex flex-col border-r border-slate-200 bg-white transition-all duration-300 ease-in-out shrink-0 z-30 ${
          isExpanded ? 'w-64 shadow-lg' : 'w-16'
        }`}
      >
        {/* Brand Header */}
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-3.5">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 font-bold text-white shadow-sm">
              <Route className="h-4 w-4" />
            </div>
            <span
              className={`whitespace-nowrap text-sm font-bold tracking-tight text-slate-900 transition-opacity duration-200 ${
                isExpanded ? 'opacity-100' : 'opacity-0 pointer-events-none'
              }`}
            >
              Smart Route Planner
            </span>
          </div>
          {isExpanded && (
            <button
              type="button"
              onClick={() => setPinnedOpen(!pinnedOpen)}
              title={pinnedOpen ? 'Unpin sidebar' : 'Pin sidebar open'}
              className="hidden rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 lg:block"
            >
              {pinnedOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </button>
          )}
        </div>

        {/* Primary Navigation List with Tooltips */}
        <nav className="flex-1 space-y-1.5 p-2" aria-label="Primary Navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.path);
            return (
              <div key={item.path} className="relative group">
                <NavLink
                  to={item.path}
                  onClick={() => setMobileNavOpen(false)}
                  className={`flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span
                    className={`whitespace-nowrap transition-opacity duration-200 ${
                      isExpanded ? 'opacity-100' : 'opacity-0 pointer-events-none'
                    }`}
                  >
                    {item.label}
                  </span>
                </NavLink>

                {/* Tooltip in Collapsed Mode */}
                {!isExpanded && (
                  <div className="pointer-events-none absolute left-full top-1/2 ml-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-slate-900 px-2.5 py-1 text-xs font-semibold text-white opacity-0 shadow-md transition-opacity group-hover:opacity-100 z-50">
                    {item.label}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Footer info in expanded mode */}
        {isExpanded && (
          <div className="border-t border-slate-200 p-4 text-xs text-slate-500">
            <p className="font-semibold text-slate-700">Karachi Field Route Ops</p>
            <p className="mt-0.5">Leaflet OSM · SQLite DB</p>
          </div>
        )}
      </aside>

      {/* Mobile Drawer (Click to expand) */}
      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-slate-950/40"
            onClick={() => setMobileNavOpen(false)}
          />
          <aside className="relative z-10 flex w-64 flex-col bg-white shadow-xl">
            <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4">
              <span className="text-sm font-bold text-slate-900">Smart Route Planner</span>
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                className="rounded p-1 text-slate-500 hover:bg-slate-100"
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
                    <Icon className="h-5 w-5 shrink-0" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </aside>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
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
              {currentNav.label}
            </h1>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <button
              type="button"
              onClick={() => navigate('/settings')}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-900"
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
              <span className="font-mono text-[11px]">
                {dbHealth?.activeDatabase || 'SQLite'}
              </span>
            </button>
          </div>
        </header>

        {/* Notice toast */}
        {notice && (
          <div
            className={`border-b px-4 py-2.5 text-xs font-medium transition-colors ${
              notice.kind === 'error'
                ? 'border-red-200 bg-red-50 text-red-900'
                : 'border-emerald-200 bg-emerald-50 text-emerald-900'
            }`}
          >
            <div className="flex items-center justify-between">
              <span>{notice.text}</span>
              <button
                type="button"
                onClick={onDismissNotice}
                className="text-xs opacity-70 hover:opacity-100"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {/* Content Outlet */}
        <main className="flex-1 p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
