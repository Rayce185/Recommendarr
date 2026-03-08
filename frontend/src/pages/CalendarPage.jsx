import { useState, useEffect, useMemo, useRef } from "react";
import { Calendar, Film, Tv, Loader2, ChevronLeft, ChevronRight, Eye, X } from "lucide-react";
import { api } from "../api.js";

function getDaysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

function getMonthGrid(year, month) {
  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const startOffset = firstDay === 0 ? 6 : firstDay - 1; // Mon=0
  const daysInMonth = getDaysInMonth(year, month);
  const prevDays = getDaysInMonth(year, month - 1);
  const cells = [];
  // Previous month trailing days
  for (let i = startOffset - 1; i >= 0; i--) cells.push({ day: prevDays - i, current: false });
  // Current month
  for (let d = 1; d <= daysInMonth; d++) cells.push({ day: d, current: true });
  // Next month leading days
  while (cells.length % 7 !== 0) cells.push({ day: cells.length - startOffset - daysInMonth + 1, current: false });
  return cells;
}

function DayCell({ cell, dateKey, items, isToday, isSelected, onClick }) {
  const dayItems = items || [];
  const show = dayItems.slice(0, 3);
  const extra = dayItems.length - 3;
  return (
    <div className={`cal-day ${cell.current ? "" : "cal-day-dim"} ${isToday ? "cal-day-today" : ""} ${isSelected ? "cal-day-selected" : ""} ${dayItems.length > 0 ? "cal-day-has-items" : ""}`}
      onClick={() => dayItems.length > 0 && onClick?.(dateKey)}>
      <div className="cal-day-num">{cell.day}</div>
      {show.length > 0 && (
        <div className="cal-day-posters">
          {show.map((item, i) => (
            <div key={i} className="cal-day-thumb" title={item.title}>
              {item.poster ? <img src={item.poster} alt="" /> : <div className="cal-thumb-empty">{item.media_type === "movie" ? "M" : "T"}</div>}
              {item.monitored && <div className="cal-thumb-dot" />}
            </div>
          ))}
          {extra > 0 && <span className="cal-day-more">+{extra}</span>}
        </div>
      )}
    </div>
  );
}

