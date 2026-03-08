import { useState, useEffect, useCallback } from "react";
import { Users, TrendingUp, Heart, Loader2, UserPlus } from "lucide-react";
import { authFetch, API_BASE } from "../api.js";
import { LoadingState, ErrorState } from "../components/StateDisplays.jsx";
import FriendsPanel from "../components/FriendsPanel.jsx";
import FriendActivityFeed from "../components/FriendActivityFeed.jsx";

function SocialPage({ user }) {
  const [tab, setTab] = useState("overview");
  const [overlaps, setOverlaps] = useState(null);
  const [serverStats, setServerStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [domain, setDomain] = useState("all");
  const [friendUsernames, setFriendUsernames] = useState(new Set());
  const [pendingUsernames, setPendingUsernames] = useState(new Set());
  const [sendingTo, setSendingTo] = useState(null);

  const loadOverview = useCallback(() => {
    if (!user?.username) return;
    setLoading(true);
    setError(null);
    Promise.all([
      authFetch(`${API_BASE}/users/${user.username}/taste-overlap?domain=${domain}`).then(r => r.json()),
      authFetch(`${API_BASE}/social/server-stats`).then(r => r.json()),
      authFetch(`${API_BASE}/friends`).then(r => r.json()),
      authFetch(`${API_BASE}/friends/pending`).then(r => r.json()),
    ])
      .then(([ov, ss, fr, pe]) => {
        setOverlaps(ov);
        setServerStats(ss);
        setFriendUsernames(new Set((fr.friends || []).map(f => f.username)));
        const allPending = [...(pe.incoming || []).map(p => p.username), ...(pe.outgoing || []).map(p => p.username)];
        setPendingUsernames(new Set(allPending));
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user?.username, domain]);

  useEffect(() => { if (tab === "overview") loadOverview(); }, [tab, loadOverview]);

  const sendFriendRequest = async (username) => {
    setSendingTo(username);
    try {
      const res = await authFetch(`${API_BASE}/friends/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username }),
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || "Failed to send request");
        return;
      }
      if (data.status === "accepted") {
        setFriendUsernames(prev => new Set([...prev, username]));
      } else {
        setPendingUsernames(prev => new Set([...prev, username]));
      }
    } catch (err) {
      alert(err.message);
    } finally {
      setSendingTo(null);
    }
  };

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "activity", label: "Activity" },
    { id: "friends", label: "Friends" },
  ];

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2><Users size={22} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Social</h2>
          {tab === "overview" && (
            <select className="wrapped-year-select" value={domain} onChange={e => setDomain(e.target.value)}>
              <option value="all">All Content</option>
              <option value="movies">Movies</option>
              <option value="tv">TV Shows</option>
              <option value="anime">Anime</option>
            </select>
          )}
        </div>
        <div className="trending-tab-row" style={{ marginTop: 8 }}>
          {tabs.map(t => (
            <button key={t.id} className={`trending-tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="page-body">
        {tab === "overview" && <OverviewTab
          loading={loading} error={error} overlaps={overlaps} serverStats={serverStats}
          onRetry={loadOverview} friendUsernames={friendUsernames} pendingUsernames={pendingUsernames}
          sendingTo={sendingTo} onSendRequest={sendFriendRequest} currentUser={user?.username}
        />}
        {tab === "activity" && <FriendActivityFeed user={user} />}
        {tab === "friends" && <FriendsPanel user={user} />}
      </div>
    </>
  );
}

function OverviewTab({ loading, error, overlaps, serverStats, onRetry, friendUsernames, pendingUsernames, sendingTo, onSendRequest, currentUser }) {
  if (loading) return <LoadingState message="Analyzing taste profiles across your server..." />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;

  const ols = overlaps?.overlaps || [];
  const ss = serverStats || {};

  return (
    <>
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

      <div className="wrapped-chart-section">
        <h3><Heart size={16} style={{ verticalAlign: "text-bottom", marginRight: 4 }} />Taste Neighbors</h3>
        {ols.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Not enough data to compute taste overlaps yet.</p>
        ) : (
          <div className="social-overlap-list">
            {ols.map(o => {
              const isFriend = friendUsernames.has(o.username);
              const isPending = pendingUsernames.has(o.username);
              const isSelf = o.username === currentUser;
              return (
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
                      <span className="social-overlap-name">
                        {o.friendly_name || o.username}
                        {isFriend && <span style={{ fontSize: 10, marginLeft: 6, color: "var(--green, #22c55e)" }}>friend</span>}
                      </span>
                      <div className="social-overlap-bar-track">
                        <div className="social-overlap-bar-fill" style={{
                          width: `${o.overlap_pct}%`,
                          background: o.overlap_pct >= 80 ? "var(--green, #22c55e)" :
                                      o.overlap_pct >= 60 ? "var(--accent)" :
                                      o.overlap_pct >= 40 ? "var(--yellow, #eab308)" : "var(--text-muted)"
                        }} />
                      </div>
                    </div>
                    <span className="social-overlap-pct" style={{
                      color: o.overlap_pct >= 80 ? "var(--green, #22c55e)" :
                             o.overlap_pct >= 60 ? "var(--accent)" :
                             o.overlap_pct >= 40 ? "var(--yellow, #eab308)" : "var(--text-muted)"
                    }}>{o.overlap_pct}%</span>
                    {!isSelf && !isFriend && !isPending && (
                      <button className="btn-small btn-ghost" disabled={sendingTo === o.username}
                        onClick={() => onSendRequest(o.username)} title="Send friend request"
                        style={{ marginLeft: 8, flexShrink: 0 }}>
                        <UserPlus size={14} />
                      </button>
                    )}
                    {isPending && !isFriend && (
                      <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 8, flexShrink: 0 }}>Pending</span>
                    )}
                  </div>
                  {o.shared_genres.length > 0 && (
                    <div className="social-overlap-genres">
                      {o.shared_genres.map(g => <span key={g} className="social-genre-chip shared">{g}</span>)}
                      {o.unique_to_them.map(g => <span key={g} className="social-genre-chip unique" title="They watch this, you don't">{g}</span>)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

export default SocialPage;
