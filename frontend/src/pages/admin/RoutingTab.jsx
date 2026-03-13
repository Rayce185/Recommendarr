import { useState, useEffect, useCallback } from "react";
import { ArrowUp, ArrowDown, Plus, Trash2, Wand2, RotateCcw, Loader2, Save, X, Edit2, Shuffle, AlertTriangle } from "lucide-react";
import { routing } from "../../api.js";

const RULE_FIELDS = ["genre_include", "genre_require", "keyword_include", "company_include"];

function RuleRow({ rule, idx, total, onMove, onEdit, onDelete }) {
  const isCatchall = rule.is_catchall;
  return (
    <div className="admin-card" style={{ marginBottom: 4, padding: "8px 12px", opacity: isCatchall ? 0.7 : 1 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)", minWidth: 20, textAlign: "right" }}>#{idx + 1}</span>
          <span style={{ fontWeight: 600, fontSize: 13 }}>{rule.name}</span>
          <span style={{ fontSize: 11, background: rule.media_type === "movie" ? "#ffc107" : "#17a2b8", color: "#000", borderRadius: 3, padding: "1px 5px" }}>{rule.media_type}</span>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>→ {rule.target}</span>
          <span style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{rule.root_folder}</span>
          {isCatchall && <span style={{ fontSize: 10, background: "var(--accent)", color: "#fff", borderRadius: 3, padding: "1px 5px" }}>catchall</span>}
        </div>
        <div style={{ display: "flex", gap: 2 }}>
          <button className="test-btn" onClick={() => onMove(idx, -1)} disabled={idx === 0} style={{ padding: "2px 4px" }}><ArrowUp size={11} /></button>
          <button className="test-btn" onClick={() => onMove(idx, 1)} disabled={idx === total - 1} style={{ padding: "2px 4px" }}><ArrowDown size={11} /></button>
          <button className="test-btn" onClick={() => onEdit(idx)} style={{ padding: "2px 6px" }}><Edit2 size={11} /></button>
          <button className="test-btn" onClick={() => onDelete(idx)} style={{ padding: "2px 6px", color: "var(--red)" }}><Trash2 size={11} /></button>
        </div>
      </div>
      {RULE_FIELDS.some(f => rule[f]?.length) && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, marginLeft: 28 }}>
          {rule.genre_include?.length > 0 && <span>genres: {rule.genre_include.join(", ")} · </span>}
          {rule.genre_require?.length > 0 && <span>require: {rule.genre_require.join(" + ")} · </span>}
          {rule.keyword_include?.length > 0 && <span>keywords: {rule.keyword_include.slice(0, 3).join(", ")}{rule.keyword_include.length > 3 ? ` +${rule.keyword_include.length - 3}` : ""} · </span>}
          {rule.company_include?.length > 0 && <span>companies: {rule.company_include.join(", ")}</span>}
        </div>
      )}
    </div>
  );
}

