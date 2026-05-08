export type ReadingPoint = {
  t: string;
  kw: number;
};

export type DashboardSnapshot = {
  site: {
    name: string;
    slug: string;
    deviceName: string;
    deviceId: string;
    location: string;
  };
  metrics: {
    activePowerKw: number;
    importKwhToday: number;
    exportKwhToday: number;
    demandKw: number;
    demandPeakKw: number;
    demandPeakAt: string;
    demandWindowMinutes: number;
    frequencyHz: number;
    voltageUnbalancePct: number;
    currentUnbalancePct: number;
    thdVoltagePct: number[];
    thdCurrentPct: number[];
    voltages: number[];
    currents: number[];
    activePowerPhasesKw: number[];
    powerFactor: number[];
    edgeHeartbeatAgeSec: number;
    modbusErrorsPerMin: number;
    bufferDepthSec: number;
    haltedBlocks: string[];
  };
  series: ReadingPoint[];
};

export const fixture: DashboardSnapshot = {
  site: {
    name: "Bench Load Assessment",
    slug: "bench",
    deviceName: "Acuvim L revenue meter",
    deviceId: "bench-acuvim-l-01",
    location: "Johan workbench"
  },
  metrics: {
    activePowerKw: 286.4,
    importKwhToday: 1842.7,
    exportKwhToday: 312.8,
    demandKw: 271.9,
    demandPeakKw: 318.6,
    demandPeakAt: "14:23",
    demandWindowMinutes: 15,
    frequencyHz: 50.02,
    voltageUnbalancePct: 1.4,
    currentUnbalancePct: 3.8,
    thdVoltagePct: [2.1, 2.3, 2.0],
    thdCurrentPct: [7.6, 8.1, 6.8],
    voltages: [230.8, 229.4, 231.2],
    currents: [418.2, 393.7, 428.5],
    activePowerPhasesKw: [96.2, 91.1, 99.1],
    powerFactor: [0.94, 0.92, 0.95, 0.94],
    edgeHeartbeatAgeSec: 7,
    modbusErrorsPerMin: 0.2,
    bufferDepthSec: 0,
    haltedBlocks: []
  },
  series: [
    { t: "08:00", kw: 118 },
    { t: "09:00", kw: 156 },
    { t: "10:00", kw: 211 },
    { t: "11:00", kw: 247 },
    { t: "12:00", kw: 262 },
    { t: "13:00", kw: 301 },
    { t: "14:00", kw: 318 },
    { t: "15:00", kw: 286 },
    { t: "16:00", kw: 244 },
    { t: "17:00", kw: 181 }
  ]
};

export function jitterSnapshot(base: DashboardSnapshot, tick: number): DashboardSnapshot {
  const wave = Math.sin(tick / 4);
  const small = Math.cos(tick / 5);
  const activePowerKw = round1(base.metrics.activePowerKw + wave * 8.2 + small * 2.1);
  const demandKw = round1(base.metrics.demandKw + wave * 3.4);
  const frequencyHz = round2(base.metrics.frequencyHz + Math.sin(tick / 8) * 0.03);

  return {
    ...base,
    metrics: {
      ...base.metrics,
      activePowerKw,
      demandKw,
      frequencyHz,
      edgeHeartbeatAgeSec: tick % 11,
      voltages: base.metrics.voltages.map((v, i) => round1(v + Math.sin(tick / 6 + i) * 0.8)),
      currents: base.metrics.currents.map((v, i) => round1(v + Math.cos(tick / 5 + i) * 7.5)),
      activePowerPhasesKw: base.metrics.activePowerPhasesKw.map((v, i) => round1(v + Math.sin(tick / 4 + i) * 3.2))
    },
    series: [...base.series.slice(1), { t: "live", kw: activePowerKw }]
  };
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}
