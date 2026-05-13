import type { DashboardSnapshot, DeviceOption, ReadingPoint } from "@/lib/fixtures";

const API_BASE_KEY = "solamon-api-base";
export const TOKEN_KEY = "solamon-access-token";
export const USER_KEY = "solamon-user";

type SiteDetail = {
  slug: string;
  name: string;
  timezone?: string | null;
  last_seen_at?: string | null;
  is_active: boolean;
  devices: DeviceSummary[];
  health?: {
    heartbeat_age_seconds?: number | null;
    modbus_errors_per_minute?: number;
    edge_buffer_depth_seconds?: number;
  } | null;
};

type DeviceSummary = {
  id: string;
  name: string;
  manufacturer?: string | null;
  model?: string | null;
  host: string;
  port: number;
  unit_id: number;
  status: "online" | "offline" | "unreachable" | "fault" | "unknown";
  last_seen_at?: string | null;
};

type DeviceSnapshot = {
  snapshot_time: string;
  metrics: Record<string, unknown>;
  operating_state?: string | null;
  active_faults?: string[] | null;
};

type ReadingSeries = {
  metric: string;
  points: Array<{ time: string; value: number | null; quality: "good" | "uncertain" | "bad" }>;
};

type LoginResponse = {
  access_token: string;
  expires_in: number;
  user: {
    email: string;
    display_name: string;
    role: string;
    tier: string;
  };
};

export function apiBase(): string {
  if (typeof window === "undefined") {
    return process.env.NEXT_PUBLIC_SOLAMON_API_BASE ?? "/api/v1";
  }
  return (
    window.localStorage.getItem(API_BASE_KEY) ||
    process.env.NEXT_PUBLIC_SOLAMON_API_BASE ||
    "/api/v1"
  ).replace(/\/$/, "");
}

export function setApiBase(value: string): void {
  const trimmed = value.trim().replace(/\/$/, "");
  if (!trimmed || trimmed === "/api/v1" || trimmed === "https://cloud.amendi.dev/api/v1") {
    window.localStorage.removeItem(API_BASE_KEY);
    return;
  }
  window.localStorage.setItem(API_BASE_KEY, trimmed);
}

export function authToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function currentUserLabel(): string {
  if (typeof window === "undefined") return "operator";
  const raw = window.localStorage.getItem(USER_KEY);
  if (!raw) return "operator";
  try {
    const user = JSON.parse(raw) as LoginResponse["user"];
    return user.display_name || user.email || "operator";
  } catch {
    return "operator";
  }
}

export async function loginToCloud(email: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${apiBase()}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  if (!response.ok) {
    throw new Error(response.status === 401 ? "Email or password incorrect" : `Login failed (${response.status})`);
  }
  const body = (await response.json()) as LoginResponse;
  window.localStorage.setItem(TOKEN_KEY, body.access_token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(body.user));
  window.localStorage.removeItem("solamon-demo-auth");
  return body;
}

export async function loadDashboardSnapshot(slug: string, preferredDeviceId?: string): Promise<DashboardSnapshot> {
  const token = authToken();
  if (!token) {
    throw new Error("No cloud token yet");
  }
  const site = await apiFetch<SiteDetail>(`/sites/${slug}`, token);
  const device = chooseDevice(site.devices, preferredDeviceId);
  if (!device) {
    throw new Error(`Site ${slug} has no devices`);
  }

  const [snapshot, series] = await Promise.all([
    apiFetch<DeviceSnapshot>(`/sites/${slug}/devices/${device.id}/snapshot`, token),
    loadPowerSeries(slug, device.id, token, 24)
  ]);

  return mapCloudSnapshot(site, device, snapshot, series);
}

function chooseDevice(devices: DeviceSummary[], preferredDeviceId?: string): DeviceSummary | undefined {
  if (preferredDeviceId) {
    const preferred = devices.find((device) => device.id === preferredDeviceId);
    if (preferred) return preferred;
  }

  const online = devices
    .filter((device) => device.status === "online")
    .sort((a, b) => timestamp(b.last_seen_at) - timestamp(a.last_seen_at))[0];
  if (online) return online;

  return [...devices].sort((a, b) => timestamp(b.last_seen_at) - timestamp(a.last_seen_at))[0];
}

async function loadPowerSeries(
  slug: string,
  deviceId: string,
  token: string,
  hoursBack: number
): Promise<ReadingPoint[]> {
  const to = new Date();
  const from = new Date(to.getTime() - hoursBack * 60 * 60 * 1000);
  const query = new URLSearchParams({
    metric: "active_power_total",
    from: from.toISOString(),
    to: to.toISOString(),
    aggregate: "raw"
  });
  const response = await apiFetch<ReadingSeries>(`/sites/${slug}/devices/${deviceId}/readings?${query}`, token);
  if (response.points.length === 0) return [];
  return response.points.map((point) => ({
    t: new Date(point.time).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" }),
    kw: point.value ?? 0,
    iso: point.time
  }));
}

