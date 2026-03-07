import { useState, useEffect, useCallback } from "react";
import { Plus, Trash2, Zap, Loader2, CheckCircle2, XCircle, Edit2, Save, X, Server, ChevronDown, ChevronRight } from "lucide-react";
import { instances } from "../../api.js";

function InstanceForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState(initial || { name: "", type: "radarr", url: "", api_key: "", is_default_for: null });
  const set = (k, v) => setForm(p => ({ ...p, [k]: v }));
  return (
    <div className="admin-card" style={{ border: "1px solid var(--accent)", marginBottom: 12 }}>
      <h4 style={{ margin: "0 0 12px" }}>{initial ? "Edit Instance" : "Add Instance"}</h4>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Name
          <input value={form.name} onChange={e => set("name", e.target.value)} placeholder="e.g. radarr_4k"
            style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "6px 8px", color: "var(--text)", fontSize: 13 }} />
        </label>
        <label style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Type
          <select value={form.type} onChange={e => set("type", e.target.value)}
            style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "6px 8px", color: "var(--text)", fontSize: 13 }}>
            <option value="radarr">Radarr</option>
            <option value="sonarr">Sonarr</option>
          </select>
        </label>
      </div>
      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
        URL
        <input value={form.url} onChange={e => set("url", e.target.value)} placeholder="http://192.168.0.111:7878"
          style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "6px 8px", color: "var(--text)", fontSize: 13, fontFamily: "'JetBrains Mono', monospace" }} />
      </label>
      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
        API Key
        <input value={form.api_key} onChange={e => set("api_key", e.target.value)} type="password" placeholder="API key"
          style={{ width: "100%", marginTop: 4, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "6px 8px", color: "var(--text)", fontSize: 13, fontFamily: "'JetBrains Mono', monospace" }} />
      </label>
      <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
        Default for domain
        <select value={form.is_default_for || ""} onChange={e => set("is_default_for", e.target.value || null)}
          style={{ marginLeft: 8, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", color: "var(--text)", fontSize: 13 }}>
          <option value="">None</option>
          <option value="movie">Movies</option>
          <option value="tv">TV</option>
        </select>
      </label>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="test-btn" onClick={() => onSave(form)} disabled={saving || !form.name || !form.url || !form.api_key}
          style={{ background: "var(--accent)", color: "#fff", gap: 6 }}>
          {saving ? <><Loader2 size={12} className="spin" /> Saving...</> : <><Save size={12} /> Save</>}
        </button>
        <button className="test-btn" onClick={onCancel} style={{ gap: 6 }}><X size={12} /> Cancel</button>
      </div>
    </div>
  );
}

