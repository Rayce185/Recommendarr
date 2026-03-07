import { useState, useEffect, useCallback } from "react";
import { Activity, RefreshCw, Loader2, Sparkles, Clock, Trash2,
  TrendingUp, Award, Film, Star, Calendar, Zap, AlertCircle } from "lucide-react";
import { api } from "../api.js";

const EVENT_ICONS = {
  trend: TrendingUp, release: Film, award: Award,
  anniversary: Calendar, cultural_moment: Zap, controversy: AlertCircle,
};
const EVENT_COLORS = {
  trend: "#6366f1", release: "#10b981", award: "#f59e0b",
  anniversary: "#8b5cf6", cultural_moment: "#ef4444", controversy: "#ec4899",
};

function PulsePage({ isAdmin }) {
  const [themes, setThemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshResult, setRefreshResult] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.pulseThemes(20);
      setThemes(data.themes || []);
    } catch (e) {
      setError(e.message || "Failed to load pulse themes");
    }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshResult(null);
    try {
      const data = await api.pulseRefresh();
      setRefreshResult(data);
      await load();
    } catch (e) {
      setRefreshResult({ status: "error", message: e.message });
    }
    setRefreshing(false);
  };

  const handleDeactivate = async (id) => {
    try {
      await api.pulseDeactivateTheme(id);
      setThemes(prev => prev.filter(t => t.id !== id));
    } catch (e) {
      console.error("Deactivate failed:", e);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: "40px 0", textAlign: "center" }}>
        <Loader2 size={24} className="spinning" style={{ color: "var(--accent)" }} />
        <div style={{ marginTop: 8, color: "var(--text-muted)", fontSize: 13 }}>Loading cultural pulse...</div>
      </div>
    );
  }

  return (
    <div style={{ padding: "0 4px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 20, fontWeight: 700, display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
            <Activity size={20} /> Cultural Pulse
          </h2>
          <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "6px 0 0" }}>
            Trending themes from entertainment news — powered by AI analysis of RSS feeds
          </p>
        </div>
        {isAdmin && (
          <button onClick={handleRefresh} disabled={refreshing}
            className="btn btn-secondary" style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
            {refreshing ? <><Loader2 size={13} className="spinning" /> Refreshing...</> :
             <><RefreshCw size={13} /> Refresh Pulse</>}
          </button>
        )}
      </div>

      {/* Refresh result banner */}
      {refreshResult && (
        <div style={{
          padding: "8px 12px", borderRadius: 6, marginBottom: 16, fontSize: 12,
          background: refreshResult.status === "ok" ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
          border: `1px solid ${refreshResult.status === "ok" ? "rgba(16,185,129,0.3)" : "rgba(239,68,68,0.3)"}`,
          color: refreshResult.status === "ok" ? "var(--green)" : "var(--red)",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          {refreshResult.status === "ok" ? <Sparkles size={13} /> : <AlertCircle size={13} />}
          {refreshResult.message || refreshResult.error}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="admin-card" style={{ textAlign: "center", padding: 30 }}>
          <AlertCircle size={20} style={{ color: "var(--red)", marginBottom: 8 }} />
          <div style={{ fontSize: 13, color: "var(--red)" }}>{error}</div>
        </div>
      )}

      {/* Empty state */}
      {!error && themes.length === 0 && (
        <div className="admin-card" style={{ textAlign: "center", padding: 40 }}>
          <Activity size={32} style={{ color: "var(--text-muted)", marginBottom: 12 }} />
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>No active pulse themes</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>
            Cultural Pulse analyzes entertainment RSS feeds to detect trending themes.
          </div>
          {isAdmin && (
            <button onClick={handleRefresh} disabled={refreshing}
              className="btn btn-primary" style={{ fontSize: 13 }}>
              {refreshing ? "Refreshing..." : "Run First Pulse Scan"}
            </button>
          )}
        </div>
      )}

      {/* Theme cards */}
      <div className="pulse-activity-grid">
        {themes.map(theme => (
          <ThemeCard key={theme.id} theme={theme} isAdmin={isAdmin} onDeactivate={handleDeactivate} />
        ))}
      </div>
    </div>
  );
}


function ThemeCard({ theme, isAdmin, onDeactivate }) {
  const Icon = EVENT_ICONS[theme.event_type] || TrendingUp;
  const color = EVENT_COLORS[theme.event_type] || "var(--accent)";
  const mapping = theme.mapping;

  const expiresIn = theme.expires_at
    ? Math.max(0, Math.ceil((new Date(theme.expires_at) - new Date()) / (1000 * 60 * 60 * 24)))
    : null;

  return (
    <div className="admin-card" style={{ position: "relative", borderLeft: `3px solid ${color}` }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 8 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 8, flexShrink: 0,
          background: `${color}20`, display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <Icon size={16} color={color} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.3 }}>{theme.title}</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            <span style={{
              padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 600,
              background: `${color}20`, color: color, textTransform: "capitalize",
            }}>
              {theme.event_type?.replace("_", " ")}
            </span>
            {theme.priority === "high" && (
              <span style={{ color: "#ef4444", display: "flex", alignItems: "center", gap: 2 }}>
                <Star size={10} /> High Priority
              </span>
            )}
          </div>
        </div>
        {isAdmin && (
          <button onClick={() => onDeactivate(theme.id)}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 4 }}
            title="Deactivate theme">
            <Trash2 size={13} />
          </button>
        )}
      </div>

      {/* Description */}
      {theme.description && (
        <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 10px", lineHeight: 1.5 }}>
          {theme.description}
        </p>
      )}

      {/* Mapped genres */}
      {mapping?.genres?.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
          {mapping.genres.map(g => (
            <span key={g} style={{
              padding: "2px 8px", borderRadius: 10, fontSize: 11, fontWeight: 500,
              background: "var(--bg-secondary)", color: "var(--text-secondary)",
            }}>{g}</span>
          ))}
        </div>
      )}

      {/* Mapped keywords */}
      {mapping?.keywords?.length > 0 && (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
          {mapping.keywords.slice(0, 6).map(k => (
            <span key={k} style={{
              padding: "2px 6px", borderRadius: 4, fontSize: 10,
              background: "rgba(99,102,241,0.08)", color: "var(--accent)",
              border: "1px solid rgba(99,102,241,0.15)",
            }}>#{k}</span>
          ))}
        </div>
      )}

      {/* Footer: expiry */}
      {expiresIn !== null && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 4, marginTop: 6 }}>
          <Clock size={10} />
          {expiresIn === 0 ? "Expires today" : `${expiresIn}d remaining`}
        </div>
      )}
    </div>
  );
}


export default PulsePage;
