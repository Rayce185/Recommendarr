import { useState, useEffect, useCallback } from "react";
import { Play, Download, RefreshCw, AlertCircle, Loader2 } from "lucide-react";
import { api, authFetch, API_BASE } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";
import { FilterPanel, loadSavedFilters, saveFilters } from "../components/FilterPanel.jsx";

function RecommendationsPage({ user, mode, onCardClick }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [cached, setCached] = useState(false);
  const [cacheAge, setCacheAge] = useState(null); // seconds
  const [profileModifiedAt, setProfileModifiedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState(loadSavedFilters);

  const modeConfig = {
    tonight: { title: "Watch Tonight", desc: "In your library, matched to your taste", icon: Play },
    grab: { title: "Worth Grabbing", desc: "Not in your library yet — request via Seerr", icon: Download },
    rediscover: { title: "Rediscover", desc: "Rewatchable favorites from your history", icon: RefreshCw },
  };
  const cfg = modeConfig[mode] || modeConfig.tonight;

  const load = useCallback((forceRefresh = false, filterOverride = null) => {
    if (!user) return;
    if (forceRefresh) setRefreshing(true); else setLoading(true);
    setError(null);
    const f = filterOverride || filters;
    const opts = { limit: 30, refresh: forceRefresh || undefined };
    if (f.excludeGenres?.length) opts.exclude_genres = f.excludeGenres.join(",");
    if (f.includeGenres?.length) opts.include_genres = f.includeGenres.join(",");
    if (f.excludeLibraries?.length) opts.exclude_libraries = f.excludeLibraries.join(",");
    if (f.watchedFilter && f.watchedFilter !== 'all') opts.watched_filter = f.watchedFilter;
    if (f.minYear) opts.min_year = f.minYear;
    if (f.maxYear) opts.max_year = f.maxYear;
    if (f.minRating) opts.min_rating = f.minRating;
    api.recommend(user, mode, opts)
      .then(data => {
        const recs = data.recommendations || [];
        setItems(recs);
        setCached(data.meta?.cached || false);
        setCacheAge(data.meta?.cache_age_seconds || null);
        setProfileModifiedAt(data.meta?.profile_modified_at || null);
        // Lazy-load AI explanations if missing
        if (recs.length > 0 && !recs[0]?.explanation) {
          api.lazyExplain(user, mode).then(res => {
            if (res.status === "explained") {
              // Re-fetch from cache (now has explanations)
              api.recommend(user, mode, { ...opts, refresh: undefined })
                .then(d2 => { if (d2.recommendations?.length) setItems(d2.recommendations); });
            }
          }).catch(() => {}); // Non-fatal
        }
      })
      .catch(err => setError(err.message))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }, [user, mode, filters]);

  useEffect(() => { load(); }, [load]);

  const handleFeedback = useCallback(async (item, action) => {
    if (action === null) {
      // Toggle off — remove feedback
      setItems(prev => prev.map(it => it.tmdb_id === item.tmdb_id ? { ...it, user_feedback: null } : it));
      try {
        await authFetch(`${API_BASE}/users/${user}/feedback/${item.tmdb_id}`, { method: "DELETE" });
      } catch (e) {}
      return;
    }
    // Optimistic update
    if (action === "dismiss") {
      setItems(prev => prev.filter(it => it.tmdb_id !== item.tmdb_id));
    } else {
      setItems(prev => prev.map(it => it.tmdb_id === item.tmdb_id ? { ...it, user_feedback: action } : it));
    }
    try {
      await api.submitFeedback(user, {
        tmdb_id: item.tmdb_id,
        media_type: item.media_type || "movie",
        action,
        title: item.title || "",
        genres: item.genres || [],
        keywords: item.keywords || [],
      });
    } catch (e) {
      // Revert on error
      if (action === "dismiss") load();
    }
  }, [user, load]);

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2>{cfg.title}</h2>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {cached && cacheAge != null && (
              <span style={{ fontSize: 11, color: "var(--text-muted)", opacity: 0.7 }}>
                Updated {cacheAge < 60 ? "just now" : `${Math.floor(cacheAge / 60)} min ago`}
              </span>
            )}
            {profileModifiedAt && cached && cacheAge != null && (() => {
              const modTime = new Date(profileModifiedAt).getTime();
              const recsTime = Date.now() - (cacheAge * 1000);
              return modTime > recsTime;
            })() && (
              <span style={{ fontSize: 11, color: "#eab308", fontWeight: 500, display: "flex", alignItems: "center", gap: 3 }}>
                <AlertCircle size={12} /> Profile changed — refresh recommended
              </span>
            )}
            <button
              className="btn btn-secondary"
              style={{ padding: "6px 10px", fontSize: 12 }}
              onClick={() => load(true)}
              disabled={refreshing}
              title="Force refresh recommendations"
            >
              <RefreshCw size={14} className={refreshing ? "spinning" : ""} /> {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
        <p>{cfg.desc}</p>
      </div>
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        onApply={(f) => { setFilters(f); saveFilters(f); load(true, f); }}
      />
      <div className="page-body">
        {loading ? <LoadingState message={`Finding ${mode === 'grab' ? 'new releases' : 'recommendations'}...`} /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         items.length === 0 ? <EmptyState icon={cfg.icon} title="No recommendations" message={`No ${mode} picks found for this user.`} /> :
         <div className="card-grid">
           {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={item} onClick={onCardClick} onFeedback={handleFeedback} />)}
         </div>}
      </div>
    </>
  );
}


export default RecommendationsPage;
