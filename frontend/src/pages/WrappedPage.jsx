import { useState, useEffect, useCallback } from "react";
import { BarChart3, Clock, Activity, Film, Tv, Monitor } from "lucide-react";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";

function WrappedPage({ user }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [year, setYear] = useState(new Date().getFullYear());

  const load = useCallback(() => {
    if (!user?.username) return;
    setLoading(true);
    setError(null);
    api.wrapped(user.username, year)
      .then(d => setData(d))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user?.username, year]);

  useEffect(() => { load(); }, [load]);

  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - i);

  if (loading) return (
    <>
      <div className="page-header">
        <h2><BarChart3 size={22} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Plex Wrapped</h2>
      </div>
      <div className="page-body"><LoadingState message="Crunching your viewing stats..." /></div>
    </>
  );

  if (error) return (
    <>
      <div className="page-header"><h2>Plex Wrapped</h2></div>
      <div className="page-body"><ErrorState message={error} onRetry={load} /></div>
    </>
  );

  if (!data || data.empty) return (
    <>
      <div className="page-header">
        <h2>Plex Wrapped</h2>
        <YearSelector year={year} options={yearOptions} onChange={setYear} />
      </div>
      <div className="page-body"><EmptyState icon={BarChart3} title="No viewing data" message={`No watch history found for ${year}.`} /></div>
    </>
  );

  const s = data.summary;
  const peak = data.peak;
  const charts = data.charts;

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2><BarChart3 size={22} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Plex Wrapped {year}</h2>
          <YearSelector year={year} options={yearOptions} onChange={setYear} />
        </div>
        <p>Your viewing journey in numbers</p>
      </div>
      <div className="page-body">
        {/* Hero stats */}
        <div className="wrapped-hero">
          <div className="wrapped-stat-card hero">
            <div className="wrapped-stat-value">{s.total_hours.toLocaleString()}</div>
            <div className="wrapped-stat-label">Hours Watched</div>
            <div className="wrapped-stat-sub">That's {s.days_equivalent} full days of content</div>
          </div>
          <div className="wrapped-stat-card">
            <div className="wrapped-stat-value">{s.movies_watched}</div>
            <div className="wrapped-stat-label">Movies</div>
          </div>
          <div className="wrapped-stat-card">
            <div className="wrapped-stat-value">{s.shows_watched}</div>
            <div className="wrapped-stat-label">Shows</div>
            <div className="wrapped-stat-sub">{s.episodes_watched} episodes</div>
          </div>
          <div className="wrapped-stat-card">
            <div className="wrapped-stat-value">{s.avg_completion}%</div>
            <div className="wrapped-stat-label">Avg Completion</div>
          </div>
          <div className="wrapped-stat-card">
            <div className="wrapped-stat-value">{s.longest_streak_days}</div>
            <div className="wrapped-stat-label">Day Streak</div>
            <div className="wrapped-stat-sub">consecutive days</div>
          </div>
          <div className="wrapped-stat-card">
            <div className="wrapped-stat-value">{s.binge_sessions}</div>
            <div className="wrapped-stat-label">Binge Sessions</div>
            <div className="wrapped-stat-sub">3+ episodes in a row</div>
          </div>
        </div>

        {/* Peak times */}
        <div className="wrapped-insight-row">
          <div className="wrapped-insight">
            <Clock size={16} />
            <span>Peak hour: <strong>{peak.hour_label}</strong></span>
          </div>
          <div className="wrapped-insight">
            <Activity size={16} />
            <span>Most active day: <strong>{peak.day}</strong></span>
          </div>
          <div className="wrapped-insight">
            <Film size={16} />
            <span>~{s.feature_films_equivalent} feature films worth of content</span>
          </div>
        </div>

        {/* Monthly Activity */}
        <div className="wrapped-chart-section">
          <h3>Monthly Activity</h3>
          <div className="wrapped-chart" style={{ height: 220 }}>
            <WrappedBarChart data={charts.monthly} dataKey="hours" xKey="month" color="var(--accent)" label="hours" />
          </div>
        </div>

        {/* Hourly + Daily side by side */}
        <div className="wrapped-chart-row">
          <div className="wrapped-chart-section" style={{ flex: 1 }}>
            <h3>By Hour of Day</h3>
            <div className="wrapped-chart" style={{ height: 180 }}>
              <WrappedBarChart data={charts.hourly} dataKey="plays" xKey="hour" color="#6366f1" />
            </div>
          </div>
          <div className="wrapped-chart-section" style={{ flex: 1 }}>
            <h3>By Day of Week</h3>
            <div className="wrapped-chart" style={{ height: 180 }}>
              <WrappedBarChart data={charts.daily} dataKey="plays" xKey="day" color="#8b5cf6" />
            </div>
          </div>
        </div>

        {/* Genre Breakdown */}
        {charts.genres.length > 0 && (
          <div className="wrapped-chart-section">
            <h3>Top Genres</h3>
            <div className="wrapped-genre-bars">
              {charts.genres.map((g, i) => {
                const maxCount = charts.genres[0].count;
                const pct = (g.count / maxCount) * 100;
                return (
                  <div key={g.genre} className="wrapped-genre-row">
                    <span className="wrapped-genre-name">{g.genre}</span>
                    <div className="wrapped-genre-bar-track">
                      <div className="wrapped-genre-bar-fill" style={{ width: `${pct}%`, opacity: 1 - (i * 0.06) }} />
                    </div>
                    <span className="wrapped-genre-count">{g.count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Top Movies */}
        {/* Top Movies + Shows side by side */}
        <div className="wrapped-chart-row">
          {data.top_movies.length > 0 && (
            <div className="wrapped-chart-section" style={{ flex: 1 }}>
              <h3><Film size={16} style={{ verticalAlign: "text-bottom", marginRight: 4 }} />Most Watched Movies</h3>
              <div className="wrapped-top-list">
                {data.top_movies.slice(0, 5).map((m, i) => (
                  <div key={i} className="wrapped-top-item">
                    <span className="wrapped-rank">#{i + 1}</span>
                    <div className="wrapped-top-info">
                      <span className="wrapped-top-title">{m.title}</span>
                      {m.year && <span className="wrapped-top-year">{m.year}</span>}
                    </div>
                    <span className="wrapped-top-plays">{m.plays}x</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {data.top_shows.length > 0 && (
            <div className="wrapped-chart-section" style={{ flex: 1 }}>
              <h3><Tv size={16} style={{ verticalAlign: "text-bottom", marginRight: 4 }} />Most Watched Shows</h3>
              <div className="wrapped-top-list">
                {data.top_shows.slice(0, 5).map((m, i) => (
                  <div key={i} className="wrapped-top-item">
                    <span className="wrapped-rank">#{i + 1}</span>
                    <div className="wrapped-top-info">
                      <span className="wrapped-top-title">{m.title}</span>
                      {m.year && <span className="wrapped-top-year">{m.year}</span>}
                    </div>
                    <span className="wrapped-top-plays">{m.plays} eps</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Platforms */}
        {charts.platforms && charts.platforms.length > 0 && (
          <div className="wrapped-chart-section">
            <h3><Monitor size={16} style={{ verticalAlign: "text-bottom", marginRight: 4 }} />Watching Platforms</h3>
            <div className="wrapped-genre-bars">
              {charts.platforms.map((p, i) => {
                const maxCount = charts.platforms[0].count;
                const pct = (p.count / maxCount) * 100;
                return (
                  <div key={p.platform} className="wrapped-genre-row">
                    <span className="wrapped-genre-name">{p.platform}</span>
                    <div className="wrapped-genre-bar-track">
                      <div className="wrapped-genre-bar-fill" style={{ width: `${pct}%`, background: "#8b5cf6", opacity: 1 - (i * 0.12) }} />
                    </div>
                    <span className="wrapped-genre-count">{p.count}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function YearSelector({ year, options, onChange }) {
  return (
    <select className="wrapped-year-select" value={year} onChange={e => onChange(parseInt(e.target.value))}>
      {options.map(y => <option key={y} value={y}>{y}</option>)}
    </select>
  );
}

function WrappedBarChart({ data, dataKey, xKey, color, label }) {
  // Simple SVG bar chart — no external dependency needed
  if (!data || data.length === 0) return null;
  const maxVal = Math.max(...data.map(d => d[dataKey]), 1);
  const barWidth = Math.max(100 / data.length - 1, 2);

  return (
    <svg viewBox={`0 0 ${data.length * (barWidth + 1)} 100`} preserveAspectRatio="none" style={{ width: "100%", height: "100%" }}>
      {data.map((d, i) => {
        const h = (d[dataKey] / maxVal) * 85;
        return (
          <g key={i}>
            <rect
              x={i * (barWidth + 1)}
              y={100 - h}
              width={barWidth}
              height={h}
              fill={color}
              rx={1}
              opacity={0.85}
            >
              <title>{d[xKey]}: {d[dataKey]} {label || ""}</title>
            </rect>
          </g>
        );
      })}
    </svg>
  );
}

export default WrappedPage;
