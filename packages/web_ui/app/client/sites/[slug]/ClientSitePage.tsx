"use client";

import { Activity, BatteryCharging, Clock3, Gauge, Info, ShieldCheck, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ClientLoadProfileChart, loadStats } from "@/components/client/ClientLoadProfileChart";
import { ClientShell } from "@/components/client/ClientShell";
import { authToken, loadDashboardSnapshot } from "@/lib/api";
import type { DashboardSnapshot } from "@/lib/fixtures";
import { fmt } from "@/lib/format";

export function ClientSitePage({ slug }: { slug: string }) {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [longSeries, setLongSeries] = useState<DashboardSnapshot["series"]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    if (!authToken()) {
      router.push(`/client/login?callbackUrl=/client/sites/${slug}`);
      return;
    }

    let cancelled = false;
    async function refresh() {
      try {
        const fullWindow = await loadDashboardSnapshot(slug, undefined, 168);
        const next = { ...fullWindow, series: recentWindow(fullWindow.series, 24) };
        if (!cancelled) {
          setSnapshot(next);
          setLongSeries(fullWindow.series);
          setError("");
          setBusy(false);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Could not load this assessment");
          setBusy(false);
        }
      }
    }

    refresh();
    const id = window.setInterval(refresh, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [router, slug]);

  const status = freshnessStatus(snapshot?.site.lastSeenAt);
  const lastSeenLabel = relativeTime(snapshot?.site.lastSeenAt);

  if (busy) {
    return (
      <ClientShell siteName="Loading site" status="delayed" lastSeenLabel="--">
        <section className="client-content">
          <div className="client-loading">Loading assessment...</div>
        </section>
      </ClientShell>
    );
  }

  if (error || !snapshot) {
    return (
      <ClientShell siteName="Assessment unavailable" status="offline" lastSeenLabel="--">
        <section className="client-content">
          <div className="client-error-card">
            <h1>We could not load this assessment</h1>
            <p>Please refresh. If the issue persists, contact Solamon support.</p>
            {error ? <details><summary>Technical details</summary><code>{error}</code></details> : null}
          </div>
        </section>
      </ClientShell>
    );
  }

  return (
    <ClientShell siteName={snapshot.site.name} status={status} lastSeenLabel={lastSeenLabel}>
      <ClientAssessment snapshot={snapshot} longSeries={longSeries} />
    </ClientShell>
  );
}

