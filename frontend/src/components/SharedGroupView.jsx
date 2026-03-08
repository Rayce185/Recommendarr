/* SharedGroupView — Read-only view of a shared group night session
 * Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
 */
import { useState, useEffect } from "react";
import "../styles/group-night-share.css";
import { Users, ArrowLeft, Clock, Share2 } from "lucide-react";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "./StateDisplays.jsx";
import MediaCard from "./MediaCard.jsx";

export default function SharedGroupView({ code, onCardClick, onBack }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    api.getGroupSession(code)
      .then(setSession)
      .catch(e => setError(e.message || "Session not found"))
      .finally(() => setLoading(false));
  }, [code]);

  if (loading) return <LoadingState message="Loading shared session..." />;
  if (error) return <ErrorState message={error} />;
  if (!session) return <EmptyState icon={Share2} title="Session not found" />;

  const created = new Date(session.created_at);
  const dateStr = created.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  const timeStr = created.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

  return (
    <>
      <div className="page-header">
        <div className="shared-header-row">
          <button className="btn btn-ghost" onClick={onBack}><ArrowLeft size={16} /> Back</button>
          <div>
            <h2><Users size={20} style={{ marginRight: 8 }} />
              {session.title || "Shared Group Night"}</h2>
            <p className="shared-meta">
              <Clock size={12} /> {dateStr} at {timeStr}
              <span className="shared-meta-sep">·</span>
              Created by <strong>{session.creator}</strong>
              <span className="shared-meta-sep">·</span>
              {session.participants.length} people
              <span className="shared-meta-sep">·</span>
              {session.domain === "all" ? "All content" : session.domain}
            </p>
          </div>
        </div>
      </div>
      <div className="page-body">
        <div className="shared-participants">
          {session.participants.map(u => (
            <span key={u} className="shared-participant-chip">{u}</span>
          ))}
        </div>
        <div className="shared-results-header">
          <span>{session.picks.length} group picks</span>
        </div>
        <div className="card-grid">
          {session.picks.map((item, i) => (
            <div key={`${item.tmdb_id}-${i}`} className="group-card-wrapper">
              <MediaCard item={{ ...item, score: null }} onClick={onCardClick} />
              {item.explanation && (
                <div className="group-score-breakdown">
                  {item.explanation.replace("Group fit: ", "").split(" / ").map((part, j) => {
                    const [uname, pct] = part.split(":");
                    const pctNum = parseFloat(pct);
                    const color = pctNum >= 70 ? "var(--green)" : pctNum >= 50 ? "var(--yellow, #eab308)" : "var(--red, #ef4444)";
                    return (
                      <div key={j} className="group-user-score">
                        <span className="group-user-score-name">{uname}</span>
                        <div className="group-user-score-bar">
                          <div className="group-user-score-fill" style={{ width: `${Math.min(pctNum, 100)}%`, background: color }} />
                        </div>
                        <span className="group-user-score-pct" style={{ color }}>{pctNum.toFixed(0)}%</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
