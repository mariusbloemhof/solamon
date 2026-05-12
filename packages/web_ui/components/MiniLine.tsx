import type { ReadingPoint } from "@/lib/fixtures";

export function MiniLine({ data, height = 52 }: { data: ReadingPoint[]; height?: number }) {
  const width = 320;
  const pad = 8;
  const safeData = data.length > 0 ? data : [{ t: "now", kw: 0 }];
  const values = safeData.map((d) => d.kw);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const coords = safeData
    .map((d, i) => {
      const x = pad + (i / Math.max(safeData.length - 1, 1)) * (width - pad * 2);
      const y = pad + (1 - (d.kw - min) / range) * (height - pad * 2);
      return { x, y };
    });
  const points = coords.map((point) => `${point.x},${point.y}`).join(" ");
  const baseline = height - pad;
  const area = `${pad},${baseline} ${points} ${width - pad},${baseline}`;

  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Power trend">
      <defs>
        <linearGradient id="sparkAreaGradient" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="oklch(58% 0.16 145)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="oklch(58% 0.16 145)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={area} fill="url(#sparkAreaGradient)" stroke="none" />
      <polyline points={points} fill="none" stroke="oklch(58% 0.16 145)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {coords.at(-1) ? <circle className="spark-dot" cx={coords.at(-1)!.x} cy={coords.at(-1)!.y} r="4" /> : null}
    </svg>
  );
}