function ClientAssessment({ snapshot, longSeries }: { snapshot: DashboardSnapshot; longSeries: DashboardSnapshot["series"] }) {
  const stats = useMemo(() => loadStats(snapshot.series), [snapshot.series]);
  const longStats = useMemo(() => longTermStats(longSeries), [longSeries]);
  const peakTime = stats.peak ? stats.peak.t : "--";
  const energy = estimateEnergyKwh(snapshot.series);
  const pf = snapshot.metrics.powerFactor[3] || snapshot.metrics.powerFactor.find(Boolean) || 0;
  const quality = qualitySummary(snapshot);
  const pattern = patternSummary(snapshot, stats.averageKw);

  return (
    <section className="client-content">
      <div className="client-hero">
        <div>
          <span className="client-kicker">Live site assessment</span>
          <h1>{snapshot.site.name}</h1>
          <p>
            24 hour measurement window for {snapshot.site.deviceName}. Times shown in{" "}
            {snapshot.site.timezone ?? "site timezone"}.
          </p>
        </div>
        <div className="client-meter-card">
          <span>Meter</span>
          <strong>{snapshot.site.deviceName}</strong>
          <small>{snapshot.site.location}</small>
        </div>
      </div>

      <div className="client-kpi-grid">
        <ClientKpi title="Current load" value={fmt(snapshot.metrics.activePowerKw)} unit="kW" icon={<Zap size={18} />} detail="Latest received reading" />
        <ClientKpi title="Peak load" value={stats.peak ? fmt(stats.peak.kw) : "--"} unit="kW" icon={<Gauge size={18} />} detail={stats.peak ? `At ${peakTime}` : "Waiting for data"} />
        <ClientKpi title="Average load" value={fmt(stats.averageKw)} unit="kW" icon={<Activity size={18} />} detail="Across this 24h window" />
        <ClientKpi title="Energy measured" value={fmt(energy)} unit="kWh" icon={<BatteryCharging size={18} />} detail="Estimated from active power trace" />
        <ClientKpi title="Power factor" value={pf ? fmt(pf, 2) : "--"} unit="" icon={<ShieldCheck size={18} />} detail={pf >= 0.9 ? "Healthy operating range" : "Needs review"} />
      </div>

      <ClientLoadProfileChart data={snapshot.series} />

      <LongTermAnalysis stats={longStats} />

      <div className="client-insight-grid">
        <InsightCard title="Load pattern" text={pattern} />
        <InsightCard title="Peak event" text={stats.peak ? `Peak load reached ${fmt(stats.peak.kw)} kW at ${peakTime}.` : "Not enough readings yet to identify a peak event."} />
        <InsightCard title="Operating quality" text={quality} />
        <InsightCard title="Data confidence" text={`${stats.samples.toLocaleString("en-ZA")} active-power samples in the current view. Last received ${relativeTime(snapshot.site.lastSeenAt)}.`} />
      </div>

      <div className="client-detail-grid">
        <PhasePanel title="Voltage per phase" labels={["L1", "L2", "L3"]} values={snapshot.metrics.voltages} unit="V" />
        <PhasePanel title="Current per phase" labels={["L1", "L2", "L3"]} values={snapshot.metrics.currents} unit="A" />
        <PhasePanel title="Power per phase" labels={["L1", "L2", "L3"]} values={snapshot.metrics.activePowerPhasesKw} unit="kW" />
        <div className="client-detail-card">
          <div className="client-card-title"><span>Measurement status</span><Info size={16} /></div>
          <dl className="client-facts">
            <div><dt>Frequency</dt><dd>{fmt(snapshot.metrics.frequencyHz, 2)} Hz</dd></div>
            <div><dt>Voltage unbalance</dt><dd>{fmt(snapshot.metrics.voltageUnbalancePct)}%</dd></div>
            <div><dt>Current unbalance</dt><dd>{fmt(snapshot.metrics.currentUnbalancePct)}%</dd></div>
            <div><dt>Samples</dt><dd>{stats.samples.toLocaleString("en-ZA")}</dd></div>
          </dl>
        </div>
      </div>
    </section>
  );
}

function LongTermAnalysis({ stats }: { stats: LongStats }) {
  return (
    <div className="client-longterm">
      <div className="client-longterm-head">
        <div>
          <span className="client-kicker">7 day usage intelligence</span>
          <h2>Operating trend</h2>
        </div>
        <span>{stats.coverageLabel}</span>
      </div>
      <div className="client-longterm-grid">
        <div className="client-trend-panel">
          <div className="client-card-title"><span>Smoothed usage profile</span><Activity size={16} /></div>
          {stats.trend.length ? <SevenDayUsageChart points={stats.trend} days={stats.days} /> : <div className="client-empty-inline">Waiting for enough readings.</div>}
          <div className="client-trend-legend">
            <span><i className="energy" /> Smoothed kW</span>
            <span><i className="peak" /> Daily peak markers</span>
          </div>
        </div>
        <div className="client-trend-summary">
          <ClientKpi title="7 day energy" value={fmt(stats.energyKwh, 0)} unit="kWh" icon={<BatteryCharging size={18} />} detail="Estimated from received active power" />
          <ClientKpi title="Weekly peak" value={stats.peak ? fmt(stats.peak.kw) : "--"} unit="kW" icon={<Gauge size={18} />} detail={stats.peak ? `Seen ${stats.peak.when}` : "Waiting for history"} />
          <ClientKpi title="Peak usage time" value={stats.peakHourLabel} unit="" icon={<Clock3 size={18} />} detail="Highest average hour of day" />
          <div className="client-profile-card">
            <div className="client-card-title"><span>Load profile mix</span><Zap size={16} /></div>
            <LoadBand label="Light" value={stats.bands.lightPct} />
            <LoadBand label="Working" value={stats.bands.workingPct} />
            <LoadBand label="Peak" value={stats.bands.peakPct} />
          </div>
        </div>
      </div>
    </div>
  );
}

