import { useState, useEffect, useCallback } from "react";
import { UserPlus, UserMinus, Check, X, Clock, Shield, Loader2, Sparkles } from "lucide-react";
import { authFetch, API_BASE } from "../api.js";

function FriendsPanel({ user }) {
  const [friends, setFriends] = useState([]);
  const [pending, setPending] = useState({ incoming: [], outgoing: [] });
  const [privacy, setPrivacy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [suggestions, setSuggestions] = useState([]);

  const load = useCallback(async () => {
    if (!user?.username) return;
    setLoading(true);
    try {
      const [fRes, pRes, prRes] = await Promise.all([
        authFetch(`${API_BASE}/friends`).then(r => r.json()),
        authFetch(`${API_BASE}/friends/pending`).then(r => r.json()),
        authFetch(`${API_BASE}/privacy`).then(r => r.json()),
      ]);
      setFriends(fRes.friends || []);
      setPending(pRes);
      setPrivacy(prRes);
      // Load taste overlaps for friend suggestions
      const friendNames = new Set((fRes.friends || []).map(f => f.username));
      const pendingNames = new Set([
        ...(pRes.incoming || []).map(p => p.username),
        ...(pRes.outgoing || []).map(p => p.username),
      ]);
      try {
        const ovRes = await authFetch(`${API_BASE}/users/${user.username}/taste-overlap?domain=all`);
        const ovData = await ovRes.json();
        const sug = (ovData.overlaps || [])
          .filter(o => !friendNames.has(o.username) && !pendingNames.has(o.username) && o.overlap_pct >= 30)
          .slice(0, 5);
        setSuggestions(sug);
      } catch (e) { /* ok */ }
    } catch (err) {
      console.error("Failed to load friends:", err);
    } finally {
      setLoading(false);
    }
  }, [user?.username]);

  useEffect(() => { load(); }, [load]);

  const doAction = async (url, method, body) => {
    const key = body?.username || url;
    setActionLoading(key);
    try {
      const opts = { method, headers: { "Content-Type": "application/json" } };
      if (body) opts.body = JSON.stringify(body);
      const res = await authFetch(`${API_BASE}${url}`, opts);
      if (!res.ok) {
        const data = await res.json();
        alert(data.detail || "Action failed");
        return;
      }
      await load();
    } catch (err) {
      alert(err.message);
    } finally {
      setActionLoading(null);
    }
  };

  const acceptRequest = (username) => doAction("/friends/respond", "POST", { username, accept: true });
  const declineRequest = (username) => doAction("/friends/respond", "POST", { username, accept: false });
  const removeFriend = (username) => {
    if (!confirm(`Remove ${username} as a friend?`)) return;
    doAction(`/friends/${username}`, "DELETE");
  };

  const togglePrivacy = async (key) => {
    const updated = { ...privacy, [key]: !privacy[key] };
    setPrivacy(updated);
    try {
      await authFetch(`${API_BASE}/privacy`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: updated[key] }),
      });
    } catch (err) {
      setPrivacy(privacy);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>
        <Loader2 size={24} className="spin" /> Loading friends...
      </div>
    );
  }

  const hasIncoming = pending.incoming.length > 0;
  const hasOutgoing = pending.outgoing.length > 0;

  return (
    <div className="friends-panel">
      {/* Pending Incoming */}
      {hasIncoming && (
        <div className="wrapped-chart-section" style={{ marginBottom: 16 }}>
          <h3 style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <UserPlus size={16} /> Pending Requests ({pending.incoming.length})
          </h3>
          <div className="social-overlap-list">
            {pending.incoming.map(r => (
              <div key={r.username} className="social-overlap-card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {r.thumb ? (
                    <img src={r.thumb} alt="" className="group-user-avatar" />
                  ) : (
                    <div className="group-user-avatar group-user-avatar-placeholder">
                      {(r.display_name || r.username).charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div>
                    <span className="social-overlap-name">{r.display_name}</span>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      <Clock size={10} style={{ verticalAlign: "text-bottom" }} /> {new Date(r.requested_at).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    className="btn-small btn-accent"
                    disabled={actionLoading === r.username}
                    onClick={() => acceptRequest(r.username)}
                    title="Accept"
                  >
                    <Check size={14} /> Accept
                  </button>
                  <button
                    className="btn-small btn-ghost"
                    disabled={actionLoading === r.username}
                    onClick={() => declineRequest(r.username)}
                    title="Decline"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Friends List */}
      <div className="wrapped-chart-section" style={{ marginBottom: 16 }}>
        <h3>Your Friends ({friends.length})</h3>
        {friends.length === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            No friends yet. Visit the Taste Neighbors tab and send friend requests to people with similar taste!
          </p>
        ) : (
          <div className="social-overlap-list">
            {friends.map(f => (
              <div key={f.username} className="social-overlap-card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {f.thumb ? (
                    <img src={f.thumb} alt="" className="group-user-avatar" />
                  ) : (
                    <div className="group-user-avatar group-user-avatar-placeholder">
                      {(f.display_name || f.username).charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div>
                    <span className="social-overlap-name">{f.display_name}</span>
                    {f.since && (
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        Friends since {new Date(f.since).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                </div>
                <button
                  className="btn-small btn-ghost"
                  disabled={actionLoading === f.username}
                  onClick={() => removeFriend(f.username)}
                  title="Remove friend"
                >
                  <UserMinus size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Outgoing Requests */}
      {hasOutgoing && (
        <div className="wrapped-chart-section" style={{ marginBottom: 16 }}>
          <h3 style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Clock size={16} /> Sent Requests ({pending.outgoing.length})
          </h3>
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {pending.outgoing.map(r => (
              <div key={r.username} style={{ padding: "6px 0", borderBottom: "1px solid var(--border-subtle, rgba(255,255,255,0.06))" }}>
                {r.display_name} — waiting for response
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Friend Suggestions */}
      {suggestions.length > 0 && (
        <div className="wrapped-chart-section" style={{ marginBottom: 16 }}>
          <h3 style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Sparkles size={16} /> Suggested Friends
          </h3>
          <p style={{ color: "var(--text-muted)", fontSize: 12, marginBottom: 8 }}>Based on taste overlap</p>
          <div className="social-overlap-list">
            {suggestions.map(s => (
              <div key={s.username} className="social-overlap-card" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                  {s.thumb ? (
                    <img src={s.thumb} alt="" className="group-user-avatar" />
                  ) : (
                    <div className="group-user-avatar group-user-avatar-placeholder">
                      {(s.friendly_name || s.username).charAt(0).toUpperCase()}
                    </div>
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span className="social-overlap-name">{s.friendly_name || s.username}</span>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {s.overlap_pct}% match{s.shared_genres.length > 0 ? ` · ${s.shared_genres.slice(0, 3).join(", ")}` : ""}
                    </div>
                  </div>
                </div>
                <button
                  className="btn-small btn-accent"
                  disabled={actionLoading === s.username}
                  onClick={() => doAction("/friends/request", "POST", { username: s.username })}
                >
                  <UserPlus size={14} /> Add
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Privacy Settings */}
      <div className="wrapped-chart-section">
        <h3
          style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
          onClick={() => setShowPrivacy(p => !p)}
        >
          <Shield size={16} /> Privacy Settings {showPrivacy ? "▾" : "▸"}
        </h3>
        {showPrivacy && privacy && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
            {[
              ["allow_friend_requests", "Allow friend requests"],
              ["show_activity_to_friends", "Show my activity to friends"],
              ["show_in_server_stats", "Include me in server stats"],
              ["anonymize_activity", "Anonymize my activity in feeds"],
            ].map(([key, label]) => (
              <label key={key} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={privacy[key]}
                  onChange={() => togglePrivacy(key)}
                  style={{ accentColor: "var(--accent)" }}
                />
                {label}
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default FriendsPanel;
