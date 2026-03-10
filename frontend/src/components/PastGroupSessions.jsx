/* PastGroupSessions — List past shared group night sessions
 * Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
 */
import { useState } from "react";
import { Clock, Users, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { api } from "../api.js";

function timeAgo(isoStr) {
  const d = new Date(isoStr);
  const now = new Date();
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString();
}

export default function PastGroupSessions({ nicknames, onSubtabChange }) {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [collapsed, setCollapsed] = useState(true);
  const [loaded, setLoaded] = useState(false);

  const load = () => {
    if (loaded) { setCollapsed(c => !c); return; }
    setLoading(true);
    api.listGroupSessions(20)
      .then(data => { setSessions(data.sessions || []); setLoaded(true); setCollapsed(false); })
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  };

  const viewSession = (code) => {
    onSubtabChange?.(code);
  };

  if (!loaded && !loading) {
    return (
      <div className="past-sessions-section">
        <button className="past-sessions-toggle" onClick={load}>
          <Clock size={14} />
          <span>Past Sessions</span>
          <ChevronDown size={14} />
        </button>
      </div>
    );
  }

  return (
    <div className="past-sessions-section">
      <button className="past-sessions-toggle" onClick={() => setCollapsed(c => !c)}>
        <Clock size={14} />
        <span>Past Sessions</span>
        <span className="past-sessions-count">{sessions.length}</span>
        {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>

      {!collapsed && (
        <div className="past-sessions-list">
          {loading && <div className="past-sessions-loading">Loading...</div>}
          {!loading && sessions.length === 0 && (
            <div className="past-sessions-empty">No shared sessions yet. Use the Share button after generating group picks.</div>
          )}
          {!loading && sessions.map(s => (
            <button key={s.code} className="past-session-card" onClick={() => viewSession(s.code)}>
              <div className="past-session-top">
                <span className="past-session-title">{s.title || `Session ${s.code}`}</span>
                <span className="past-session-time">{timeAgo(s.created_at)}</span>
              </div>
              <div className="past-session-meta">
                <Users size={11} />
                <span>{s.participants.map(p => nicknames?.[p] || p).join(", ")}</span>
                <span className="past-session-domain">{s.domain}</span>
                <ExternalLink size={11} className="past-session-link-icon" />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
