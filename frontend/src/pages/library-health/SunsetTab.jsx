import { useState, useEffect, useCallback } from "react";
import { Sunset, ThumbsUp, ThumbsDown, Clock, Film, Tv, Loader2, AlertTriangle } from "lucide-react";
import { api } from "../../api.js";
import { posterUrl } from "../../utils.js";

function VitalityBar({ score }) {
  const pct = Math.min(100, Math.max(0, score));
  const color = pct >= 40 ? "var(--green)" : pct >= 15 ? "var(--orange, #f59e0b)" : "var(--red)";
  return (
    <div className="lh-vitality-bar">
      <div className="lh-vitality-fill" style={{ width: `${pct}%`, background: color }} />
      <span className="lh-vitality-label">{score.toFixed(1)}</span>
    </div>
  );
}

function GraceCountdown({ expiresAt }) {
  if (!expiresAt) return null;
  const ms = new Date(expiresAt) - Date.now();
  if (ms <= 0) return <span className="lh-grace expired">Grace expired</span>;
  const days = Math.floor(ms / 86400000);
  const hours = Math.floor((ms % 86400000) / 3600000);
  return <span className="lh-grace"><Clock size={11} /> {days}d {hours}h left</span>;
}

function SunsetCard({ item, onVote, voting }) {
  const poster = posterUrl(item.poster_url);
  const isMovie = item.media_type === "movie";
  return (
    <div className="lh-sunset-card">
      <div className="lh-sunset-poster">
        {poster ? <img src={poster} alt={item.title} loading="lazy" /> : <div className="no-poster"><Film size={24} /></div>}
      </div>
      <div className="lh-sunset-info">
        <div className="lh-sunset-header">
          <h4>{item.title} {item.year && <span className="lh-year">({item.year})</span>}</h4>
          <span className="lh-type-badge" style={{ background: isMovie ? "var(--blue)" : "var(--purple)" }}>
            {isMovie ? <Film size={10} /> : <Tv size={10} />} {isMovie ? "Movie" : "Series"}
          </span>
        </div>
        <VitalityBar score={item.vitality_score || 0} />
        <div className="lh-sunset-signals">
          {item.signals && Object.entries(item.signals).map(([k, v]) => (
            <span key={k} className="lh-signal" title={k}>{k}: {typeof v === "number" ? v.toFixed(1) : v}</span>
          ))}
        </div>
        <div className="lh-sunset-footer">
          <div className="lh-vote-row">
            <button className={`lh-vote-btn keep ${item.user_vote === "keep" ? "active" : ""}`} disabled={voting}
              onClick={() => onVote(item.tmdb_id, item.media_type, "keep")}>
              <ThumbsUp size={13} /> Keep {item.keep_votes > 0 && <span>({item.keep_votes})</span>}
            </button>
            <button className={`lh-vote-btn kick ${item.user_vote === "kick" ? "active" : ""}`} disabled={voting}
              onClick={() => onVote(item.tmdb_id, item.media_type, "kick")}>
              <ThumbsDown size={13} /> Kick {item.kick_votes > 0 && <span>({item.kick_votes})</span>}
            </button>
          </div>
          <GraceCountdown expiresAt={item.grace_expires_at} />
        </div>
      </div>
    </div>
  );
}

function SunsetTab({ user }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [voting, setVoting] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.healthSunset();
      setItems(data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleVote = async (tmdbId, mediaType, vote) => {
    setVoting(true);
    try {
      await api.healthVote(tmdbId, mediaType, vote);
      await load();
    } catch (err) {
      console.error("Vote failed:", err);
    } finally {
      setVoting(false);
    }
  };

  if (loading) return <div className="lh-loading"><Loader2 size={20} className="spin" /> Loading sunset zone...</div>;
  if (error) return <div className="lh-error"><AlertTriangle size={16} /> {error}</div>;

  if (!items.length) return (
    <div className="lh-empty">
      <Sunset size={32} style={{ opacity: 0.4 }} />
      <p>No items in the sunset zone. Your library is healthy!</p>
    </div>
  );

  return (
    <div className="lh-sunset-list">
      <div className="lh-sunset-header-bar">
        <span>{items.length} item{items.length !== 1 ? "s" : ""} in sunset zone</span>
      </div>
      {items.map(item => (
        <SunsetCard key={`${item.tmdb_id}-${item.media_type}`} item={item} onVote={handleVote} voting={voting} />
      ))}
    </div>
  );
}

export default SunsetTab;
