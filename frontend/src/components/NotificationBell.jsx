import { useState, useEffect, useRef } from "react";
import { Bell, Calendar, Star, AlertTriangle, Film, Tv, X } from "lucide-react";
import { api } from "../api.js";

const ICON_MAP = {
  calendar: Calendar,
  star: Star,
  alert: AlertTriangle,
};

const PRIORITY_COLORS = {
  high: "#ef4444",
  normal: "#f59e0b",
  low: "#6b7280",
};

export default function NotificationBell({ onNavigate }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dropPos, setDropPos] = useState({ top: 0, left: 0 });
  const ref = useRef(null);
  const btnRef = useRef(null);

  // Close on outside click
  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleToggle = async () => {
    if (open) { setOpen(false); return; }
    // Calculate position from button — keep dropdown within viewport
    if (btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      const vw = window.innerWidth;
      const dropW = Math.min(340, vw - 20);
      // Anchor right edge to bell's right edge, but clamp to viewport
      let left = rect.right - dropW;
      if (left < 10) left = 10;
      if (left + dropW > vw - 10) left = vw - dropW - 10;
      setDropPos({ top: rect.bottom + 8, left });
    }
    setOpen(true);
    setLoading(true);
    try {
      const result = await api.notifications();
      setData(result);
    } catch (e) {
      setData({ notifications: [], counts: { total: 0 } });
    }
    setLoading(false);
  };

  // Auto-refresh count every 5 min
  useEffect(() => {
    const refresh = () => api.notifications().then(setData).catch(() => {});
    refresh();
    const interval = setInterval(refresh, 300000);
    return () => clearInterval(interval);
  }, []);

  const count = data?.counts?.high_priority || 0;

  return (
    <div className="notification-bell-wrapper" ref={ref}>
      <button ref={btnRef} className="notification-bell-btn" onClick={handleToggle} title="Notifications">
        <Bell size={18} />
        {count > 0 && <span className="notification-badge">{count > 9 ? "9+" : count}</span>}
      </button>

      {open && (
        <div className="notification-dropdown" style={{ top: dropPos.top, left: dropPos.left }}>
          <div className="notification-header">
            <span>Notifications</span>
            <button className="notification-close" onClick={() => setOpen(false)}><X size={14} /></button>
          </div>
          <div className="notification-body">
            {loading ? (
              <div className="notification-empty">Loading\u2026</div>
            ) : !data?.notifications?.length ? (
              <div className="notification-empty">All clear \u2014 nothing new right now.</div>
            ) : (
              data.notifications.map((n, i) => {
                const Icon = ICON_MAP[n.icon] || Bell;
                return (
                  <div
                    key={i}
                    className={`notification-item priority-${n.priority}`}
                    onClick={() => {
                      if (n.type === "calendar" && onNavigate) onNavigate("calendar");
                      setOpen(false);
                    }}
                  >
                    <div className="notification-icon" style={{ color: PRIORITY_COLORS[n.priority] }}>
                      <Icon size={15} />
                    </div>
                    <div className="notification-content">
                      <div className="notification-title">{n.title}</div>
                      <div className="notification-message">{n.message}</div>
                    </div>
                    {n.media_type && (
                      <div className="notification-type">
                        {n.media_type === "movie" ? <Film size={11} /> : <Tv size={11} />}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
          {data?.counts?.total > 0 && (
            <div className="notification-footer">
              {data.counts.calendar > 0 && <span>{data.counts.calendar} releasing soon</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