function RuleEditor({ rule, onSave, onCancel, instanceNames }) {
  const [form, setForm] = useState(rule || {
    name: "", media_type: "movie", target: instanceNames[0] || "", root_folder: "",
    quality_profile_id: 1, tags: [], genre_include: [], genre_require: [],
    keyword_include: [], company_include: [], is_catchall: false, series_type: null,
  });
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));
  const setList = (k, v) => set(k, v.split(",").map(s => s.trim()).filter(Boolean));

  return (
    <div className="admin-card" style={{ border: "1px solid var(--accent)", marginBottom: 12 }}>
      <h4 style={{ margin: "0 0 10px" }}>{rule ? "Edit Rule" : "New Rule"}</h4>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Name
          <input value={form.name} onChange={e => set("name", e.target.value)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }} />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Media Type
          <select value={form.media_type} onChange={e => set("media_type", e.target.value)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }}>
            <option value="movie">movie</option><option value="tv">tv</option>
          </select>
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Target Instance
          <select value={form.target} onChange={e => set("target", e.target.value)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }}>
            {instanceNames.map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Root Folder
          <input value={form.root_folder} onChange={e => set("root_folder", e.target.value)} placeholder="/media/Movies" style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }} />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Profile ID
          <input type="number" value={form.quality_profile_id} onChange={e => set("quality_profile_id", parseInt(e.target.value) || 1)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }} />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Series Type
          <select value={form.series_type || ""} onChange={e => set("series_type", e.target.value || null)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }}>
            <option value="">—</option><option value="standard">standard</option><option value="anime">anime</option>
          </select>
        </label>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Genre Include <span style={{ fontSize: 10 }}>(comma-sep)</span>
          <input value={(form.genre_include || []).join(", ")} onChange={e => setList("genre_include", e.target.value)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }} />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Genre Require <span style={{ fontSize: 10 }}>(ALL must match)</span>
          <input value={(form.genre_require || []).join(", ")} onChange={e => setList("genre_require", e.target.value)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }} />
        </label>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Keyword Include <span style={{ fontSize: 10 }}>(comma-sep)</span>
          <input value={(form.keyword_include || []).join(", ")} onChange={e => setList("keyword_include", e.target.value)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }} />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Company Include <span style={{ fontSize: 10 }}>(comma-sep)</span>
          <input value={(form.company_include || []).join(", ")} onChange={e => setList("company_include", e.target.value)} style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "5px 8px", color: "var(--text)", fontSize: 12 }} />
        </label>
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
        <label style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4, color: "var(--text-muted)" }}>
          <input type="checkbox" checked={form.is_catchall || false} onChange={e => set("is_catchall", e.target.checked)} /> Catchall
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Tags <span style={{ fontSize: 10 }}>(IDs, comma-sep)</span>
          <input value={(form.tags || []).join(", ")} onChange={e => set("tags", e.target.value.split(",").map(s => parseInt(s.trim())).filter(n => !isNaN(n)))}
            style={{ marginLeft: 4, width: 120, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", color: "var(--text)", fontSize: 12 }} />
        </label>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="test-btn" onClick={() => onSave(form)} disabled={!form.name || !form.target || !form.root_folder}
          style={{ background: "var(--accent)", color: "#fff", gap: 6 }}><Save size={12} /> Save</button>
        <button className="test-btn" onClick={onCancel} style={{ gap: 6 }}><X size={12} /> Cancel</button>
      </div>
    </div>
  );
}

