import { useState, useEffect, useCallback } from "react";
import { Users, Loader2, GitCompare, X, Plus, Percent } from "lucide-react";
import { api } from "../api.js";
import TasteRadarChart, { USER_COLORS } from "../components/TasteRadarChart.jsx";
import { LoadingState, ErrorState } from "../components/StateDisplays.jsx";
import { formatHours } from "../utils.js";

function TasteComparePage({ user }) {
  const [allUsers, setAllUsers] = useState([]);
  const [selected, setSelected] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [error, setError] = useState(null);
  const [domain, setDomain] = useState("all");

  // Load available users on mount
  useEffect(() => {
    api.users()
      .then((data) => {
        const list = (data.users || []).filter((u) => u.is_active);
        setAllUsers(list);
        // Pre-select current user
        if (user && list.find((u) => u.username === user)) {
          setSelected([user]);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingUsers(false));
  }, [user]);

  const addUser = (username) => {
    if (selected.length >= 6) return;
    if (!selected.includes(username)) {
      setSelected((prev) => [...prev, username]);
    }
  };

  const removeUser = (username) => {
    setSelected((prev) => prev.filter((u) => u !== username));
    setComparison(null);
  };

  const runComparison = useCallback(async () => {
    if (selected.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.compareProfiles(selected, domain);
      setComparison(data);
    } catch (e) {
      setError(e.message || "Comparison failed");
    }
    setLoading(false);
  }, [selected, domain]);

  const availableToAdd = allUsers.filter(
    (u) => !selected.includes(u.username),
  );

  return (
    <>
      <div className="page-header">
        <h2>Taste Radar</h2>
        <p>Compare taste profiles across users</p>
      </div>
      <div className="page-body">
        {/* User picker */}
        <div className="compare-picker">
          <div className="compare-selected">
            {selected.map((uname, i) => (
              <span
                key={uname}
                className="compare-chip"
                style={{
                  borderColor: USER_COLORS[i % USER_COLORS.length],
                  background: USER_COLORS[i % USER_COLORS.length] + "18",
                }}
              >
                <span
                  className="compare-chip-dot"
                  style={{
                    background: USER_COLORS[i % USER_COLORS.length],
                  }}
                />
                {uname}
                <button
                  className="compare-chip-remove"
                  onClick={() => removeUser(uname)}
                >
                  <X size={12} />
                </button>
              </span>
            ))}
            {selected.length < 6 && availableToAdd.length > 0 && (
              <select
                className="compare-add-select"
                value=""
                onChange={(e) => {
                  if (e.target.value) addUser(e.target.value);
                }}
              >
                <option value="">
                  <Plus size={12} /> Add user...
                </option>
                {availableToAdd.map((u) => (
                  <option key={u.username} value={u.username}>
                    {u.friendly_name || u.username}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="compare-controls">
            <select
              className="compare-domain-select"
              value={domain}
              onChange={(e) => {
                setDomain(e.target.value);
                setComparison(null);
              }}
            >
              <option value="all">All Content</option>
              <option value="movies">Movies</option>
              <option value="tv">TV Shows</option>
              <option value="anime">Anime</option>
            </select>
            <button
              className="btn btn-primary compare-go"
              disabled={selected.length < 2 || loading}
              onClick={runComparison}
            >
              {loading ? (
                <Loader2 size={14} className="spin" />
              ) : (
                <GitCompare size={14} />
              )}
              {loading ? "Building..." : "Compare"}
            </button>
          </div>
        </div>

        {loadingUsers && <LoadingState message="Loading users..." />}
        {error && <ErrorState message={error} onRetry={runComparison} />}

        {!comparison && !loading && !error && (
          <div className="compare-hint">
            <GitCompare size={40} strokeWidth={1} />
            <p>Select 2–6 users and hit Compare to see the taste radar overlay.</p>
          </div>
        )}

        {/* Radar chart */}
        {comparison && (
          <>
            <TasteRadarChart
              axes={comparison.axes || []}
              users={(comparison.users || []).map((u, i) => ({
                username: u.username,
                scores: u.scores,
                color: USER_COLORS[i % USER_COLORS.length],
              }))}
              size={440}
            />

            {/* Stats comparison grid */}
            <div className="compare-stats-grid">
              {(comparison.users || []).map((u, i) => (
                <div
                  key={u.username}
                  className="compare-stat-card"
                  style={{
                    borderTopColor: USER_COLORS[i % USER_COLORS.length],
                  }}
                >
                  <div className="compare-stat-name">{u.username}</div>
                  <div className="compare-stat-row">
                    <span>Watched</span>
                    <strong>{u.stats?.total_watched?.toLocaleString() || 0}</strong>
                  </div>
                  <div className="compare-stat-row">
                    <span>Hours</span>
                    <strong>{formatHours(u.stats?.total_hours || 0)}</strong>
                  </div>
                  <div className="compare-stat-row">
                    <span>Completion</span>
                    <strong>{u.stats?.avg_completion?.toFixed(0) || 0}%</strong>
                  </div>
                  <div className="compare-stat-row">
                    <span>Rewatches</span>
                    <strong>{u.stats?.rewatch_count?.toLocaleString() || 0}</strong>
                  </div>
                </div>
              ))}
            </div>

            {/* Pairwise similarity */}
            {(comparison.pairs || []).length > 0 && (
              <div className="compare-pairs">
                <h3>
                  <Percent size={16} /> Taste Similarity
                </h3>
                {comparison.pairs.map((p) => (
                  <div key={`${p.user_a}-${p.user_b}`} className="compare-pair-row">
                    <span className="pair-users">
                      {p.user_a} × {p.user_b}
                    </span>
                    <div className="pair-bar-track">
                      <div
                        className="pair-bar-fill"
                        style={{ width: `${Math.min(100, p.similarity_pct)}%` }}
                      />
                    </div>
                    <span className="pair-pct">{p.similarity_pct}%</span>
                    {p.shared_genres?.length > 0 && (
                      <div className="pair-shared">
                        Shared:{" "}
                        {p.shared_genres.join(", ")}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Keyword comparison */}
            <KeywordComparison users={comparison.users || []} />
          </>
        )}
      </div>
    </>
  );
}

function KeywordComparison({ users }) {
  if (users.length < 2) return null;
  // Find keywords each user uniquely loves
  const allKwSets = users.map(
    (u) => new Set((u.top_keywords || []).map((k) => k.keyword)),
  );

  const unique = users.map((u, i) => {
    const others = new Set();
    allKwSets.forEach((s, j) => {
      if (j !== i) s.forEach((k) => others.add(k));
    });
    return {
      username: u.username,
      keywords: (u.top_keywords || [])
        .filter((k) => !others.has(k.keyword))
        .slice(0, 6),
    };
  });

  const hasUnique = unique.some((u) => u.keywords.length > 0);
  if (!hasUnique) return null;

  return (
    <div className="compare-keywords">
      <h3>Unique Interests</h3>
      <div className="compare-kw-grid">
        {unique.map(
          (u, i) =>
            u.keywords.length > 0 && (
              <div key={u.username} className="compare-kw-col">
                <div
                  className="compare-kw-user"
                  style={{ color: USER_COLORS[i % USER_COLORS.length] }}
                >
                  {u.username}
                </div>
                <div className="keyword-chips">
                  {u.keywords.map((k) => (
                    <span className="keyword-chip" key={k.keyword}>
                      {k.keyword}
                    </span>
                  ))}
                </div>
              </div>
            ),
        )}
      </div>
    </div>
  );
}

export default TasteComparePage;
