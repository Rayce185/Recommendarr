import { useState, useEffect, useCallback } from "react";
import {
  Bell, Calendar, Star, AlertTriangle, Film, Tv, X,
  CheckCheck, RotateCcw, Filter, Users,
} from "lucide-react";
import { api } from "../api.js";

const TYPE_META = {
  calendar: { icon: Calendar, label: "Releasing Soon", color: "#3b82f6" },
  milestone: { icon: Star, label: "Milestones", color: "#f59e0b" },
  system: { icon: AlertTriangle, label: "System", color: "#ef4444" },
  group_night: { icon: Users, label: "Group Night", color: "#8b5cf6" },
};

const PRIORITY_COLORS = { high: "#ef4444", normal: "#f59e0b", low: "#6b7280" };

export default function NotificationsPage({ onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [dismissing, setDismissing] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.notifications();
      setData(result);
    } catch {
      setData({ notifications: [], counts: { total: 0 } });
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDismiss = async (id) => {
    setDismissing(id);
    try {
      await api.dismissNotification(id);
      setData((prev) =>
        prev
          ? {
              ...prev,
              notifications: prev.notifications.filter((n) => n.id !== id),
              counts: { ...prev.counts, total: Math.max(0, prev.counts.total - 1) },
            }
          : prev
      );
    } catch {}
    setDismissing(null);
  };

  const handleDismissAll = async () => {
    try {
      await api.dismissAllNotifications();
      setData((prev) =>
        prev ? { ...prev, notifications: [], counts: { total: 0, calendar: 0, milestones: 0, system: 0, high_priority: 0 } } : prev
      );
    } catch {}
  };

  const handleRestore = async () => {
    try {
      await api.clearDismissedNotifications();
      load();
    } catch {}
  };

  const filtered =
    data?.notifications?.filter((n) => filter === "all" || n.type === filter) || [];

  const groupedByType = {};
  for (const n of filtered) {
    const t = n.type || "system";
    if (!groupedByType[t]) groupedByType[t] = [];
    groupedByType[t].push(n);
  }

  return (
    <div className="notifications-page">
      <div className="page-header" style={{ marginBottom: 20 }}>
        <h1 style={{ display: "flex", alignItems: "center", gap: 10, fontSize: "1.4rem" }}>
          <Bell size={22} /> Notifications
          {data?.counts?.total > 0 && (
            <span className="notif-page-badge">{data.counts.total}</span>
          )}
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: 4 }}>
          Upcoming releases, milestones, and system alerts
        </p>
      </div>

      {/* Filter bar */}
      <div className="notif-toolbar">
        <div className="notif-filters">
          {[
            { key: "all", label: "All" },
            { key: "calendar", label: "Calendar" },
            { key: "milestone", label: "Milestones" },
            { key: "system", label: "System" },
            { key: "group_night", label: "Group Night" },
          ].map((f) => (
            <button
              key={f.key}
              className={`notif-filter-btn ${filter === f.key ? "active" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              {f.label}
              {f.key !== "all" && data?.counts?.[f.key === "milestone" ? "milestones" : f.key] > 0 && (
                <span className="notif-filter-count">
                  {data.counts[f.key === "milestone" ? "milestones" : f.key === "group_night" ? "group_nights" : f.key]}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="notif-actions">
          <button
            className="notif-action-btn"
            onClick={handleRestore}
            title="Restore dismissed notifications"
          >
            <RotateCcw size={14} /> Restore
          </button>
          {filtered.length > 0 && (
            <button className="notif-action-btn danger" onClick={handleDismissAll}>
              <CheckCheck size={14} /> Dismiss All
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {loading ? (
        <div className="notif-loading">Loading notifications…</div>
      ) : filtered.length === 0 ? (
        <div className="notif-empty-state">
          <Bell size={40} style={{ opacity: 0.3, marginBottom: 12 }} />
          <p style={{ fontSize: "1rem", fontWeight: 500 }}>All clear</p>
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
            {filter !== "all"
              ? "No notifications in this category."
              : "Nothing new right now. Check back later!"}
          </p>
        </div>
      ) : (
        Object.entries(groupedByType).map(([type, items]) => {
          const meta = TYPE_META[type] || TYPE_META.system;
          const TypeIcon = meta.icon;
          return (
            <div key={type} className="notif-group">
              <div className="notif-group-header">
                <TypeIcon size={16} style={{ color: meta.color }} />
                <span>{meta.label}</span>
                <span className="notif-group-count">{items.length}</span>
              </div>
              <div className="notif-group-list">
                {items.map((n) => (
                  <NotificationRow
                    key={n.id}
                    notif={n}
                    dismissing={dismissing === n.id}
                    onDismiss={() => handleDismiss(n.id)}
                    onNavigate={onNavigate}
                  />
                ))}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

function NotificationRow({ notif, dismissing, onDismiss, onNavigate }) {
  const meta = TYPE_META[notif.type] || TYPE_META.system;
  const Icon = meta.icon;

  return (
    <div
      className={`notif-row priority-${notif.priority}`}
      onClick={() => {
        if (notif.type === "calendar" && onNavigate) onNavigate("calendar");
      }}
      style={{ cursor: notif.type === "calendar" ? "pointer" : "default" }}
    >
      <div className="notif-row-icon" style={{ color: PRIORITY_COLORS[notif.priority] }}>
        <Icon size={18} />
      </div>
      <div className="notif-row-body">
        <div className="notif-row-title">{notif.title}</div>
        <div className="notif-row-message">{notif.message}</div>
        {notif.release_date && (
          <div className="notif-row-date">{notif.release_date}</div>
        )}
      </div>
      <div className="notif-row-meta">
        {notif.media_type && (
          <span className="notif-media-badge">
            {notif.media_type === "movie" ? <Film size={12} /> : <Tv size={12} />}
          </span>
        )}
        <button
          className="notif-row-dismiss"
          onClick={(e) => { e.stopPropagation(); onDismiss(); }}
          disabled={dismissing}
          title="Dismiss"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
