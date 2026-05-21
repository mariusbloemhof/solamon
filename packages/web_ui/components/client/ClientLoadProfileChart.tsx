import type { ReadingPoint } from "@/lib/fixtures";
import { fmt } from "@/lib/format";

type ChartStats = {
  peak: ReadingPoint | null;
  averageKw: number;
  latest: ReadingPoint | null;
  samples: number;
};

export function loadStats(data: ReadingPoint[]): ChartStats {
  const usable = data.filter((point) => Number.isFinite(point.kw));
  const latest = usable.at(-1) ?? null;
  const peak = usable.reduce<ReadingPoint | null>(
    (best, point) => (!best || point.kw > best.kw ? point : best),
    null
  );
  const averageKw =
    usable.length > 0 ? usable.reduce((sum, point) => sum + point.kw, 0) / usable.length : 0;
  return { peak, averageKw, latest, samples: usable.length };
}

export function ClientLoadProfileChart({ data }: { data: ReadingPoint[] }) {
  const width = 1240;
  const height = 390;
  const pad = { top: 42, right: 42, bottom: 48, left: 58 };
  const stats = loadStats(data);
  const values = data.map((point) => point.kw).filter(Number.isFinite);
  const maxValue = Math.max(...values, 1);
  const max = Math.max(10, maxValue * 1.16);
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const xy = (point: ReadingPoint, index: number) => {
    const x = pad.left + (index / Math.max(data.length - 1, 1)) * plotW;
    const y = pad.top + (1 - Math.max(0, point.kw) / max) * plotH;
    return { x, y };
  };

  const line = data.map((point, index) => {
    const { x, y } = xy(point, index);
    return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const area = data.length
    ? `${line} L ${pad.left + plotW} ${pad.top + plotH} L ${pad.left} ${pad.top + plotH} Z`
    : "";
  const avgY = pad.top + (1 - stats.averageKw / max) * plotH;
  const peakIndex = stats.peak ? data.indexOf(stats.peak) : -1;
  const latestIndex = stats.latest ? data.indexOf(stats.latest) : -1;
  const peakXY = stats.peak && peakIndex >= 0 ? xy(stats.peak, peakIndex) : null;
  const latestXY = stats.latest && latestIndex >= 0 ? xy(stats.latest, latestIndex) : null;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
    value: max * (1 - ratio),
    y: pad.top + plotH * ratio
  }));
  const labels = labelPoints(data);

  return (
    <div className="client-chart-frame">
      <div className="client-chart-head">
        <div>
          <span className="client-kicker">kW active power trace</span>
          <h2>Load profile</h2>
        </div>
        <div className="client-chart-meta">
          <span>{stats.samples.toLocaleString("en-ZA")} samples</span>
          <span>24h live trace</span>
        </div>
      </div>
      {data.length === 0 ? (
        <div className="client-empty-chart">Waiting for active power readings.</div>
      ) : (
        <svg className="client-load-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="24 hour active power chart">
          <defs>
            <linearGradient id="clientLoadFill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="oklch(58% 0.16 145 / 0.22)" />
              <stop offset="100%" stopColor="oklch(58% 0.16 145 / 0.03)" />
            </linearGradient>
          </defs>
          <rect x={pad.left} y={pad.top} width={plotW} height={plotH} rx="4" className="client-chart-plot" />
          {ticks.map((tick) => (
            <g key={tick.y}>
              <line x1={pad.left} x2={pad.left + plotW} y1={tick.y} y2={tick.y} className="client-grid-line" />
              <text x={pad.left - 16} y={tick.y + 5} textAnchor="end" className="client-axis-label">
                {fmt(tick.value, 0)}
              </text>
            </g>
          ))}
          <line x1={pad.left} x2={pad.left + plotW} y1={avgY} y2={avgY} className="client-average-line" />
          <text x={pad.left + plotW - 8} y={avgY - 8} textAnchor="end" className="client-average-label">
            avg {fmt(stats.averageKw)} kW
          </text>
          <path d={area} className="client-area" />
          <path d={line} className="client-line" />
          {peakXY && stats.peak ? (
            <g>
              <line x1={peakXY.x} x2={peakXY.x} y1={pad.top} y2={pad.top + plotH} className="client-marker-line" />
              <circle cx={peakXY.x} cy={peakXY.y} r="8" className="client-peak-dot" />
              <text x={Math.min(peakXY.x + 14, pad.left + plotW - 130)} y={Math.max(peakXY.y - 14, pad.top + 18)} className="client-peak-label">
                Peak {fmt(stats.peak.kw)} kW
              </text>
            </g>
          ) : null}
          {latestXY && stats.latest ? (
            <g>
              <circle cx={latestXY.x} cy={latestXY.y} r="8" className="client-live-dot" />
              <text x={Math.max(latestXY.x - 84, pad.left + 8)} y={Math.max(latestXY.y - 14, pad.top + 18)} className="client-live-label">
                Live now
              </text>
            </g>
          ) : null}
          {labels.map((label) => (
            <text key={`${label.index}-${label.text}`} x={xy(data[label.index], label.index).x} y={height - 14} textAnchor="middle" className="client-axis-label">
              {label.text}
            </text>
          ))}
          <text x={pad.left - 38} y={pad.top - 16} className="client-axis-unit">kW</text>
        </svg>
      )}
    </div>
  );
}

function labelPoints(data: ReadingPoint[]): Array<{ index: number; text: string }> {
  if (data.length === 0) return [];
  const count = Math.min(6, data.length);
  const seen = new Set<number>();
  return Array.from({ length: count }, (_, i) => Math.round((i / Math.max(count - 1, 1)) * (data.length - 1)))
    .filter((index) => {
      if (seen.has(index)) return false;
      seen.add(index);
      return true;
    })
    .map((index) => ({ index, text: data[index].t }));
}
