import { useState, useEffect, useCallback } from "react";
import { History, Film, Tv, Clock, ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "../api.js";
import { posterUrl, scorePercent, scoreColor } from "../utils.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";

const MODE_LABELS = {
  tonight: "Watch Tonight",
  grab: "Worth Grabbing",
  rediscover: "Rediscover",
  mood: "Mood Match",
  group: "Group Night",
};

const PAGE_SIZE = 50;

function HistoryPage({ user, onCardClick }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [offset, setOffset] = useState(0);
  const [modeFilter, setModeFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const load = useCallback(() => {
    if (!user?.username) return;
    setLoading(true);
    setError(null);
    const opts = { limit: PAGE_SIZE, offset, mode: modeFilter || undefined, media_type: typeFilter || undefined };
    Promise.all([
      api.recHistory(user.username, opts),
      offset === 0 ? api.recHistoryStats(user.username) : Promise.resolve(null),
    ])
      .then(([histData, statsData]) => {
        setItems(histData.items || []);
        setTotal(histData.total || 0);
        if (statsData) setStats(statsData);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user, offset, modeFilter, typeFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setOffset(0); }, [modeFilter, typeFilter]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  if (loading && items.length === 0) return <LoadingState message="Loading recommendation history..." />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="page-content">
      <div className="page-header">
        <h2><History size={22} style={{ marginRight: 8 }} />Recommendation History</h2>
        {stats && (
          <div className="history-stats">
            <span className="stat-badge">{stats.total} total</span>
            <span className="stat-badge">{stats.unique_titles} unique</span>
            {stats.watched > 0 && <span className="stat-badge good">✓ {stats.watched} watched</span>}
            {stats.requested > 0 && <span className="stat-badge">{stats.requested} requested</span>}
          </div>
        )}
      </div>

      <div className="history-filters">
        <select value={modeFilter} onChange={e => setModeFilter(e.target.value)} className="filter-select">
          <option value="">All Modes</option>
          {Object.entries(MODE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="filter-select">
          <option value="">All Types</option>
          <option value="movie">Movies</option>
          <option value="tv">TV Shows</option>
        </select>
      </div>

      {items.length === 0 ? (
        <EmptyState icon={History} message="No recommendation history yet" detail="Recommendations will appear here as you use the app." />
      ) : (
        <>
          <div className="history-list">
            {items.map((item) => (
              <div key={item.id} className="history-item" onClick={() => onCardClick && onCardClick({ ...item, tmdb_id: item.tmdb_id, media_type: item.media_type })}>
                <div className="history-poster">
                  {item.poster_url ? (
                    <img src={item.poster_url} alt={item.title} loading="lazy" />
                  ) : (
                    <div className="no-poster-sm"><Film size={20} /></div>
                  )}
                </div>
                <div className="history-info">
                  <div className="history-title">
                    {item.title || `TMDB #${item.tmdb_id}`}
                    {item.year && <span className="history-year"> ({item.year})</span>}
                  </div>
                  <div className="history-meta">
                    <span className={`mode-badge mode-${item.mode}`}>{MODE_LABELS[item.mode] || item.mode}</span>
                    <span className="type-badge">{item.media_type === "movie" ? <Film size={12} /> : <Tv size={12} />} {item.media_type}</span>
                    {item.score != null && (
                      <span className="score-badge" style={{ color: scoreColor(item.score) }}>
                        {scorePercent(item.score)}%
                      </span>
                    )}
                    <span className="time-badge">
                      <Clock size={12} /> {formatTimeAgo(item.created_at)}
                    </span>
                  </div>
                  {item.explanation && (
                    <div className="history-explanation">{item.explanation}</div>
                  )}
                </div>
                <div className="history-actions">
                  {item.was_watched && <span className="action-icon watched" title="Watched">✓</span>}
                  {item.was_requested && <span className="action-icon requested" title="Requested">↓</span>}
                </div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                <ChevronLeft size={16} /> Prev
              </button>
              <span className="page-info">Page {currentPage} of {totalPages}</span>
              <button disabled={currentPage >= totalPages} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next <ChevronRight size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function formatTimeAgo(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

export default HistoryPage;
