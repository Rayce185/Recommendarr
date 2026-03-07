import { useState, useEffect, useCallback } from "react";
import { Heart, Star, Film, Tv, BarChart3, Save, Loader2, Download, Upload } from "lucide-react";
import { api } from "../api.js";
import ProfileDataTab from "../components/ProfileDataTab.jsx";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import { formatHours } from "../utils.js";

function TasteProfilePage({ user }) {
  const [profile, setProfile] = useState(null);
  const [overrides, setOverrides] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("overview");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [newBoostKw, setNewBoostKw] = useState("");
  const [newBlockKw, setNewBlockKw] = useState("");

  const load = useCallback(() => {
    if (!user) return;
    setLoading(true);
    setError(null);
    Promise.all([api.userProfile(user), api.getOverrides(user)])
      .then(([p, o]) => { setProfile(p); setOverrides(o); setDirty(false); })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const updateOverrides = (patch) => {
    setOverrides(prev => ({ ...prev, ...patch }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await api.saveOverrides(user, overrides);
      setOverrides(result.overrides);
      setDirty(false);
    } catch (e) {}
    setSaving(false);
  };

  const setGenreBoost = (genre, val) => {
    const boosts = { ...(overrides?.genre_boosts || {}) };
    if (Math.abs(val) < 0.05) delete boosts[genre]; else boosts[genre] = val;
    updateOverrides({ genre_boosts: boosts });
  };

  const toggleGenreBlock = (genre) => {
    const blocks = [...(overrides?.genre_blocks || [])];
    const idx = blocks.indexOf(genre);
    if (idx >= 0) blocks.splice(idx, 1); else blocks.push(genre);
    updateOverrides({ genre_blocks: blocks });
  };

  const addKeyword = (kw, type) => {
    if (!kw.trim()) return;
    const key = type === "boost" ? "keyword_boosts" : "keyword_blocks";
    const list = [...(overrides?.[key] || [])];
    if (!list.includes(kw.trim())) list.push(kw.trim());
    updateOverrides({ [key]: list });
    if (type === "boost") setNewBoostKw(""); else setNewBlockKw("");
  };

  const removeKeyword = (kw, type) => {
    const key = type === "boost" ? "keyword_boosts" : "keyword_blocks";
    updateOverrides({ [key]: (overrides?.[key] || []).filter(k => k !== kw) });
  };

  if (loading) return <><div className="page-header"><h2>Taste Profile</h2></div><div className="page-body"><LoadingState message="Building taste profile..." /></div></>;
  if (error) return <><div className="page-header"><h2>Taste Profile</h2></div><div className="page-body"><ErrorState message={error} onRetry={load} /></div></>;
  if (!profile) return null;

  const genreColors = ["#e5a00d", "#3b82f6", "#22c55e", "#a855f7", "#ef4444", "#06b6d4", "#f97316", "#ec4899", "#84cc16", "#6366f1"];
  const allGenres = (profile.genres || []).map(g => g.genre);

  return (
    <>
      <div className="page-header">
        <h2>Taste Profile</h2>
        <p>Behavior analysis + manual tuning for {user}</p>
      </div>
      <div className="page-body">
        <div className="profile-tabs">
          {[["overview", "Overview"], ["genres", "Genre Tuning"], ["keywords", "Keywords"], ["data", "Import/Export"]].map(([id, label]) => (
            <button key={id} className={`profile-tab ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>

        {tab === "overview" && (
          <>
            <div className="profile-stats">
              <div className="stat-card">
                <div className="stat-value">{profile.stats?.total_watched?.toLocaleString() || 0}</div>
                <div className="stat-label">Total Watched</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: "var(--accent)" }}>{formatHours(profile.stats?.total_hours || 0)}</div>
                <div className="stat-label">Watch Time</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: "var(--green)" }}>{profile.stats?.avg_completion?.toFixed(0) || 0}%</div>
                <div className="stat-label">Avg Completion</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: "var(--purple)" }}>{profile.stats?.rewatch_count?.toLocaleString() || 0}</div>
                <div className="stat-label">Rewatches</div>
              </div>
            </div>
            <div className="section-header"><h3><BarChart3 size={18} /> Genre Affinities</h3></div>
            {(profile.genres || []).slice(0, 12).map((g, i) => (
              <div className="genre-bar-container" key={g.genre}>
                <div className="genre-bar-header">
                  <span className="genre-name">{g.genre}</span>
                  <span className="genre-stats">{g.watch_count} titles · {g.total_hours?.toFixed(1) || 0}h</span>
                </div>
                <div className="genre-bar-track">
                  <div className="genre-bar-fill" style={{ width: `${g.score * 100}%`, background: genreColors[i % genreColors.length] }} />
                </div>
              </div>
            ))}
            {profile.keywords?.length > 0 && (
              <>
                <div className="section-header" style={{ marginTop: 24 }}><h3><Sparkles size={18} /> Top Keywords</h3></div>
                <div className="keyword-chips">
                  {profile.keywords.slice(0, 20).map(k => (
                    <span className="keyword-chip" key={k.keyword}>{k.keyword} <span style={{opacity: 0.5, fontSize: "0.7rem"}}>×{k.count}</span></span>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {tab === "genres" && (
          <>
            <div className="section-header"><h3><SlidersHorizontal size={18} /> Genre Boost / Suppress / Block</h3></div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 16 }}>
              Drag sliders to boost (right) or suppress (left) genres. Block to completely exclude.
            </p>
            {allGenres.map(genre => {
              const boost = overrides?.genre_boosts?.[genre] || 0;
              const blocked = (overrides?.genre_blocks || []).includes(genre);
              return (
                <div className="genre-tuning-row" key={genre}>
                  <span className="genre-tuning-name">{genre}</span>
                  <input
                    type="range" min="-1" max="1" step="0.1"
                    className="genre-tuning-slider"
                    value={blocked ? 0 : boost}
                    disabled={blocked}
                    onChange={e => setGenreBoost(genre, parseFloat(e.target.value))}
                    style={blocked ? { opacity: 0.3 } : {}}
                  />
                  <span className="genre-tuning-value">{blocked ? "—" : (boost > 0 ? "+" : "") + boost.toFixed(1)}</span>
                  <button
                    className={`genre-tuning-block ${blocked ? "blocked" : ""}`}
                    onClick={() => toggleGenreBlock(genre)}
                  >{blocked ? "Blocked" : "Block"}</button>
                </div>
              );
            })}
            {dirty && (
              <div className="profile-save-bar">
                <span className="changes-badge">Unsaved changes</span>
                <button className="btn btn-primary" style={{ padding: "6px 16px", fontSize: 13 }} onClick={handleSave} disabled={saving}>
                  {saving ? <><Loader2 size={14} className="spin" /> Saving...</> : <><Save size={14} /> Save Changes</>}
                </button>
              </div>
            )}
          </>
        )}

        {tab === "keywords" && (
          <>
            <div className="section-header"><h3><ThumbsUp size={18} /> Preferred Keywords</h3></div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 10 }}>
              Titles matching these keywords get a score boost.
            </p>
            <div className="keyword-chips">
              {(overrides?.keyword_boosts || []).map(kw => (
                <span className="keyword-chip boost" key={kw}>{kw} <button onClick={() => removeKeyword(kw, "boost")}><X size={12} /></button></span>
              ))}
              {(overrides?.keyword_boosts || []).length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-dim)" }}>None yet</span>}
            </div>
            <div className="keyword-add-row">
              <input placeholder="Add keyword..." value={newBoostKw} onChange={e => setNewBoostKw(e.target.value)} onKeyDown={e => e.key === "Enter" && addKeyword(newBoostKw, "boost")} />
              <button onClick={() => addKeyword(newBoostKw, "boost")}>+ Boost</button>
            </div>

            <div className="section-header" style={{ marginTop: 24 }}><h3><ThumbsDown size={18} /> Blocked Keywords</h3></div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 10 }}>
              Titles matching these keywords get a score penalty.
            </p>
            <div className="keyword-chips">
              {(overrides?.keyword_blocks || []).map(kw => (
                <span className="keyword-chip block" key={kw}>{kw} <button onClick={() => removeKeyword(kw, "block")}><X size={12} /></button></span>
              ))}
              {(overrides?.keyword_blocks || []).length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-dim)" }}>None yet</span>}
            </div>
            <div className="keyword-add-row">
              <input placeholder="Add keyword..." value={newBlockKw} onChange={e => setNewBlockKw(e.target.value)} onKeyDown={e => e.key === "Enter" && addKeyword(newBlockKw, "block")} />
              <button onClick={() => addKeyword(newBlockKw, "block")}>+ Block</button>
            </div>

            {dirty && (
              <div className="profile-save-bar">
                <span className="changes-badge">Unsaved changes</span>
                <button className="btn btn-primary" style={{ padding: "6px 16px", fontSize: 13 }} onClick={handleSave} disabled={saving}>
                  {saving ? <><Loader2 size={14} className="spin" /> Saving...</> : <><Save size={14} /> Save Changes</>}
                </button>
              </div>
            )}
          </>
        )}

        {tab === "data" && <ProfileDataTab user={user} />}
      </div>
    </>
  );
}





export default TasteProfilePage;
