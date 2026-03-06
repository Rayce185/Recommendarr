import { useState, useEffect, useCallback } from "react";
import { Users, TrendingUp, Heart, Loader2, Film } from "lucide-react";
import { api, authFetch, API_BASE } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";

function SocialPage({ user }) {
  const [overlaps, setOverlaps] = useState(null);
  const [serverStats, setServerStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [domain, setDomain] = useState("all");

  const load = useCallback(() => {
    if (!user?.username) return;
    setLoading(true);
    setError(null);
    Promise.all([
      authFetch(`${API_BASE}/users/${user.username}/taste-overlap?domain=${domain}`).then(r => r.json()),
      authFetch(`${API_BASE}/social/server-stats`).then(r => r.json()),
    ])
      .then(([ov, ss]) => { setOverlaps(ov); setServerStats(ss); })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user?.username, domain]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <><div className="page-header"><h2><Users size={22} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Social</h2></div><div className="page-body"><LoadingState message="Analyzing taste profiles across your server..." /></div></>;
  if (error) return <><div className="page-header"><h2>Social</h2></div><div className="page-body"><ErrorState message={error} onRetry={load} /></div></>;

  const ols = overlaps?.overlaps || [];
  const ss = serverStats || {};

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2><Users size={22} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Social</h2>
          <select className="wrapped-year-select" value={domain} onChange={e => setDomain(e.target.value)}>
            <option value="all">All Content</option>
            <option value="movies">Movies</option>
            <option value="tv">TV Shows</option>
            <option value="anime">Anime</option>
          </select>
        </div>
        <p>See who shares your taste and what's popular on the server</p>
      </div>
      <div className="page-body">
        {/* Server Overview */}
        {ss.total_users && (
          <div className="social-server-row">
            <div className="wrapped-stat-card">
              <div className="wrapped-stat-value">{ss.active_users}</div>
              <div className="wrapped-stat-label">Active Users</div>
              <div className="wrapped-stat-sub">of {ss.total_users} total</div>
            </div>
            <div className="wrapped-stat-card">
              <div className="wrapped-stat-value">{ss.recent_unique_viewers}</div>
              <div className="wrapped-stat-label">Recent Viewers</div>
              <div className="wrapped-stat-sub">last 100 plays</div>
            </div>
          </div>
        )}

        {/* Server Trending */}
        {ss.server_trending?.length > 0 && (
          <div className="wrapped-chart-section" style={{ marginBottom: 20 }}>
            <h3><TrendingUp size={16} style={{ verticalAlign: "text-bottom", marginRight: 4 }} />Server Trending</h3>
            <div className="wrapped-top-list">
              {ss.server_trending.slice(0, 8).map((t, i) => (
                <div key={i} className="wrapped-top-item">
                  <span className="wrapped-rank">#{i + 1}</span>
                  <div className="wrapped-top-info">
                    <span className="wrapped-top-title">{t.title}</span>
                  </div>
                  <span className="wrapped-top-plays">{t.plays} plays</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Taste Neighbors */}
        <div className="wrapped-chart-section">
          <h3><Heart size={16} style={{ verticalAlign: "text-bottom", marginRight: 4 }} />Taste Neighbors</h3>
          {ols.length === 0 ? (
            <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Not enough data to compute taste overlaps yet.</p>
          ) : (
            <div className="social-overlap-list">
              {ols.map((o, i) => (
                <div key={o.username} className="social-overlap-card">
                  <div className="social-overlap-header">
                    {o.thumb ? (
                      <img src={o.thumb} alt="" className="group-user-avatar" />
                    ) : (
                      <div className="group-user-avatar group-user-avatar-placeholder">
                        {(o.friendly_name || o.username).charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div className="social-overlap-info">
                      <span className="social-overlap-name">{o.friendly_name || o.username}</span>
                      <div className="social-overlap-bar-track">
                        <div
                          className="social-overlap-bar-fill"
                          style={{
                            width: `${o.overlap_pct}%`,
                            background: o.overlap_pct >= 80 ? "var(--green, #22c55e)" :
                                        o.overlap_pct >= 60 ? "var(--accent)" :
                                        o.overlap_pct >= 40 ? "var(--yellow, #eab308)" : "var(--text-muted)"
                          }}
                        />
                      </div>
                    </div>
                    <span className="social-overlap-pct" style={{
                      color: o.overlap_pct >= 80 ? "var(--green, #22c55e)" :
                             o.overlap_pct >= 60 ? "var(--accent)" :
                             o.overlap_pct >= 40 ? "var(--yellow, #eab308)" : "var(--text-muted)"
                    }}>{o.overlap_pct}%</span>
                  </div>
                  {o.shared_genres.length > 0 && (
                    <div className="social-overlap-genres">
                      {o.shared_genres.map(g => <span key={g} className="social-genre-chip shared">{g}</span>)}
                      {o.unique_to_them.map(g => <span key={g} className="social-genre-chip unique" title="They watch this, you don't">{g}</span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default SocialPage;