function InstanceCard({ inst, onEdit, onDelete, onTest }) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try { const r = await onTest(inst.name); setTestResult(r); } catch (e) { setTestResult({ connected: false, message: e.message }); }
    setTesting(false);
  };

  const handleExpand = async () => {
    if (!expanded && !detail) {
      try { const d = await instances.detail(inst.name); setDetail(d); } catch { /* ignore */ }
    }
    setExpanded(p => !p);
  };

  const handleDelete = async () => {
    setDeleting(true);
    try { await onDelete(inst.name); } catch { setDeleting(false); }
  };

  const typeColor = inst.type === "radarr" ? "#ffc107" : "#17a2b8";

  return (
    <div className="admin-card" style={{ marginBottom: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button onClick={handleExpand} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 0 }}>
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          {inst.connected ? <CheckCircle2 size={14} style={{ color: "var(--green)" }} /> : <XCircle size={14} style={{ color: "var(--red)" }} />}
          <span style={{ fontWeight: 600, fontSize: 14 }}>{inst.name}</span>
          <span style={{ fontSize: 11, background: typeColor, color: "#000", borderRadius: 3, padding: "1px 6px", fontWeight: 600 }}>{inst.type}</span>
          {inst.is_default_for && <span style={{ fontSize: 11, color: "var(--accent)" }}>★ default {inst.is_default_for}</span>}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="test-btn" onClick={handleTest} disabled={testing} style={{ fontSize: 11 }}>
            {testing ? <Loader2 size={11} className="spin" /> : <Zap size={11} />} Test
          </button>
          <button className="test-btn" onClick={() => onEdit(inst)} style={{ fontSize: 11 }}><Edit2 size={11} /> Edit</button>
          <button className="test-btn" onClick={handleDelete} disabled={deleting} style={{ fontSize: 11, color: "var(--red)" }}>
            {deleting ? <Loader2 size={11} className="spin" /> : <Trash2 size={11} />}
          </button>
        </div>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, fontFamily: "'JetBrains Mono', monospace" }}>{inst.url}</div>
      {testResult && (
        <div className={`test-result ${testResult.connected ? "ok" : "err"}`} style={{ marginTop: 6 }}>
          {testResult.connected ? <CheckCircle2 size={11} /> : <XCircle size={11} />} {testResult.message}
        </div>
      )}
      {expanded && detail && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)", fontSize: 12 }}>
          {detail.root_folders?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ fontWeight: 600, color: "var(--text-muted)" }}>Root Folders:</span>
              {detail.root_folders.map((f, i) => (
                <div key={i} style={{ marginLeft: 12, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{f.path} ({f.freeSpace ? Math.round(f.freeSpace / 1e9) + " GB free" : "—"})</div>
              ))}
            </div>
          )}
          {detail.quality_profiles?.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ fontWeight: 600, color: "var(--text-muted)" }}>Quality Profiles:</span>
              <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>{detail.quality_profiles.map(p => p.name).join(", ")}</span>
            </div>
          )}
          {detail.tags?.length > 0 && (
            <div>
              <span style={{ fontWeight: 600, color: "var(--text-muted)" }}>Tags:</span>
              <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>{detail.tags.map(t => t.label).join(", ")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ServarrTab() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await instances.list(); setList(r.instances || []); setError(null); }
    catch (e) { setError(e.message); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async (form) => {
    setSaving(true); setError(null);
    try { await instances.add(form); setAdding(false); await load(); }
    catch (e) { setError(e.message); }
    setSaving(false);
  };

  const handleUpdate = async (form) => {
    setSaving(true); setError(null);
    try { await instances.update(editing.name, form); setEditing(null); await load(); }
    catch (e) { setError(e.message); }
    setSaving(false);
  };

  const handleDelete = async (name) => {
    setError(null);
    try { await instances.remove(name); await load(); }
    catch (e) { setError(e.message); }
  };

  const handleTest = async (name) => {
    return await instances.test(name);
  };

  const handleEdit = (inst) => {
    setEditing(inst); setAdding(false);
  };

  if (loading) return <div style={{ textAlign: "center", padding: 24, color: "var(--text-muted)" }}><Loader2 size={20} className="spin" /> Loading instances...</div>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h4 style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}><Server size={15} /> Radarr / Sonarr Instances</h4>
        {!adding && !editing && (
          <button className="test-btn" onClick={() => { setAdding(true); setEditing(null); }} style={{ gap: 6 }}>
            <Plus size={12} /> Add Instance
          </button>
        )}
      </div>

      {error && <div style={{ background: "rgba(255,0,0,0.1)", border: "1px solid var(--red)", borderRadius: 6, padding: "8px 12px", marginBottom: 12, fontSize: 13, color: "var(--red)" }}>{error}</div>}

      {adding && <InstanceForm onSave={handleAdd} onCancel={() => setAdding(false)} saving={saving} />}
      {editing && <InstanceForm initial={{ name: editing.name, type: editing.type, url: editing.url, api_key: "", is_default_for: editing.is_default_for }} onSave={handleUpdate} onCancel={() => setEditing(null)} saving={saving} />}

      {list.length === 0 && !adding ? (
        <div className="admin-card" style={{ textAlign: "center", color: "var(--text-muted)", padding: 24 }}>
          No instances configured. Click "Add Instance" to get started.
        </div>
      ) : (
        list.map(inst => <InstanceCard key={inst.name} inst={inst} onEdit={handleEdit} onDelete={handleDelete} onTest={handleTest} />)
      )}
    </div>
  );
}
