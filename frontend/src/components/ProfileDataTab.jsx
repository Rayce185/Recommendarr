import { useState } from "react";
import { Download, Upload, Loader2 } from "lucide-react";
import { api } from "../api.js";

export default function ProfileDataTab({ user }) {
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importMode, setImportMode] = useState("merge");

  const handleExport = async () => {
    setExporting(true);
    try {
      const data = await api.exportProfile(user);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `recommendarr-profile-${user}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error("Export failed:", e);
    }
    setExporting(false);
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportResult(null);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const result = await api.importProfile(user, data, importMode);
      setImportResult(result);
    } catch (err) {
      setImportResult({ status: "error", message: err.message || "Import failed" });
    }
    setImporting(false);
    e.target.value = "";
  };

  return (
    <>
      <div className="section-header"><h3><Download size={18} /> Export Profile</h3></div>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
        Download your feedback history and taste preferences as a JSON file. Use this to back up your data or transfer it to another instance.
      </p>
      <button className="btn btn-primary" onClick={handleExport} disabled={exporting} style={{ padding: "8px 18px", fontSize: 13, display: "inline-flex", alignItems: "center", gap: 6 }}>
        {exporting ? <Loader2 size={14} className="spinner" /> : <Download size={14} />}
        Export Profile
      </button>

      <div className="section-header" style={{ marginTop: 28 }}><h3><Upload size={18} /> Import Profile</h3></div>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>
        Restore from a previously exported profile. Choose merge to add new data without overwriting, or replace to fully overwrite existing data.
      </p>
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <select value={importMode} onChange={e => setImportMode(e.target.value)} style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text)", padding: "6px 12px", fontSize: 13 }}>
          <option value="merge">Merge (add new, keep existing)</option>
          <option value="replace">Replace (overwrite all)</option>
        </select>
        <label className="btn btn-secondary" style={{ padding: "8px 18px", fontSize: 13, display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          {importing ? <Loader2 size={14} className="spinner" /> : <Upload size={14} />}
          Choose File
          <input type="file" accept=".json" onChange={handleImport} style={{ display: "none" }} />
        </label>
      </div>
      {importResult && (
        <div style={{ marginTop: 12, padding: "10px 14px", borderRadius: 8, fontSize: 13,
          background: importResult.status === "ok" ? "rgba(46,204,113,0.08)" : "rgba(239,68,68,0.08)",
          border: `1px solid ${importResult.status === "ok" ? "rgba(46,204,113,0.2)" : "rgba(239,68,68,0.2)"}`,
          color: importResult.status === "ok" ? "#2ecc71" : "#ef4444" }}>
          {importResult.status === "ok"
            ? `Imported ${importResult.imported_feedback} feedback entries. Overrides ${importResult.overrides_updated ? "updated" : "unchanged"}.`
            : `Error: ${importResult.message || "Import failed"}`}
        </div>
      )}
    </>
  );
}
