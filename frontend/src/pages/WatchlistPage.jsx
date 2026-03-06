import { useState, useEffect, useCallback } from "react";
import { Bookmark, Loader2, Film, Tv, ChevronDown } from "lucide-react";
import { api } from "../api.js";
import { posterUrl } from "../utils.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";

const WATCHLIST_SORTS = [
  { value: "addedAt:desc", label: "Recently Added" },
  { value: "addedAt:asc", label: "Oldest Added" },
  { value: "titleSort:asc", label: "Title A–Z" },
  { value: "titleSort:desc", label: "Title Z–A" },
  { value: "year:desc", label: "Newest Release" },
  { value: "year:asc", label: "Oldest Release" },
  { value: "rating:desc", label: "Highest Rated" },
];

function WatchlistPage({ user, onCardClick }) {
  const [items, setItems] = useState([]);
  const [libraries, setLibraries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState("addedAt:desc");
  const [filterLib, setFilterLib] = useState("all"); // "all" | library title
  const [removing, setRemoving] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [playResult, setPlayResult] = useState(null);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    api.watchlist(sort, null)
      .then(data => {
        setItems(data.items || []);
        if (data.libraries) setLibraries(data.libraries);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [sort]);

  useEffect(() => { load(); }, [load]);

  const handleRemove = async (item) => {
    setRemoving(item.tmdb_id);
    try {
      await api.watchlistDelete(item.tmdb_id, item.media_type);
      setItems(prev => prev.filter(i => i.tmdb_id !== item.tmdb_id));
    } catch (e) { console.error("Remove failed:", e); }
    setRemoving(null);
  };

  const handlePlay = async (item) => {
    if (!item.in_library) return;
    setPlayingId(item.tmdb_id); setPlayResult(null);
    try {
      const result = await api.playOnDevice(item.tmdb_id, item.media_type);
      setPlayResult({ id: item.tmdb_id, ...result });
    } catch (e) {
      setPlayResult({ id: item.tmdb_id, success: false, message: e.message });
    }
    setTimeout(() => { setPlayingId(null); setPlayResult(null); }, 3000);
  };

  // Build subtabs from Plex libraries with item counts
  const libCounts = {};
  items.forEach(item => {
    const lib = item.library_name || "Uncategorized";
    libCounts[lib] = (libCounts[lib] || 0) + 1;
  });
  // Order: libraries in Plex order, then Uncategorized if any
  const libTabs = libraries
    .filter(l => libCounts[l.title])
    .map(l => ({ id: l.title, label: l.title, count: libCounts[l.title] }));
  if (libCounts["Uncategorized"]) {
    libTabs.push({ id: "Uncategorized", label: "Uncategorized", count: libCounts["Uncategorized"] });
  }

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <h2><Bookmark size={20} style={{ verticalAlign: -3, marginRight: 6 }} />Watchlist</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select value={sort} onChange={e => setSort(e.target.value)} style={{ fontSize: 12, padding: "4px 8px" }}>
              {WATCHLIST_SORTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={load}>
              <RefreshCw size={13} />
            </button>
          </div>
        </div>
        <p>Your Plex watchlist — titles you want to watch later</p>
      </div>

      <div className="watchlist-subtabs">
        <button
          className={`wl-subtab ${filterLib === "all" ? "active" : ""}`}
          onClick={() => setFilterLib("all")}
        >
          All <span className="wl-count">{items.length}</span>
        </button>
        {libTabs.map(tab => (
          <button
            key={tab.id}
            className={`wl-subtab ${filterLib === tab.id ? "active" : ""}`}
            onClick={() => setFilterLib(tab.id)}
          >
            {tab.label} <span className="wl-count">{tab.count}</span>
          </button>
        ))}
      </div>

      <div className="page-body">
        {loading ? <LoadingState message="Loading watchlist..." /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         items.length === 0 ? <EmptyState icon={Bookmark} title="Watchlist empty" message="Add titles to your Plex watchlist to see them here." /> :
         <div className="card-grid">
           {items
             .filter(item => filterLib === "all" || (item.library_name || "Uncategorized") === filterLib)
             .map((item, i) => (
             <div className="media-card watchlist-card" key={`${item.tmdb_id}-${i}`} onClick={() => onCardClick(item)}>
               <div className="card-poster">
                 {item.poster_url ? (
                   <img src={item.poster_url} alt={item.title} loading="lazy" />
                 ) : (
                   <div className="no-poster"><Film size={32} /></div>
                 )}
                 <div className="card-overlay">
                   <div className="card-actions-row">
                     {item.in_library && item.plex_url && (
                       <button className="card-action-btn plex-btn" title="Play in Plex" onClick={(e) => { e.stopPropagation(); window.open(item.plex_url, "_blank"); }}>
                         <Play size={14} fill="currentColor" />
                       </button>
                     )}
                     {item.in_library && (
                       <button
                         className={`card-action-btn ${playResult?.id === item.tmdb_id ? (playResult.success ? "plex-btn" : "dismiss-btn") : "info-btn"}`}
                         title="Watch Now on device"
                         disabled={playingId === item.tmdb_id}
                         onClick={(e) => { e.stopPropagation(); handlePlay(item); }}
                       >
                         {playingId === item.tmdb_id ? <Loader2 size={14} className="spinner" /> :
                          playResult?.id === item.tmdb_id && playResult.success ? <CheckCircle2 size={14} /> :
                          <Monitor size={14} />}
                       </button>
                     )}
                     <button
                       className="card-action-btn dismiss-btn"
                       title="Remove from Watchlist"
                       disabled={removing === item.tmdb_id}
                       onClick={(e) => { e.stopPropagation(); handleRemove(item); }}
                     >
                       {removing === item.tmdb_id ? <Loader2 size={14} className="spinner" /> : <XCircle size={14} />}
                     </button>
                   </div>
                 </div>
                 {item.in_library && <div className="card-badge library-badge">In Library</div>}
                 {item.is_watched && <div className="card-badge watched-badge"><Eye size={10} /> Watched</div>}
               </div>
               <div className="card-info">
                 <div className="card-title">{item.title}</div>
                 <div className="card-meta">
                   {item.year && <span>{item.year}</span>}
                   {item.vote_average > 0 && <><span className="sep">·</span><span>★ {item.vote_average.toFixed(1)}</span></>}
                   <span className="sep">·</span>
                   <span style={{ color: item.media_type === "movie" ? "var(--blue)" : "var(--purple)", fontSize: 10, textTransform: "uppercase", fontWeight: 600 }}>
                     {item.media_type === "movie" ? "Movie" : "TV"}
                   </span>
                 </div>
                 {item.genres?.length > 0 && (
                   <div className="card-genres">{item.genres.slice(0, 3).join(" · ")}</div>
                 )}
               </div>
             </div>
           ))}
         </div>}
      </div>
    </>
  );
}

export default WatchlistPage;