function SevenDayUsageChart({ points, days }: { points: TrendPoint[]; days: DailyBucket[] }) {
  const width = 860;
  const height = 260;
  const pad = { top: 20, right: 24, bottom: 38, left: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const max = Math.max(...points.map((point) => point.kw), ...days.map((day) => day.peakKw), 1) * 1.12;
  const usablePoints = points.length > 1 ? points : [];
  const x = (index: number, count: number) => pad.left + (index / Math.max(count - 1, 1)) * plotW;
  const y = (kw: number) => pad.top + (1 - Math.max(0, kw) / max) * plotH;
  const line = smoothPath(usablePoints.map((point, index) => ({ x: x(index, usablePoints.length), y: y(point.kw) })));
  const area = line ? `${line} L ${pad.left + plotW} ${pad.top + plotH} L ${pad.left} ${pad.top + plotH} Z` : "";
  const dayX = (index: number) => pad.left + (index / Math.max(days.length - 1, 1)) * plotW;
  const labelablePeaks = days.filter((day) => day.hasData && day.peakKw > 0);

  return (
    <svg className="client-usage-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Smoothed 7 day usage chart">
      <defs>
        <linearGradient id="clientUsageFill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="oklch(62% 0.15 150 / 0.18)" />
          <stop offset="100%" stopColor="oklch(62% 0.15 150 / 0.02)" />
        </linearGradient>
      </defs>
      {[0, 0.5, 1].map((ratio) => (
        <g key={ratio}>
          <line x1={pad.left} x2={pad.left + plotW} y1={pad.top + plotH * ratio} y2={pad.top + plotH * ratio} className="client-grid-line" />
          <text x={pad.left - 12} y={pad.top + plotH * ratio + 4} textAnchor="end" className="client-axis-label">
            {fmt(max * (1 - ratio), 0)}
          </text>
        </g>
      ))}
      {area ? <path d={area} className="client-usage-area" /> : null}
      {line ? <path d={line} className="client-usage-line" /> : null}
      {days.map((day, index) => (
        <g key={day.key}>
          <line x1={dayX(index)} x2={dayX(index)} y1={pad.top} y2={pad.top + plotH} className="client-day-line" />
          {day.hasData ? (
            <circle cx={dayX(index)} cy={y(day.peakKw)} r="4.5" className="client-day-peak">
              <title>{`${day.label} daily peak: ${fmt(day.peakKw)} kW`}</title>
            </circle>
          ) : null}
          <text x={dayX(index)} y={height - 12} textAnchor="middle" className={day.hasData ? "client-axis-label" : "client-axis-label muted"}>
            {day.label}
          </text>
        </g>
      ))}
      {labelablePeaks.slice(-3).map((day) => {
        const index = days.indexOf(day);
        const px = dayX(index);
        const py = y(day.peakKw);
        const anchor = index >= days.length - 2 ? "end" : "start";
        const textX = anchor === "end" ? px - 8 : px + 8;
        return (
          <text key={`${day.key}-peak-label`} x={textX} y={Math.max(pad.top + 14, py - 8)} textAnchor={anchor} className="client-day-peak-label">
            {fmt(day.peakKw)} kW
          </text>
        );
      })}
      <text x={pad.left - 34} y={pad.top - 6} className="client-axis-unit">kW</text>
    </svg>
  );
}

function LoadBand({ label, value }: { label: string; value: number }) {
  return (
    <div className="client-load-band">
      <span>{label}</span>
      <div><i style={{ width: `${Math.round(value)}%` }} /></div>
      <strong>{fmt(value, 0)}%</strong>
    </div>
  );
}

function ClientKpi({ title, value, unit, icon, detail }: { title: string; value: string; unit: string; icon: ReactNode; detail: string }) {
  return (
    <div className="client-kpi">
      <div className="client-card-title"><span>{title}</span>{icon}</div>
      <div className="client-kpi-value"><strong>{value}</strong>{unit ? <span>{unit}</span> : null}</div>
      <p>{detail}</p>
    </div>
  );
}

function InsightCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="client-insight-card">
      <span>{title}</span>
      <p>{text}</p>
    </div>
  );
}

