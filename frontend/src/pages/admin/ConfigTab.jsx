import { Settings, SlidersHorizontal, Save, Loader2, Clock, Eye, EyeOff, X } from "lucide-react";
import AISettingsPanel from "../AISettingsPanel.jsx";

export default function ConfigTab({
  sysSettings, editMode, editValues, saving, saveMsg, showKeys,
  enterEditMode, handleSaveSettings, setEditMode, setSaveMsg,
  handleEditField, toggleShowKey
}) {
  if (!sysSettings) return null;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        {!editMode ? (
          <button className="test-btn" onClick={enterEditMode} style={{ gap: 6 }}><SlidersHorizontal size={12} /> Edit Settings</button>
        ) : (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="test-btn" onClick={handleSaveSettings} disabled={saving} style={{ background: "var(--accent)", color: "#fff", gap: 6 }}>
              {saving ? <><Loader2 size={12} className="spin" /> Saving...</> : <><Save size={12} /> Save Changes</>}
            </button>
            <button className="test-btn" onClick={() => { setEditMode(false); setSaveMsg(null); }} style={{ gap: 6 }}><X size={12} /> Cancel</button>
          </div>
        )}
        {saveMsg && <span style={{ fontSize: 13, color: saveMsg.type === "ok" ? "var(--green)" : "var(--red)" }}>{saveMsg.text}</span>}
      </div>

      {/* Service Endpoints */}
      <div className="admin-card" style={{ marginBottom: 12 }}>
        <h4><Settings size={15} /> Service Endpoints</h4>
        {sysSettings.services && Object.entries(sysSettings.services).map(([name, svc]) => (
          <div key={name} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6, textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</div>
            {Object.entries(svc).map(([propLabel, prop]) => {
              if (!prop || !prop.field) return (
                <div className="service-row" key={propLabel} style={{ padding: "3px 0" }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 80 }}>{propLabel}</span>
                  <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{prop?.value || "\u2014"}</span>
                </div>
              );
              const isKey = propLabel.includes("key") || propLabel.includes("token") || propLabel === "api_key";
              const field = prop.field;
              return (
                <div className="service-row" key={propLabel} style={{ padding: "3px 0", gap: 8 }}>
                  <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 80 }}>
                    {propLabel.replace(/_/g, " ")}
                    {prop.overridden && <span title="Overridden from settings.json" style={{ color: "var(--accent)", marginLeft: 4, fontSize: 10 }}>\u25cf</span>}
                  </span>
                  {editMode ? (
                    <div style={{ display: "flex", gap: 4, flex: 1, justifyContent: "flex-end" }}>
                      <input
                        type={isKey && !showKeys[field] ? "password" : "text"}
                        value={editValues[field] ?? ""}
                        onChange={e => handleEditField(field, e.target.value)}
                        style={{ flex: 1, maxWidth: 360, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", color: "var(--text)", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}
                      />
                      {isKey && (
                        <button onClick={() => toggleShowKey(field)} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 6px", cursor: "pointer", color: "var(--text-muted)", fontSize: 11 }}>
                          {showKeys[field] ? <EyeOff size={12} /> : <Eye size={12} />}
                        </button>
                      )}
                    </div>
                  ) : (
                    <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{prop.value || "\u2014"}</span>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* AI Integration */}
      <AISettingsPanel />

      {/* Auth & App */}
      <div className="admin-card" style={{ marginBottom: 12 }}>
        <h4><Clock size={15} /> Auth &amp; App</h4>
        {[...(sysSettings.auth ? Object.entries(sysSettings.auth) : []), ...(sysSettings.app ? Object.entries(sysSettings.app) : [])].map(([propLabel, prop]) => {
          if (!prop || !prop.field) return null;
          const field = prop.field;
          return (
            <div className="service-row" key={propLabel} style={{ padding: "3px 0", gap: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {propLabel.replace(/_/g, " ")}
                {prop.overridden && <span title="Overridden" style={{ color: "var(--accent)", marginLeft: 4, fontSize: 10 }}>\u25cf</span>}
              </span>
              {editMode ? (
                <input
                  type={typeof prop.value === "number" ? "number" : "text"}
                  value={editValues[field] ?? ""}
                  onChange={e => handleEditField(field, typeof prop.value === "number" ? parseInt(e.target.value) || 0 : e.target.value)}
                  style={{ maxWidth: 200, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", color: "var(--text)", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}
                />
              ) : (
                <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
                  {typeof prop.value === "boolean" ? (prop.value ? "true" : "false") : prop.value}
                  {propLabel === "jwt_expiry_hours" && ` (${Math.round((prop.value || 0) / 24)}d)`}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {editMode && (
        <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "8px 0" }}>
          <span style={{ color: "var(--accent)", marginRight: 4 }}>\u25cf</span> = overridden from settings.json (env var value replaced).
          Changes are live immediately. Service clients may need a connection test to verify new URLs/keys.
        </div>
      )}
    </div>
  );
}
