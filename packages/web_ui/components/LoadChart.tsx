"use client";

import { useMemo, useState, type MouseEvent } from "react";
import type { ReadingPoint } from "@/lib/fixtures";

type ChartPoint = {
  x: number;
  y: number;
  label: string;
  kw: number;
  iso?: string;
};

export function LoadChart({
  data,
  averageKw,
  peakKw
}: {
  data: ReadingPoint[];
  averageKw?: number;
  peakKw?: number;
}) {
  const [hoverX, setHoverX] = useState<number | null>(null);
  const width = 900;
  const height = 350;
  const padLeft = 54;
  const padRight = 26;
  const padTop = 42;
  const padBottom = 48;
  const safeData = data.length > 0 ? data : [{ t: "now", kw: 0 }];
  const values = safeData.map((d) => d.kw);
  const min = Math.min(0, Math.min(...values) * 0.9);
  const max = Math.max(...values, averageKw ?? 0, peakKw ?? 0) * 1.12;
  const range = Math.max(max - min, 1);
  const chartWidth = width - padLeft - padRight;
  const chartHeight = height - padTop - padBottom;
  const pointList = useMemo(() => safeData.map((d, i) => {
    const x = padLeft + (i / Math.max(safeData.length - 1, 1)) * chartWidth;
    const y = padTop + (1 - (d.kw - min) / range) * chartHeight;
    return { x, y, label: d.t, kw: d.kw, iso: d.iso };
  }), [safeData, chartWidth, chartHeight, max, min, range]);
  const linePath = smoothPath(pointList);
  const baselineY = height - padBottom;
  const areaPath = `${linePath} L ${pointList.at(-1)?.x ?? padLeft} ${baselineY} L ${padLeft} ${baselineY} Z`;
  const yFor = (kw: number) => padTop + (1 - (kw - min) / range) * chartHeight;
  const averageY = typeof averageKw === "number" ? yFor(averageKw) : null;
  const peakY = typeof peakKw === "number" ? yFor(peakKw) : null;
  const peakPoint = pointList.reduce((best, point) => (point.kw > best.kw ? point : best), pointList[0]);
  const lastPoint = pointList[pointList.length - 1];
  const activePoint = nearestPoint(pointList, hoverX) ?? lastPoint;
  const tooltipWidth = 142;
  const tooltipX = Math.min(width - padRight - tooltipWidth, Math.max(padLeft + 6, activePoint.x + 12));
  const tooltipY = Math.min(baselineY - 76, Math.max(padTop + 8, activePoint.y - 68));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const kw = min + (1 - ratio) * range;
    return {
      y: padTop + ratio * chartHeight,
      label: `${Math.round(kw)}`
    };
  });
  const xLabels = pointList.filter((_, i) => {
    if (safeData.length <= 8) return true;
    return i % Math.ceil(safeData.length / 6) === 0 || i === safeData.length - 1;
  });

  function onPointerMove(event: MouseEvent<SVGSVGElement>) {
    const svg = event.currentTarget;
    const bounds = svg.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    setHoverX(Math.max(padLeft, Math.min(width - padRight, x)));
  }

  return (
    <svg
      className="chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Load profile chart"
      onMouseMove={onPointerMove}
      onMouseLeave={() => setHoverX(null)}
    >
      <defs>
        <linearGradient id="loadAreaGradient" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="oklch(79% 0.15 145)" stopOpacity="0.55" />
          <stop offset="72%" stopColor="oklch(94% 0.06 145)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="oklch(100% 0 0)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="loadStrokeGradient" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="oklch(58% 0.16 240)" />
          <stop offset="48%" stopColor="oklch(58% 0.16 145)" />
          <stop offset="100%" stopColor="oklch(72% 0.16 80)" />
        </linearGradient>
        <filter id="loadGlow" x="-10%" y="-50%" width="120%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect className="chart-plot" x={padLeft} y={padTop} width={chartWidth} height={chartHeight} rx="5" />
      {ticks.map((tick) => (
        <g key={tick.y}>
          <line className="chart-grid-line" x1={padLeft} x2={width - padRight} y1={tick.y} y2={tick.y} />
          <text className="chart-axis-label" x={padLeft - 10} y={tick.y + 4} textAnchor="end">{tick.label}</text>
        </g>
      ))}
      <text className="chart-axis-unit" x={padLeft - 10} y={18} textAnchor="end">kW</text>
      <g className="chart-header">
        <text x={padLeft} y="20">Active power trace</text>
        <text x={width - padRight} y="20" textAnchor="end">
          {safeData.length.toLocaleString("en-ZA")} samples
        </text>
      </g>
      {peakY !== null ? (
        <>
          <line className="chart-threshold peak" x1={padLeft} x2={width - padRight} y1={peakY} y2={peakY} />
          <text className="chart-threshold-label peak" x={width - padRight - 8} y={Math.max(padTop + 12, peakY - 9)} textAnchor="end">peak {Math.round(peakKw!)} kW</text>
        </>
      ) : null}
      {averageY !== null ? (
        <>
          <line className="chart-threshold average" x1={padLeft} x2={width - padRight} y1={averageY} y2={averageY} />
          <text className="chart-threshold-label average" x={width - padRight - 8} y={Math.min(height - 48, averageY + 18)} textAnchor="end">avg {Math.round(averageKw!)} kW</text>
        </>
      ) : null}
      <path d={areaPath} fill="url(#loadAreaGradient)" />
      <path className="chart-line glow" d={linePath} />
      <path className="chart-line" d={linePath} />
      {pointList.map((point, i) => {
        const isPeak = point === peakPoint;
        const isLast = point === lastPoint;
        const isVisible = isPeak || isLast || safeData.length <= 14 || i % Math.ceil(safeData.length / 10) === 0;
        if (!isVisible) return null;
        return (
          <g className={`chart-point ${isPeak ? "peak" : ""} ${isLast ? "latest" : ""}`} key={`${point.label}-${i}`}>
            <title>{`${point.label}: ${Math.round(point.kw)} kW`}</title>
            <circle cx={point.x} cy={point.y} r={isPeak || isLast ? 5 : 3.5} />
          </g>
        );
      })}
      {peakPoint && peakPoint !== lastPoint ? (
        <g className="chart-callout peak-callout">
          <line x1={peakPoint.x} x2={peakPoint.x} y1={peakPoint.y + 8} y2={baselineY} />
          <text x={Math.min(width - 148, Math.max(padLeft + 18, peakPoint.x + 10))} y={Math.max(padTop + 20, peakPoint.y - 14)}>
            measured peak
          </text>
        </g>
      ) : null}
      {lastPoint ? (
        <g className="chart-callout latest-callout">
          <text x={Math.min(width - 88, lastPoint.x - 34)} y={Math.max(padTop + 18, lastPoint.y - 14)}>
            live now
          </text>
        </g>
      ) : null}
      {activePoint ? (
        <g className="chart-crosshair">
          <line x1={activePoint.x} x2={activePoint.x} y1={padTop} y2={baselineY} />
          <line x1={padLeft} x2={width - padRight} y1={activePoint.y} y2={activePoint.y} />
          <circle cx={activePoint.x} cy={activePoint.y} r="6" />
          <g className="chart-tooltip" transform={`translate(${tooltipX} ${tooltipY})`}>
            <rect width={tooltipWidth} height="56" rx="6" />
            <text x="10" y="20">{activePoint.label}</text>
            <text x="10" y="42">{formatKw(activePoint.kw)} kW</text>
          </g>
        </g>
      ) : null}
      {xLabels.map((point, i) => (
        <text className="chart-x-label" key={`${point.label}-${i}`} x={point.x} y={height - 12} textAnchor="middle">
          {point.label}
        </text>
      ))}
    </svg>
  );
}

function nearestPoint(points: ChartPoint[], x: number | null): ChartPoint | null {
  if (x === null || points.length === 0) return null;
  return points.reduce((best, point) => (
    Math.abs(point.x - x) < Math.abs(best.x - x) ? point : best
  ), points[0]);
}

function formatKw(value: number): string {
  return value.toLocaleString("en-ZA", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1
  });
}

function smoothPath(points: ChartPoint[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

  const commands = [`M ${points[0].x} ${points[0].y}`];
  for (let i = 0; i < points.length - 1; i += 1) {
    const current = points[i];
    const next = points[i + 1];
    const previous = points[i - 1] ?? current;
    const afterNext = points[i + 2] ?? next;
    const cp1x = current.x + (next.x - previous.x) / 6;
    const cp1y = current.y + (next.y - previous.y) / 6;
    const cp2x = next.x - (afterNext.x - current.x) / 6;
    const cp2y = next.y - (afterNext.y - current.y) / 6;
    commands.push(`C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${next.x} ${next.y}`);
  }
  return commands.join(" ");
}
