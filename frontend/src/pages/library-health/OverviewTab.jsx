import { useState, useEffect } from "react";
import { Activity, Film, Tv, TrendingDown, Skull, HeartPulse, Loader2 } from "lucide-react";
import { api } from "../../api.js";

function ZoneBar({ zones, total }) {
  if (!total) return null;
  const pcts = {
    healthy: ((zones?.healthy || 0) / total * 100).toFixed(1),
    sunset: ((zones?.sunset || 0) / total * 100).toFixed(1),
    dead: ((zones?.dead || 0) / total * 100).toFixed(1),
  };
  return (
    <div className="lh-zone-bar">
      {pcts.healthy > 0 && <div className="lh-zone-seg healthy" style={{ width: `${pcts.healthy}%` }} title={`Healthy: ${zones.healthy}`} />}
      {pcts.sunset > 0 && <div className="lh-zone-seg sunset" style={{ width: `${pcts.sunset}%` }} title={`Sunset: ${zones.sunset}`} />}
      {pcts.dead > 0 && <div className="lh-zone-seg dead" style={{ width: `${pcts.dead}%` }} title={`Dead: ${zones.dead}`} />}
    </div>
  );
}

function ScoreDistribution({ stats }) {
  const buckets = stats?.score_distribution || [];
  if (!buckets.length) return null;
  const max = Math.max(...buckets.map(b => b.count), 1);
  return (
    <div className="lh-distribution">
      <h4><Activity size={14} /> Score Distribution</h4>
      <div className="lh-dist-chart">
        {buckets.map((b, i) => (
          <div key={i} className="lh-dist-col" title={`${b.range}: ${b.count} items`}>
            <div className="lh-dist-fill" style={{ height: `${(b.count / max) * 100}%`, background: b.count > 0 ? `hsl(${(b.min_score / 100) * 120}, 70%, 50%)` : "var(--border)" }} />
            <span className="lh-dist-label">{b.range}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function OverviewTab({ stats, onRefresh }) {
  const zones = stats?.zones || {};
  const total = stats?.total_items || 0;
  const scored = stats?.scored_items || 0;
  const avgScore = stats?.avg_score != null ? stats.avg_score.toFixed(1) : "—";
  const lastRun = stats?.last_scored_at;

  return (
    <div className="lh-overview">
      <div className="admin-grid" style={{ marginBottom: 20 }}>
        <div className="admin-card">
          <h4><HeartPulse size={15} /> Healthy</h4>
          <div className="lh-stat-value healthy-text">{zones.healthy || 0}</div>
          <div className="lh-stat-sub">score ≥ 40</div>
        </div>
        <div className="admin-card">
          <h4><TrendingDown size={15} /> Sunset Zone</h4>
          <div className="lh-stat-value sunset-text">{zones.sunset || 0}</div>
          <div className="lh-stat-sub">score 15–39</div>
        </div>
        <div className="admin-card">
          <h4><Skull size={15} /> Dead</h4>
          <div className="lh-stat-value dead-text">{zones.dead || 0}</div>
          <div className="lh-stat-sub">score &lt; 15</div>
        </div>
        <div className="admin-card">
          <h4><Activity size={15} /> Average</h4>
          <div className="lh-stat-value">{avgScore}</div>
          <div className="lh-stat-sub">{scored}/{total} scored</div>
        </div>
      </div>

      <ZoneBar zones={zones} total={total} />

      <ScoreDistribution stats={stats} />

      {lastRun && (
        <div className="lh-last-run">Last scored: {new Date(lastRun).toLocaleString()}</div>
      )}
    </div>
  );
}

export default OverviewTab;
