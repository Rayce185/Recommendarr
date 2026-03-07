import { useState, useEffect, useCallback } from "react";
import { Search, Film, Tv, Loader2, Star } from "lucide-react";
import { api } from "../api.js";
import Skeleton from "../components/Skeleton.jsx";
import { posterUrl } from "../utils.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";
import CustomSelect from "../components/CustomSelect.jsx";

function BrowsePage({ onCardClick }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState("discover"); // "search" | "discover"
  const [mediaType, setMediaType] = useState("movie");
  const [genres, setGenres] = useState({ movie_genres: [], tv_genres: [] });
  const [selectedGenre, setSelectedGenre] = useState(null);
  const [yearRange, setYearRange] = useState(null); // { min, max }
  const [sortBy, setSortBy] = useState("popularity.desc");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalResults, setTotalResults] = useState(0);
  const searchInputRef = useRef(null);

  // Load genres on mount
  useEffect(() => {
    api.browseGenres().then(setGenres).catch(() => {});
  }, []);

  // Auto-discover on filter change
  useEffect(() => {
    if (mode === "discover") doDiscover(1);
  }, [mediaType, selectedGenre, yearRange, sortBy]);

  const doSearch = async (p = 1) => {
    if (!query.trim()) return;
    setLoading(true);
    setMode("search");
    try {
      const data = await api.browseSearch(query, p);
      if (p === 1) setResults(data.results);
      else setResults(prev => [...prev, ...data.results]);
      setPage(p);
      setTotalPages(5); // TMDB multi-search doesn't return total_pages reliably
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const doDiscover = async (p = 1) => {
    setLoading(true);
    try {
      const data = await api.browseDiscover({
        media_type: mediaType,
        genre_id: selectedGenre,
        year_min: yearRange?.min,
        year_max: yearRange?.max,
        sort_by: sortBy,
        page: p,
      });
      if (p === 1) setResults(data.results);
      else setResults(prev => [...prev, ...data.results]);
      setPage(p);
      setTotalPages(data.total_pages || 1);
      setTotalResults(data.total_results || 0);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const loadMore = () => {
    if (page >= totalPages) return;
    if (mode === "search") doSearch(page + 1);
    else doDiscover(page + 1);
  };

  const clearSearch = () => {
    setQuery("");
    setMode("discover");
    doDiscover(1);
  };

  const currentGenres = mediaType === "movie" ? genres.movie_genres : genres.tv_genres;

  const decades = [
    { label: "2020s", min: 2020, max: 2029 },
    { label: "2010s", min: 2010, max: 2019 },
    { label: "2000s", min: 2000, max: 2009 },
    { label: "90s", min: 1990, max: 1999 },
    { label: "80s", min: 1980, max: 1989 },
    { label: "Classic", min: 1900, max: 1979 },
  ];

  const sortOptions = [
    { value: "popularity.desc", label: "Most Popular" },
    { value: "vote_average.desc", label: "Highest Rated" },
    { value: "primary_release_date.desc", label: "Newest First" },
    { value: "primary_release_date.asc", label: "Oldest First" },
    { value: "revenue.desc", label: "Highest Revenue" },
  ];

  return (
    <div className="page-content">
      <div className="page-header">
        <h1 className="page-title"><Search size={22} style={{ marginRight: 8 }} />Browse & Search</h1>
        <p className="page-subtitle">Search TMDB or discover by genre, decade, and more</p>
      </div>

      {/* Search bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search movies & TV shows..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") doSearch(1); }}
            style={{
              width: "100%", padding: "10px 40px 10px 14px", borderRadius: 10, border: "1px solid var(--border)",
              background: "var(--bg-surface)", color: "var(--text-primary)", fontSize: 14, outline: "none",
              boxSizing: "border-box",
            }}
          />
          {query && (
            <button onClick={clearSearch} style={{
              position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)",
              background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", padding: 4,
            }}><X size={14} /></button>
          )}
        </div>
        <button onClick={() => doSearch(1)} style={{
          padding: "10px 20px", borderRadius: 10, border: "none", background: "var(--accent)", color: "#000",
          fontWeight: 600, cursor: "pointer", fontSize: 14, display: "flex", alignItems: "center", gap: 6,
        }}>
          <Search size={14} /> Search
        </button>
      </div>

      {/* Filters — only show in discover mode */}
      {mode === "discover" && (
        <div style={{ marginBottom: 20 }}>
          {/* Media type + Sort */}
          <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
            <div style={{ display: "flex", gap: 2, background: "var(--bg-surface)", borderRadius: 8, padding: 2 }}>
              {["movie", "tv"].map(mt => (
                <button key={mt} onClick={() => { setMediaType(mt); setSelectedGenre(null); }}
                  style={{
                    padding: "6px 14px", borderRadius: 6, border: "none", fontSize: 12, fontWeight: 600, cursor: "pointer",
                    background: mediaType === mt ? "var(--accent)" : "transparent",
                    color: mediaType === mt ? "#000" : "var(--text-secondary)",
                  }}>
                  {mt === "movie" ? "Movies" : "TV Shows"}
                </button>
              ))}
            </div>

            <select value={sortBy} onChange={e => setSortBy(e.target.value)}
              style={{
                padding: "6px 10px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-surface)",
                color: "var(--text-secondary)", fontSize: 12, outline: "none",
              }}>
              {sortOptions.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>

            {totalResults > 0 && (
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: "auto" }}>
                {totalResults.toLocaleString()} results
              </span>
            )}
          </div>

          {/* Decades */}
          <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
            <button onClick={() => setYearRange(null)}
              className={`filter-chip ${!yearRange ? "chip-active" : ""}`}>All Years</button>
            {decades.map(d => (
              <button key={d.label} onClick={() => setYearRange(yearRange?.min === d.min ? null : { min: d.min, max: d.max })}
                className={`filter-chip ${yearRange?.min === d.min ? "chip-active" : ""}`}>{d.label}</button>
            ))}
          </div>

          {/* Genres */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button onClick={() => setSelectedGenre(null)}
              className={`filter-chip ${!selectedGenre ? "chip-active" : ""}`}>All Genres</button>
            {currentGenres.map(g => (
              <button key={g.id} onClick={() => setSelectedGenre(selectedGenre === g.id ? null : g.id)}
                className={`filter-chip ${selectedGenre === g.id ? "chip-active" : ""}`}>{g.name}</button>
            ))}
          </div>
        </div>
      )}

      {mode === "search" && query && (
        <div style={{ marginBottom: 16 }}>
          <button onClick={clearSearch} className="filter-chip chip-active" style={{ cursor: "pointer" }}>
            <X size={12} /> Clear search — back to Browse
          </button>
        </div>
      )}

      {/* Results Grid */}
      {loading && results.length === 0 ? (
        <Skeleton.CardGrid count={8} />
      ) : results.length === 0 ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--text-muted)" }}>
          {mode === "search" ? "No results found." : "No titles match these filters."}
        </div>
      ) : (
        <>
          <div className="card-grid">
            {results.map((item, idx) => (
              <div key={`${item.tmdb_id}-${idx}`} className="media-card" onClick={() => onCardClick(item)}>
                <div className="card-poster">
                  {item.poster_url ? (
                    <img src={item.poster_url} alt={item.title} loading="lazy" />
                  ) : (
                    <div style={{ aspectRatio: "2/3", background: "var(--bg-elevated)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", fontSize: 12 }}>No Poster</div>
                  )}
                  {item.in_library && item.is_watched && <div className="card-badge badge-watched"><Eye size={10} /> Seen</div>}
                  {item.in_library && !item.is_watched && <div className="card-badge badge-library">In Library</div>}
                  {item.vote_average > 0 && (
                    <div style={{ position: "absolute", bottom: 6, right: 6, background: "rgba(0,0,0,0.75)", borderRadius: 6, padding: "2px 6px", fontSize: 11, fontWeight: 600, color: item.vote_average >= 7 ? "#2ecc71" : item.vote_average >= 5 ? "#f59e0b" : "#ef4444", display: "flex", alignItems: "center", gap: 3 }}>
                      <Star size={10} /> {item.vote_average.toFixed(1)}
                    </div>
                  )}
                </div>
                <div className="card-info">
                  <div className="card-title">{item.title}</div>
                  <div className="card-meta">
                    {item.year && <span>{item.year}</span>}
                    {item.media_type && <><span className="sep">·</span><span>{item.media_type === "movie" ? "Movie" : "Series"}</span></>}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Load More */}
          {page < totalPages && (
            <div style={{ textAlign: "center", marginTop: 24 }}>
              <button onClick={loadMore} disabled={loading} style={{
                padding: "10px 32px", borderRadius: 10, border: "1px solid var(--border)", background: "var(--bg-surface)",
                color: "var(--text-primary)", fontSize: 14, fontWeight: 500, cursor: "pointer",
              }}>
                {loading ? <><Loader2 size={14} className="spinning" /> Loading...</> : "Load More"}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default BrowsePage;
