import { useState, useEffect, useCallback } from "react";
import { Play, Download, RefreshCw, AlertCircle } from "lucide-react";
import Skeleton from "../components/Skeleton.jsx";
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
  const [staleness, setStaleness] = useState(null);
  const [filters, setFilters] = useState(loadSavedFilters);
  const [seriesProgress, setSeriesProgress] = useState({});

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
      .finally(() => {
        setLoading(false); setRefreshing(false);
        api.myStaleness().then(setStaleness).catch(() => {});
      });
  }, [user, mode, filters]);

  useEffect(() => { load(); }, [load]);

  // Fetch series progress for TV items
  useEffect(() => {
    if (!user || !items.length) return;
    const tvIds = items.filter(i => i.media_type === "tv").map(i => i.tmdb_id).filter(Boolean);
    if (!tvIds.length) { setSeriesProgress({}); return; }
    api.seriesProgress(user, tvIds)
      .then(d => setSeriesProgress(d.items || {}))
      .catch(() => setSeriesProgress({}));
  }, [user, items]);

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
            {staleness && staleness.staleness !== "fresh" && staleness.staleness !== "never" && (
              <span style={{
                fontSize: 11, fontWeight: 500, display: "flex", alignItems: "center", gap: 3,
                padding: "2px 8px", borderRadius: 10,
                background: staleness.plays_since_refresh >= 20 ? "rgba(239,68,68,0.12)" :
                  staleness.plays_since_refresh >= 5 ? "rgba(249,115,22,0.12)" : "rgba(245,158,11,0.12)",
                color: staleness.plays_since_refresh >= 20 ? "#ef4444" :
                  staleness.plays_since_refresh >= 5 ? "#f97316" : "#f59e0b",
              }}>
                <Play size={10} /> {staleness.plays_since_refresh} new play{staleness.plays_since_refresh !== 1 ? "s" : ""}
              </span>
            )}
            {staleness && staleness.staleness === "fresh" && (
              <span style={{ fontSize: 11, color: "#10b981", display: "flex", alignItems: "center", gap: 3 }}>
                ✓ Up to date
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
        {loading ? <Skeleton.CardGrid count={8} /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         items.length === 0 ? <EmptyState icon={cfg.icon} title="No recommendations" message={`No ${mode} picks found for this user.`} /> :
         <div className="card-grid">
           {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={{...item, series_progress: seriesProgress[item.tmdb_id] || null}} onClick={onCardClick} onFeedback={handleFeedback} />)}
         </div>}
      </div>
    </>
  );
}


export default RecommendationsPage;
