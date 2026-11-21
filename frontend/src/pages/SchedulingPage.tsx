import React, { useState, useEffect } from 'react';
import { AlertTriangle, CalendarClock, Play, ShieldAlert, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import type { CspRunResult, Distributor, OfficeLocation } from '../types';

interface SchedulingPageProps {
  onNotify: (kind: 'success' | 'error', text: string) => void;
}

function toMins(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

export const SchedulingPage: React.FC<SchedulingPageProps> = ({ onNotify }) => {
  const navigate = useNavigate();
  const [offices, setOffices] = useState<OfficeLocation[]>([]);
  const [officeId, setOfficeId] = useState<string>('');
  const [distributors, setDistributors] = useState<Distributor[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const [scheduleDate, setScheduleDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [workStartTime, setWorkStartTime] = useState('09:00');
  const [workEndTime, setWorkEndTime] = useState('17:00');
  const [slotIncrementMinutes, setSlotIncrementMinutes] = useState(15);
  const [travelBufferMinutes, setTravelBufferMinutes] = useState(15);
  const [lunchBreakEnabled, setLunchBreakEnabled] = useState(true);
  const [lunchStartTime, setLunchStartTime] = useState('12:30');
  const [lunchDurationMinutes, setLunchDurationMinutes] = useState(60);
  const [maxVisitsPerDay, setMaxVisitsPerDay] = useState(8);

  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CspRunResult | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [offRes, distRes, latestSchedRes] = await Promise.all([
          api.getOffices(),
          api.getDistributors({ active: 'true', pageSize: 100 }),
          api.getLatestSchedule(),
        ]);
        setOffices(offRes.data.offices);
        const defOffice = offRes.data.defaultOffice || offRes.data.offices[0];
        setOfficeId(latestSchedRes.data?.officeId || defOffice?.id || '');
        setDistributors(distRes.data.items);
        setSelectedIds(distRes.data.items.map((d) => d.id));

        if (latestSchedRes.data && latestSchedRes.data.entries.length > 0) {
          const entries = latestSchedRes.data.entries;
          const schedDate = String(latestSchedRes.data.scheduleDate || entries[0].schedule_date).slice(0, 10);
          setScheduleDate(schedDate);
          const scheduledIds = new Set(entries.map((e) => e.distributor_id));
          const unscheduledList = distRes.data.items
            .filter((d) => !scheduledIds.has(d.id))
            .map((d) => ({
              distributorId: d.id,
              distributorName: d.name,
              priority: d.priority,
              visitDurationMinutes: d.visit_duration_minutes,
              openingTime: d.opening_time,
              closingTime: d.closing_time,
              reason: 'Not included in the latest saved schedule run.',
            }));

          setResult({
            routePlanId: latestSchedRes.data.routePlanId,
            officeId: latestSchedRes.data.officeId,
            officeName: latestSchedRes.data.officeName,
            scheduleDate: schedDate,
            allDistributorsScheduled: unscheduledList.length === 0,
            usesFixedTravelBuffer: true,
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
        }
      } catch (err) {
        onNotify('error', err instanceof Error ? err.message : 'Failed to load distributors');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const handleRunCsp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedIds.length === 0) {
      onNotify('error', 'Select at least 1 distributor to schedule.');
      return;
    }
    if (workEndTime <= workStartTime) {
      onNotify('error', 'Work end time must be after work start time.');
      return;
    }

    setRunning(true);
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
      });
      setResult(res.data);
      onNotify(
        'success',
        `Scheduled ${res.data.scheduled.length} visit(s); ${res.data.unscheduled.length} unscheduled.`
      );
    } catch (err) {
      onNotify('error', err instanceof Error ? err.message : 'CSP scheduler failed');
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <div className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white" />;
  }

  const dayStartMin = toMins(workStartTime);
  const dayEndMin = Math.max(dayStartMin + 60, toMins(workEndTime));
  const totalDaySpan = dayEndMin - dayStartMin;
  const lunchStartMin = toMins(lunchStartTime);

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-slate-200 bg-white px-5 py-3.5 text-xs text-slate-600">
        <span className="font-semibold text-slate-900">Week 5 · Constraint Satisfaction Problem (CSP):</span>{' '}
        Models each distributor visit as a variable with start-time domains filtered by officer working hours, distributor opening/closing hours, mandatory lunch interval, and non-overlapping fixed travel buffers. Note: this is a simplified fixed-buffer CSP schedule; it does not verify real-time road traffic feasibility.
      </div>

      <div className="grid gap-6 lg:grid-cols-12">
        <form
          onSubmit={handleRunCsp}
          className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 lg:col-span-4"
        >
          <h3 className="text-base font-semibold text-slate-900">Schedule Constraints</h3>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700">Schedule Date</label>
              <input
                type="date"
                required
                value={scheduleDate}
                onChange={(e) => setScheduleDate(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-xs"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700">Base Office</label>
              <select
                value={officeId}
                onChange={(e) => setOfficeId(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs"
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

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700">Work Start</label>
              <input
                type="time"
                required
                value={workStartTime}
                onChange={(e) => setWorkStartTime(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700">Work End</label>
              <input
                type="time"
                required
                value={workEndTime}
                onChange={(e) => setWorkEndTime(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700">Slot Step (min)</label>
              <select
                value={slotIncrementMinutes}
                onChange={(e) => setSlotIncrementMinutes(Number(e.target.value))}
                className="mt-1 w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 font-mono text-sm"
              >
                <option value={5}>5 min</option>
                <option value={10}>10 min</option>
                <option value={15}>15 min</option>
                <option value={30}>30 min</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700">Travel Buffer (min)</label>
              <input
                type="number"
                min={0}
                max={120}
                value={travelBufferMinutes}
                onChange={(e) => setTravelBufferMinutes(Number(e.target.value))}
                className="mt-1 w-full rounded-md border border-slate-200 px-2.5 py-1.5 font-mono text-sm"
              />
            </div>
          </div>

          <div className="space-y-2 border-t border-slate-100 pt-3">
            <label className="inline-flex items-center gap-2 text-xs font-medium text-slate-700">
              <input
                type="checkbox"
                checked={lunchBreakEnabled}
                onChange={(e) => setLunchBreakEnabled(e.target.checked)}
              />
              Enforce mandatory lunch break interval
            </label>
            {lunchBreakEnabled && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] text-slate-500">Lunch Start</label>
                  <input
                    type="time"
                    value={lunchStartTime}
                    onChange={(e) => setLunchStartTime(e.target.value)}
                    className="mt-0.5 w-full rounded-md border border-slate-200 px-2.5 py-1 font-mono text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] text-slate-500">Duration (min)</label>
                  <input
                    type="number"
                    min={15}
                    max={120}
                    value={lunchDurationMinutes}
                    onChange={(e) => setLunchDurationMinutes(Number(e.target.value))}
                    className="mt-0.5 w-full rounded-md border border-slate-200 px-2.5 py-1 font-mono text-xs"
                  />
                </div>
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700">Max Visits Per Day</label>
            <input
              type="number"
              min={1}
              max={30}
              value={maxVisitsPerDay}
              onChange={(e) => setMaxVisitsPerDay(Number(e.target.value))}
              className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 font-mono text-sm"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-slate-700">
                Distributors ({selectedIds.length}/{distributors.length})
              </label>
              <button
                type="button"
                onClick={() =>
                  setSelectedIds(
                    selectedIds.length === distributors.length ? [] : distributors.map((d) => d.id)
                  )
                }
                className="text-xs font-medium text-blue-600"
              >
                {selectedIds.length === distributors.length ? 'Clear' : 'Select All'}
              </button>
            </div>
            <div className="mt-2 max-h-48 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200">
              {distributors.map((d) => (
                <label
                  key={d.id}
                  className="flex cursor-pointer items-center justify-between px-3 py-1.5 text-xs hover:bg-slate-50"
                >
                  <span className="flex items-center gap-2 font-medium text-slate-800">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(d.id)}
                      onChange={() =>
                        setSelectedIds((prev) =>
                          prev.includes(d.id) ? prev.filter((x) => x !== d.id) : [...prev, d.id]
                        )
                      }
                    />
                    {d.name}
                  </span>
                  <span className="font-mono text-[11px] tabular-nums text-slate-500">
                    {d.opening_time}–{d.closing_time} · {d.visit_duration_minutes}m
                  </span>
                </label>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={running || selectedIds.length === 0}
            className="inline-flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {running ? 'Solving CSP...' : 'Solve & Save Schedule'}
          </button>
        </form>

        <div className="space-y-6 lg:col-span-8">
          {!result ? (
            <div className="flex h-80 flex-col items-center justify-center rounded-lg border border-slate-200 bg-white p-8 text-center">
              <CalendarClock className="h-8 w-8 text-slate-400" />
              <p className="mt-3 text-base font-semibold text-slate-900">
                Configure Constraints and Run the CSP Solver
              </p>
              <p className="mt-1 max-w-md text-sm text-slate-600">
                The solver assigns non-overlapping start times within working hours and each distributor&apos;s opening window, then persists feasible visits to Neon PostgreSQL.
              </p>
            </div>
          ) : (
            <>
              <div className="rounded-lg border border-slate-200 bg-white p-5 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div>
                    <h3 className="text-base font-semibold text-slate-900">
                      Daily Schedule Timeline ({result.scheduleDate})
                    </h3>
                    <p className="text-xs text-slate-500">
                      {result.officeName ? `From ${result.officeName} · ` : ''}
                      {result.scheduled.length} scheduled · {result.unscheduled.length} unscheduled ·{' '}
                      {result.backtracks} backtrack(s) · {result.executionTimeMs} ms
                    </p>
                  </div>
                  <span className="text-xs font-medium text-amber-700">
                    Uses fixed {travelBufferMinutes}m buffer (not road traffic)
                  </span>
                </div>

                {/* Bayesian Delay Risk Advisory Panel */}
                {result.bayesianAdvisory && result.bayesianAdvisory.hasHighRisk && (
                  <div className="rounded-md border border-amber-300 bg-amber-50 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="h-4 w-4 text-amber-700" />
                        <span className="text-xs font-semibold text-amber-900">
                          Bayesian Network Delay Advisory: {result.bayesianAdvisory.highRiskCount} High-Risk Visit(s)
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => navigate('/delay-prediction')}
                        className="text-[11px] font-medium text-amber-800 hover:text-amber-900 underline"
                      >
                        Open Delay Prediction Page →
                      </button>
                    </div>
                    <p className="text-xs text-amber-800 leading-relaxed">
                      {result.bayesianAdvisory.recommendationText}
                    </p>
                    <div className="pt-1 flex items-center gap-3">
                      <button
                        type="button"
                        onClick={() => {
                          const newBuffer = result.bayesianAdvisory?.recommendedTravelBuffer ?? (travelBufferMinutes + 10);
                          setTravelBufferMinutes(newBuffer);
                          onNotify('success', `Updated travel buffer to ${newBuffer} min. Click "Solve & Save Schedule" to re-validate.`);
                        }}
                        className="inline-flex items-center gap-1.5 rounded bg-amber-800 px-3 py-1 text-xs font-medium text-white hover:bg-amber-900"
                      >
                        <Sparkles className="h-3 w-3" />
                        Set Buffer to {result.bayesianAdvisory.recommendedTravelBuffer} min
                      </button>
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <div className="flex justify-between font-mono text-[11px] tabular-nums text-slate-500">
                    <span>{workStartTime}</span>
                    <span>{lunchBreakEnabled ? `Lunch ${lunchStartTime}` : ''}</span>
                    <span>{workEndTime}</span>
                  </div>
                  <div className="relative h-14 w-full overflow-hidden rounded-md border border-slate-200 bg-slate-50">
                    {lunchBreakEnabled &&
                      lunchStartMin >= dayStartMin &&
                      lunchStartMin < dayEndMin && (
                        <div
                          style={{
                            left: `${((lunchStartMin - dayStartMin) / totalDaySpan) * 100}%`,
                            width: `${(lunchDurationMinutes / totalDaySpan) * 100}%`,
                          }}
                          className="absolute top-0 bottom-0 flex items-center justify-center border-x border-amber-300 bg-amber-100/80 text-[10px] font-medium text-amber-900"
                        >
                          Lunch
                        </div>
                      )}

                    {result.scheduled.map((entry) => {
                      const leftPct = ((entry.startMinutes - dayStartMin) / totalDaySpan) * 100;
                      const widthPct = (entry.durationMinutes / totalDaySpan) * 100;
                      return (
                        <div
                          key={entry.distributorId}
                          title={`${entry.distributorName}: ${entry.startTime}–${entry.endTime}`}
                          style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 2)}%` }}
                          className="absolute top-1.5 bottom-1.5 flex items-center justify-center overflow-hidden rounded border border-blue-700 bg-blue-600 px-1 text-[10px] font-medium text-white"
                        >
                          <span className="truncate">{entry.startTime}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="overflow-x-auto pt-2">
                  <table className="w-full text-left text-sm">
                    <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-600">
                      <tr>
                        <th className="px-4 py-2.5">Slot Window</th>
                        <th className="px-4 py-2.5">Distributor</th>
                        <th className="px-4 py-2.5 text-right">Duration</th>
                        <th className="px-4 py-2.5 text-right">Buffer</th>
                        <th className="px-4 py-2.5 text-right">Opening Window</th>
                        <th className="px-4 py-2.5 text-right">Priority</th>
                        <th className="px-4 py-2.5 text-center">Delay Risk (BN)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {result.scheduled.map((s) => (
                        <tr key={s.distributorId}>
                          <td className="px-4 py-2.5 font-mono text-xs font-semibold tabular-nums text-blue-700">
                            {s.startTime} – {s.endTime}
                          </td>
                          <td className="px-4 py-2.5 font-medium text-slate-900">
                            {s.distributorName}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-700">
                            {s.durationMinutes} min
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-500">
                            +{s.bufferMinutes} min
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-600">
                            {s.openingTime}–{s.closingTime}
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-slate-700">
                            {s.priority}/5
                          </td>
                          <td className="px-4 py-2.5 text-center">
                            <span
                              title={s.delayAdvisory || `Risk: ${s.delayRisk ?? 'Low'}`}
                              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                                s.delayRisk === 'High'
                                  ? 'bg-red-100 text-red-800'
                                  : s.delayRisk === 'Medium'
                                    ? 'bg-amber-100 text-amber-800'
                                    : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              <span
                                className={`h-1.5 w-1.5 rounded-full ${
                                  s.delayRisk === 'High'
                                    ? 'bg-red-600'
                                    : s.delayRisk === 'Medium'
                                      ? 'bg-amber-600'
                                      : 'bg-emerald-600'
                                }`}
                              />
                              {s.delayRisk ?? 'Low'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {result.unscheduled.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-white p-5">
                  <h3 className="text-sm font-semibold text-slate-900">
                    Unscheduled Distributors ({result.unscheduled.length}) — Hard Constraint Reasons
                  </h3>
                  <div className="mt-3 divide-y divide-slate-100">
                    {result.unscheduled.map((u) => (
                      <div key={u.distributorId} className="py-2.5 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium text-slate-900">{u.distributorName}</span>
                          <span className="font-mono text-xs tabular-nums text-slate-500">
                            Window {u.openingTime}–{u.closingTime} · {u.visitDurationMinutes}m · Priority {u.priority}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-amber-800">{u.reason}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