async function apiFetch<T>(path: string, token: string): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`${path} failed (${response.status})`);
  }
  return (await response.json()) as T;
}

function mapCloudSnapshot(
  site: SiteDetail,
  device: DeviceSummary,
  snapshot: DeviceSnapshot,
  series: ReadingPoint[]
): DashboardSnapshot {
  const m = snapshot.metrics ?? {};
  const realSeries = appendSnapshotPoint(series, pointFromSnapshot(m, snapshot.snapshot_time));
  return {
    site: {
      name: site.name,
      slug: site.slug,
      deviceName: [device.manufacturer, device.model].filter(Boolean).join(" ") || device.name,
      deviceId: device.id,
      location: `${device.host}:${device.port} unit ${device.unit_id}`,
      devices: site.devices.map(deviceOption)
    },
    metrics: {
      activePowerKw: num(m.active_power_total, 0),
      importKwhToday: num(m.import_active_energy_kwh, 0),
      exportKwhToday: num(m.export_active_energy_kwh, 0),
      demandKw: num(m.active_power_demand, num(m.active_power_total, 0)),
      demandPeakKw: num(m.active_power_demand_max, 0),
      demandPeakAt: timeLabel(m.active_power_demand_max_timestamp),
      demandWindowMinutes: num(m.demand_window_minutes, 15),
      frequencyHz: num(m.frequency_hz, 0),
      voltageUnbalancePct: num(m.voltage_unbalance_pct, 0),
      currentUnbalancePct: num(m.current_unbalance_pct, 0),
      thdVoltagePct: [num(m.thd_voltage_l1, 0), num(m.thd_voltage_l2, 0), num(m.thd_voltage_l3, 0)],
      thdCurrentPct: [num(m.thd_current_l1, 0), num(m.thd_current_l2, 0), num(m.thd_current_l3, 0)],
      voltages: [num(m.voltage_l1_n, 0), num(m.voltage_l2_n, 0), num(m.voltage_l3_n, 0)],
      currents: [num(m.current_l1, 0), num(m.current_l2, 0), num(m.current_l3, 0)],
      activePowerPhasesKw: [num(m.active_power_l1, 0), num(m.active_power_l2, 0), num(m.active_power_l3, 0)],
      powerFactor: [
        num(m.power_factor_l1, 0),
        num(m.power_factor_l2, 0),
        num(m.power_factor_l3, 0),
        num(m.power_factor_total, 0)
      ],
      edgeHeartbeatAgeSec: site.health?.heartbeat_age_seconds ?? ageSeconds(site.last_seen_at),
      modbusErrorsPerMin: site.health?.modbus_errors_per_minute ?? 0,
      bufferDepthSec: site.health?.edge_buffer_depth_seconds ?? 0,
      haltedBlocks: Array.isArray(m.halted_blocks) ? m.halted_blocks.map(String) : []
    },
    series: realSeries
  };
}

function deviceOption(device: DeviceSummary): DeviceOption {
  const makeModel = [device.manufacturer, device.model].filter(Boolean).join(" ");
  const label = makeModel ? `${device.name} (${makeModel})` : device.name;
  return {
    id: device.id,
    name: device.name,
    label,
    status: device.status,
    lastSeenAt: device.last_seen_at ?? null
  };
}

function pointFromSnapshot(metrics: Record<string, unknown>, snapshotTime?: string): ReadingPoint {
  const value = num(metrics.active_power_total, 0);
  const iso = validIso(snapshotTime) ? snapshotTime! : new Date().toISOString();
  return {
    t: new Date(iso).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" }),
    kw: value,
    iso
  };
}

function appendSnapshotPoint(series: ReadingPoint[], snapshotPoint: ReadingPoint): ReadingPoint[] {
  const sorted = [...series]
    .filter((point) => Number.isFinite(point.kw))
    .sort((a, b) => timestamp(a.iso) - timestamp(b.iso));
  if (sorted.length === 0) return [snapshotPoint];

  const last = sorted[sorted.length - 1];
  const lastTime = timestamp(last.iso);
  const snapshotTime = timestamp(snapshotPoint.iso);
  if (!lastTime || !snapshotTime) return [...sorted, snapshotPoint];

  const secondsApart = Math.abs(snapshotTime - lastTime) / 1000;
  if (secondsApart <= 10) {
    return [...sorted.slice(0, -1), snapshotPoint];
  }
  if (snapshotTime > lastTime) {
    return [...sorted, snapshotPoint];
  }
  return sorted;
}

function num(value: unknown, fallback: number): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function timeLabel(value: unknown): string {
  if (typeof value !== "string" || !value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" });
}

function ageSeconds(value?: string | null): number {
  if (!value) return 0;
  const time = timestamp(value);
  return time ? Math.max(0, Math.round((Date.now() - time) / 1000)) : 0;
}

function timestamp(value?: string | null): number {
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function validIso(value?: string): boolean {
  return Boolean(value && !Number.isNaN(new Date(value).getTime()));
}
