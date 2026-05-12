import type { ReadingPoint } from "@/lib/fixtures";

export function LoadChart({ data }: { data: ReadingPoint[] }) {
  const width = 900;
  const height = 260;
  const padX = 36;
  const padY = 28;
  const safeData = data.length > 0 ? data : [{ t: "now", kw: 0 }];
  const values = safeData.map((d) => d.kw);
  const min = Math.min(0, Math.min(...values) * 0.92);
  const max = Math.max(...values) * 1.08;
  const range = Math.max(max - min, 1);
  const pointList = safeData.map((d, i) => {
    const x = padX + (i / Math.max(safeData.length - 1, 1)) * (width - padX * 2);
    const y = padY + (1 - (d.kw - min) / range) * (height - padY * 2);
    return { x, y, label: d.t };
  });
  const points = pointList
    .map((point) => `${point.x},${point.y}`)
    .join(" ");
  const area = `${padX},${height - padY} ${points} ${width - padX},${height - padY}`;

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Load profile chart">
      {[0, 1, 2, 3, 4].map((n) => (
        <line key={n} x1={padX} x2={width - padX} y1={padY + n * 46} y2={padY + n * 46} stroke="oklch(90% 0.008 240)" />
      ))}
      <polygon points={area} fill="oklch(94% 0.06 145)" opacity="0.7" />
      <polyline points={points} fill="none" stroke="oklch(58% 0.16 145)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      {pointList.map((point, i) => {
        if (safeData.length > 12 && i % Math.ceil(safeData.length / 8) !== 0 && i !== safeData.length - 1) return null;
        return (
          <text key={point.label + i} x={point.x} y={height - 5} textAnchor="middle" fontSize="16" fill="oklch(50% 0.018 240)">
            {point.label}
          </text>
        );
      })}
      <text x={padX} y={16} fontSize="15" fill="oklch(50% 0.018 240)">{Math.round(max)} kW</text>
      <text x={padX} y={height - 34} fontSize="15" fill="oklch(50% 0.018 240)">0 kW</text>
    </svg>
  );
}
