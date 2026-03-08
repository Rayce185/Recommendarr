import { Film, Play, Download, Bookmark, ExternalLink, ThumbsUp, ThumbsDown, EyeOff, Eye } from "lucide-react";
import { api, authFetch, API_BASE } from "../api.js";
import { posterUrl, scorePercent, scoreColor } from "../utils.js";

function MediaCard({ item, onClick, onFeedback }) {
  const poster = posterUrl(item.poster_url || item.poster_path);
  const sc = item.score != null ? scorePercent(item.score) : null;
  const typeColor = item.media_type === "movie" ? "var(--blue)" : "var(--purple)";

  return (
    <div className="media-card" onClick={() => onClick(item)}>
      <div className="card-poster">
        {poster ? (
          <img src={poster} alt={item.title} loading="lazy" />
        ) : (
          <div className="no-poster"><Film size={32} /></div>
        )}
        <div className="card-overlay">
          <div className="card-actions-row">
            {item.plex_url && (
              <button className="card-action-btn plex-btn" title="Play in Plex" onClick={(e) => { e.stopPropagation(); window.open(item.plex_url, "_blank"); }}>
                <Play size={14} fill="currentColor" />
              </button>
            )}
            {!item.in_library && item.tmdb_id && (
              <button className="card-action-btn seerr-btn" title="Add to Library" onClick={async (e) => {
                e.stopPropagation();
                const btn = e.target.closest(".card-action-btn");
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border:2px solid transparent;border-top-color:currentColor;border-radius:50%;animation:spin .6s linear infinite;display:inline-block"></span>';
                try {
                  const res = await api.addToLibrary(item.tmdb_id, item.media_type || "movie");
                  btn.style.background = "var(--green)";
                  btn.innerHTML = res.already_exists ? "✓" : "✓";
                  btn.title = res.message;
                } catch (err) {
                  btn.style.background = "var(--red)";
                  btn.innerHTML = "✗";
                  btn.title = err.message;
                }
              }}>
                <Download size={14} />
              </button>
            )}
            <button className="card-action-btn watchlist-btn" title="Add to Plex Watchlist" onClick={(e) => {
              e.stopPropagation();
              api.watchlistAdd(item.tmdb_id, item.media_type || "movie").then(() => {
                e.target.closest(".card-action-btn").style.background = "var(--green)";
              });
            }}>
              <Bookmark size={14} />
            </button>
            <button className="card-action-btn info-btn" title="Details" onClick={(e) => { e.stopPropagation(); onClick(item); }}>
              <ExternalLink size={14} />
            </button>
          </div>
          {onFeedback && (
            <div className="card-feedback-row">
              <button
                className={`card-fb-btn fb-up ${item.user_feedback === "up" ? "active" : ""}`}
                title="Like — recommend more like this"
                onClick={(e) => { e.stopPropagation(); onFeedback(item, item.user_feedback === "up" ? null : "up"); }}
              ><ThumbsUp size={13} /></button>
              <button
                className={`card-fb-btn fb-down ${item.user_feedback === "down" ? "active" : ""}`}
                title="Dislike — recommend less like this"
                onClick={(e) => { e.stopPropagation(); onFeedback(item, item.user_feedback === "down" ? null : "down"); }}
              ><ThumbsDown size={13} /></button>
              <button
                className={`card-fb-btn fb-dismiss ${item.user_feedback === "dismiss" ? "active" : ""}`}
                title="Dismiss — hide this recommendation"
                onClick={(e) => { e.stopPropagation(); onFeedback(item, "dismiss"); }}
              ><EyeOff size={13} /></button>
            </div>
          )}
        </div>
        {sc != null && (
          <div className="card-score" style={{ color: scoreColor(item.score), borderColor: scoreColor(item.score) }}>
            {sc}%
          </div>
        )}
        {item.user_feedback === "up" && <div className="card-badge badge-liked"><ThumbsUp size={10} /></div>}
        {item.user_feedback === "down" && <div className="card-badge badge-disliked"><ThumbsDown size={10} /></div>}
        {item.is_watched && <div className="card-badge badge-watched"><Eye size={10} /> Seen</div>}
        {item.in_library === true && !item.is_watched && <div className="card-badge badge-library">In Library</div>}
        {item.in_library === false && <div className="card-badge badge-grab">Not in Library</div>}
      </div>
      <div className="card-info">
        <h3>{item.title}</h3>
        <div className="card-meta">
          <span className="type-dot" style={{ background: typeColor }} />
          <span>{item.media_type === "movie" ? "Movie" : "Series"}</span>
          {item.year && <><span>·</span><span>{item.year}</span></>}
        </div>
        {item.explanation_signals?.length > 0 && item.explanation_signals[0]?.startsWith("Because") && (
          <div className="card-trace">{item.explanation_signals[0]}</div>
        )}
      </div>
    </div>
  );
}

export default MediaCard;
