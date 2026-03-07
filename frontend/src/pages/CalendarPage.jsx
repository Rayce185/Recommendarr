import { useState, useEffect, useMemo } from "react";
import { Calendar, Film, Tv, Loader2, Filter, ChevronLeft, ChevronRight, Eye } from "lucide-react";
import { api } from "../api.js";
import { posterUrl } from "../utils.js";

const DAYS_OPTIONS = [30, 60, 90, 180, 365];

function WeekGroup({ weekStart, items, onCardClick }) {
  const label = useMemo(() => {
    if (weekStart === "unknown") return "Date TBD";
    const d = new Date(weekStart + "T00:00:00");
    const end = new Date(d); end.setDate(end.getDate() + 6);
    const fmt = (dt) => dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    return `${fmt(d)} — ${fmt(end)}`;
  }, [weekStart]);

  return (
    <div className="calendar-week">
      <div className="calendar-week-label">{label}</div>
      <div className="calendar-week-items">
        {items.map((item, i) => (
          <CalendarCard key={`${item.tmdb_id}-${item.media_type}-${i}`} item={item} onClick={onCardClick} />
        ))}
      </div>
    </div>
  );
}

function CalendarCard({ item, onClick }) {
  const rd = item.release_date;
  const dateLabel = rd
    ? new Date(rd + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : "TBD";

  return (
    <div
      className={`calendar-card ${item.monitored ? "monitored" : ""}`}
      onClick={() => onClick?.({ tmdb_id: item.tmdb_id, media_type: item.media_type })}
    >
      <div className="calendar-card-poster">
        {item.poster ? (
          <img src={item.poster} alt={item.title} loading="lazy" />
        ) : (
          <div className="calendar-card-no-poster">
            {item.media_type === "movie" ? <Film size={24} /> : <Tv size={24} />}
          </div>
        )}
        {item.monitored && <span className="calendar-badge monitored-badge"><Eye size={10} /> Monitored</span>}
        <span className="calendar-badge date-badge">{dateLabel}</span>
      </div>
      <div className="calendar-card-info">
        <div className="calendar-card-title">{item.title}</div>
        {item.episode_title && (
          <div className="calendar-card-episode">
            S{String(item.season).padStart(2, "0")}E{String(item.episode).padStart(2, "0")} — {item.episode_title}
          </div>
        )}
        <div className="calendar-card-meta">
          {item.media_type === "movie" ? <Film size={11} /> : <Tv size={11} />}
          <span>{item.media_type === "movie" ? "Movie" : "TV"}</span>
          {item.vote_average > 0 && <span>★ {item.vote_average.toFixed(1)}</span>}
        </div>
      </div>
    </div>
  );
}

export default function CalendarPage({ onCardClick }) {
  const [items, setItems] = useState([]);
  const [weeks, setWeeks] = useState({});
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(90);
  const [mediaType, setMediaType] = useState("all");
  const [source, setSource] = useState("all");
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.calendar(days, mediaType, source)
      .then(data => {
        if (cancelled) return;
        setItems(data.items || []);
        setWeeks(data.weeks || {});
        setTotal(data.total || 0);
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [days, mediaType, source]);

  const sortedWeeks = useMemo(() => {
    return Object.entries(weeks)
      .filter(([k]) => k !== "unknown")
      .sort(([a], [b]) => a.localeCompare(b));
  }, [weeks]);

  const unknownItems = weeks["unknown"] || [];

  return (
    <div className="page-container">
      <div className="page-header">
        <h2><Calendar size={22} /> Coming Soon</h2>
        <span className="page-subtitle">{total} upcoming titles</span>
      </div>

      <div className="calendar-filters">
        <div className="filter-group">
          <label>Timeframe</label>
          <select value={days} onChange={e => setDays(Number(e.target.value))}>
            {DAYS_OPTIONS.map(d => <option key={d} value={d}>{d} days</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label>Type</label>
          <select value={mediaType} onChange={e => setMediaType(e.target.value)}>
            <option value="all">All</option>
            <option value="movie">Movies</option>
            <option value="tv">TV Shows</option>
          </select>
        </div>
        <div className="filter-group">
          <label>Source</label>
          <select value={source} onChange={e => setSource(e.target.value)}>
            <option value="all">TMDB + Monitored</option>
            <option value="tmdb">TMDB Only</option>
            <option value="monitored">Monitored Only</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="loading-state"><Loader2 size={28} className="spinner" /> Loading calendar…</div>
      ) : items.length === 0 ? (
        <div className="empty-state">No upcoming titles found for the selected filters.</div>
      ) : (
        <div className="calendar-timeline">
          {sortedWeeks.map(([weekKey, weekItems]) => (
            <WeekGroup key={weekKey} weekStart={weekKey} items={weekItems} onCardClick={onCardClick} />
          ))}
          {unknownItems.length > 0 && (
            <WeekGroup weekStart="unknown" items={unknownItems} onCardClick={onCardClick} />
          )}
        </div>
      )}
    </div>
  );
}
