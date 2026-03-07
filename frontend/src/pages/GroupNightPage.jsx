import { useState, useEffect, useCallback } from "react";
import { Users, Sparkles, Loader2, CheckCircle2 } from "lucide-react";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";

function GroupNightPage({ user, allUsers, onCardClick }) {
  const [selectedUsers, setSelectedUsers] = useState([]);
  const [domain, setDomain] = useState("all");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [meta, setMeta] = useState(null);

  // Pre-select the logged-in user
  useEffect(() => {
    if (user?.username && selectedUsers.length === 0) {
      setSelectedUsers([user.username]);
    }
  }, [user?.username]);

  const toggleUser = (username) => {
    setSelectedUsers(prev =>
      prev.includes(username) ? prev.filter(u => u !== username) : [...prev, username]
    );
  };

  const selectAll = () => setSelectedUsers((allUsers || []).map(u => u.username));
  const selectNone = () => setSelectedUsers(user?.username ? [user.username] : []);

  const findGroupPicks = () => {
    if (selectedUsers.length < 2) return;
    setLoading(true);
    setError(null);
    api.groupRecommend(user.username, selectedUsers, { domain, limit: 30, watched_filter: "unseen" })
      .then(data => {
        setItems(data.recommendations || []);
        setMeta(data.meta || null);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  };

  const sortedUsers = [...(allUsers || [])].sort((a, b) => {
    // Current user first, then active users, then alphabetical
    if (a.username === user?.username) return -1;
    if (b.username === user?.username) return 1;
    if (a.is_active && !b.is_active) return -1;
    if (!a.is_active && b.is_active) return 1;
    return a.friendly_name.localeCompare(b.friendly_name);
  });

  return (
    <>
      <div className="page-header">
        <h2><Users size={22} style={{ verticalAlign: "text-bottom", marginRight: 6 }} />Group Night</h2>
        <p>Find something everyone will enjoy — picks scored against all selected users</p>
      </div>
      <div className="page-body">
        {/* User Selector */}
        <div className="group-selector">
          <div className="group-selector-header">
            <span className="group-selector-label">Who's watching?</span>
            <span className="group-selector-count">{selectedUsers.length} selected</span>
            <div className="group-selector-actions">
              <button className="btn-text" onClick={selectAll}>All</button>
              <button className="btn-text" onClick={selectNone}>Reset</button>
            </div>
          </div>
          <div className="group-user-grid">
            {sortedUsers.map(u => {
              const selected = selectedUsers.includes(u.username);
              const isSelf = u.username === user?.username;
              return (
                <div
                  key={u.username}
                  className={`group-user-chip ${selected ? "selected" : ""} ${isSelf ? "is-self" : ""}`}
                  onClick={() => toggleUser(u.username)}
                >
                  {u.thumb ? (
                    <img src={u.thumb} alt="" className="group-user-avatar" />
                  ) : (
                    <div className="group-user-avatar group-user-avatar-placeholder">
                      {(u.friendly_name || u.username).charAt(0).toUpperCase()}
                    </div>
                  )}
                  <span className="group-user-name">{u.friendly_name || u.username}</span>
                  {isSelf && <span className="group-self-badge">you</span>}
                  <div className={`group-check ${selected ? "checked" : ""}`}>
                    {selected && <CheckCircle2 size={14} />}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="group-controls">
            <div className="filter-group">
              <label>Content</label>
              <select value={domain} onChange={e => setDomain(e.target.value)}>
                <option value="all">All</option>
                <option value="movies">Movies</option>
                <option value="tv">TV Shows</option>
                <option value="anime">Anime</option>
              </select>
            </div>
            <button
              className="btn btn-primary group-go-btn"
              onClick={findGroupPicks}
              disabled={selectedUsers.length < 2 || loading}
            >
              {loading ? <><Loader2 size={15} className="spin" /> Analyzing tastes...</> :
               selectedUsers.length < 2 ? "Select at least 2 people" :
               <><Sparkles size={15} /> Find Group Picks</>}
            </button>
          </div>
        </div>

        {/* Results */}
        {error && <ErrorState message={error} onRetry={findGroupPicks} />}
        {!loading && items.length > 0 && (
          <>
            <div className="group-results-header">
              <span className="group-results-count">{items.length} picks for {selectedUsers.length} people</span>
              <span className="group-results-hint">Scored so nobody hates the pick — 70% worst-case, 30% average appeal</span>
            </div>
            <div className="card-grid">
              {items.map((item, i) => (
                <div key={`${item.tmdb_id}-${i}`} className="group-card-wrapper">
                  <MediaCard item={item} onClick={onCardClick} />
                  {item.explanation && (
                    <div className="group-score-breakdown">
                      {item.explanation.replace("Group fit: ", "").split(" / ").map((part, j) => {
                        const [uname, pct] = part.split(":");
                        const pctNum = parseFloat(pct);  // already percentage from backend
                        const color = pctNum >= 70 ? "var(--green)" : pctNum >= 50 ? "var(--yellow, #eab308)" : "var(--red, #ef4444)";
                        return (
                          <div key={j} className="group-user-score">
                            <span className="group-user-score-name">{uname}</span>
                            <div className="group-user-score-bar">
                              <div className="group-user-score-fill" style={{ width: `${Math.min(pctNum, 100)}%`, background: color }} />
                            </div>
                            <span className="group-user-score-pct" style={{ color }}>{pctNum.toFixed(0)}%</span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
        {!loading && !error && items.length === 0 && meta && (
          <EmptyState icon={Users} title="No group picks found" message="Try selecting different users or changing the content filter." />
        )}
      </div>
    </>
  );
}

export default GroupNightPage;
