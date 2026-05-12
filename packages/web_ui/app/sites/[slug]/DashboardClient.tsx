"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  Cable,
  Clock3,
  Download,
  Gauge,
  RadioTower,
  TrendingUp,
  Zap
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { LoadChart } from "@/components/LoadChart";
import { MiniLine } from "@/components/MiniLine";
import { currentUserLabel, loadDashboardSnapshot } from "@/lib/api";
import type { DashboardSnapshot, ReadingPoint } from "@/lib/fixtures";
import { fmt, nowTime } from "@/lib/format";

const deviceSelectionKey = (slug: string) => `solamon-selected-device:${slug}`;

type Assessment = {
  averageKw: number;
  peakKw: number;
  baseLoadKw: number;
  loadFactorPct: number;
  estimatedDailyKwh: number;
  highUseHours: number;
  eveningAverageKw: number;
  recommendedSolarKwp: number;
  recommendedInverterKw: number;
  recommendedBatteryKwh: number;
};

export default function DashboardClient({
  slug = "bench",
  variant = "dashboard"
}: {
  slug?: string;
  variant?: "dashboard" | "assessment";
}) {
  const [, setTick] = useState(0);
  const [cloudData, setCloudData] = useState<DashboardSnapshot | null>(null);
  const [cloudError, setCloudError] = useState("");
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [userLabel, setUserLabel] = useState("operator");
  const [windowLabel, setWindowLabel] = useState<"24H" | "7D" | "30D">("24H");
  const [lastUpdateLabel, setLastUpdateLabel] = useState("--:--:--");
  const data = cloudData;
  const assessment = useMemo(() => (cloudData ? buildAssessment(cloudData) : undefined), [cloudData]);
  const dataMode = cloudData ? "cloud" : "offline";
  const deviceOptions = data?.site.devices ?? [];
  const activeDevice = data ? deviceOptions.find((device) => device.id === data.site.deviceId) : undefined;

  useEffect(() => {
    setLastUpdateLabel(nowTime());
    const id = window.setInterval(() => {
      setTick((n) => n + 1);
      setLastUpdateLabel(nowTime());
    }, 2000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    setSelectedDeviceId(window.localStorage.getItem(deviceSelectionKey(slug)) ?? "");
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    setUserLabel(currentUserLabel());

    async function refresh() {
      try {
        const snapshot = await loadDashboardSnapshot(slug, selectedDeviceId || undefined);
        if (!cancelled) {
          setCloudData(snapshot);
          setCloudError("");
          if (!selectedDeviceId) {
            window.localStorage.setItem(deviceSelectionKey(slug), snapshot.site.deviceId);
            setSelectedDeviceId(snapshot.site.deviceId);
          }
        }
      } catch (exc) {
        if (!cancelled) {
          setCloudError(exc instanceof Error ? exc.message : "Cloud data unavailable");
        }
      }
    }

    refresh();
    const id = window.setInterval(refresh, 10_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [slug, selectedDeviceId]);

  function onDeviceChange(deviceId: string) {
    window.localStorage.setItem(deviceSelectionKey(slug), deviceId);
    setSelectedDeviceId(deviceId);
  }

  function exportCsv() {
    if (!data) return;
    const rows = ["time,active_power_kw", ...data.series.map((point) => `${point.iso ?? point.t},${point.kw}`)];
    const url = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${data.site.slug}-load-${windowLabel.toLowerCase()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  if (!data || !assessment) {
    return (
      <AppShell active={variant === "assessment" ? "assessment" : "dashboard"} dataMode={dataMode} userLabel={userLabel}>
        <NoLiveData
          callbackPath={variant === "assessment" ? `/sites/${slug}/assessment` : `/sites/${slug}`}
          message={cloudError}
        />
      </AppShell>
    );
  }

  if (variant === "dashboard") {
    return (
      <AppShell active="dashboard" dataMode={dataMode} userLabel={userLabel}>
        <div className="page-heading">
          <div>
            <div className="eyebrow">Live Operations</div>
            <h1>{data.site.name}</h1>
            <p>
              {data.site.deviceName} - {data.site.location} -{" "}
              live Acuvim field telemetry
            </p>
          </div>
          <div className="heading-actions">
            <select
              aria-label="Select device"
              className="select compact-select"
              value={selectedDeviceId || data.site.deviceId}
              onChange={(event) => onDeviceChange(event.target.value)}
            >
              {deviceOptions.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.label}
                </option>
              ))}
            </select>
            <span className="pill ok"><RadioTower size={14} /> Last update {lastUpdateLabel}</span>
            <span className={`pill ${deviceStatusClass(activeDevice?.status)}`}>
              {activeDevice?.status ?? "unknown"}
            </span>
          </div>
        </div>

        <div className="gauges">
          <GaugeTile
            label="Total load"
            value={data.metrics.activePowerKw}
            unit="kW"
            max={Math.max(assessment.peakKw * 1.2, 1)}
            detail={`avg ${fmt(assessment.averageKw)} kW`}
          />
          <GaugeTile
            label="Demand peak"
            value={data.metrics.demandPeakKw}
            unit="kW"
            max={Math.max(assessment.peakKw * 1.2, 1)}
            detail={`at ${data.metrics.demandPeakAt}`}
          />
          <GaugeTile
            label="Energy today"
            value={data.metrics.importKwhToday}
            unit="kWh"
            max={Math.max(assessment.estimatedDailyKwh * 1.25, 1)}
            detail={`${fmt(data.metrics.exportKwhToday)} kWh export`}
          />
          <GaugeTile
            label="Frequency"
            value={data.metrics.frequencyHz}
            unit="Hz"
            max={55}
            detail="target 50.00 Hz"
            tone={Math.abs(data.metrics.frequencyHz - 50) > 0.5 ? "warn" : "ok"}
          />
          <GaugeTile
            label="Power factor"
            value={data.metrics.powerFactor[3] ?? 0}
            unit=""
            max={1}
            detail="total meter PF"
          />
          <GaugeTile
            label="Edge health"
            value={data.metrics.edgeHeartbeatAgeSec}
            unit="s"
            max={120}
            detail={`${fmt(data.metrics.modbusErrorsPerMin, 1)}/min Modbus errors`}
            tone={data.metrics.edgeHeartbeatAgeSec > 90 ? "warn" : "ok"}
          />
        </div>

        <div className="grid dashboard-grid">
          <div className="card span-8">
            <div className="card-title">
              <span>Load profile</span>
              <span className="pill muted">24h live trace</span>
            </div>
            <LoadChart data={data.series} />
          </div>
          <div className="card span-4">
            <div className="card-title">
              <span>Operational summary</span>
              <Activity size={18} />
            </div>
            <div className="quality-grid">
              <QualityStat label="Voltage unbalance" value={`${fmt(data.metrics.voltageUnbalancePct)}%`} />
              <QualityStat label="Current unbalance" value={`${fmt(data.metrics.currentUnbalancePct)}%`} />
              <QualityStat label="Demand window" value={`${fmt(data.metrics.demandWindowMinutes, 0)} min`} />
              <QualityStat label="Buffer depth" value={`${fmt(data.metrics.bufferDepthSec, 0)} s`} />
            </div>
            {data.metrics.haltedBlocks.length > 0 ? (
              <p className="subtext warn-text">Halted blocks: {data.metrics.haltedBlocks.join(", ")}</p>
            ) : (
              <p className="subtext">Telemetry is flowing without halted blocks.</p>
            )}
          </div>

          <PhaseCard title="Voltage per phase" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.voltages} unit="V" max={253} />
          <PhaseCard title="Current per phase" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.currents} unit="A" max={500} />
          <PhaseCard title="Per-phase power" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.activePowerPhasesKw} unit="kW" max={Math.max(assessment.peakKw / 3, 1)} />
          <PhaseCard title="Power factor" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.powerFactor.slice(0, 3)} unit="" max={1} />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell active="assessment" dataMode={dataMode} userLabel={userLabel}>
      <div className="page-heading">
        <div>
          <div className="eyebrow">Client Load Assessment</div>
          <h1>{data.site.name}</h1>
          <p>
            {data.site.deviceName} - {data.site.location} -{" "}
            live Acuvim field telemetry
          </p>
        </div>
        <div className="heading-actions">
          <select
            aria-label="Select device"
            className="select compact-select"
            value={selectedDeviceId || data.site.deviceId}
            onChange={(event) => onDeviceChange(event.target.value)}
          >
            {deviceOptions.map((device) => (
              <option key={device.id} value={device.id}>
                {device.label}
              </option>
            ))}
          </select>
          <button className="button secondary" onClick={exportCsv}>
            <Download size={15} /> Export CSV
          </button>
        </div>
      </div>

      <section className="assessment-strip">
        <div>
          <span className="section-label">30-day capture</span>
          <strong>{windowLabel === "30D" ? "Assessment window" : "Early pattern signal"}</strong>
          <p>
            Peak, base load, evening demand, and load factor are the first sizing inputs for Johan's
            recommendation.
          </p>
        </div>
        <div className="segmented" aria-label="Analysis window">
          {(["24H", "7D", "30D"] as const).map((label) => (
            <button
              key={label}
              className={windowLabel === label ? "active" : ""}
              onClick={() => setWindowLabel(label)}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="pill ok"><RadioTower size={14} /> Last update {lastUpdateLabel}</span>
        <span className={`pill ${deviceStatusClass(activeDevice?.status)}`}>
          {activeDevice?.status ?? "unknown"}
        </span>
      </section>

      <div className="gauges">
        <GaugeTile
          label="Total load"
          value={data.metrics.activePowerKw}
          unit="kW"
          max={Math.max(assessment.peakKw * 1.2, 1)}
          detail={`avg ${fmt(assessment.averageKw)} kW`}
        />
        <GaugeTile
          label="Peak demand"
          value={assessment.peakKw}
          unit="kW"
          max={Math.max(assessment.peakKw * 1.2, 1)}
          detail={`${assessment.highUseHours} high-use hours`}
        />
        <GaugeTile
          label="Base load"
          value={assessment.baseLoadKw}
          unit="kW"
          max={Math.max(assessment.peakKw, 1)}
          detail={`${fmt(assessment.loadFactorPct, 0)}% load factor`}
        />
        <GaugeTile
          label="Energy today"
          value={data.metrics.importKwhToday}
          unit="kWh"
          max={Math.max(assessment.estimatedDailyKwh * 1.25, 1)}
          detail={`${fmt(data.metrics.exportKwhToday)} kWh export`}
        />
        <GaugeTile
          label="Power quality"
          value={data.metrics.frequencyHz}
          unit="Hz"
          max={55}
          detail={`${fmt(data.metrics.voltageUnbalancePct)}% voltage unbalance`}
          tone={Math.abs(data.metrics.frequencyHz - 50) > 0.5 ? "warn" : "ok"}
        />
        <GaugeTile
          label="Edge health"
          value={data.metrics.edgeHeartbeatAgeSec}
          unit="s"
          max={120}
          detail={`${fmt(data.metrics.modbusErrorsPerMin, 1)}/min Modbus errors`}
          tone={data.metrics.edgeHeartbeatAgeSec > 90 ? "warn" : "ok"}
        />
      </div>

      <div className="grid dashboard-grid">
        <div className="card span-8">
          <div className="card-title">
            <span>Consumption profile</span>
            <span className="pill muted">{windowLabel.toLowerCase()} load trace</span>
          </div>
          <LoadChart data={data.series} />
        </div>

        <div className="card span-4">
          <div className="card-title">
            <span>Recommendation signal</span>
            <TrendingUp size={18} />
          </div>
          <div className="sizing-list">
            <SizingRow label="Solar array" value={`${fmt(assessment.recommendedSolarKwp)} kWp`} />
            <SizingRow label="Inverter capacity" value={`${fmt(assessment.recommendedInverterKw)} kW`} />
            <SizingRow label="Usable battery" value={`${fmt(assessment.recommendedBatteryKwh)} kWh`} />
          </div>
          <p className="subtext">
            Preliminary only. Confidence improves as the field meter fills the 30-day profile.
          </p>
          <MiniLine data={data.series.slice(-12)} height={64} />
        </div>

        <MetricCard
          className="span-3"
          title="Average load"
          icon={<Activity size={18} />}
          value={fmt(assessment.averageKw)}
          unit="kW"
          detail={`Estimated ${fmt(assessment.estimatedDailyKwh, 0)} kWh/day`}
        />
        <MetricCard
          className="span-3"
          title="Evening demand"
          icon={<Clock3 size={18} />}
          value={fmt(assessment.eveningAverageKw)}
          unit="kW"
          detail="17:00-21:00 planning window"
        />
        <MetricCard
          className="span-3"
          title="Demand"
          icon={<Gauge size={18} />}
          value={fmt(data.metrics.demandKw)}
          unit="kW"
          detail={`Peak ${fmt(data.metrics.demandPeakKw)} kW at ${data.metrics.demandPeakAt}`}
        />
        <MetricCard
          className="span-3"
          title="Power factor"
          icon={<Zap size={18} />}
          value={fmt(data.metrics.powerFactor[3] ?? 0, 2)}
          unit=""
          detail="Total meter power factor"
        />

        <PhaseCard title="Voltage per phase" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.voltages} unit="V" max={253} />
        <PhaseCard title="Current per phase" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.currents} unit="A" max={500} />
        <PhaseCard title="Per-phase power" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.activePowerPhasesKw} unit="kW" max={Math.max(assessment.peakKw / 3, 1)} />
        <PhaseCard title="Power factor" className="span-3" labels={["L1", "L2", "L3"]} values={data.metrics.powerFactor.slice(0, 3)} unit="" max={1} />

        <div className="card span-6">
          <div className="card-title">
            <span>Usage pattern notes</span>
            <span className="pill muted">{data.series.length} samples</span>
          </div>
          <div className="insight-list">
            <Insight label="Sizing peak" value={`${fmt(assessment.peakKw)} kW`} detail="Use for inverter and generator headroom checks." />
            <Insight label="Persistent base" value={`${fmt(assessment.baseLoadKw)} kW`} detail="Always-on load informs minimum solar offset and overnight storage." />
            <Insight label="Load factor" value={`${fmt(assessment.loadFactorPct, 0)}%`} detail="Higher values indicate flatter industrial demand; lower values suggest peak shaving value." />
          </div>
        </div>

        <div className="card span-6">
          <div className="card-title">
            <span>Quality and reliability</span>
            <Cable size={18} />
          </div>
          <div className="quality-grid">
            <QualityStat label="Frequency" value={`${fmt(data.metrics.frequencyHz, 2)} Hz`} />
            <QualityStat label="Voltage unbalance" value={`${fmt(data.metrics.voltageUnbalancePct)}%`} />
            <QualityStat label="Current unbalance" value={`${fmt(data.metrics.currentUnbalancePct)}%`} />
            <QualityStat label="Buffer depth" value={`${fmt(data.metrics.bufferDepthSec, 0)} s`} />
          </div>
          {data.metrics.haltedBlocks.length > 0 ? (
            <p className="subtext warn-text">Halted blocks: {data.metrics.haltedBlocks.join(", ")}</p>
          ) : (
            <p className="subtext">No halted telemetry blocks reported.</p>
          )}
        </div>
      </div>
    </AppShell>
  );
}

