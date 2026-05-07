import type { ReadingPoint } from "@/lib/fixtures";

export function LoadChart({ data }: { data: ReadingPoint[] }) {
  const width = 900;
  const height = 260;
  const padX = 36;
  const padY = 24;
  const values = data.map((d) => d.kw);
  const min = Math.min(...values) * 0.92;
  const max = Math.max(...values) * 1.08;
  const range = Math.max(max - min, 1);
  const points = data
    .map((d, i) => {
      const x = padX + (i / Math.max(data.length - 1, 1)) * (width - padX * 2);
      const y = padY + (1 - (d.kw - min) / range) * (height - padY * 2);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Load profile chart">
      {[0, 1, 2, 3].map((n) => (
        <line key={n} x1={padX} x2={width - padX} y1={padY + n * 62} y2={padY + n * 62} stroke="#e2e8f0" />
      ))}
      <polyline points={points} fill="none" stroke="#0a1f44" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => {
        const x = padX + (i / Math.max(data.length - 1, 1)) * (width - padX * 2);
        return (
          <text key={d.t + i} x={x} y={height - 4} textAnchor="middle" fontSize="22" fill="#687386">
            {d.t}
          </text>
        );
      })}
    </svg>
  );
}