function DayDetail({ dateKey, items, onCardClick, onClose }) {
  const label = new Date(dateKey + "T00:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  return (
    <div className="cal-detail">
      <div className="cal-detail-header">
        <span>{label} — {items.length} release{items.length !== 1 ? "s" : ""}</span>
        <button className="cal-detail-close" onClick={onClose}><X size={16} /></button>
      </div>
      <div className="cal-detail-grid">
        {items.map((item, i) => (
          <div key={i} className="cal-detail-card" onClick={() => onCardClick?.({ tmdb_id: item.tmdb_id, media_type: item.media_type })}>
            <div className="cal-detail-poster">
              {item.poster ? <img src={item.poster} alt={item.title} /> : <div className="cal-detail-no-poster">{item.media_type === "movie" ? <Film size={20} /> : <Tv size={20} />}</div>}
              {item.monitored && <span className="calendar-badge monitored-badge"><Eye size={9} /></span>}
            </div>
            <div className="cal-detail-info">
              <div className="cal-detail-title">{item.title}</div>
              {item.episode_title && <div className="cal-detail-ep">S{String(item.season).padStart(2,"0")}E{String(item.episode).padStart(2,"0")} — {item.episode_title}</div>}
              <div className="cal-detail-meta">{item.media_type === "movie" ? "Movie" : "TV"}{item.vote_average > 0 ? ` · ★${item.vote_average.toFixed(1)}` : ""}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function MonthPicker({ viewYear, viewMonth, onSelect, onClose }) {
  const ref = useRef(null);
  const [pickerYear, setPickerYear] = useState(viewYear);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  return (
    <div className="month-picker" ref={ref}>
      <div className="month-picker-year-nav">
        <button onClick={() => setPickerYear(y => y - 1)}><ChevronLeft size={14} /></button>
        <span>{pickerYear}</span>
        <button onClick={() => setPickerYear(y => y + 1)}><ChevronRight size={14} /></button>
      </div>
      <div className="month-picker-grid">
        {MONTHS.map((m, i) => (
          <button key={m}
            className={`month-picker-btn ${i === viewMonth && pickerYear === viewYear ? "month-picker-active" : ""} ${i === new Date().getMonth() && pickerYear === new Date().getFullYear() ? "month-picker-today" : ""}`}
            onClick={() => { onSelect(pickerYear, i); onClose(); }}>
            {m}
          </button>
        ))}
      </div>
    </div>
  );
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function CalendarPage({ onCardClick }) {
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mediaType, setMediaType] = useState("all");
  const [source, setSource] = useState("all");
  const [selectedDay, setSelectedDay] = useState(null);
  const [showPicker, setShowPicker] = useState(false);

  const monthLabel = new Date(viewYear, viewMonth).toLocaleDateString("en-US", { month: "long", year: "numeric" });

  const navMonth = (delta) => {
    let m = viewMonth + delta, y = viewYear;
    if (m > 11) { m = 0; y++; } else if (m < 0) { m = 11; y--; }
    setViewYear(y); setViewMonth(m); setSelectedDay(null);
  };

  // Fetch calendar data covering the full viewed month (including past days)
  useEffect(() => {
    const monthStart = new Date(viewYear, viewMonth, 1);
    const monthEnd = new Date(viewYear, viewMonth + 1, 0);
    const totalDays = Math.ceil((monthEnd - monthStart) / 86400000) + 1;
    const startDate = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-01`;
    setLoading(true);
    api.calendar(Math.min(totalDays, 365), mediaType, source, startDate)
      .then(d => setItems(d.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [viewYear, viewMonth, mediaType, source]);

  // Group items by YYYY-MM-DD for the viewed month
  const dayMap = useMemo(() => {
    const map = {};
    const prefix = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}`;
    for (const item of items) {
      const rd = item.release_date;
      if (rd && rd.startsWith(prefix)) {
        (map[rd] ||= []).push(item);
      }
    }
    return map;
  }, [items, viewYear, viewMonth]);

  const grid = useMemo(() => getMonthGrid(viewYear, viewMonth), [viewYear, viewMonth]);
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const totalInMonth = Object.values(dayMap).reduce((sum, arr) => sum + arr.length, 0);

  return (
    <div className="page-container">
      <div className="page-header">
        <h2><Calendar size={22} /> Coming Soon</h2>
        <span className="page-subtitle">{totalInMonth} releases in {monthLabel}</span>
      </div>
      {/* Month nav + filters */}
      <div className="cal-controls">
        <div className="cal-month-nav">
          <button onClick={() => navMonth(-1)}><ChevronLeft size={18} /></button>
          <span className="cal-month-label cal-month-clickable" onClick={() => setShowPicker(p => !p)}>{monthLabel}</span>
            {showPicker && <MonthPicker viewYear={viewYear} viewMonth={viewMonth} onSelect={(y,m) => { setViewYear(y); setViewMonth(m); setSelectedDay(null); }} onClose={() => setShowPicker(false)} />}
          <button onClick={() => navMonth(1)}><ChevronRight size={18} /></button>
          {(viewYear !== today.getFullYear() || viewMonth !== today.getMonth()) && (
            <button className="cal-today-btn" onClick={() => { setViewYear(today.getFullYear()); setViewMonth(today.getMonth()); setSelectedDay(null); }}>Today</button>
          )}
        </div>
        <div className="calendar-filters" style={{ marginBottom: 0 }}>
          <div className="filter-group">
            <label>Type</label>
            <select value={mediaType} onChange={e => setMediaType(e.target.value)}>
              <option value="all">All</option><option value="movie">Movies</option><option value="tv">TV Shows</option>
            </select>
          </div>
          <div className="filter-group">
            <label>Source</label>
            <select value={source} onChange={e => setSource(e.target.value)}>
              <option value="all">TMDB + Monitored</option><option value="tmdb">TMDB Only</option><option value="monitored">Monitored Only</option>
            </select>
          </div>
        </div>
      </div>
      {loading ? (
        <div className="loading-state"><Loader2 size={28} className="spinner" /> Loading calendar…</div>
      ) : (
        <>
          {/* Month grid */}
          <div className="cal-grid">
            {WEEKDAYS.map(d => <div key={d} className="cal-header">{d}</div>)}
            {grid.map((cell, i) => {
              const dateKey = cell.current ? `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(cell.day).padStart(2, "0")}` : null;
              return <DayCell key={i} cell={cell} dateKey={dateKey} items={dateKey ? dayMap[dateKey] : []}
                isToday={dateKey === todayKey} isSelected={selectedDay === dateKey}
                onClick={(dk) => setSelectedDay(selectedDay === dk ? null : dk)} />;
            })}
          </div>
          {/* Selected day detail */}
          {selectedDay && dayMap[selectedDay] && (
            <DayDetail dateKey={selectedDay} items={dayMap[selectedDay]} onCardClick={onCardClick} onClose={() => setSelectedDay(null)} />
          )}
        </>
      )}
    </div>
  );
}