function NoLiveData({ callbackPath, message }: { callbackPath: string; message: string }) {
  const isAuthIssue = !message || message.includes("No cloud token") || message.includes("401") || message.includes("403");

  return (
    <div className="empty-state">
      <div className="empty-state-icon">
        <AlertTriangle size={22} />
      </div>
      <div>
        <div className="eyebrow">Live Devices Only</div>
        <h1>No live device data available</h1>
        <p>
          This dashboard only shows registered devices from the cloud API. Fixture, seeded, and
          demo devices are hidden so the field assessment cannot be mistaken for live telemetry.
        </p>
        {message ? <p className="subtext">Current status: {message}</p> : null}
      </div>
      <div className="empty-state-actions">
        {isAuthIssue ? (
          <Link className="button" href={`/login?callbackUrl=${encodeURIComponent(callbackPath)}`}>
            Sign in
          </Link>
        ) : null}
        <button className="button secondary" type="button" onClick={() => window.location.reload()}>
          Retry
        </button>
      </div>
    </div>
  );
}

function buildAssessment(data: DashboardSnapshot): Assessment {
  const values = data.series.map((point) => point.kw).filter(Number.isFinite);
  const averageKw = avg(values, data.metrics.activePowerKw);
  const peakKw = Math.max(...values, data.metrics.demandPeakKw, data.metrics.activePowerKw, 1);
  const sorted = [...values].sort((a, b) => a - b);
  const lowSlice = sorted.slice(0, Math.max(1, Math.ceil(sorted.length * 0.25)));
  const baseLoadKw = avg(lowSlice, Math.min(data.metrics.activePowerKw, peakKw));
  const loadFactorPct = (averageKw / peakKw) * 100;
  const estimatedDailyKwh = estimateDailyKwh(data.series, averageKw);
  const highUseHours = Math.round(values.filter((value) => value >= peakKw * 0.8).length * sampleHours(data.series));
  const evening = data.series.filter((point) => {
    const hour = pointHour(point);
    return hour >= 17 && hour <= 21;
  }).map((point) => point.kw);
  const eveningAverageKw = avg(evening, averageKw);

  return {
    averageKw,
    peakKw,
    baseLoadKw,
    loadFactorPct,
    estimatedDailyKwh,
    highUseHours,
    eveningAverageKw,
    recommendedSolarKwp: Math.max(10, estimatedDailyKwh / 4.8),
    recommendedInverterKw: peakKw * 1.15,
    recommendedBatteryKwh: Math.max(eveningAverageKw * 3, estimatedDailyKwh * 0.25)
  };
}

