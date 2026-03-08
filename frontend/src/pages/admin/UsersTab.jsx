/* UsersTab — Admin per-user staleness monitoring and cache warming
 * Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
 */
import { useState, useEffect, useCallback } from "react";
import { Users, RefreshCw, Loader2, CheckCircle2, XCircle,
  AlertTriangle, Clock, Zap, Play } from "lucide-react";
import { api } from "../../api.js";

const STALENESS_META = {
  fresh:          { label: "Fresh",        color: "#10b981", icon: CheckCircle2 },
  slightly_stale: { label: "Slightly stale", color: "#f59e0b", icon: Clock },
  stale:          { label: "Stale",        color: "#f97316", icon: AlertTriangle },
  very_stale:     { label: "Very stale",   color: "#ef4444", icon: AlertTriangle },
  never:          { label: "Never warmed", color: "#6b7280", icon: XCircle },
};

export default function UsersTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [warming, setWarming] = useState({});
  const [warmResults, setWarmResults] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.userStaleness();
      setData(result);
    } catch { setData({ users: [], total: 0 }); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleWarm = async (username) => {
    setWarming(p => ({ ...p, [username]: true }));
    setWarmResults(p => ({ ...p, [username]: null }));
    try {
      const result = await api.warmUser(username);
      setWarmResults(p => ({ ...p, [username]: result }));
      // Reload staleness data after warm
      setTimeout(() => load(), 1000);
    } catch (e) {
      setWarmResults(p => ({
        ...p, [username]: { status: "error", errors: [e.message] },
      }));
    }
    setWarming(p => ({ ...p, [username]: false }));
  };

  const handleWarmAll = async () => {
    const staleUsers = (data?.users || [])
      .filter(u => u.is_active && u.staleness !== "fresh");
    for (const u of staleUsers) {
      await handleWarm(u.username);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
        <Loader2 size={20} className="spin" /> Loading user staleness...
      </div>
    );
  }

  const users = data?.users || [];
  const activeUsers = users.filter(u => u.is_active);
  const staleCount = activeUsers.filter(u => u.staleness !== "fresh").length;
  const neverWarmed = activeUsers.filter(u => u.staleness === "never").length;

  return (
    <div>
      {/* Summary bar */}
      <div style={{
        display: "flex", gap: 16, marginBottom: 16, padding: "12px 16px",
        background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)",
        borderRadius: 10, fontSize: "0.82rem", color: "var(--text-secondary)",
        alignItems: "center", flexWrap: "wrap",
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
          <Users size={14} /> <strong style={{ color: "var(--text)" }}>{activeUsers.length}</strong> active users
        </span>
        {staleCount > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, color: "#f59e0b" }}>
            <AlertTriangle size={13} /> <strong>{staleCount}</strong> stale
          </span>
        )}
        {neverWarmed > 0 && (
          <span style={{ display: "flex", alignItems: "center", gap: 5, color: "#6b7280" }}>
            <XCircle size={13} /> <strong>{neverWarmed}</strong> never warmed
          </span>
        )}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="test-btn" onClick={load} style={{ gap: 4, fontSize: 11 }}>
            <RefreshCw size={12} /> Refresh
          </button>
          {staleCount > 0 && (
            <button className="test-btn" onClick={handleWarmAll}
              style={{ gap: 4, fontSize: 11, background: "var(--accent)", color: "#fff" }}>
              <Zap size={12} /> Warm All Stale ({staleCount})
            </button>
          )}
        </div>
      </div>

      {/* User table */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {users.map(u => {
          const meta = STALENESS_META[u.staleness] || STALENESS_META.never;
          const Icon = meta.icon;
          const isWarming = warming[u.username];
          const result = warmResults[u.username];
          return (
            <div key={u.username} className="admin-card" style={{
              padding: "10px 14px", display: "flex", alignItems: "center", gap: 12,
              opacity: u.is_active ? 1 : 0.5,
              borderLeft: `3px solid ${meta.color}`,
            }}>
              {/* Avatar */}
              {u.thumb ? (
                <img src={u.thumb} alt="" style={{ width: 32, height: 32, borderRadius: "50%", flexShrink: 0 }} />
              ) : (
                <div style={{ width: 32, height: 32, borderRadius: "50%", background: "var(--bg-secondary)",
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 600, flexShrink: 0 }}>
                  {(u.friendly_name || u.username).charAt(0).toUpperCase()}
                </div>
              )}

              {/* Name + status */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "0.85rem", fontWeight: 500 }}>
                  {u.friendly_name || u.username}
                  {!u.is_active && <span style={{ marginLeft: 6, fontSize: 10, color: "var(--text-muted)" }}>inactive</span>}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", gap: 10, marginTop: 2, flexWrap: "wrap" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 3, color: meta.color }}>
                    <Icon size={11} /> {meta.label}
                  </span>
                  {u.plays_since_refresh > 0 && (
                    <span style={{ display: "flex", alignItems: "center", gap: 3 }}>
                      <Play size={10} /> {u.plays_since_refresh} play{u.plays_since_refresh !== 1 ? "s" : ""} since refresh
                    </span>
                  )}
                  {u.refresh_age_hours !== null && (
                    <span>
                      <Clock size={10} style={{ verticalAlign: -1 }} /> {u.refresh_age_hours < 1
                        ? `${Math.round(u.refresh_age_hours * 60)}m ago`
                        : u.refresh_age_hours < 24
                        ? `${Math.round(u.refresh_age_hours)}h ago`
                        : `${Math.round(u.refresh_age_hours / 24)}d ago`}
                    </span>
                  )}
                </div>
              </div>

              {/* Warm result toast */}
              {result && !isWarming && (
                <div style={{
                  fontSize: 11, padding: "3px 8px", borderRadius: 6,
                  background: result.status === "ok" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
                  color: result.status === "ok" ? "#10b981" : "#ef4444",
                  display: "flex", alignItems: "center", gap: 4,
                }}>
                  {result.status === "ok" ? <CheckCircle2 size={11} /> : <AlertTriangle size={11} />}
                  {result.total_ms ? `${(result.total_ms / 1000).toFixed(1)}s` : "Error"}
                </div>
              )}

              {/* Warm button */}
              <button
                className="test-btn"
                onClick={() => handleWarm(u.username)}
                disabled={isWarming}
                style={{ gap: 4, fontSize: 11, whiteSpace: "nowrap", flexShrink: 0 }}
              >
                {isWarming ? (
                  <><Loader2 size={11} className="spin" /> Warming...</>
                ) : (
                  <><Zap size={11} /> Warm</>
                )}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
