import { useMemo } from "react";

/**
 * Pure SVG radar (spider) chart for multi-user taste comparison.
 * No external chart library — full control over dark-theme styling.
 *
 * Props:
 *   axes:  string[]           — genre labels (one per spoke)
 *   users: { username, scores: number[], color }[]
 *   size:  number             — SVG width/height (default 400)
 */

const RINGS = 5;
const LABEL_PAD = 24;

const USER_COLORS = [
  "#e5a00d", // gold
  "#3b82f6", // blue
  "#22c55e", // green
  "#a855f7", // purple
  "#ef4444", // red
  "#06b6d4", // cyan
];

function polarToXY(cx, cy, r, angleDeg) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cx + r * Math.sin(rad) };
}

function TasteRadarChart({ axes = [], users = [], size = 400 }) {
  const n = axes.length;
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size / 2 - LABEL_PAD - 20;
  const angleStep = n > 0 ? 360 / n : 0;

  const spokePoints = useMemo(() => {
    return axes.map((_, i) => {
      const angle = i * angleStep;
      return polarToXY(cx, cy, maxR, angle);
    });
  }, [axes.length, cx, cy, maxR, angleStep]);

  const ringPolygons = useMemo(() => {
    return Array.from({ length: RINGS }, (_, ri) => {
      const r = maxR * ((ri + 1) / RINGS);
      const points = axes
        .map((_, i) => {
          const p = polarToXY(cx, cy, r, i * angleStep);
          return `${p.x},${p.y}`;
        })
        .join(" ");
      return points;
    });
  }, [axes.length, cx, cy, maxR, angleStep]);

  const userPolygons = useMemo(() => {
    return users.map((u, ui) => {
      const pts = (u.scores || []).map((s, i) => {
        const r = maxR * Math.max(0, Math.min(1, s));
        const p = polarToXY(cx, cy, r, i * angleStep);
        return `${p.x},${p.y}`;
      });
      return {
        points: pts.join(" "),
        color: u.color || USER_COLORS[ui % USER_COLORS.length],
        username: u.username,
      };
    });
  }, [users, cx, cy, maxR, angleStep]);

  if (n < 3) {
    return (
      <div className="radar-empty">
        Need at least 3 genre axes for radar chart
      </div>
    );
  }

  return (
    <div className="radar-chart-container">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width="100%"
        style={{ maxWidth: size }}
        className="radar-svg"
      >
        {/* Background rings */}
        {ringPolygons.map((pts, ri) => (
          <polygon
            key={`ring-${ri}`}
            points={pts}
            fill="none"
            stroke="var(--border)"
            strokeWidth={ri === RINGS - 1 ? 1.5 : 0.5}
            opacity={0.4}
          />
        ))}

        {/* Spokes */}
        {spokePoints.map((p, i) => (
          <line
            key={`spoke-${i}`}
            x1={cx}
            y1={cy}
            x2={p.x}
            y2={p.y}
            stroke="var(--border)"
            strokeWidth={0.5}
            opacity={0.3}
          />
        ))}

        {/* User polygons (filled, semi-transparent) */}
        {userPolygons.map((u, i) => (
          <polygon
            key={`area-${i}`}
            points={u.points}
            fill={u.color}
            fillOpacity={0.12}
            stroke={u.color}
            strokeWidth={2}
            strokeLinejoin="round"
          />
        ))}

        {/* Data points */}
        {users.map((u, ui) =>
          (u.scores || []).map((s, si) => {
            const r = maxR * Math.max(0, Math.min(1, s));
            const p = polarToXY(cx, cy, r, si * angleStep);
            const color =
              u.color || USER_COLORS[ui % USER_COLORS.length];
            return (
              <circle
                key={`dot-${ui}-${si}`}
                cx={p.x}
                cy={p.y}
                r={3}
                fill={color}
                stroke="var(--bg-primary)"
                strokeWidth={1}
              />
            );
          }),
        )}

        {/* Axis labels */}
        {axes.map((label, i) => {
          const p = polarToXY(cx, cy, maxR + LABEL_PAD, i * angleStep);
          const angle = i * angleStep;
          let anchor = "middle";
          if (angle > 10 && angle < 170) anchor = "start";
          else if (angle > 190 && angle < 350) anchor = "end";
          return (
            <text
              key={`label-${i}`}
              x={p.x}
              y={p.y}
              textAnchor={anchor}
              dominantBaseline="central"
              className="radar-label"
            >
              {label}
            </text>
          );
        })}
      </svg>

      {/* Legend */}
      {users.length > 1 && (
        <div className="radar-legend">
          {users.map((u, i) => (
            <div key={u.username} className="radar-legend-item">
              <span
                className="radar-legend-dot"
                style={{
                  background:
                    u.color || USER_COLORS[i % USER_COLORS.length],
                }}
              />
              <span className="radar-legend-name">{u.username}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export { USER_COLORS };
export default TasteRadarChart;
