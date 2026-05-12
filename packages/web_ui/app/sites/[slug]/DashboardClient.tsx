"use client";

import { Activity, BatteryCharging, Cable, Clock3, Gauge, RadioTower, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { LoadChart } from "@/components/LoadChart";
import { MiniLine } from "@/components/MiniLine";
import { currentUserLabel, loadDashboardSnapshot } from "@/lib/api";
import { fixture, jitterSnapshot, type DashboardSnapshot } from "@/lib/fixtures";
import { fmt, nowTime } from "@/lib/format";

const deviceSelectionKey = (slug: string) => `solamon-selected-device:${slug}`;

export default function DashboardClient({ slug = "bench" }: { slug?: string }) {
  const [tick, setTick] = useState(0);
  const [cloudData, setCloudData] = useState<DashboardSnapshot | null>(null);
  const [cloudError, setCloudError] = useState("");
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [userLabel, setUserLabel] = useState("operator");
  const data = useMemo(
    () => (cloudData ? cloudData : jitterSnapshot(fixture, tick)),
    [cloudData, tick]
  );
  const dataMode = cloudData ? "cloud" : "fixtures";
  const deviceOptions = data.site.devices;

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 2000);
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

  return (
    <AppShell active="dashboard" dataMode={dataMode} userLabel={userLabel}>
      <div className="page-heading">
        <div>
          <h1>{data.site.name}</h1>
          <p>
            {data.site.deviceName} - {data.site.location} -{" "}
            {cloudData ? "live cloud telemetry" : `fixture fallback${cloudError ? ` (${cloudError})` : ""}`}
          </p>
        </div>
        <div className="inline-row">
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
          <span className="pill ok"><RadioTower size={14} /> Last update {nowTime()}</span>
          <span className={`pill ${deviceStatusClass(deviceOptions.find((device) => device.id === data.site.deviceId)?.status)}`}>
            {deviceOptions.find((device) => device.id === data.site.deviceId)?.status ?? "unknown"}
          </span>
          <span className="pill muted">{data.site.deviceId}</span>
        </div>
      </div>

      <div className="grid dashboard-grid">
        <MetricCard
          className="span-4"
          title="Active power"
          icon={<Zap size={18} />}
          value={fmt(data.metrics.activePowerKw)}
          unit="kW"
          detail="Server-rendered initial value, then live WebSocket-style updates"
          trend={<MiniLine data={data.series.slice(-8)} />}
        />
        <MetricCard
          className="span-4"
          title="Energy today"
          icon={<BatteryCharging size={18} />}
          value={fmt(data.metrics.importKwhToday)}
          unit="kWh import"
          detail={`${fmt(data.metrics.exportKwhToday)} kWh export - 6.4% above yesterday`}
        />
        <MetricCard
          className="span-4"
          title="Demand"
          icon={<Gauge size={18} />}
          value={fmt(data.metrics.demandKw)}
          unit="kW"
          detail={`Peak ${fmt(data.metrics.demandPeakKw)} kW at ${data.metrics.demandPeakAt}; window ${data.metrics.demandWindowMinutes} min`}
        />

        <PhaseCard title="Voltage per phase" className="span-3" labels={["Va", "Vb", "Vc"]} values={data.metrics.voltages} unit="V" max={253} />
        <PhaseCard title="Current per phase" className="span-3" labels={["Ia", "Ib", "Ic"]} values={data.metrics.currents} unit="A" max={500} />
        <PhaseCard title="Per-phase power" className="span-3" labels={["Pa", "Pb", "Pc"]} values={data.metrics.activePowerPhasesKw} unit="kW" max={120} />
        <PhaseCard title="Power factor" className="span-3" labels={["PFa", "PFb", "PFc"]} values={data.metrics.powerFactor.slice(0, 3)} unit="" max={1} />

        <MetricCard className="span-3" title="Frequency" icon={<Activity size={18} />} value={fmt(data.metrics.frequencyHz, 2)} unit="Hz" detail="Target 50.00 Hz; healthy band 49.5-50.5" />
        <MetricCard className="span-3" title="Voltage unbalance" icon={<Cable size={18} />} value={fmt(data.metrics.voltageUnbalancePct)} unit="%" detail="Below 2% target; 5% alert threshold" />
        <MetricCard className="span-3" title="Current unbalance" icon={<Cable size={18} />} value={fmt(data.metrics.currentUnbalancePct)} unit="%" detail="Watch if sustained over 5%" />
        <MetricCard className="span-3" title="Edge health" icon={<Clock3 size={18} />} value={`${data.metrics.edgeHeartbeatAgeSec}s`} unit="ago" detail={`${data.metrics.modbusErrorsPerMin}/min Modbus errors; buffer ${data.metrics.bufferDepthSec}s`} />

        <div className="card span-7">
          <div className="card-title">
            <span>Load profile</span>
            <span className="pill muted">1h / 6h / 24h / 7d ready</span>
          </div>
          <LoadChart data={data.series} />
        </div>

        <div className="card span-5">
          <div className="card-title">
            <span>POC readiness</span>
            <span className={cloudData ? "pill ok" : "pill warn"}>
              {cloudData ? "Live data attached" : "Waiting for cloud data"}
            </span>
          </div>
          <div className="timeline">
            {[
              cloudData ? "Authenticated cloud API session" : "Fixture fallback active",
              "Device snapshot adapter",
              "Active-power readings range query",
              "Live refresh polling every 10s",
              "Control screen remains demo until cloud command endpoint lands"
            ].map((item) => (
              <div className="timeline-row done" key={item}>
                <span className="timeline-dot" />
                <strong>{item}</strong>
                <span className="subtext">ok</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function deviceStatusClass(status?: string): string {
  if (status === "online") return "ok";
  if (status === "offline" || status === "unknown") return "muted";
  return "warn";
}

function MetricCard({
  title,
  icon,
  value,
  unit,
  detail,
  trend,
  className
}: {
  title: string;
  icon: React.ReactNode;
  value: string;
  unit: string;
  detail: string;
  trend?: React.ReactNode;
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
      {trend}
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
