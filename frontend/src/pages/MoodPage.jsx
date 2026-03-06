import { useState, useEffect, useCallback } from "react";
import { Sparkles, Loader2, Search } from "lucide-react";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";
import CustomSelect from "../components/CustomSelect.jsx";

function MoodPage({ user, onCardClick }) {
  const [presets, setPresets] = useState([]);
  const [query, setQuery] = useState("");
  const [activePreset, setActivePreset] = useState(null);
  const [moodInfo, setMoodInfo] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [presetsLoading, setPresetsLoading] = useState(true);
  const [mediaFilter, setMediaFilter] = useState("all");
  const [watchedFilter, setWatchedFilter] = useState("all");

  useEffect(() => {
    api.moodPresets()
      .then(data => setPresets(data.presets || []))
      .finally(() => setPresetsLoading(false));
  }, []);

  const search = useCallback((q) => {
    if (!user || !q) return;
    setLoading(true);
    setMoodInfo(null);
    const opts = { mood: q, limit: 30, domain: mediaFilter };
    if (watchedFilter !== "all") opts.watched_filter = watchedFilter;
    Promise.all([
      api.recommend(user, "mood", opts),
      api.moodParse(q)
    ]).then(([recData, parseData]) => {
      setItems(recData.recommendations || []);
      setMoodInfo(parseData);
    }).catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [user, mediaFilter, watchedFilter]);

  const handlePreset = (preset) => {
    setActivePreset(preset.name);
    setQuery(preset.query);
    search(preset.query);
  };

  const handleSubmit = (e) => {
    e?.preventDefault();
    setActivePreset(null);
    search(query);
  };

  return (
    <>
      <div className="page-header">
        <h2>Mood Match</h2>
        <p>Describe what you're in the mood for — anything goes</p>
      </div>
      <div className="page-body">
        <div className="mood-search-bar">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSubmit()}
            placeholder='Try "cozy rainy day movie" or "intense sci-fi with plot twists"'
          />
          <button onClick={handleSubmit} disabled={!query.trim() || loading}>
            {loading ? <Loader2 size={16} className="spinner" /> : <Search size={16} />}
            Search
          </button>
        </div>

        <div className="mood-filters" style={{ display: "flex", gap: "12px", alignItems: "center", margin: "8px 0 4px" }}>
          <select value={mediaFilter} onChange={e => { setMediaFilter(e.target.value); if (query.trim()) search(query); }}
            style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", fontSize: 13 }}>
            <option value="all">All Media</option>
            <option value="movies">Movies Only</option>
            <option value="tv">TV Shows Only</option>
            <option value="anime">Anime Only</option>
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-muted)", cursor: "pointer" }}>
            <select value={watchedFilter} onChange={e => { setWatchedFilter(e.target.value); if (query.trim()) search(query); }}
              style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", fontSize: 13 }}>
              <option value="all">All</option>
              <option value="unseen">Unseen Only</option>
              <option value="seen">Seen Only</option>
            </select>
          </label>
        </div>

        {!presetsLoading && presets.length > 0 && (
          <div className="mood-presets">
            {presets.map((p, i) => (
              <button
                key={i}
                className={`preset-chip ${activePreset === p.name ? 'active' : ''}`}
                onClick={() => handlePreset(p)}
              >
                {p.name}
              </button>
            ))}
          </div>
        )}

        {moodInfo && (
          <div className="mood-explanation">
            <Sparkles size={16} />
            <span>{moodInfo.explanation || "Mood parsed successfully"}</span>
          </div>
        )}

        {loading ? <LoadingState message="Matching your mood..." /> :
         items.length > 0 ? (
          <div className="card-grid">
            {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={item} onClick={onCardClick} />)}
          </div>
         ) : !loading && query && items.length === 0 && moodInfo ? (
          <EmptyState icon={Sparkles} title="No mood matches" message="Try describing your mood differently." />
         ) : null}
      </div>
    </>
  );
}


export default MoodPage;
