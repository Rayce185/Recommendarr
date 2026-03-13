import { useState, useEffect, useCallback } from "react";
import { Layers, ChevronDown, CheckCircle2, Film, XCircle, Loader2 } from "lucide-react";
import Skeleton from "../components/Skeleton.jsx";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";

function CollectionsPage({ user, onCardClick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [computing, setComputing] = useState(false);

  const load = useCallback(() => {
    if (!user?.username) return;
    setLoading(true);
    setError(null);
    api.collections(user.username)
      .then(d => {
        setData(d);
        if (d?.computing) {
          setComputing(true);
          setTimeout(() => { setComputing(false); load(); }, 15000);
        } else {
          setComputing(false);
        }
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user?.username]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <><div className="page-header"><h2>Complete The Collection</h2></div><div className="page-body"><Skeleton.CardGrid count={6} /></div></>;
  if (error) return <><div className="page-header"><h2>Complete The Collection</h2></div><div className="page-body"><ErrorState message={error} onRetry={load} /></div></>;

  const collections = data?.collections || [];

  return (
    <>
      <div className="page-header">
        <h2>Complete The Collection</h2>
        <p>{collections.length} franchise{collections.length !== 1 ? "s" : ""} with missing entries</p>
      </div>
      <div className="page-body">
        {computing && (
          <div style={{ padding: "12px 16px", borderRadius: 8, marginBottom: 16,
            background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.2)",
            display: "flex", alignItems: "center", gap: 8, fontSize: "0.85rem", color: "var(--accent)" }}>
            <Loader2 size={14} className="spin" />
            Scanning your library for franchise collections — this only happens once. Auto-refreshing in 15 seconds...
          </div>
        )}
        {collections.length === 0 ? (
          <EmptyState icon={Layers} title="All caught up!" message="You've completed every franchise in your watch history." />
        ) : (
          <div className="coll-list">
            {collections.map(c => (
              <div key={c.collection_id} className="coll-card">
                <div className="coll-header" onClick={() => setExpanded(expanded === c.collection_id ? null : c.collection_id)}>
                  {c.poster_url && <img src={c.poster_url} alt="" className="coll-poster" loading="lazy" />}
                  <div className="coll-info">
                    <h3>{c.name}</h3>
                    <div className="coll-meta">
                      <span className="coll-progress">{c.watched_count}/{c.total_parts} watched</span>
                      <span className="coll-pct">{c.completion_pct}%</span>
                    </div>
                    <div className="coll-bar">
                      <div className="coll-bar-fill" style={{ width: `${c.completion_pct}%` }} />
                    </div>
                    <div className="coll-missing-summary">
                      {c.missing.length} missing: {c.missing.slice(0, 3).map(m => m.title).join(", ")}
                      {c.missing.length > 3 && ` +${c.missing.length - 3} more`}
                    </div>
                  </div>
                  <ChevronDown size={18} className={expanded === c.collection_id ? "coll-chev open" : "coll-chev"} />
                </div>
                {expanded === c.collection_id && (
                  <div className="coll-parts">
                    {c.parts.map(p => (
                      <div key={p.tmdb_id} className={`coll-part ${p.watched ? "watched" : ""}`}
                           onClick={() => !p.watched && onCardClick && onCardClick({ tmdb_id: p.tmdb_id, media_type: "movie", title: p.title, year: p.year, poster_url: p.poster_url })}>
                        {p.poster_url && <img src={p.poster_url} alt="" className="coll-part-poster" loading="lazy" />}
                        <div className="coll-part-info">
                          <span className="coll-part-title">{p.title} {p.year ? `(${p.year})` : ""}</span>
                          <span className="coll-part-status">
                            {p.watched ? <><CheckCircle2 size={12} style={{ color: "var(--green)" }} /> Watched</> :
                             p.in_library ? <><Film size={12} style={{ color: "var(--accent)" }} /> In Library</> :
                             <><XCircle size={12} style={{ color: "var(--text-muted)" }} /> Not in Library</>}
                          </span>
                        </div>
                        {p.vote_average > 0 && <span className="coll-part-score">{p.vote_average.toFixed(1)}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}


export default CollectionsPage;
