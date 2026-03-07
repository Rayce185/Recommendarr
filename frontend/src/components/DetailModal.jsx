import { useState, useEffect, useCallback } from "react";
import { X, Star, Clock, Play, Download, ExternalLink, ThumbsUp, ThumbsDown, Bookmark,
  CheckCircle2, XCircle, Film, Layers, ChevronDown, Loader2, Eye, Heart, MapPin, Sparkles } from "lucide-react";
import { api, authFetch, API_BASE } from "../api.js";
import { posterUrl, fixPosterUrl, scoreColor, scorePercent } from "../utils.js";
import WatchProviders from "./WatchProviders.jsx";
import WhyNotPanel from "./WhyNotPanel.jsx";

function DetailModal({ item, detail, loading: detailLoading, onClose, onRequest, requesting, requestResult, onFeedback, user }) {
  const d = detail || item;
  const poster = posterUrl(d.poster_url || item.poster_url, "w500");
  const backdrop = d.backdrop_url ? fixPosterUrl(d.backdrop_url) : null;
  const hasTrailer = d.trailer_url;
  const [collectionData, setCollectionData] = useState(null);
  const [collLoading, setCollLoading] = useState(false);
  const [collRequestingId, setCollRequestingId] = useState(null);

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Fetch collection info for movies
  useEffect(() => {
    const tmdbId = d.tmdb_id || item.tmdb_id;
    const mediaType = item.media_type || d.media_type;
    if (mediaType !== "movie" || !tmdbId) return;
    setCollLoading(true);
    api.collectionFor(tmdbId)
      .then(data => setCollectionData(data))
      .catch(() => setCollectionData(null))
      .finally(() => setCollLoading(false));
  }, [d.tmdb_id, item.tmdb_id]);

  const handleCollectionRequest = async (partTmdbId) => {
    setCollRequestingId(partTmdbId);
    try {
      await api.addToLibrary(partTmdbId, "movie");
      setCollectionData(prev => prev ? {
        ...prev,
        parts: prev.parts.map(p => p.tmdb_id === partTmdbId ? { ...p, requested: true } : p),
        missing: prev.missing.map(p => p.tmdb_id === partTmdbId ? { ...p, requested: true } : p),
      } : null);
    } catch (e) { console.error("Collection request failed:", e); }
    setCollRequestingId(null);
  };

  const breakdownLabels = { genre: "Genre Match", keyword: "Theme Match", rating: "Rating Fit", personnel: "Cast/Crew Match", popularity: "Popularity", mood: "Mood Fit", staleness: "Time Since Watched", completion: "Watch Completion" };

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-container">
        <div className="modal-backdrop">
          {backdrop ? <img src={backdrop} alt="" /> : <div style={{ background: "var(--bg-elevated)", height: "100%" }} />}
          <div className="backdrop-gradient" />
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <div className="modal-top-row">
            <div className="modal-poster">
              {poster ? <img src={poster} alt={d.title} /> : <div style={{ background: "var(--bg-elevated)", aspectRatio: "2/3" }} />}
            </div>
            <div className="modal-title-block">
              <h2>{d.title}</h2>
              <div className="modal-title-meta">
                {d.year && <span>{d.year}</span>}
                {d.runtime && <><span className="sep">·</span><span>{d.runtime} min</span></>}
                {d.episode_runtime && !d.runtime && <><span className="sep">·</span><span>{d.episode_runtime} min/ep</span></>}
                {d.vote_average > 0 && <><span className="sep">·</span><span style={{ color: d.vote_average >= 7 ? "#2ecc71" : d.vote_average >= 5 ? "#f59e0b" : "#ef4444", fontWeight: 600 }}>★ {d.vote_average.toFixed(1)}</span></>}
                {d.content_rating && <><span className="sep">·</span><span style={{ padding: "1px 6px", border: "1px solid var(--text-muted)", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>{d.content_rating}</span></>}
                {d.media_type && <><span className="sep">·</span><span>{d.media_type === "movie" ? "Movie" : "Series"}</span></>}
                {d.status && <><span className="sep">·</span><span style={{ color: d.status === "Ended" || d.status === "Canceled" ? "var(--text-muted)" : "#2ecc71" }}>{d.status}</span></>}
              </div>
              {d.tagline && <div style={{ fontSize: 13, fontStyle: "italic", color: "var(--text-muted)", marginTop: 4 }}>{d.tagline}</div>}
              {detailLoading && !detail && (
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, color: "var(--text-muted)", fontSize: 12 }}>
                  <Loader2 size={14} className="spinning" /> Loading details...
                </div>
              )}
              {(d.number_of_seasons || d.number_of_episodes) && (
                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6, display: "flex", gap: 12 }}>
                  {d.number_of_seasons && <span>{d.number_of_seasons} Season{d.number_of_seasons !== 1 ? "s" : ""}</span>}
                  {d.number_of_episodes && <span>{d.number_of_episodes} Episode{d.number_of_episodes !== 1 ? "s" : ""}</span>}
                </div>
              )}
              <div className="modal-genres">
                {(d.genres || []).slice(0, 6).map((g, i) => <span className="genre-tag" key={i}>{typeof g === 'string' ? g : g.name}</span>)}
              </div>
            </div>
          </div>

          {collectionData && (
            <div className="modal-collection-badge">
              <Layers size={15} />
              <span className="coll-name">{collectionData.name}</span>
              <span className="coll-progress">{collectionData.watched_count}/{collectionData.total_parts} watched</span>
              <div className="coll-bar"><div className="coll-bar-fill" style={{ width: `${collectionData.completion_pct}%` }} /></div>
            </div>
          )}

          {item.explanation && (
            <div className="modal-explanation">
              <Sparkles size={16} />
              <span>{item.explanation}</span>
            </div>
          )}

          {/* Because You Watched traces */}
          {item.explanation_signals?.some(s => s.startsWith("Because")) && (
            <div className="modal-traces">
              {item.explanation_signals.filter(s => s.startsWith("Because")).map((t, i) => (
                <div key={i} className="trace-item">{t}</div>
              ))}
            </div>
          )}

          {/* External Ratings */}
          {(d.vote_average > 0 || d.imdb_id) && (
            <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
              {d.vote_average > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg-card)", padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)" }}>
                  <span style={{ fontSize: 18, fontWeight: 700, color: d.vote_average >= 7 ? "#2ecc71" : d.vote_average >= 5 ? "#f59e0b" : "#ef4444" }}>
                    {d.vote_average.toFixed(1)}
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.2 }}>
                    <span style={{ fontSize: 10, fontWeight: 600, color: "var(--text-secondary)", textTransform: "uppercase" }}>TMDB</span>
                    <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{d.vote_count?.toLocaleString()} votes</span>
                  </div>
                </div>
              )}
              {d.imdb_id && (
                <a href={`https://www.imdb.com/title/${d.imdb_id}`} target="_blank" rel="noopener noreferrer"
                   style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg-card)", padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)", textDecoration: "none", color: "var(--text-secondary)", fontSize: 12, fontWeight: 600 }}>
                  <span style={{ color: "#f5c518", fontWeight: 700, fontSize: 14 }}>IMDb</span>
                  <ExternalLink size={10} />
                </a>
              )}
              {d.tmdb_id && (
                <a href={`https://www.themoviedb.org/${item.media_type || d.media_type || "movie"}/${d.tmdb_id}`} target="_blank" rel="noopener noreferrer"
                   style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg-card)", padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)", textDecoration: "none", color: "var(--text-secondary)", fontSize: 12, fontWeight: 600 }}>
                  <span style={{ color: "#01d277", fontWeight: 700, fontSize: 13 }}>TMDB</span>
                  <ExternalLink size={10} />
                </a>
              )}
            </div>
          )}

          {item.score_breakdown && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>Why we recommended this</div>
              <div className="modal-score-row">
              {Object.entries(item.score_breakdown).map(([key, val]) => (
                <div className="score-pill" key={key} title={`How well this title matches your taste profile for ${(breakdownLabels[key] || key).toLowerCase()}`}>
                  <span className="score-dot" style={{ background: val > 0.5 ? "var(--green)" : val > 0 ? "var(--accent)" : "var(--text-muted)" }} />
                  {breakdownLabels[key] || key}: {Math.round(Math.min(val, 1) * 100)}%
                </div>
              ))}
            </div>
            </div>
          )}

          {d.overview && <p className="modal-overview">{d.overview}</p>}

          {hasTrailer && (
            <div className="modal-trailer">
              <iframe src={d.trailer_url} allow="autoplay; encrypted-media" allowFullScreen title="Trailer" />
            </div>
          )}

          <WatchProviders providers={d.watch_providers} link={d.watch_providers_link} />

          {/* Networks / Studios */}
          {((d.networks && d.networks.length > 0) || (d.production_companies && d.production_companies.length > 0)) && (
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 16 }}>
              {d.networks && d.networks.length > 0 && (
                <div style={{ marginBottom: 4 }}><span style={{ fontWeight: 600 }}>Network:</span> {d.networks.join(", ")}</div>
              )}
              {d.production_companies && d.production_companies.length > 0 && (
                <div><span style={{ fontWeight: 600 }}>Studio:</span> {d.production_companies.slice(0, 3).join(", ")}</div>
              )}
            </div>
          )}

          {d.keywords && d.keywords.length > 0 && (
            <div className="modal-keywords">
              {d.keywords.slice(0, 15).map((kw, i) => <span className="keyword-tag" key={i}>{typeof kw === 'string' ? kw : kw.name}</span>)}
            </div>
          )}

          {(d.directors?.length > 0 || d.cast?.length > 0) && (
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 20 }}>
              {d.directors?.length > 0 && <div><strong>Director:</strong> {d.directors.join(", ")}</div>}
              {d.cast?.length > 0 && <div style={{ marginTop: 4 }}><strong>Cast:</strong> {d.cast.slice(0, 5).map(c => typeof c === "string" ? c : c.name || c.character || "").filter(Boolean).join(", ")}</div>}
            </div>
          )}

          {/* Watched / In Library badge */}
          {(item.in_library === true || d.in_library === true) && (
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 8, background: "rgba(46,204,113,0.12)", border: "1px solid rgba(46,204,113,0.3)", color: "#2ecc71", fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
              <CheckCircle2 size={14} /> In Your Library
            </div>
          )}

          {/* Feedback buttons */}
          {onFeedback && (
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button className={`btn btn-sm ${item.user_feedback === "up" ? "btn-success" : "btn-secondary"}`}
                onClick={() => onFeedback(item, item.user_feedback === "up" ? null : "up")}
                style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 14px", fontSize: 13 }}>
                <ThumbsUp size={14} /> {item.user_feedback === "up" ? "Liked" : "Like"}
              </button>
              <button className={`btn btn-sm ${item.user_feedback === "down" ? "btn-danger" : "btn-secondary"}`}
                onClick={() => onFeedback(item, item.user_feedback === "down" ? null : "down")}
                style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 14px", fontSize: 13, ...(item.user_feedback === "down" ? { background: "rgba(231,76,60,0.15)", borderColor: "rgba(231,76,60,0.3)", color: "#e74c3c" } : {}) }}>
                <ThumbsDown size={14} /> {item.user_feedback === "down" ? "Disliked" : "Dislike"}
              </button>
            </div>
          )}

          {/* Why Not? — negative transparency */}
          {user && <WhyNotPanel tmdbId={d.tmdb_id || item.tmdb_id} mediaType={item.media_type || d.media_type || "movie"} user={user} />}

          <div className="modal-actions">
            {(item.in_library === true || d.in_library === true) && (item.plex_url || d.plex_url) && (
              <button className="btn btn-primary" onClick={() => window.open(item.plex_url || d.plex_url, "_blank")}>
                <Play size={15} /> Play on Plex
              </button>
            )}
            {/* Add to Library — show unless explicitly in library */}
            {item.in_library !== true && d.in_library !== true && (
              <button
                className={`btn ${requestResult?.success ? "btn-success" : "btn-primary"}`}
                onClick={() => onRequest(d.tmdb_id || item.tmdb_id, item.media_type)}
                disabled={requesting || requestResult?.success}
              >
                {requesting ? <><Loader2 size={15} className="spinner" /> Adding...</> :
                 requestResult?.success ? <><CheckCircle2 size={15} /> {requestResult.already_exists ? "Already in Library" : "Added!"}</> :
                 <><Download size={15} /> Add to Library</>}
              </button>
            )}
            <button className="btn btn-secondary watchlist-modal-btn" onClick={() => {
              api.watchlistAdd(d.tmdb_id || item.tmdb_id, item.media_type || "movie").then(() => {
                const btn = document.querySelector(".watchlist-modal-btn");
                if (btn) { btn.innerHTML = "✓ Added!"; btn.disabled = true; btn.classList.add("btn-success"); }
              });
            }}>
              <Bookmark size={15} /> Plex Watchlist
            </button>
            <button className="btn btn-secondary" onClick={() => window.open(`https://www.themoviedb.org/${item.media_type || "movie"}/${d.tmdb_id || item.tmdb_id}`, "_blank")}>
              <ExternalLink size={15} /> TMDB
            </button>
            {d.imdb_id && (
              <button className="btn btn-secondary" onClick={() => window.open(`https://www.imdb.com/title/${d.imdb_id}`, "_blank")}>
                <ExternalLink size={15} /> IMDb
              </button>
            )}
            <button className="btn btn-secondary" onClick={() => window.open(`https://trakt.tv/search/tmdb/${d.tmdb_id || item.tmdb_id}?id_type=${item.media_type === "tv" ? "show" : "movie"}`, "_blank")}>
              <ExternalLink size={15} /> Trakt
            </button>
          </div>

          {collectionData && collectionData.missing.length > 0 && (
            <div className="modal-collection-missing">
              <h4><Layers size={14} /> Missing from {collectionData.name}</h4>
              <div className="coll-missing-grid">
                {collectionData.missing.map(p => (
                  <div className="coll-missing-item" key={p.tmdb_id}>
                    {p.poster_url ? <img src={p.poster_url} alt={p.title} /> : <div className="coll-missing-noposter" />}
                    <div className="coll-missing-info">
                      <span className="coll-missing-title">{p.title}</span>
                      <span className="coll-missing-year">{p.year || "TBA"}{p.vote_average ? ` · ★ ${p.vote_average.toFixed(1)}` : ""}</span>
                    </div>
                    <button
                      className={`btn btn-sm ${p.requested ? "btn-success" : "btn-primary"}`}
                      onClick={() => handleCollectionRequest(p.tmdb_id)}
                      disabled={collRequestingId === p.tmdb_id || p.requested || p.in_library}
                    >
                      {p.in_library ? <><CheckCircle2 size={12} /> In Library</> :
                       p.requested ? <><CheckCircle2 size={12} /> Requested</> :
                       collRequestingId === p.tmdb_id ? <Loader2 size={12} className="spinner" /> :
                       <><Download size={12} /> Request</>}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


export default DetailModal;
