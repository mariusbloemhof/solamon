"use client";

import { Activity, BatteryCharging, Gauge, Info, ShieldCheck, Zap } from "lucide-react";
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
        const next = await loadDashboardSnapshot(slug, undefined, 24);
        if (!cancelled) {
          setSnapshot(next);
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
      <ClientAssessment snapshot={snapshot} />
    </ClientShell>
  );
}

function ClientAssessment({ snapshot }: { snapshot: DashboardSnapshot }) {
  const stats = useMemo(() => loadStats(snapshot.series), [snapshot.series]);
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
