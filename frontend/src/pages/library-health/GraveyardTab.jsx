import { useState, useEffect, useCallback } from "react";
import { Skull, Download, Search, Film, Tv, Loader2, AlertTriangle, Clock, CheckCircle2, XCircle } from "lucide-react";
import { api } from "../../api.js";
import { posterUrl } from "../../utils.js";

function EtaBadge({ eta }) {
  if (!eta) return null;
  const colors = { instant: "var(--green)", hours: "var(--blue)", days: "var(--orange, #f59e0b)", weeks: "var(--red)", rare: "var(--text-muted)" };
  return <span className="lh-eta-badge" style={{ color: colors[eta] || "var(--text-muted)" }}>{eta}</span>;
}

function GraveyardCard({ item, isAdmin, onRedownload, onCheckAvail, checking, redownloading }) {
  const poster = posterUrl(item.poster_url);
  const isMovie = item.media_type === "movie";
  const kickedDate = item.kicked_at ? new Date(item.kicked_at).toLocaleDateString() : "Unknown";

  return (
    <div className="lh-graveyard-card">
      <div className="lh-sunset-poster small">
        {poster ? <img src={poster} alt={item.title} loading="lazy" /> : <div className="no-poster"><Film size={20} /></div>}
      </div>
      <div className="lh-sunset-info">
        <div className="lh-sunset-header">
          <h4>{item.title} {item.year && <span className="lh-year">({item.year})</span>}</h4>
          <span className="lh-type-badge" style={{ background: isMovie ? "var(--blue)" : "var(--purple)" }}>
            {isMovie ? <Film size={10} /> : <Tv size={10} />}
          </span>
        </div>
        <div className="lh-graveyard-meta">
          <span><Clock size={11} /> Kicked: {kickedDate}</span>
          {item.kicked_by && <span>by {item.kicked_by}</span>}
          <EtaBadge eta={item.redownload_eta} />
        </div>
        {item.availability_status && (
          <div className={`lh-avail ${item.availability_status}`}>
            {item.availability_status === "available" ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
            {" "}{item.availability_status === "available" ? "Available for re-download" : "Not currently available"}
          </div>
        )}
        <div className="lh-graveyard-actions">
          <button className="lh-action-btn" onClick={() => onCheckAvail(item.id)} disabled={checking}>
            {checking ? <Loader2 size={12} className="spin" /> : <Search size={12} />} Check Availability
          </button>
          {isAdmin && (
            <button className="lh-action-btn primary" onClick={() => onRedownload(item.id)} disabled={redownloading}>
              {redownloading ? <Loader2 size={12} className="spin" /> : <Download size={12} />} Re-download
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function GraveyardTab({ isAdmin }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [checking, setChecking] = useState(null);
  const [redownloading, setRedownloading] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.healthGraveyard();
      setItems(data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCheckAvail = async (id) => {
    setChecking(id);
    try {
      const result = await api.healthCheckAvailability(id);
      setItems(prev => prev.map(it => it.id === id ? { ...it, availability_status: result.available ? "available" : "unavailable" } : it));
    } catch (err) {
      console.error("Availability check failed:", err);
    } finally {
      setChecking(null);
    }
  };

  const handleRedownload = async (id) => {
    setRedownloading(id);
    try {
      await api.healthRedownload(id);
      await load();
    } catch (err) {
      console.error("Redownload failed:", err);
    } finally {
      setRedownloading(null);
    }
  };

  if (loading) return <div className="lh-loading"><Loader2 size={20} className="spin" /> Loading graveyard...</div>;
  if (error) return <div className="lh-error"><AlertTriangle size={16} /> {error}</div>;

  if (!items.length) return (
    <div className="lh-empty">
      <Skull size={32} style={{ opacity: 0.4 }} />
      <p>The graveyard is empty. No items have been kicked yet.</p>
    </div>
  );

  return (
    <div className="lh-graveyard-list">
      <div className="lh-sunset-header-bar">
        <span>{items.length} kicked item{items.length !== 1 ? "s" : ""}</span>
      </div>
      {items.map(item => (
        <GraveyardCard key={item.id} item={item} isAdmin={isAdmin}
          onCheckAvail={handleCheckAvail} onRedownload={handleRedownload}
          checking={checking === item.id} redownloading={redownloading === item.id} />
      ))}
    </div>
  );
}

export default GraveyardTab;