export default function RoutingTab() {
  const [rules, setRules] = useState([]);
  const [isDefault, setIsDefault] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [detectResult, setDetectResult] = useState(null);
  const [editIdx, setEditIdx] = useState(null);
  const [adding, setAdding] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState(null);
  const [instanceNames, setInstanceNames] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rr, ir] = await Promise.all([routing.get(), routing.instanceInfo()]);
      setRules(rr.rules || []); setIsDefault(rr.is_default ?? true);
      setInstanceNames((ir.instances || []).map(i => i.name));
      setError(null); setDirty(false);
    } catch (e) { setError(e.message); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleMove = (idx, dir) => {
    const next = [...rules]; const swap = idx + dir;
    [next[idx], next[swap]] = [next[swap], next[idx]];
    setRules(next); setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true); setError(null);
    try { await routing.update(rules); setDirty(false); setIsDefault(false); }
    catch (e) { setError(e.message); }
    setSaving(false);
  };

  const handleReset = async () => {
    if (!confirm("Reset all routing rules to defaults?")) return;
    setSaving(true); setError(null);
    try { const r = await routing.reset(); setRules(r.rules || []); setIsDefault(true); setDirty(false); }
    catch (e) { setError(e.message); }
    setSaving(false);
  };

  const handleAutoDetect = async () => {
    setDetecting(true); setError(null); setDetectResult(null);
    try { const r = await routing.autoDetect(); setDetectResult(r); }
    catch (e) { setError(e.message); }
    setDetecting(false);
  };

  const applyDetected = () => {
    if (detectResult?.rules) { setRules(detectResult.rules); setDirty(true); setDetectResult(null); }
  };

  const handleDelete = (idx) => { setRules(r => r.filter((_, i) => i !== idx)); setDirty(true); };
  const handleEditSave = (form) => { setRules(r => r.map((rule, i) => i === editIdx ? form : rule)); setEditIdx(null); setDirty(true); };
  const handleAddSave = (form) => { setRules(r => [...r, form]); setAdding(false); setDirty(true); };

  if (loading) return <div style={{ textAlign: "center", padding: 24, color: "var(--text-muted)" }}><Loader2 size={20} className="spin" /> Loading routing rules...</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
        <h4 style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
          <Shuffle size={15} /> Routing Rules
          {isDefault && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>(defaults)</span>}
          {dirty && <span style={{ fontSize: 11, color: "var(--accent)" }}>• unsaved</span>}
        </h4>
        <div style={{ display: "flex", gap: 6 }}>
          <button className="test-btn" onClick={handleAutoDetect} disabled={detecting} style={{ gap: 6 }}>
            {detecting ? <Loader2 size={12} className="spin" /> : <Wand2 size={12} />} Auto-Detect
          </button>
          <button className="test-btn" onClick={() => { setAdding(true); setEditIdx(null); }} style={{ gap: 6 }}><Plus size={12} /> Add Rule</button>
          <button className="test-btn" onClick={handleReset} style={{ gap: 6 }}><RotateCcw size={12} /> Reset</button>
          {dirty && (
            <button className="test-btn" onClick={handleSave} disabled={saving} style={{ background: "var(--accent)", color: "#fff", gap: 6 }}>
              {saving ? <Loader2 size={12} className="spin" /> : <Save size={12} />} Save Rules
            </button>
          )}
        </div>
      </div>

      {error && <div style={{ background: "rgba(255,0,0,0.1)", border: "1px solid var(--red)", borderRadius: 6, padding: "8px 12px", marginBottom: 12, fontSize: 13, color: "var(--red)" }}>{error}</div>}

      {detectResult && (
        <div className="admin-card" style={{ border: "1px solid var(--accent)", marginBottom: 12 }}>
          <h4 style={{ margin: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}><Wand2 size={14} /> Auto-Detected Rules ({detectResult.rules?.length || 0})</h4>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            Method: {detectResult.method} · Instances analyzed: {detectResult.instance_analysis?.length || 0}
          </div>
          <div style={{ maxHeight: 200, overflow: "auto", marginBottom: 8 }}>
            {(detectResult.rules || []).map((r, i) => (
              <div key={i} style={{ fontSize: 12, padding: "3px 0", color: "var(--text-muted)" }}>
                {i + 1}. <strong>{r.name}</strong> → {r.target}:{r.root_folder} {r.is_catchall && "(catchall)"}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="test-btn" onClick={applyDetected} style={{ background: "var(--accent)", color: "#fff", gap: 6 }}><Save size={12} /> Apply These</button>
            <button className="test-btn" onClick={() => setDetectResult(null)} style={{ gap: 6 }}><X size={12} /> Dismiss</button>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
            <AlertTriangle size={10} /> Applying replaces current rules. Click "Save Rules" to persist.
          </div>
        </div>
      )}

      {adding && <RuleEditor onSave={handleAddSave} onCancel={() => setAdding(false)} instanceNames={instanceNames} />}
      {editIdx !== null && <RuleEditor rule={rules[editIdx]} onSave={handleEditSave} onCancel={() => setEditIdx(null)} instanceNames={instanceNames} />}

      {rules.length === 0 ? (
        <div className="admin-card" style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
          No routing rules. Use "Auto-Detect" or add rules manually.
        </div>
      ) : (
        rules.map((rule, idx) => (
          <RuleRow key={idx} rule={rule} idx={idx} total={rules.length} onMove={handleMove} onEdit={setEditIdx} onDelete={handleDelete} />
        ))
      )}
    </div>
  );
}