function avg(values: number[], fallback: number): number {
  if (values.length === 0) return fallback;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function estimateDailyKwh(series: ReadingPoint[], averageKw: number): number {
  if (series.length < 2 || !series.every((point) => point.iso)) return averageKw * 24;
  let kwh = 0;
  for (let i = 1; i < series.length; i += 1) {
    const prev = series[i - 1];
    const next = series[i];
    const dtHours = (Date.parse(next.iso!) - Date.parse(prev.iso!)) / 3_600_000;
    if (dtHours > 0 && dtHours <= 3) {
      kwh += ((prev.kw + next.kw) / 2) * dtHours;
    }
  }
  const first = Date.parse(series[0].iso!);
  const last = Date.parse(series[series.length - 1].iso!);
  const capturedHours = Math.max((last - first) / 3_600_000, 1);
  return (kwh / capturedHours) * 24;
}

function sampleHours(series: ReadingPoint[]): number {
  if (series.length < 2 || !series[0].iso || !series[1].iso) return 1;
  return Math.max((Date.parse(series[1].iso) - Date.parse(series[0].iso)) / 3_600_000, 0.01);
}

function pointHour(point: ReadingPoint): number {
  if (point.iso) return new Date(point.iso).getHours();
  const match = point.t.match(/^(\d{1,2})/);
  return match ? Number(match[1]) : 12;
}

function deviceStatusClass(status?: string): string {
  if (status === "online") return "ok";
  if (status === "offline" || status === "unknown") return "muted";
  return "warn";
}

function GaugeTile({
  label,
  value,
  unit,
  max,
  detail,
  tone = "ok"
}: {
  label: string;
  value: number;
  unit: string;
  max: number;
  detail: string;
  tone?: "ok" | "warn";
}) {
  const pct = Math.max(0, Math.min(1, value / max));
  const dash = `${pct * 100} ${100 - pct * 100}`;
  return (
    <div className="gauge-tile">
      <div className="gauge-label"><span className={`dot ${tone === "warn" ? "warn" : ""}`} />{label}</div>
      <svg viewBox="0 0 120 70" role="img" aria-label={`${label}: ${fmt(value)} ${unit}`}>
        <path className="gauge-track" d="M18 58a42 42 0 0 1 84 0" pathLength="100" />
        <path className={`gauge-fill ${tone}`} d="M18 58a42 42 0 0 1 84 0" pathLength="100" strokeDasharray={dash} />
      </svg>
      <div className="gauge-value">
        <strong>{fmt(value, unit === "Hz" ? 2 : 1)}</strong>
        <span>{unit}</span>
      </div>
      <div className="gauge-delta">{detail}</div>
    </div>
  );
}

function MetricCard({
  title,
  icon,
  value,
  unit,
  detail,
  className
}: {
  title: string;
  icon: React.ReactNode;
  value: string;
  unit: string;
  detail: string;
  className?: string;
}) {
  return (
    <div className={`card ${className ?? ""}`}>
      <div className="card-title">
        <span>{title}</span>
        {icon}
      </div>
      <div className="metric">
        <strong>{value}</strong>
        <span>{unit}</span>
      </div>
      <p className="subtext">{detail}</p>
    </div>
  );
}

function PhaseCard({
  title,
  labels,
  values,
  unit,
  max,
  className
}: {
  title: string;
  labels: string[];
  values: number[];
  unit: string;
  max: number;
  className?: string;
}) {
  return (
    <div className={`card ${className ?? ""}`}>
      <div className="card-title"><span>{title}</span></div>
      <div className="mini-grid">
        {values.map((value, index) => (
          <div className="phase-tile" key={labels[index]}>
            <b>{labels[index]}</b>
            <strong>{fmt(value, unit ? 1 : 2)} {unit}</strong>
            <div className="bar">
              <span style={{ width: `${Math.min(100, Math.abs(value / max) * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SizingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="sizing-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Insight({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="insight-row">
      <div>
        <strong>{label}</strong>
        <p>{detail}</p>
      </div>
      <span>{value}</span>
    </div>
  );
}

function QualityStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="quality-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
