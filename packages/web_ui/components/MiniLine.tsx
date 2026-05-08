import type { ReadingPoint } from "@/lib/fixtures";

export function MiniLine({ data, height = 52 }: { data: ReadingPoint[]; height?: number }) {
  const width = 320;
  const pad = 8;
  const values = data.map((d) => d.kw);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const points = data
    .map((d, i) => {
      const x = pad + (i / Math.max(data.length - 1, 1)) * (width - pad * 2);
      const y = pad + (1 - (d.kw - min) / range) * (height - pad * 2);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Power trend">
      <polyline points={points} fill="none" stroke="oklch(58% 0.16 145)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
