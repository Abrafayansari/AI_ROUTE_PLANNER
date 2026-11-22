import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Award,
  BookOpen,
  Calendar,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Coffee,
  Database,
  Filter,
  Layers,
  MapPin,
  Play,
  RefreshCw,
  Save,
  Search,
  ShieldAlert,
  Sliders,
  Sparkles,
  Table as TableIcon,
  X,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { LeafletRouteMap } from '../components/LeafletRouteMap';
import type { SchematicPoint } from '../components/SchematicMap';
import { formatTime12Hour } from '../utils/time';
import type {
  CspRunResult,
  Distributor,
  OfficeLocation,
  OptimizationObjective,
  ScheduledVisitEntry,
  TravelMode,
  UnscheduledVisitReport,
} from '../types';

interface SchedulingPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

function toMins(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

const STORAGE_KEY_TRAVEL_BUFFER = 'smart_route_planner_travel_buffer';

export const SchedulingPage: React.FC<SchedulingPageProps> = ({ onNotify }) => {
  const navigate = useNavigate();

  // Input Data States
  const [offices, setOffices] = useState<OfficeLocation[]>([]);
  const [officeId, setOfficeId] = useState<string>('');
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [distributorSearch, setDistributorSearch] = useState('');

  // Primary Configuration States
  const [scheduleDate, setScheduleDate] = useState('2026-11-21');
  const [workStartTime, setWorkStartTime] = useState('09:00');
  const [workEndTime, setWorkEndTime] = useState('17:00');
  const [maxVisitsPerDay, setMaxVisitsPerDay] = useState(8);
  const [optimizationObjective, setOptimizationObjective] =
    useState<OptimizationObjective>('FASTEST_TIME');

  // Advanced Configuration (Accordion)
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [slotIncrementMinutes, setSlotIncrementMinutes] = useState(15);
  const [travelBufferMinutes, setTravelBufferMinutes] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY_TRAVEL_BUFFER);
    const num = Number(saved);
    return !Number.isNaN(num) && num >= 0 && num <= 120 && saved !== null ? num : 15;
  });
  const [lunchBreakEnabled, setLunchBreakEnabled] = useState(true);
  const [lunchStartTime, setLunchStartTime] = useState('12:30');
  const [lunchDurationMinutes, setLunchDurationMinutes] = useState(60);
  const [travelMode, setTravelMode] = useState<TravelMode>('DRIVE');
  const [useRoadTravelTimes, setUseRoadTravelTimes] = useState(true);

  // Status & View Modes
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [result, setResult] = useState<CspRunResult | null>(null);
  const [workflowStage, setWorkflowStage] = useState<'configure' | 'generate' | 'review'>('configure');
  const [activeView, setActiveView] = useState<'timeline' | 'table' | 'map'>('timeline');
  const [academicDrawerOpen, setAcademicDrawerOpen] = useState(false);
  const [selectedVisitForMap, setSelectedVisitForMap] = useState<ScheduledVisitEntry | null>(null);

  // Smart Fix Modal & State
  const [smartFixModalOpen, setSmartFixModalOpen] = useState(false);
  const [smartFixMode, setSmartFixMode] = useState<'QUICK_FIX' | 'SMART_OPTIMIZE' | 'SUGGESTIONS_ONLY'>('QUICK_FIX');
  const [smartFixLoading, setSmartFixLoading] = useState(false);
  const [smartFixApplying, setSmartFixApplying] = useState(false);
  const [smartFixRestoring, setSmartFixRestoring] = useState(false);
  const [smartFixData, setSmartFixData] = useState<import('../types').SmartFixResponse | null>(null);
  const [hasBackupSnapshot, setHasBackupSnapshot] = useState(false);

  // Ref to travel buffer input for Bayesian quick-adjust action
  const travelBufferInputRef = useRef<HTMLInputElement | null>(null);

  // Load initial data and any latest saved schedule
  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [offRes, distRes, latestSchedRes] = await Promise.all([
          api.getOffices(),
          api.getDistributors({ active: 'true', pageSize: 100 }),
          api.getLatestSchedule().catch(() => null),
        ]);
        setOffices(offRes.data.offices);
        const defOffice = offRes.data.defaultOffice || offRes.data.offices[0];
        setOfficeId(latestSchedRes?.data?.officeId || defOffice?.id || '');
        setDistributors(distRes.data.items);
        setSelectedIds(distRes.data.items.map((d) => d.id));

        if (latestSchedRes?.data && latestSchedRes.data.entries.length > 0) {
          const entries = latestSchedRes.data.entries;
          const schedDate = String(latestSchedRes.data.scheduleDate || entries[0].schedule_date).slice(0, 10);
          setScheduleDate(schedDate);
          const scheduledIds = new Set(entries.map((e) => e.distributor_id));
          const unscheduledList: UnscheduledVisitReport[] = distRes.data.items
            .filter((d) => !scheduledIds.has(d.id))
            .map((d) => {
              let reason = 'Excluded by schedule constraints.';
              if (entries.length >= maxVisitsPerDay) {
                reason = `Maximum daily visit cap (${maxVisitsPerDay}) reached by higher-priority accounts.`;
              } else if (d.priority < 3) {
                reason = 'Lower priority account deferred due to available shift duration and route constraints.';
              }
              return {
                distributorId: d.id,
                distributorName: d.name,
                priority: d.priority,
                visitDurationMinutes: d.visit_duration_minutes,
                openingTime: d.opening_time,
                closingTime: d.closing_time,
                reason,
              };
            });

          const usesFixed = entries.every((e) => e.travel_from_previous_minutes == null);

          setResult({
            routePlanId: latestSchedRes.data.routePlanId,
            officeId: latestSchedRes.data.officeId,
            officeName: latestSchedRes.data.officeName,
            scheduleDate: schedDate,
            provider: latestSchedRes.data.provider,
            providerLabel: latestSchedRes.data.providerLabel,
            dataSource: latestSchedRes.data.dataSource,
            isLiveTraffic: latestSchedRes.data.isLiveTraffic,
            durationType: latestSchedRes.data.durationType,
            durationLabel: latestSchedRes.data.durationLabel,
            allDistributorsScheduled: unscheduledList.length === 0,
            usesFixedTravelBuffer: usesFixed,
            scheduled: entries.map((e) => ({
              distributorId: e.distributor_id,
              distributorName: e.distributor_name,
              priority: e.priority,
              startTime: e.start_time,
              endTime: e.end_time,
              startMinutes: toMins(e.start_time),
              endMinutes: toMins(e.end_time),
              durationMinutes: e.visit_duration_minutes,
              bufferMinutes: travelBufferMinutes,
              travelMinutesFromPrevious: e.travel_from_previous_minutes ?? undefined,
              openingTime: e.opening_time,
              closingTime: e.closing_time,
              distanceKm: e.distanceKm,
              delayRisk: e.delayRisk,
              delayProbabilities: e.delayProbabilities,
              recommendedBufferMinutes: e.recommendedBufferMinutes,
              delayAdvisory: e.delayAdvisory,
            })),
            unscheduled: unscheduledList,
            backtracks: 0,
            executionTimeMs: 0,
            constraintsSummary: entries[0].constraint_notes || 'Loaded from database',
            bayesianAdvisory: latestSchedRes.data.bayesianAdvisory,
          });
          setWorkflowStage('review');
        }
      } catch (err) {
        onNotify('error', err instanceof Error ? err.message : 'Failed to load scheduling workspace');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  // Filter distributors by search query
  const filteredDistributors = useMemo(() => {
    if (!distributorSearch.trim()) return distributors;
    const q = distributorSearch.toLowerCase();
    return distributors.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        (d.address && d.address.toLowerCase().includes(q))
    );
  }, [distributors, distributorSearch]);

  // Run CSP Solver through backend API
  const handleRunCsp = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (selectedIds.length === 0) {
      onNotify('error', 'Select at least 1 distributor to schedule.');
      return;
    }
    if (workEndTime <= workStartTime) {
      onNotify('error', 'Work end time must be strictly after work start time.');
      return;
    }

    setRunning(true);
    setWorkflowStage('generate');
    setScheduleError(null);
    try {
      const res = await api.runSchedule({
        distributorIds: selectedIds,
        officeId: officeId || undefined,
        scheduleDate,
        workStartTime,
        workEndTime,
        slotIncrementMinutes,
        travelBufferMinutes,
        lunchBreakEnabled,
        lunchStartTime,
        lunchDurationMinutes,
        maxVisitsPerDay,
        travelMode,
        optimizationObjective,
        useRoadTravelTimes,
      });
      setResult(res.data);
      setWorkflowStage('review');
      localStorage.setItem(STORAGE_KEY_TRAVEL_BUFFER, String(travelBufferMinutes));
      onNotify(
        'success',
        `Generated schedule: ${res.data.scheduled.length} scheduled, ${res.data.unscheduled.length} unscheduled.`
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'CSP scheduling failed';
      setScheduleError(msg);
      setWorkflowStage('configure');
      onNotify('error', msg);
    } finally {
      setRunning(false);
    }
  };

  // Save Schedule explicitly to the database
  const handleSaveSchedule = async () => {
    if (!result || result.scheduled.length === 0) {
      onNotify('error', 'Generate a valid schedule before saving.');
      return;
    }
    setSaving(true);
    try {
      // Re-trigger solver to persist or refresh DB record
      const res = await api.runSchedule({
        distributorIds: selectedIds,
        officeId: officeId || undefined,
        scheduleDate,
        workStartTime,
        workEndTime,
        slotIncrementMinutes,
        travelBufferMinutes,
        lunchBreakEnabled,
        lunchStartTime,
        lunchDurationMinutes,
        maxVisitsPerDay,
        travelMode,
        optimizationObjective,
        useRoadTravelTimes,
        routePlanId: result.routePlanId,
      });
      setResult(res.data);
      onNotify('success', `Daily schedule for ${scheduleDate} saved successfully.`);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to save schedule');
    } finally {
      setSaving(false);
    }
  };

  // Focus and expand travel buffer setting on advisory action
  const handleFocusTravelBuffer = () => {
    setAdvancedOpen(true);
    setTimeout(() => {
      travelBufferInputRef.current?.focus();
      travelBufferInputRef.current?.select();
    }, 150);
  };

  // Preview Smart Fix
  const handleOpenSmartFix = async (mode: 'QUICK_FIX' | 'SMART_OPTIMIZE' | 'SUGGESTIONS_ONLY' = 'QUICK_FIX') => {
    setSmartFixMode(mode);
    setSmartFixModalOpen(true);
    setSmartFixLoading(true);
    try {
      const res = await api.previewSmartFix({
        mode,
        routePlanId: result?.routePlanId || undefined,
        officeId: officeId || undefined,
        distributorIds: selectedIds,
        scheduleDate,
        workStartTime,
        workEndTime,
        slotIncrementMinutes,
        travelBufferMinutes,
        lunchBreakEnabled,
        lunchStartTime,
        lunchDurationMinutes,
        maxVisitsPerDay,
        travelMode,
        optimizationObjective,
        useRoadTravelTimes,
      });
      setSmartFixData(res.data);
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Smart Fix diagnostic failed');
    } finally {
      setSmartFixLoading(false);
    }
  };

  // Apply Smart Fix Proposal
  const handleApplySmartFix = async () => {
    if (!smartFixData || !smartFixData.activeProposal.scheduled.length) {
      onNotify('error', 'No feasible proposal to apply.');
      return;
    }
    setSmartFixApplying(true);
    try {
      const applyRes = await api.applySmartFix({
        routePlanId: smartFixData.routePlanId || result?.routePlanId || undefined,
        officeId: officeId || undefined,
        scheduleDate,
        mode: smartFixData.mode,
        scheduled: smartFixData.activeProposal.scheduled as unknown as Array<Record<string, unknown>>,
      });

      // Update local state with the newly applied schedule
      if (result) {
        setResult({
          ...result,
          scheduled: smartFixData.activeProposal.scheduled,
          unscheduled: smartFixData.activeProposal.unscheduled,
          allDistributorsScheduled: smartFixData.activeProposal.unscheduled.length === 0,
        });
      }

      // Also reload latest schedule from database to ensure 100% synchronization and persistence
      try {
        const latestRes = await api.getLatestSchedule();
        if (latestRes.data && latestRes.data.entries.length > 0) {
          const entries = latestRes.data.entries;
          const distMap = new Map(distributors.map((d) => [d.id, d]));
          const scheduledEntries: ScheduledVisitEntry[] = entries.map((e) => {
            const d = distMap.get(e.distributor_id);
            return {
              distributorId: e.distributor_id,
              distributorName: e.distributor_name,
              priority: e.priority,
              startTime: e.start_time,
              endTime: e.end_time,
              startMinutes: toMins(e.start_time),
              endMinutes: toMins(e.end_time),
              durationMinutes: e.visit_duration_minutes,
              bufferMinutes: travelBufferMinutes,
              travelMinutesFromPrevious: e.travel_from_previous_minutes || undefined,
              openingTime: d?.opening_time || '08:00',
              closingTime: d?.closing_time || '18:00',
              distanceKm: e.distanceKm,
              delayRisk: e.delayRisk,
            };
          });
          setResult((prev) => prev ? {
            ...prev,
            routePlanId: latestRes.data?.routePlanId ?? prev.routePlanId,
            scheduled: scheduledEntries,
            unscheduled: smartFixData.activeProposal.unscheduled,
            allDistributorsScheduled: smartFixData.activeProposal.unscheduled.length === 0,
          } : prev);
        }
      } catch {
        // Fallback to local state if background refetch fails
      }

      setHasBackupSnapshot(true);
      setSmartFixModalOpen(false);
      onNotify('success', applyRes.data.message || 'Smart Fix applied successfully.');
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to apply Smart Fix proposal');
    } finally {
      setSmartFixApplying(false);
    }
  };

  // Restore Pre-Repair Schedule
  const handleRestoreSchedule = async () => {
    const planId = smartFixData?.routePlanId || result?.routePlanId;
    if (!planId) return;
    setSmartFixRestoring(true);
    try {
      const res = await api.restoreSchedule({ routePlanId: planId });
      // Reload latest schedule from DB
      const latest = await api.getLatestSchedule();
      if (latest.data && latest.data.entries.length > 0) {
        const distMap = new Map(distributors.map((d) => [d.id, d]));
        const schedEntries: ScheduledVisitEntry[] = latest.data.entries.map((e) => {
          const d = distMap.get(e.distributor_id);
          return {
            distributorId: e.distributor_id,
            distributorName: e.distributor_name,
            priority: e.priority,
            startTime: e.start_time,
            endTime: e.end_time,
            startMinutes: toMins(e.start_time),
            endMinutes: toMins(e.end_time),
            durationMinutes: e.visit_duration_minutes,
            bufferMinutes: travelBufferMinutes,
            travelMinutesFromPrevious: e.travel_from_previous_minutes || undefined,
            openingTime: d?.opening_time || '08:00',
            closingTime: d?.closing_time || '18:00',
            distanceKm: e.distanceKm,
            delayRisk: e.delayRisk,
          };
        });
        if (result) {
          setResult({
            ...result,
            scheduled: schedEntries,
          });
        }
      }
      setHasBackupSnapshot(false);
      setSmartFixModalOpen(false);
      onNotify('success', res.data.message || 'Original schedule restored.');
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'Failed to restore schedule');
    } finally {
      setSmartFixRestoring(false);
    }
  };

  // KPI Calculations grounded in verified backend schedule data
  const kpiStats = useMemo(() => {
    if (!result) {
      return {
        scheduledCount: 0,
        unscheduledCount: 0,
        highRiskCount: 0,
        utilizationText: 'N/A',
      };
    }

    const scheduledCount = result.scheduled.length;
    const unscheduledCount = result.unscheduled.length;
    const highRiskCount = result.scheduled.filter(
      (s) => s.delayRisk === 'High' || (s.delayProbabilities && s.delayProbabilities.High >= 0.45)
    ).length;

    // Working hours available minutes (excluding lunch break if enabled)
    const workStartM = toMins(workStartTime);
    const workEndM = toMins(workEndTime);
    const totalWorkM = Math.max(0, workEndM - workStartM);
    const lunchM = lunchBreakEnabled ? lunchDurationMinutes : 0;
    const availableWorkingDuration = Math.max(1, totalWorkM - lunchM);

    // Total scheduled visit duration
    const scheduledVisitDuration = result.scheduled.reduce(
      (sum, s) => sum + (s.durationMinutes || 0),
      0
    );

    const utilizationPct = Math.round((scheduledVisitDuration / availableWorkingDuration) * 100);
    const utilizationText = totalWorkM > 0 ? `${utilizationPct}%` : 'N/A';

    return {
      scheduledCount,
      unscheduledCount,
      highRiskCount,
      utilizationText,
    };
  }, [result, workStartTime, workEndTime, lunchBreakEnabled, lunchDurationMinutes]);

  // Map representation points & polyline
  const mapPoints: SchematicPoint[] = useMemo(() => {
    const currentOff = offices.find((o) => o.id === officeId) || offices[0];
    const pts: SchematicPoint[] = [];
    if (currentOff) {
      pts.push({
        id: currentOff.id,
        name: currentOff.name,
        latitude: currentOff.latitude,
        longitude: currentOff.longitude,
        isOffice: true,
      });
    }

    if (result && result.scheduled.length > 0) {
      const scheduledDistMap = new Map(distributors.map((d) => [d.id, d]));
      for (const s of result.scheduled) {
        const dist = scheduledDistMap.get(s.distributorId);
        if (dist) {
          pts.push({
            id: dist.id,
            name: `${s.startTime} - ${dist.name}`,
            latitude: dist.latitude,
            longitude: dist.longitude,
            isOffice: false,
          });
        }
      }
    } else {
      for (const d of distributors.filter((d) => selectedIds.includes(d.id))) {
        pts.push({
          id: d.id,
          name: d.name,
          latitude: d.latitude,
          longitude: d.longitude,
          isOffice: false,
        });
      }
    }
    return pts;
  }, [offices, officeId, distributors, result, selectedIds]);

  const mapOrderIds = useMemo(() => {
    if (!result || result.scheduled.length === 0) return [];
    return result.scheduled.map((s) => s.distributorId);
  }, [result]);

  const dayStartMin = toMins(workStartTime);
  const dayEndMin = Math.max(dayStartMin + 60, toMins(workEndTime));
  const totalDaySpan = dayEndMin - dayStartMin;
  const lunchStartMin = toMins(lunchStartTime);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-16 animate-pulse rounded-lg border border-slate-200 bg-white" />
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="h-96 animate-pulse rounded-lg border border-slate-200 bg-white lg:col-span-4" />
          <div className="h-96 animate-pulse rounded-lg border border-slate-200 bg-white lg:col-span-8" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* 2. Top Application Header (64px) */}
      <header className="flex min-h-[64px] flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-5 py-3 shadow-sm">
        {/* Left: Title & Subtitle */}
        <div>
          <h1 className="text-base font-bold text-slate-900">Visit Scheduling</h1>
          <p className="text-xs text-slate-500">
            Plan and organize your daily distributor visits.
          </p>
        </div>

        {/* Center: Three-stage workflow indicator */}
        <div className="hidden items-center gap-2 sm:flex">
          <div
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
              workflowStage === 'configure'
                ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-600'
                : 'bg-slate-100 text-slate-600'
            }`}
          >
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">
              1
            </span>
            <span>Configure</span>
          </div>
          <ChevronRight className="h-3.5 w-3.5 text-slate-300" />
          <div
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
              workflowStage === 'generate'
                ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-600'
                : 'bg-slate-100 text-slate-600'
            }`}
          >
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">
              2
            </span>
            <span>Generate</span>
          </div>
          <ChevronRight className="h-3.5 w-3.5 text-slate-300" />
          <div
            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
              workflowStage === 'review'
                ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-600'
                : 'bg-slate-100 text-slate-600'
            }`}
          >
            <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-600 text-[10px] text-white">
              3
            </span>
            <span>Review</span>
          </div>
        </div>

        {/* Right Action Area */}
        <div className="flex items-center gap-3">
          <div className="hidden items-center gap-1.5 text-xs font-medium text-slate-600 md:flex">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span>SQLite Connected</span>
          </div>

          {/* <button
            type="button"
            onClick={() => handleOpenSmartFix('QUICK_FIX')}
            className="inline-flex items-center gap-1.5 rounded-md border border-purple-200 bg-purple-50 px-3 py-1.5 text-xs font-semibold text-purple-700 hover:bg-purple-100 shadow-xs"
            title="Intelligent schedule repair, diagnostics, and optimization"
          >
            <Sparkles className="h-3.5 w-3.5 text-purple-600" />
            <span>Smart Fix</span>
          </button> */}

          <button
            type="button"
            onClick={() => setAcademicDrawerOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            title="Inspect Constraint Satisfaction formulation and solver telemetry"
          >
            <BookOpen className="h-3.5 w-3.5 text-blue-600" />
            <span className="hidden sm:inline">Course Project View</span>
          </button>

          <button
            type="button"
            onClick={handleSaveSchedule}
            disabled={saving || !result || result.scheduled.length === 0}
            className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
          >
            <Save className="h-3.5 w-3.5" />
            <span>{saving ? 'Saving...' : 'Save Schedule'}</span>
          </button>
        </div>
      </header>

      {/* 3. Desktop Two-Column Workspace */}
      <div className="grid gap-6 lg:grid-cols-12 items-start">
        {/* LEFT COLUMN: ~380px Configuration Card */}
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm lg:col-span-4 flex flex-col max-h-[calc(100vh-140px)]">
          {/* Scrollable Configuration Body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            <div className="border-b border-slate-100 pb-3">
              <h2 className="text-sm font-bold text-slate-900">Schedule Parameters</h2>
              <p className="text-xs text-slate-500">Configure officer constraints &amp; visit list</p>
            </div>

            {/* Basic Configuration */}
            <div>
              <label className="block text-xs font-medium text-slate-700">Schedule Date</label>
              <input
                type="date"
                required
                value={scheduleDate}
                onChange={(e) => setScheduleDate(e.target.value)}
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
                {offices.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700">Working Hours</label>
                <div className="mt-1 flex items-center gap-1">
                  <input
                    type="time"
                    value={workStartTime}
                    onChange={(e) => setWorkStartTime(e.target.value)}
                    className="w-full rounded-md border border-slate-200 px-1.5 py-1 font-mono text-xs text-center"
                  />
                  <span className="text-slate-400">–</span>
                  <input
                    type="time"
                    value={workEndTime}
                    onChange={(e) => setWorkEndTime(e.target.value)}
                    className="w-full rounded-md border border-slate-200 px-1.5 py-1 font-mono text-xs text-center"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700">Max Visits / Day</label>
                <input
                  type="number"
                  min={1}
                  max={25}
                  value={maxVisitsPerDay}
                  onChange={(e) => setMaxVisitsPerDay(Math.max(1, Number(e.target.value)))}
                  className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-xs"
                />
              </div>
            </div>

            {/* Optimization Objective */}
            <div>
              <label className="block text-xs font-medium text-slate-700">Optimization Goal</label>
              <div className="mt-1.5 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setOptimizationObjective('FASTEST_TIME')}
                  className={`rounded-md border p-2 text-left text-xs transition-colors ${
                    optimizationObjective === 'FASTEST_TIME'
                      ? 'border-blue-600 bg-blue-50/60 text-blue-800 ring-1 ring-blue-600 font-semibold'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <div>Fastest Time</div>
                  <div className="text-[10px] text-slate-500">Minimizes road travel</div>
                </button>
                <button
                  type="button"
                  onClick={() => setOptimizationObjective('SHORTEST_DISTANCE')}
                  className={`rounded-md border p-2 text-left text-xs transition-colors ${
                    optimizationObjective === 'SHORTEST_DISTANCE'
                      ? 'border-blue-600 bg-blue-50/60 text-blue-800 ring-1 ring-blue-600 font-semibold'
                      : 'border-slate-200 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  <div>Shortest Distance</div>
                  <div className="text-[10px] text-slate-500">Minimizes distance km</div>
                </button>
              </div>
            </div>

            {/* 5. Advanced Settings Accordion */}
            <div className="rounded-md border border-slate-200">
              <button
                type="button"
                onClick={() => setAdvancedOpen(!advancedOpen)}
                className="flex w-full items-center justify-between px-3 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                <span className="flex items-center gap-1.5">
                  <Sliders className="h-3.5 w-3.5 text-blue-600" />
                  Advanced Settings
                </span>
                <ChevronDown
                  className={`h-4 w-4 transition-transform duration-200 ${
                    advancedOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>

              {advancedOpen && (
                <div className="border-t border-slate-200 bg-slate-50/50 p-3 space-y-3">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-600">
                        Slot Step (min)
                      </label>
                      <input
                        type="number"
                        min={5}
                        max={60}
                        step={5}
                        value={slotIncrementMinutes}
                        onChange={(e) => setSlotIncrementMinutes(Number(e.target.value))}
                        className="mt-1 w-full rounded border border-slate-200 bg-white px-2 py-1 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-600">
                        Travel Buffer (min)
                      </label>
                      <input
                        ref={travelBufferInputRef}
                        type="number"
                        min={0}
                        max={120}
                        step={5}
                        value={travelBufferMinutes}
                        onChange={(e) => setTravelBufferMinutes(Number(e.target.value))}
                        className="mt-1 w-full rounded border border-slate-200 bg-white px-2 py-1 font-mono text-xs focus:ring-1 focus:ring-blue-600"
                      />
                    </div>
                  </div>

                  <div className="rounded border border-slate-200 bg-white p-2 space-y-2">
                    <label className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={lunchBreakEnabled}
                        onChange={(e) => setLunchBreakEnabled(e.target.checked)}
                        className="rounded text-blue-600"
                      />
                      <span>Mandatory Lunch Break</span>
                    </label>
                    {lunchBreakEnabled && (
                      <div className="grid grid-cols-2 gap-2 pt-1">
                        <div>
                          <label className="block text-[10px] text-slate-500">Lunch Start</label>
                          <input
                            type="time"
                            value={lunchStartTime}
                            onChange={(e) => setLunchStartTime(e.target.value)}
                            className="mt-0.5 w-full rounded border border-slate-200 px-1.5 py-0.5 font-mono text-xs"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-slate-500">Duration (min)</label>
                          <input
                            type="number"
                            min={15}
                            max={120}
                            step={15}
                            value={lunchDurationMinutes}
                            onChange={(e) => setLunchDurationMinutes(Number(e.target.value))}
                            className="mt-0.5 w-full rounded border border-slate-200 px-1.5 py-0.5 font-mono text-xs"
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-slate-600">Travel Mode</label>
                    <select
                      value={travelMode}
                      onChange={(e) => setTravelMode(e.target.value as TravelMode)}
                      className="mt-1 w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs"
                    >
                      <option value="DRIVE">Car / Van (DRIVE)</option>
                      <option value="TWO_WHEELER">Motorcycle (TWO_WHEELER)</option>
                      <option value="WALK">Walking (WALK)</option>
                    </select>
                  </div>

                  <label className="flex items-center gap-2 text-[11px] font-medium text-slate-700 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={useRoadTravelTimes}
                      onChange={(e) => setUseRoadTravelTimes(e.target.checked)}
                      className="rounded text-blue-600"
                    />
                    <span>Enforce O–D road travel times between stops</span>
                  </label>
                </div>
              )}
            </div>

            {/* 4. Distributor Selection List */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-800">
                  Select Distributors ({selectedIds.length}/{distributors.length})
                </label>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedIds(distributors.map((d) => d.id))}
                    className="text-[11px] font-medium text-blue-600 hover:text-blue-700"
                  >
                    Select All
                  </button>
                  <span className="text-slate-300">·</span>
                  <button
                    type="button"
                    onClick={() => setSelectedIds([])}
                    className="text-[11px] font-medium text-slate-500 hover:text-slate-700"
                  >
                    Deselect All
                  </button>
                </div>
              </div>

              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter distributors..."
                  value={distributorSearch}
                  onChange={(e) => setDistributorSearch(e.target.value)}
                  className="w-full rounded-md border border-slate-200 pl-8 pr-3 py-1.5 text-xs focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Checklist */}
              <div className="max-h-56 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200 bg-slate-50/40">
                {filteredDistributors.length === 0 ? (
                  <div className="p-3 text-center text-xs text-slate-500">
                    No distributors matching filter.
                  </div>
                ) : (
                  filteredDistributors.map((d) => {
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
                          <span className="truncate max-w-[170px]">{d.name}</span>
                        </span>
                        <span className="font-mono text-[10px] tabular-nums text-slate-500">
                          {d.opening_time}–{d.closing_time} · {d.visit_duration_minutes}m
                        </span>
                      </label>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          {/* 6. Sticky Bottom Action Area */}
          <div className="border-t border-slate-200 bg-slate-50 p-4 shrink-0 rounded-b-lg">
            <button
              type="button"
              onClick={() => void handleRunCsp()}
              disabled={running || selectedIds.length === 0}
              className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {running ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  <span>Solving Constraints...</span>
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  <span>Generate Daily Schedule</span>
                </>
              )}
            </button>
            {scheduleError && (
              <p className="mt-2 text-[11px] text-red-600">{scheduleError}</p>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Schedule Dashboard Workspace */}
        <div className="space-y-5 lg:col-span-8">
          {/* 7. Four Compact KPI Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-medium text-slate-500">Scheduled Visits</p>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-slate-900">
                {kpiStats.scheduledCount}
              </p>
              <p className="mt-0.5 text-[10px] text-slate-400">Within working hours</p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-medium text-slate-500">Unscheduled</p>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-amber-700">
                {kpiStats.unscheduledCount}
              </p>
              <p className="mt-0.5 text-[10px] text-slate-400">Hard constraint limits</p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-medium text-slate-500">High Delay Risk</p>
              <p
                className={`mt-1 font-mono text-2xl font-bold tabular-nums ${
                  kpiStats.highRiskCount > 0 ? 'text-red-600' : 'text-slate-900'
                }`}
              >
                {kpiStats.highRiskCount}
              </p>
              <p className="mt-0.5 text-[10px] text-slate-400">Bayesian advisory</p>
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm">
              <p className="text-[11px] font-medium text-slate-500">Working Utilization</p>
              <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-blue-700">
                {kpiStats.utilizationText}
              </p>
              <p className="mt-0.5 text-[10px] text-slate-400">Scheduled / Available span</p>
            </div>
          </div>

          {/* 8. Bayesian Network Delay Advisory Banner */}
          {result?.bayesianAdvisory && result.bayesianAdvisory.hasHighRisk && (
            <div className="rounded-lg border border-amber-300 bg-amber-50/80 p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-amber-700 shrink-0" />
                  <span className="text-xs font-bold text-amber-900">
                    {result.bayesianAdvisory.highRiskCount} High-Risk Visits Identified
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleFocusTravelBuffer}
                  className="inline-flex items-center gap-1.5 rounded bg-amber-800 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-900"
                >
                  <Sparkles className="h-3 w-3" />
                  Adjust Travel Buffer
                </button>
              </div>
              <p className="mt-1.5 text-xs text-amber-800 leading-relaxed">
                {result.bayesianAdvisory.recommendationText}
              </p>
              <p className="mt-1 text-[11px] text-amber-700/90 italic">
                Note: Bayesian Network delay risk is a probabilistic estimate derived from distance, visit duration, time of day, and account priority, not a guaranteed delay.
              </p>
            </div>
          )}

          {/* 9. Multi-View Workspace Header */}
          <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3 bg-slate-50/60">
              <div className="flex items-center gap-1 rounded-md border border-slate-200 bg-white p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setActiveView('timeline')}
                  className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 font-semibold transition-colors ${
                    activeView === 'timeline'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Clock className="h-3.5 w-3.5" />
                  Timeline View
                </button>
                <button
                  type="button"
                  onClick={() => setActiveView('table')}
                  className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 font-semibold transition-colors ${
                    activeView === 'table'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <TableIcon className="h-3.5 w-3.5" />
                  Table View
                </button>
                <button
                  type="button"
                  onClick={() => setActiveView('map')}
                  className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 font-semibold transition-colors ${
                    activeView === 'map'
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <MapPin className="h-3.5 w-3.5" />
                  Map View
                </button>
              </div>

              <div className="text-xs text-slate-500 font-mono">
                {result ? `${result.scheduled.length} Scheduled · ${result.unscheduled.length} Unscheduled` : 'Awaiting schedule'}
              </div>
            </div>

            {/* View Render Area */}
            <div className="p-5">
              {!result ? (
                <div className="flex h-64 flex-col items-center justify-center text-center">
                  <CalendarClock className="h-10 w-10 text-slate-300" />
                  <p className="mt-3 text-sm font-semibold text-slate-800">No Schedule Generated Yet</p>
                  <p className="mt-1 text-xs text-slate-500 max-w-sm">
                    Configure your working constraints and click &quot;Generate Daily Schedule&quot; to compute feasible visit slots.
                  </p>
                </div>
              ) : (
                <>
                  {/* TIMELINE VIEW */}
                  {activeView === 'timeline' && (
                    <div className="space-y-4">
                      {/* Visual Day Bar */}
                      <div className="space-y-1.5">
                        <div className="flex justify-between font-mono text-[11px] text-slate-500">
                          <span>{formatTime12Hour(workStartTime)} (Start)</span>
                          {lunchBreakEnabled && (
                            <span className="text-amber-800 font-medium">Lunch {formatTime12Hour(lunchStartTime)}</span>
                          )}
                          <span>{formatTime12Hour(workEndTime)} (End)</span>
                        </div>
                        <div className="relative h-12 w-full overflow-hidden rounded-md border border-slate-200 bg-slate-100">
                          {lunchBreakEnabled &&
                            lunchStartMin >= dayStartMin &&
                            lunchStartMin < dayEndMin && (
                              <div
                                style={{
                                  left: `${((lunchStartMin - dayStartMin) / totalDaySpan) * 100}%`,
                                  width: `${(lunchDurationMinutes / totalDaySpan) * 100}%`,
                                }}
                                className="absolute top-0 bottom-0 flex items-center justify-center border-x border-amber-300 bg-amber-200/90 text-[10px] font-bold text-amber-900"
                              >
                                <Coffee className="h-3 w-3 mr-1" />
                                Lunch
                              </div>
                            )}

                          {result.scheduled.map((entry) => {
                            const leftPct = ((entry.startMinutes - dayStartMin) / totalDaySpan) * 100;
                            const widthPct = (entry.durationMinutes / totalDaySpan) * 100;
                            const isHigh = entry.delayRisk === 'High';
                            return (
                              <div
                                key={entry.distributorId}
                                title={`${entry.distributorName}: ${formatTime12Hour(entry.startTime)}–${formatTime12Hour(entry.endTime)}`}
                                style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 2)}%` }}
                                className={`absolute top-1 bottom-1 flex items-center justify-center overflow-hidden rounded px-1 text-[10px] font-bold text-white shadow-xs ${
                                  isHigh ? 'bg-amber-600 border border-amber-700' : 'bg-blue-600 border border-blue-700'
                                }`}
                              >
                                <span className="truncate">{formatTime12Hour(entry.startTime)}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Chronological Sequence List */}
                      <div className="divide-y divide-slate-100 border-t border-slate-100 pt-3">
                        {result.scheduled.map((entry, idx) => {
                          const isHighRisk = entry.delayRisk === 'High';
                          return (
                            <div key={entry.distributorId} className="py-3 first:pt-0 last:pb-0">
                              {/* Travel interval indicator before visit if applicable */}
                              {idx > 0 && (
                                <div className="mb-2 flex items-center gap-2 pl-4 text-[11px] text-slate-500 font-mono">
                                  <div className="h-3 w-0.5 bg-slate-300" />
                                  <span>
                                    {entry.travelMinutesFromPrevious !== undefined
                                      ? `Est. road travel: ${entry.travelMinutesFromPrevious}m`
                                      : `Travel buffer: ${entry.bufferMinutes}m`}
                                  </span>
                                </div>
                              )}

                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2.5">
                                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-800">
                                    {idx + 1}
                                  </span>
                                  <div>
                                    <div className="flex items-center gap-2">
                                      <span className="text-sm font-semibold text-slate-900">
                                        {entry.distributorName}
                                      </span>
                                      <span className="font-mono text-xs font-bold text-blue-700">
                                        {formatTime12Hour(entry.startTime)} – {formatTime12Hour(entry.endTime)}
                                      </span>
                                    </div>
                                    <p className="text-xs text-slate-500">
                                      Visit duration: {entry.durationMinutes} min · Operating window: {formatTime12Hour(entry.openingTime)}–{formatTime12Hour(entry.closingTime)}
                                    </p>
                                  </div>
                                </div>

                                <div className="flex items-center gap-3">
                                  <span className="font-mono text-xs text-slate-600">
                                    Priority P{entry.priority}
                                  </span>
                                  <span
                                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                                      isHighRisk
                                        ? 'bg-red-100 text-red-800'
                                        : entry.delayRisk === 'Medium'
                                          ? 'bg-amber-100 text-amber-800'
                                          : 'bg-emerald-100 text-emerald-800'
                                    }`}
                                  >
                                    <span
                                      className={`h-1.5 w-1.5 rounded-full ${
                                        isHighRisk
                                          ? 'bg-red-600'
                                          : entry.delayRisk === 'Medium'
                                            ? 'bg-amber-600'
                                            : 'bg-emerald-600'
                                      }`}
                                    />
                                    {entry.delayRisk || 'Low'} Risk
                                  </span>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* TABLE VIEW */}
                  {activeView === 'table' && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs">
                        <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                          <tr>
                            <th className="px-3 py-2.5">Time Slot</th>
                            <th className="px-3 py-2.5">Distributor</th>
                            <th className="px-3 py-2.5 text-right">Visit Duration</th>
                            <th className="px-3 py-2.5 text-right">Travel Duration</th>
                            <th className="px-3 py-2.5 text-right">Buffer</th>
                            <th className="px-3 py-2.5 text-right">Operating Window</th>
                            <th className="px-3 py-2.5 text-right">Priority</th>
                            <th className="px-3 py-2.5 text-center">Delay Risk (BN)</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {result.scheduled.map((s) => (
                            <tr key={s.distributorId} className="hover:bg-slate-50/70">
                              <td className="px-3 py-2.5 font-mono font-semibold text-blue-700">
                                {formatTime12Hour(s.startTime)} – {formatTime12Hour(s.endTime)}
                              </td>
                              <td className="px-3 py-2.5 font-medium text-slate-900">
                                {s.distributorName}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-700">
                                {s.durationMinutes} min
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-600">
                                {s.travelMinutesFromPrevious !== undefined
                                  ? `${s.travelMinutesFromPrevious} min`
                                  : 'N/A'}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-600">
                                {s.bufferMinutes} min
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-600">
                                {formatTime12Hour(s.openingTime)}–{formatTime12Hour(s.closingTime)}
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-slate-700">
                                P{s.priority}
                              </td>
                              <td className="px-3 py-2.5 text-center">
                                <span
                                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                    s.delayRisk === 'High'
                                      ? 'bg-red-100 text-red-800'
                                      : s.delayRisk === 'Medium'
                                        ? 'bg-amber-100 text-amber-800'
                                        : 'bg-emerald-100 text-emerald-800'
                                  }`}
                                >
                                  {s.delayRisk || 'Low'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {/* MAP VIEW */}
                  {activeView === 'map' && (
                    <div className="space-y-3">
                      <div className="overflow-hidden rounded-md border border-slate-200">
                        <LeafletRouteMap
                          points={mapPoints}
                          routeOrderIds={mapOrderIds}
                          height={400}
                          title={`Scheduled Visit Locations (${result.scheduled.length} Stops)`}
                        />
                      </div>
                      <p className="text-[11px] text-slate-500">
                        Numbered markers represent scheduled visit stops based on actual Karachi distributor coordinates and assigned start times.
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* 10. Unscheduled Visits Section */}
          {result && result.unscheduled.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-white p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-600" />
                  <h3 className="text-sm font-bold text-slate-900">
                    Unscheduled Visits ({result.unscheduled.length})
                  </h3>
                </div>
                <span className="text-[11px] text-slate-500 font-mono">
                  Hard Constraint Evaluation
                </span>
              </div>

              <div className="divide-y divide-slate-100">
                {result.unscheduled.map((u) => (
                  <div key={u.distributorId} className="py-2.5 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-slate-900">{u.distributorName}</span>
                      <span className="font-mono text-[11px] text-slate-500">
                        Window: {formatTime12Hour(u.openingTime)}–{formatTime12Hour(u.closingTime)} · {u.visitDurationMinutes}m visit · Priority P{u.priority}
                      </span>
                    </div>
                    <p className="mt-1 text-slate-700">
                      <strong className="text-amber-800 font-medium">Solver Reason: </strong>
                      {u.reason}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Smart Fix Modal */}
      {smartFixModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-xs">
          <div className="relative w-full max-w-4xl rounded-xl bg-white shadow-2xl border border-slate-200 flex flex-col max-h-[90vh] overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/70">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100 text-purple-700">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Smart Fix &amp; Intelligent Schedule Repair</h3>
                  <p className="text-xs text-slate-500">
                    Automated conflict resolution, road travel gap diagnostics &amp; Bayesian risk optimization
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSmartFixModalOpen(false)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Mode Switcher */}
            <div className="flex items-center gap-2 border-b border-slate-200 px-6 py-3 bg-white">
              <span className="text-xs font-semibold text-slate-700 mr-2">Repair Mode:</span>
              <button
                type="button"
                onClick={() => handleOpenSmartFix('QUICK_FIX')}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  smartFixMode === 'QUICK_FIX'
                    ? 'bg-blue-600 text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                Quick Fix (Preserve Order)
              </button>
              <button
                type="button"
                onClick={() => handleOpenSmartFix('SMART_OPTIMIZE')}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  smartFixMode === 'SMART_OPTIMIZE'
                    ? 'bg-purple-600 text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                Smart Optimize (Full Search)
              </button>
              <button
                type="button"
                onClick={() => handleOpenSmartFix('SUGGESTIONS_ONLY')}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors ${
                  smartFixMode === 'SUGGESTIONS_ONLY'
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                Suggestions Only (Advisory)
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {smartFixLoading ? (
                <div className="flex h-64 flex-col items-center justify-center text-center">
                  <RefreshCw className="h-8 w-8 animate-spin text-purple-600" />
                  <p className="mt-3 text-sm font-semibold text-slate-800">
                    Running Diagnostics &amp; Evaluating Candidate Repairs...
                  </p>
                  <p className="mt-1 text-xs text-slate-500 max-w-sm">
                    Checking directed road matrix, distributor operating windows, lunch bounds, and Bayesian delay risks.
                  </p>
                </div>
              ) : smartFixData ? (
                <>
                  {/* Diagnostics Summary Banner */}
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h4 className="text-xs font-bold text-slate-900">Diagnostics Analysis</h4>
                        <p className="text-xs text-slate-600 mt-0.5">
                          {smartFixData.diagnostics.issueCount === 0 ? (
                            <span className="text-emerald-700 font-semibold">
                              ✓ Schedule is valid. All travel transitions and operating windows are feasible.
                            </span>
                          ) : (
                            <span>
                              Found <strong className="text-red-700">{smartFixData.diagnostics.criticalCount} critical</strong>,{' '}
                              <strong className="text-amber-700">{smartFixData.diagnostics.highCount} high</strong>, and{' '}
                              <strong className="text-blue-700">{smartFixData.diagnostics.mediumCount} medium</strong> issues.
                            </span>
                          )}
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2.5 py-1 text-[11px] font-semibold text-blue-800">
                          Resolved: {smartFixData.comparison.resolvedIssuesCount}
                        </span>
                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-200 px-2.5 py-1 text-[11px] font-semibold text-slate-700">
                          Remaining: {smartFixData.comparison.remainingIssuesCount}
                        </span>
                      </div>
                    </div>

                    {/* Detected Issues List */}
                    {smartFixData.diagnostics.issues.length > 0 && (
                      <div className="mt-3 divide-y divide-slate-200 border-t border-slate-200 pt-2 max-h-36 overflow-y-auto">
                        {smartFixData.diagnostics.issues.map((iss, i) => (
                          <div key={i} className="py-1.5 flex items-start gap-2 text-xs">
                            <span
                              className={`shrink-0 rounded px-1.5 py-0.2 text-[10px] font-bold ${
                                iss.severity === 'CRITICAL'
                                  ? 'bg-red-100 text-red-800'
                                  : iss.severity === 'HIGH'
                                    ? 'bg-amber-100 text-amber-800'
                                    : 'bg-blue-100 text-blue-800'
                              }`}
                            >
                              {iss.type}
                            </span>
                            <span className="text-slate-700 leading-snug">{iss.message}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Mode Specific Body */}
                  {smartFixMode === 'SUGGESTIONS_ONLY' ? (
                    <div className="space-y-3">
                      <h4 className="text-sm font-bold text-slate-900">Recommended Optimization Actions</h4>
                      {smartFixData.suggestions.suggestions.length === 0 ? (
                        <p className="text-xs text-slate-500">No suggestions needed. Schedule is currently optimal.</p>
                      ) : (
                        <div className="grid gap-3 sm:grid-cols-2">
                          {smartFixData.suggestions.suggestions.map((sug, i) => (
                            <div key={i} className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs space-y-1.5">
                              <div className="flex items-center justify-between">
                                <span className="text-[10px] font-bold uppercase tracking-wider text-purple-700">
                                  {sug.category}
                                </span>
                                <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                                  Use {sug.modeRecommended}
                                </span>
                              </div>
                              <h5 className="text-xs font-bold text-slate-900">{sug.title}</h5>
                              <p className="text-xs text-slate-600 leading-relaxed">{sug.detail}</p>
                              <div className="pt-1 text-[11px] font-medium text-emerald-700">
                                <strong>Impact: </strong>
                                {sug.impact}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    /* Old vs. Proposed Schedule Comparison */
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <h4 className="text-sm font-bold text-slate-900">
                          Old vs. Proposed Schedule Comparison ({smartFixData.activeProposal.scheduled.length} Stops)
                        </h4>
                        <div className="text-xs font-mono text-slate-500">
                          Status: <strong className="text-purple-700">{smartFixData.activeProposal.solverStatus}</strong>
                        </div>
                      </div>

                      <div className="overflow-x-auto rounded-lg border border-slate-200">
                        <table className="w-full text-left text-xs">
                          <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                            <tr>
                              <th className="px-3 py-2">Distributor</th>
                              <th className="px-3 py-2 text-center">Status</th>
                              <th className="px-3 py-2 text-center">Original Time</th>
                              <th className="px-3 py-2 text-center">Proposed Time</th>
                              <th className="px-3 py-2 text-right">Road Travel</th>
                              <th className="px-3 py-2 text-right">Buffer</th>
                              <th className="px-3 py-2 text-center">Delay Risk</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100">
                            {smartFixData.comparison.items.map((row) => (
                              <tr key={row.distributorId} className="hover:bg-slate-50/70">
                                <td className="px-3 py-2 font-medium text-slate-900">
                                  <div>{row.distributorName}</div>
                                  <div className="text-[10px] text-slate-400">
                                    Window: {formatTime12Hour(row.openingTime)}–{formatTime12Hour(row.closingTime)} · P{row.priority}
                                  </div>
                                </td>
                                <td className="px-3 py-2 text-center">
                                  <span
                                    className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                      row.status === 'MOVED'
                                        ? 'bg-amber-100 text-amber-800'
                                        : row.status === 'UNCHANGED'
                                          ? 'bg-emerald-100 text-emerald-800'
                                          : row.status === 'ADDED'
                                            ? 'bg-blue-100 text-blue-800'
                                            : 'bg-red-100 text-red-800'
                                    }`}
                                  >
                                    {row.status}
                                  </span>
                                </td>
                                <td className="px-3 py-2 text-center font-mono text-slate-500">
                                  {row.originalStartTime ? `${formatTime12Hour(row.originalStartTime)}–${formatTime12Hour(row.originalEndTime)}` : '—'}
                                </td>
                                <td className="px-3 py-2 text-center font-mono font-bold text-blue-700">
                                  {row.proposedStartTime ? `${formatTime12Hour(row.proposedStartTime)}–${formatTime12Hour(row.proposedEndTime)}` : '—'}
                                </td>
                                <td className="px-3 py-2 text-right font-mono text-slate-600">
                                  {row.travelMinutes !== null && row.travelMinutes !== undefined ? `${row.travelMinutes}m` : '—'}
                                </td>
                                <td className="px-3 py-2 text-right font-mono text-slate-600">
                                  {row.bufferMinutes !== null && row.bufferMinutes !== undefined ? `${row.bufferMinutes}m` : '—'}
                                </td>
                                <td className="px-3 py-2 text-center">
                                  <span
                                    className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                                      row.delayRisk === 'High'
                                        ? 'bg-red-100 text-red-800'
                                        : row.delayRisk === 'Medium'
                                          ? 'bg-amber-100 text-amber-800'
                                          : 'bg-emerald-100 text-emerald-800'
                                    }`}
                                  >
                                    {row.delayRisk || 'Low'}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between border-t border-slate-200 px-6 py-4 bg-slate-50/70">
              <div className="flex items-center gap-2">
                {hasBackupSnapshot && (
                  <button
                    type="button"
                    onClick={handleRestoreSchedule}
                    disabled={smartFixRestoring}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${smartFixRestoring ? 'animate-spin' : ''}`} />
                    <span>{smartFixRestoring ? 'Restoring...' : 'Restore Original Schedule'}</span>
                  </button>
                )}
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setSmartFixModalOpen(false)}
                  className="rounded-md border border-slate-300 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Cancel / Discard
                </button>

                {smartFixMode !== 'SUGGESTIONS_ONLY' && (
                  <button
                    type="button"
                    onClick={handleApplySmartFix}
                    disabled={
                      smartFixApplying ||
                      !smartFixData ||
                      !smartFixData.activeProposal.feasible ||
                      smartFixData.activeProposal.scheduled.length === 0
                    }
                    className="inline-flex items-center gap-1.5 rounded-md bg-purple-600 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-purple-700 disabled:opacity-50"
                  >
                    <Check className="h-4 w-4" />
                    <span>{smartFixApplying ? 'Applying...' : 'Apply Changes'}</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 11. Course Project View Drawer (Slide-Over Drawer ~420px) */}
      {academicDrawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/40 backdrop-blur-xs">
          <div className="relative w-full max-w-md bg-white p-6 shadow-2xl flex flex-col h-full overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-200 pb-4">
              <div>
                <h3 className="text-base font-bold text-slate-900">Course Project View</h3>
                <p className="text-xs text-slate-500">Constraint Satisfaction Problem (CSP) Formulation</p>
              </div>
              <button
                type="button"
                onClick={() => setAcademicDrawerOpen(false)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs text-slate-700">
              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-1.5">
                <span className="font-bold text-slate-900">1. CSP Variables:</span>
                <p>
                  Each selected distributor <code className="font-mono">X_i</code> is a variable representing a single visit to be assigned an integer start-time slot within the officer&apos;s daily shift.
                </p>
              </div>

              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-1.5">
                <span className="font-bold text-slate-900">2. Domain:</span>
                <p>
                  Filtered candidate start times in increments of {slotIncrementMinutes} minutes:
                  <br />
                  <code className="font-mono text-[11px]">
                    D(X_i) ⊆ [max(workStart + officeTravel, openingTime), min(workEnd - dur, closingTime - dur)]
                  </code>
                </p>
              </div>

              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-1.5">
                <span className="font-bold text-slate-900">3. Hard Constraints:</span>
                <ul className="list-disc pl-4 space-y-1 text-slate-600">
                  <li>Officer working hours ({workStartTime}–{workEndTime})</li>
                  <li>Distributor operating windows (<code className="font-mono">open_i ... close_i</code>)</li>
                  <li>Mandatory non-overlapping lunch interval ({lunchBreakEnabled ? `${lunchStartTime} (${lunchDurationMinutes}m)` : 'Disabled'})</li>
                  <li>Non-overlapping visits: <code className="font-mono">start_j ≥ end_i + travel(i, j)</code></li>
                  <li>Maximum daily visits cap: {maxVisitsPerDay} visits</li>
                </ul>
              </div>

              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-1.5">
                <span className="font-bold text-slate-900">4. Optimization Objective &amp; Soft Constraints:</span>
                <p>
                  Maximize total priority sum <code className="font-mono">∑ priority_i</code> while honoring {optimizationObjective === 'FASTEST_TIME' ? 'fastest road travel times' : 'shortest road distances'}.
                </p>
              </div>

              <div className="rounded-md border border-slate-200 bg-slate-50 p-3 space-y-2">
                <span className="font-bold text-slate-900">5. Solver Telemetry (Ground Truth):</span>
                <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                  <div className="rounded bg-white p-2 border border-slate-200">
                    <span className="text-slate-500">Backtracks:</span>{' '}
                    <strong className="text-slate-900">{result?.backtracks ?? 'N/A'}</strong>
                  </div>
                  <div className="rounded bg-white p-2 border border-slate-200">
                    <span className="text-slate-500">Execution Time:</span>{' '}
                    <strong className="text-slate-900">
                      {result?.executionTimeMs !== undefined ? `${result.executionTimeMs} ms` : 'N/A'}
                    </strong>
                  </div>
                  <div className="rounded bg-white p-2 border border-slate-200">
                    <span className="text-slate-500">Solver Status:</span>{' '}
                    <strong className="text-emerald-700">
                      {result ? (result.allDistributorsScheduled ? 'Optimal (All Placed)' : 'Feasible Subset') : 'Idle'}
                    </strong>
                  </div>
                  <div className="rounded bg-white p-2 border border-slate-200">
                    <span className="text-slate-500">Constraint Violations:</span>{' '}
                    <strong className="text-slate-900">0 (Strictly Enforced)</strong>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-auto pt-4 border-t border-slate-200">
              <button
                type="button"
                onClick={() => setAcademicDrawerOpen(false)}
                className="w-full rounded-md border border-slate-200 bg-slate-100 px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-200"
              >
                Close Course Project View
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
