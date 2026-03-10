import { useState, useEffect, useCallback } from "react";
import { Shield, RotateCcw, CheckCircle2, XCircle, SlidersHorizontal, Loader2, AlertTriangle, Film, Tv } from "lucide-react";
import { api } from "../../api.js";
import { posterUrl } from "../../utils.js";

function PendingCard({ item, onConfirm, onVeto, acting }) {
  const poster = posterUrl(item.poster_url);
  const isMovie = item.media_type === "movie";
  return (
    <div className="lh-pending-card">
      <div className="lh-sunset-poster small">
        {poster ? <img src={poster} alt={item.title} loading="lazy" /> : <div className="no-poster"><Film size={18} /></div>}
      </div>
      <div className="lh-sunset-info">
        <h4>{item.title} {item.year && <span className="lh-year">({item.year})</span>}</h4>
        <div className="lh-pending-votes">
          Keep: {item.keep_votes || 0} &middot; Kick: {item.kick_votes || 0}
        </div>
        <div className="lh-pending-actions">
          <button className="lh-action-btn danger" onClick={() => onConfirm(item.tmdb_id, item.media_type)} disabled={acting}>
            {acting ? <Loader2 size={12} className="spin" /> : <CheckCircle2 size={12} />} Confirm Kick
          </button>
          <button className="lh-action-btn" onClick={() => onVeto(item.tmdb_id, item.media_type)} disabled={acting}>
            <XCircle size={12} /> Veto
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfigSlider({ label, field, value, min, max, step, onChange }) {
  return (
    <div className="lh-config-row">
      <label>{label}</label>
      <div className="lh-slider-group">
        <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(field, parseFloat(e.target.value))} />
        <span className="lh-slider-value">{value}</span>
      </div>
    </div>
  );
}

function HealthAdminTab({ onStatsRefresh }) {
  const [pending, setPending] = useState([]);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [acting, setActing] = useState(false);
  const [recalcing, setRecalcing] = useState(false);
  const [configDirty, setConfigDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c] = await Promise.all([api.healthPending(), api.healthConfig()]);
      setPending(p.items || []);
      setConfig(c);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleConfirm = async (tmdbId, mediaType) => {
    setActing(true);
    try { await api.healthConfirmKick(tmdbId, mediaType); await load(); } catch (err) { console.error(err); }
    finally { setActing(false); }
  };

  const handleVeto = async (tmdbId, mediaType) => {
    setActing(true);
    try { await api.healthVetoKick(tmdbId, mediaType); await load(); } catch (err) { console.error(err); }
    finally { setActing(false); }
  };

  const handleRecalc = async () => {
    setRecalcing(true);
    try { await api.healthRecalculate(); onStatsRefresh?.(); } catch (err) { console.error(err); }
    finally { setRecalcing(false); }
  };

  const updateConfigField = (field, value) => {
    setConfig(prev => ({ ...prev, [field]: value }));
    setConfigDirty(true);
    setSaveMsg(null);
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      await api.healthUpdateConfig(config);
      setSaveMsg({ type: "ok", text: "Configuration saved" });
      setConfigDirty(false);
    } catch (err) {
      setSaveMsg({ type: "err", text: err.message || "Save failed" });
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="lh-loading"><Loader2 size={20} className="spin" /> Loading admin panel...</div>;
  if (error) return <div className="lh-error"><AlertTriangle size={16} /> {error}</div>;

  return (
    <div className="lh-admin">
      {/* Pending kicks */}
      <div className="lh-admin-section">
        <h3><Shield size={16} /> Pending Confirmations ({pending.length})</h3>
        {pending.length === 0 ? (
          <p className="lh-muted">No items awaiting admin confirmation.</p>
        ) : pending.map(item => (
          <PendingCard key={`${item.tmdb_id}-${item.media_type}`} item={item} onConfirm={handleConfirm} onVeto={handleVeto} acting={acting} />
        ))}
      </div>

      {/* Force recalculate */}
      <div className="lh-admin-section">
        <h3><RotateCcw size={16} /> Vitality Recalculation</h3>
        <button className="lh-action-btn primary" onClick={handleRecalc} disabled={recalcing}>
          {recalcing ? <><Loader2 size={12} className="spin" /> Recalculating...</> : <><RotateCcw size={12} /> Force Recalculate Now</>}
        </button>
      </div>

      {/* Config sliders */}
      {config && (
        <div className="lh-admin-section">
          <h3><SlidersHorizontal size={16} /> Scoring Weights &amp; Thresholds</h3>
          <ConfigSlider label="Recency Decay" field="weight_recency" value={config.weight_recency ?? 0.30} min={0} max={1} step={0.05} onChange={updateConfigField} />
          <ConfigSlider label="Play Velocity" field="weight_velocity" value={config.weight_velocity ?? 0.25} min={0} max={1} step={0.05} onChange={updateConfigField} />
          <ConfigSlider label="User Breadth" field="weight_breadth" value={config.weight_breadth ?? 0.20} min={0} max={1} step={0.05} onChange={updateConfigField} />
          <ConfigSlider label="Rec Frequency" field="weight_rec_freq" value={config.weight_rec_freq ?? 0.10} min={0} max={1} step={0.05} onChange={updateConfigField} />
          <ConfigSlider label="Niche Adjustment" field="weight_niche" value={config.weight_niche ?? 0.15} min={0} max={1} step={0.05} onChange={updateConfigField} />
          <div className="lh-config-divider" />
          <ConfigSlider label="Healthy Threshold" field="threshold_healthy" value={config.threshold_healthy ?? 40} min={20} max={80} step={5} onChange={updateConfigField} />
          <ConfigSlider label="Dead Threshold" field="threshold_dead" value={config.threshold_dead ?? 15} min={5} max={35} step={5} onChange={updateConfigField} />
          <ConfigSlider label="Grace Period (days)" field="grace_period_days" value={config.grace_period_days ?? 14} min={3} max={60} step={1} onChange={updateConfigField} />
          <ConfigSlider label="Vote Quorum" field="vote_quorum" value={config.vote_quorum ?? 3} min={1} max={10} step={1} onChange={updateConfigField} />
          {configDirty && (
            <div className="lh-config-save">
              <button className="lh-action-btn primary" onClick={handleSaveConfig} disabled={saving}>
                {saving ? <Loader2 size={12} className="spin" /> : <CheckCircle2 size={12} />} Save Config
              </button>
              {saveMsg && <span className={`lh-save-msg ${saveMsg.type}`}>{saveMsg.text}</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default HealthAdminTab;