function PhasePanel({ title, labels, values, unit }: { title: string; labels: string[]; values: number[]; unit: string }) {
  const max = Math.max(...values.map(Math.abs), 1);
  return (
    <div className="client-detail-card">
      <div className="client-card-title"><span>{title}</span></div>
      <div className="client-phase-list">
        {values.map((value, index) => (
          <div key={labels[index]} className="client-phase-row">
            <span>{labels[index]}</span>
            <div className="client-phase-bar"><i style={{ width: `${Math.min(100, Math.abs(value / max) * 100)}%` }} /></div>
            <strong>{fmt(value, unit === "kW" ? 1 : 2)} {unit}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function estimateEnergyKwh(series: DashboardSnapshot["series"]): number {
  if (series.length < 2) return 0;
  let total = 0;
  for (let i = 1; i < series.length; i += 1) {
    const previous = series[i - 1];
    const current = series[i];
    const previousTime = previous.iso ? new Date(previous.iso).getTime() : NaN;
    const currentTime = current.iso ? new Date(current.iso).getTime() : NaN;
    const hours = Number.isFinite(previousTime) && Number.isFinite(currentTime)
      ? Math.max(0, (currentTime - previousTime) / 3_600_000)
      : 24 / Math.max(series.length - 1, 1);
    total += ((previous.kw + current.kw) / 2) * hours;
  }
  return total;
}

function recentWindow(series: DashboardSnapshot["series"], hours: number): DashboardSnapshot["series"] {
  const latest = series.reduce((best, point) => Math.max(best, timestampMs(point.iso)), 0);
  if (!latest) return series.slice(-1500);
  const cutoff = latest - hours * 3_600_000;
  return series.filter((point) => timestampMs(point.iso) >= cutoff);
}

type DailyBucket = {
  key: string;
  label: string;
  energyKwh: number;
  peakKw: number;
  hasData: boolean;
};

type TrendPoint = {
  time: number;
  kw: number;
};

type LongStats = {
  days: DailyBucket[];
  trend: TrendPoint[];
  energyKwh: number;
  peak: { kw: number; when: string } | null;
  peakHourLabel: string;
  coverageLabel: string;
  bands: { lightPct: number; workingPct: number; peakPct: number };
};

function longTermStats(series: DashboardSnapshot["series"]): LongStats {
  const usable = series.filter((point) => Number.isFinite(point.kw) && timestampMs(point.iso));
  const energyKwh = estimateEnergyKwh(usable);
  const peakPoint = usable.reduce<DashboardSnapshot["series"][number] | null>(
    (best, point) => (!best || point.kw > best.kw ? point : best),
    null
  );
  const peak = peakPoint
    ? { kw: peakPoint.kw, when: new Date(peakPoint.iso ?? "").toLocaleString("en-ZA", { weekday: "short", hour: "2-digit", minute: "2-digit" }) }
    : null;
  const days = dailyBuckets(usable);
  const trend = smoothedTrend(usable);
  const daysWithData = days.filter((day) => day.hasData).length;
  const coverageLabel = daysWithData >= 7 ? "7 day view" : `${daysWithData} of 7 days received`;
  const peakHourLabel = peakHour(usable);
  const bands = loadBands(usable);
  return { days, trend, energyKwh, peak, peakHourLabel, coverageLabel, bands };
}

function dailyBuckets(series: DashboardSnapshot["series"]): DailyBucket[] {
  const buckets = new Map<string, DashboardSnapshot["series"]>();
  const latest = series.reduce((best, point) => Math.max(best, timestampMs(point.iso)), 0) || Date.now();
  const end = startOfLocalDay(latest);
  for (const point of series) {
    const time = timestampMs(point.iso);
    if (!time) continue;
    const key = localDateKey(time);
    buckets.set(key, [...(buckets.get(key) ?? []), point]);
  }
  return Array.from({ length: 7 }, (_, index) => {
    const time = end - (6 - index) * 86_400_000;
    const key = localDateKey(time);
    const points = buckets.get(key) ?? [];
    const hasData = points.length > 0;
    const date = new Date(time);
    const label = date.toLocaleDateString("en-ZA", { weekday: "short" });
    const peakKw = Math.max(...points.map((point) => point.kw), 0);
    return { key, label, energyKwh: estimateEnergyKwh(points), peakKw, hasData };
  });
}

function smoothedTrend(series: DashboardSnapshot["series"]): TrendPoint[] {
  const usable = series
    .map((point) => ({ time: timestampMs(point.iso), kw: point.kw }))
    .filter((point) => point.time && Number.isFinite(point.kw))
    .sort((a, b) => a.time - b.time);
  if (usable.length < 2) return usable;

  const bucketMinutes = 60;
  const buckets = new Map<number, { sum: number; count: number }>();
  for (const point of usable) {
    const bucketTime = Math.floor(point.time / (bucketMinutes * 60_000)) * bucketMinutes * 60_000;
    const bucket = buckets.get(bucketTime) ?? { sum: 0, count: 0 };
    bucket.sum += point.kw;
    bucket.count += 1;
    buckets.set(bucketTime, bucket);
  }

  const hourly = [...buckets.entries()]
    .sort(([a], [b]) => a - b)
    .map(([time, bucket]) => ({ time, kw: bucket.sum / Math.max(bucket.count, 1) }));

  return hourly.map((point, index) => {
    const window = hourly.slice(Math.max(0, index - 2), Math.min(hourly.length, index + 3));
    const kw = window.reduce((sum, item) => sum + item.kw, 0) / Math.max(window.length, 1);
    return { time: point.time, kw };
  });
}

function smoothPath(points: Array<{ x: number; y: number }>): string {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;
  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    const previous = points[index - 1];
    const midX = (previous.x + point.x) / 2;
    return `${path} Q ${previous.x.toFixed(1)} ${previous.y.toFixed(1)} ${midX.toFixed(1)} ${((previous.y + point.y) / 2).toFixed(1)} T ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
  }, "");
}

function localDateKey(time: number): string {
  const date = new Date(time);
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function startOfLocalDay(time: number): number {
  const date = new Date(time);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function peakHour(series: DashboardSnapshot["series"]): string {
  const buckets = new Map<number, { sum: number; count: number }>();
  for (const point of series) {
    const time = timestampMs(point.iso);
    if (!time) continue;
    const hour = new Date(time).getHours();
    const bucket = buckets.get(hour) ?? { sum: 0, count: 0 };
    bucket.sum += point.kw;
    bucket.count += 1;
    buckets.set(hour, bucket);
  }
  let bestHour = -1;
  let bestAverage = -1;
  for (const [hour, bucket] of buckets) {
    const average = bucket.sum / Math.max(bucket.count, 1);
    if (average > bestAverage) {
      bestAverage = average;
      bestHour = hour;
    }
  }
  if (bestHour < 0) return "--";
  return `${bestHour.toString().padStart(2, "0")}:00`;
}

function loadBands(series: DashboardSnapshot["series"]): LongStats["bands"] {
  if (!series.length) return { lightPct: 0, workingPct: 0, peakPct: 0 };
  const peak = Math.max(...series.map((point) => point.kw), 1);
  const bands = series.reduce(
    (acc, point) => {
      const ratio = Math.max(0, point.kw) / peak;
      if (ratio >= 0.75) acc.peak += 1;
      else if (ratio >= 0.25) acc.working += 1;
      else acc.light += 1;
      return acc;
    },
    { light: 0, working: 0, peak: 0 }
  );
  const total = Math.max(series.length, 1);
  return {
    lightPct: (bands.light / total) * 100,
    workingPct: (bands.working / total) * 100,
    peakPct: (bands.peak / total) * 100
  };
}

function timestampMs(value?: string | null): number {
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function freshnessStatus(value?: string | null): "live" | "delayed" | "offline" {
  if (!value) return "offline";
  const age = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(age)) return "offline";
  if (age <= 60_000) return "live";
  if (age <= 5 * 60_000) return "delayed";
  return "offline";
}

function relativeTime(value?: string | null): string {
  if (!value) return "--";
  const ageSec = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (!Number.isFinite(ageSec)) return "--";
  if (ageSec < 60) return `${ageSec}s ago`;
  const mins = Math.round(ageSec / 60);
  if (mins < 60) return `${mins} min ago`;
  return `${Math.round(mins / 60)}h ago`;
}

function qualitySummary(snapshot: DashboardSnapshot): string {
  const voltageOk = snapshot.metrics.voltageUnbalancePct > 0 && snapshot.metrics.voltageUnbalancePct <= 2;
  const frequencyOk = snapshot.metrics.frequencyHz >= 49.5 && snapshot.metrics.frequencyHz <= 50.5;
  if (voltageOk && frequencyOk) return "Voltage balance and frequency are within expected range for this measurement window.";
  if (!snapshot.metrics.frequencyHz && snapshot.metrics.voltages.every((v) => v === 0)) {
    return "The meter is reporting all-zero electrical values. Treat this as a measurement state to verify, not normal operation.";
  }
  return "One or more electrical quality values needs review as more data arrives.";
}

function patternSummary(snapshot: DashboardSnapshot, averageKw: number): string {
  const current = snapshot.metrics.activePowerKw;
  if (snapshot.series.length < 4) return "Not enough readings yet to describe a reliable load pattern.";
  if (current > averageKw * 1.4) return "Current load is running materially above the 24h average.";
  if (current < averageKw * 0.5) return "Current load is well below the 24h average.";
  return "Current load is broadly in line with the 24h average.";
}
