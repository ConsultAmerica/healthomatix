"use client";

import type { TrendPoint, TrendSeries } from "@/lib/fhir";

type Props = {
  series: TrendSeries;
  selectedId?: string | null;
  onSelect?: (point: TrendPoint) => void;
};

function formatTickDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "2-digit" });
}

function formatValue(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function TrendChart({ series, selectedId, onSelect }: Props) {
  const points = series.points;
  const width = 640;
  const height = 280;
  const pad = { top: 28, right: 24, bottom: 44, left: 52 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  if (!points.length) {
    return <p className="muted">No verified results for this test yet.</p>;
  }

  const values = points.map((p) => p.value);
  const refLow = series.reference_low ?? null;
  const refHigh = series.reference_high ?? null;
  const extras = [refLow, refHigh].filter((v): v is number => v != null);
  const minV = Math.min(...values, ...extras);
  const maxV = Math.max(...values, ...extras);
  const span = maxV - minV || 1;
  const yMin = minV - span * 0.15;
  const yMax = maxV + span * 0.15;

  const xAt = (index: number) =>
    pad.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW);
  const yAt = (value: number) => pad.top + ((yMax - value) / (yMax - yMin)) * innerH;

  const line = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(1)} ${yAt(p.value).toFixed(1)}`)
    .join(" ");

  const area =
    points.length > 1
      ? `${line} L ${xAt(points.length - 1).toFixed(1)} ${pad.top + innerH} L ${xAt(0).toFixed(1)} ${pad.top + innerH} Z`
      : "";

  const yTicks = [yMin, (yMin + yMax) / 2, yMax];
  const xLabelIndexes = new Set(
    points.length <= 4
      ? points.map((_, i) => i)
      : [0, Math.floor((points.length - 1) / 2), points.length - 1],
  );
  if (selectedId) {
    const selectedIndex = points.findIndex((p) => p.observation_id === selectedId);
    if (selectedIndex >= 0) xLabelIndexes.add(selectedIndex);
  }

  return (
    <div className="trend-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${series.test_label} over time in ${series.unit}`}
      >
        <defs>
          <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.18" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </linearGradient>
        </defs>

        {refLow != null && refHigh != null ? (
          <rect
            className="trend-ref-band"
            x={pad.left}
            y={yAt(refHigh)}
            width={innerW}
            height={Math.max(1, yAt(refLow) - yAt(refHigh))}
          />
        ) : null}

        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              className="trend-grid"
              x1={pad.left}
              x2={pad.left + innerW}
              y1={yAt(tick)}
              y2={yAt(tick)}
            />
            <text className="trend-axis" x={pad.left - 8} y={yAt(tick) + 4} textAnchor="end">
              {formatValue(tick)}
            </text>
          </g>
        ))}

        {area ? <path className="trend-area" d={area} /> : null}
        <path className="trend-line" d={line} fill="none" />

        {points.map((point, index) => {
          const selected = selectedId === point.observation_id;
          const outOfRange = point.in_range === false;
          const className = [
            "trend-point",
            selected ? "is-selected" : "",
            outOfRange ? "is-out-of-range" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <g key={point.observation_id}>
              <circle
                className={className}
                cx={xAt(index)}
                cy={yAt(point.value)}
                r={selected ? 6.5 : 5}
                role="button"
                tabIndex={0}
                aria-label={`${point.value} ${point.unit} on ${formatTickDate(point.effective_at)}${
                  outOfRange ? ", outside reference range" : ""
                }`}
                onClick={() => onSelect?.(point)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect?.(point);
                  }
                }}
              />
              {xLabelIndexes.has(index) ? (
                <text className="trend-axis" x={xAt(index)} y={height - 14} textAnchor="middle">
                  {formatTickDate(point.effective_at)}
                </text>
              ) : null}
            </g>
          );
        })}

        {refLow != null && refHigh != null ? (
          <text className="trend-ref-label" x={pad.left + 6} y={Math.max(14, yAt(refHigh) - 6)}>
            Reference {formatValue(refLow)}–{formatValue(refHigh)} {series.unit}
          </text>
        ) : null}
      </svg>
    </div>
  );
}
