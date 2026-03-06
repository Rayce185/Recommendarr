import { useState, useEffect, useCallback } from "react";
import { Settings, Database, Activity, Monitor, Loader2, CheckCircle2, XCircle,
  RefreshCw, Save, Trash2, Users, Globe } from "lucide-react";
import { api } from "../api.js";
import { formatHours } from "../utils.js";
import AISettingsPanel from "./AISettingsPanel.jsx";

function AdminPage({ subtab: initialSubtab, onSubtabChange, user: currentUser }) {
  const [settingsTab, setSettingsTabRaw] = useState(initialSubtab || "services");
  const [devicesList, setDevicesList] = useState([]);
  const [globalPrefs, setGlobalPrefs] = useState(null);
  const [userPrefs, setUserPrefs] = useState(null);
  const [prefsSaving, setPrefsSaving] = useState(false);
  const setSettingsTab = (t) => { setSettingsTabRaw(t); onSubtabChange?.(t); };
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [sysSettings, setSysSettings] = useState(null);
  const [cacheInfo, setCacheInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [testing, setTesting] = useState({});
  const [editMode, setEditMode] = useState(false);
  const [editValues, setEditValues] = useState({});
  const [schedule, setSchedule] = useState(null);
  const [schedSaving, setSchedSaving] = useState(false);
  const [schedSuggestion, setSchedSuggestion] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [showKeys, setShowKeys] = useState({});

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.health(),
      api.stats(),
      api.systemSettings().catch(() => null),
      api.cacheDetailed().catch(() => null),
    ])
      .then(([h, s, cfg, cache]) => { setHealth(h); setStats(s); setSysSettings(cfg); setCacheInfo(cache); })
      .then(() => {
        if (currentUser) {
          api.getSchedule(currentUser).then(setSchedule).catch(() => {});
          api.suggestSchedule(currentUser).then(setSchedSuggestion).catch(() => {});
        }
      })
      .then(() => {
        api.devices().then(r => setDevicesList(r.devices || [])).catch(() => {});
        api.preferences().then(r => setUserPrefs(r.preferences || {})).catch(() => {});
        api.globalPreferences().then(r => setGlobalPrefs(r.global_defaults || null)).catch(() => {});
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleTest = async (service) => {
    setTesting(p => ({ ...p, [service]: true }));
    setTestResults(p => ({ ...p, [service]: null }));
    try {
      const result = await api.testConnection(service);
      setTestResults(p => ({ ...p, [service]: result }));
    } catch (err) {
      setTestResults(p => ({ ...p, [service]: { status: "error", message: err.message } }));
    }
    setTesting(p => ({ ...p, [service]: false }));
  };

  const handleClearCache = async (scope) => {
    try {
      await api.cacheClear(scope);
      const cache = await api.cacheDetailed().catch(() => null);
      setCacheInfo(cache);
    } catch (err) {
      console.error(err);
    }
  };

  const enterEditMode = async () => {
    try {
      const data = await api.systemSettingsEdit();
      // Flatten all editable fields into a simple {field: value} map
      const flat = {};
      const extractFields = (obj) => {
        Object.values(obj).forEach(v => {
          if (v && typeof v === "object" && v.field) {
            flat[v.field] = v.value ?? "";
          } else if (v && typeof v === "object" && !v.field) {
            extractFields(v);
          }
        });
      };
      extractFields(data);
      setEditValues(flat);
      setEditMode(true);
      setSaveMsg(null);
    } catch (err) {
      console.error("Failed to load settings for editing:", err);
    }
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const result = await api.updateSettings(editValues);
      setSaveMsg({ type: "ok", text: `Saved ${result.updated?.length || 0} setting(s)` });
      setEditMode(false);
      // Reload display data
      const cfg = await api.systemSettings().catch(() => null);
      setSysSettings(cfg);
    } catch (err) {
      setSaveMsg({ type: "err", text: err.message || "Save failed" });
    }
    setSaving(false);
  };

  const handleEditField = (field, value) => {
    setEditValues(prev => ({ ...prev, [field]: value }));
  };

  const toggleShowKey = (field) => {
    setShowKeys(prev => ({ ...prev, [field]: !prev[field] }));
  };

  if (loading) return <><div className="page-header"><h2>System Settings</h2></div><div className="page-body"><LoadingState /></div></>;
  if (error) return <><div className="page-header"><h2>System Settings</h2></div><div className="page-body"><ErrorState message={error} onRetry={load} /></div></>;

  const settingsTabs = [
    { id: "services", label: "Services", icon: Activity },
    { id: "library", label: "Library", icon: Database },
    { id: "cache", label: "Cache", icon: BarChart3 },
    { id: "config", label: "Configuration", icon: Settings },
    { id: "prefs", label: "Preferences", icon: SlidersHorizontal },
  ];

  return (
    <>
      <div className="page-header">
        <h2>System Settings</h2>
        <p>Recommendarr v{health?.version} &middot; {health?.architecture}</p>
      </div>
      <div className="page-body">
        <div className="settings-tabs">
          {settingsTabs.map(t => (
            <button key={t.id} className={`settings-tab ${settingsTab === t.id ? "active" : ""}`} onClick={() => setSettingsTab(t.id)}>
              <t.icon size={14} /> {t.label}
            </button>
          ))}
        </div>

        {settingsTab === "services" && (
          <div className="admin-grid">
            {health?.services && Object.entries(health.services).map(([name, svc]) => (
              <div className="admin-card" key={name}>
                <div className="service-row" style={{ marginBottom: 8 }}>
                  <h4 style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
                    {svc.status === "ok" ? <CheckCircle2 size={14} style={{ color: "var(--green)" }} /> : <XCircle size={14} style={{ color: "var(--red)" }} />}
                    {name}
                  </h4>
                  <button className={`test-btn ${testing[name] ? "testing" : ""}`} onClick={() => handleTest(name)}>
                    {testing[name] ? <><Loader2 size={11} className="spin" /> Testing...</> : <><Zap size={11} /> Test</>}
                  </button>
                </div>
                <div className="service-detail">{svc.url}</div>
                {testResults[name] && (
                  <div className={`test-result ${testResults[name].status === "ok" ? "ok" : "err"}`}>
                    {testResults[name].status === "ok" ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                    {" "}{testResults[name].message}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {settingsTab === "library" && (
          <div className="admin-grid">
            <div className="admin-card">
              <h4><Film size={15} /> Movies</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.movies?.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <h4><Tv size={15} /> TV Series</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.tv_series?.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <h4><Sparkles size={15} /> Anime</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.anime_series?.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <h4><Users size={15} /> Users</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.users}</div>
            </div>
          </div>
        )}

        {settingsTab === "cache" && (
          <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button className="test-btn" onClick={() => handleClearCache("all")}><RotateCcw size={11} /> Clear All Caches</button>
              <button className="test-btn" onClick={() => handleClearCache("recommendations")}><RotateCcw size={11} /> Clear Recs Only</button>
            </div>
            {cacheInfo?.ttl && (
              <div className="admin-card" style={{ marginBottom: 12 }}>
                <h4><Clock size={15} /> TTL Settings</h4>
                {Object.entries(cacheInfo.ttl).map(([k, v]) => (
                  <div className="service-row" key={k}><span>{k}</span><span style={{ color: "var(--text-muted)", fontSize: 13 }}>{v}</span></div>
                ))}
              </div>
            )}
            {cacheInfo?.stats && (
              <div className="admin-card">
                <h4><BarChart3 size={15} /> Statistics</h4>
                {typeof cacheInfo.stats === "object" ? Object.entries(cacheInfo.stats).map(([k, v]) => (
                  <div className="service-row" key={k}><span>{k}</span><span style={{ fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{typeof v === "number" ? v.toLocaleString() : String(v)}</span></div>
                )) : <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No detailed stats available</div>}
              </div>
            )}
          </div>
        )}

        {settingsTab === "config" && sysSettings && (
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
                        <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{prop?.value || "—"}</span>
                      </div>
                    );
                    const isKey = propLabel.includes("key") || propLabel.includes("token") || propLabel === "api_key";
                    const field = prop.field;
                    return (
                      <div className="service-row" key={propLabel} style={{ padding: "3px 0", gap: 8 }}>
                        <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 80 }}>
                          {propLabel.replace(/_/g, " ")}
                          {prop.overridden && <span title="Overridden from settings.json" style={{ color: "var(--accent)", marginLeft: 4, fontSize: 10 }}>●</span>}
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
                          <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{prop.value || "—"}</span>
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
                      {prop.overridden && <span title="Overridden" style={{ color: "var(--accent)", marginLeft: 4, fontSize: 10 }}>●</span>}
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
                <span style={{ color: "var(--accent)", marginRight: 4 }}>●</span> = overridden from settings.json (env var value replaced).
                Changes are live immediately. Service clients may need a connection test to verify new URLs/keys.
              </div>
            )}
          </div>
        )}

        {settingsTab === "prefs" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Device Selector */}
            <div className="settings-device-section">
              <h4><Monitor size={15} /> Default Playback Device</h4>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px 0" }}>
                Select where "Watch Now" plays media. Refresh to detect online devices.
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <select
                  className="device-select"
                  value={typeof userPrefs?.default_device_id === "object" ? userPrefs?.default_device_id?.value : userPrefs?.default_device_id || ""}
                  onChange={async (e) => {
                    const dev = devicesList.find(d => d.client_id === e.target.value);
                    try {
                      await api.updatePreferences({
                        default_device_id: e.target.value,
                        default_device_name: dev?.name || "",
                      });
                      setUserPrefs(prev => ({
                        ...prev,
                        default_device_id: e.target.value,
                        default_device_name: dev?.name || "",
                      }));
                    } catch (err) { console.error("Failed to save device preference:", err); }
                  }}
                >
                  <option value="">— No device selected —</option>
                  {devicesList.map(d => (
                    <option key={d.client_id} value={d.client_id}>
                      {d.name} ({d.product})
                    </option>
                  ))}
                </select>
                <button className="btn btn-secondary" style={{ padding: "6px 10px", fontSize: 12, whiteSpace: "nowrap" }}
                  onClick={async () => {
                    try { const r = await api.devices(); setDevicesList(r.devices || []); } catch (e) {}
                  }}
                >
                  <RefreshCw size={13} /> Refresh
                </button>
              </div>
              {devicesList.length > 0 && (
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
                  {devicesList.length} device{devicesList.length !== 1 ? "s" : ""} online
                </div>
              )}
            </div>

            {/* Auto-Refresh Schedule */}
            <div style={{ background: "var(--bg-elevated)", borderRadius: 8, padding: 16 }}>
              <h4 style={{ margin: "0 0 4px" }}><Clock size={15} /> Scheduled Refresh</h4>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
                Automatically refresh recommendations daily at the quietest time in your viewing pattern.
              </p>
              {schedule && (() => {
                const updateSched = async (patch) => {
                  setSchedSaving(true);
                  try {
                    const res = await api.updateSchedule(schedule.username, patch);
                    setSchedule(res);
                  } catch (e) { console.error(e); }
                  setSchedSaving(false);
                };
                const applySuggestion = () => {
                  if (schedSuggestion) {
                    updateSched({ enabled: true, hour: schedSuggestion.suggested_hour, minute: 0 });
                  }
                };
                const isSuggested = schedSuggestion && schedule.hour === schedSuggestion.suggested_hour && schedule.minute === 0;
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                      <input type="checkbox" checked={schedule.enabled} onChange={e => updateSched({ enabled: e.target.checked })} />
                      <span style={{ fontSize: 13 }}>Enable daily auto-refresh</span>
                      {schedSaving && <Loader2 size={13} className="spinner" />}
                    </label>
                    {schedSuggestion && schedSuggestion.confidence !== "low" && (
                      <div style={{ background: "var(--surface)", borderRadius: 6, padding: "8px 12px", fontSize: 12, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <Sparkles size={14} style={{ color: "var(--accent)", flexShrink: 0 }} />
                        <span style={{ color: "var(--text-muted)" }}>
                          Based on {schedSuggestion.total_plays} plays, your quietest hour is{" "}
                          <strong style={{ color: "var(--text)" }}>{String(schedSuggestion.suggested_hour).padStart(2,"0")}:00</strong>
                          {" "}(peak: {String(schedSuggestion.peak_hour).padStart(2,"0")}:00)
                        </span>
                        {!isSuggested && (
                          <button onClick={applySuggestion} style={{
                            background: "var(--accent)", color: "#fff", border: "none", borderRadius: 4,
                            padding: "3px 8px", fontSize: 11, cursor: "pointer", whiteSpace: "nowrap"
                          }}>Use suggested</button>
                        )}
                        {isSuggested && <CheckCircle2 size={14} style={{ color: "var(--green)" }} />}
                      </div>
                    )}
                    {schedule.enabled && (
                      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <label style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase" }}>Time (server)</label>
                          <input type="time"
                            value={`${String(schedule.hour).padStart(2,"0")}:${String(schedule.minute).padStart(2,"0")}`}
                            onChange={e => {
                              const [h, m] = e.target.value.split(":").map(Number);
                              updateSched({ hour: h, minute: m });
                            }}
                            style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", fontSize: 13 }}
                          />
                        </div>
                      </div>
                    )}
                    {schedule.last_run_at && (
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        Last auto-refresh: {new Date(schedule.last_run_at).toLocaleString()}
                        {schedule.last_run_ms ? ` (${(schedule.last_run_ms/1000).toFixed(1)}s)` : ""}
                        {schedule.last_error && <span style={{ color: "var(--red)" }}> — Error: {schedule.last_error}</span>}
                      </div>
                    )}
                  </div>
                );
              })()}
              {!schedule && <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading schedule...</div>}
            </div>

            {/* Global Defaults (Admin only) */}            {/* Global Defaults (Admin only) */}
            {globalPrefs && (
              <div className="global-prefs-section">
                <h4><Globe size={15} /> Global Defaults (all users)</h4>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "-4px 0 12px 0" }}>
                  These apply to all Plex users unless they've overridden a specific setting.
                </p>
                <div style={{ background: "var(--bg-elevated)", borderRadius: 8, padding: 12 }}>
                  {Object.entries(globalPrefs).map(([key, info]) => (
                    <div className="pref-row" key={key}>
                      <div>
                        <span className="pref-label">{key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</span>
                        <span className={`pref-source ${info.source}`}>{info.source}</span>
                      </div>
                      <div className="pref-control">
                        {typeof info.value === "boolean" ? (
                          <label className="toggle-switch" style={{ position: "relative", width: 36, height: 20, display: "inline-block" }}>
                            <input type="checkbox" checked={info.value} onChange={async (e) => {
                              setPrefsSaving(true);
                              await api.updateGlobalPreferences({ [key]: e.target.checked });
                              const r = await api.globalPreferences();
                              setGlobalPrefs(r.global_defaults);
                              setPrefsSaving(false);
                            }} style={{ display: "none" }} />
                            <span style={{
                              position: "absolute", cursor: "pointer", inset: 0, borderRadius: 20,
                              background: info.value ? "var(--green)" : "var(--surface)", transition: "0.2s",
                            }}>
                              <span style={{
                                position: "absolute", height: 14, width: 14, left: info.value ? 18 : 4, bottom: 3,
                                background: "#fff", borderRadius: "50%", transition: "0.2s",
                              }} />
                            </span>
                          </label>
                        ) : typeof info.value === "number" ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <input type="range" min={0} max={1} step={0.1} value={info.value}
                              onChange={async (e) => {
                                const val = parseFloat(e.target.value);
                                await api.updateGlobalPreferences({ [key]: val });
                                const r = await api.globalPreferences();
                                setGlobalPrefs(r.global_defaults);
                              }}
                            />
                            <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 28 }}>{info.value}</span>
                          </div>
                        ) : (
                          <select value={info.value} onChange={async (e) => {
                            await api.updateGlobalPreferences({ [key]: e.target.value });
                            const r = await api.globalPreferences();
                            setGlobalPrefs(r.global_defaults);
                          }} style={{ padding: "4px 8px", fontSize: 12 }}>
                            {key === "language" && [["en","English"],["de","Deutsch"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
                            {key === "watchlist_sort" && WATCHLIST_SORTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                            {key === "watchlist_filter" && ["all","movie","tv"].map(v => <option key={v} value={v}>{v}</option>)}
                            {!["language","watchlist_sort","watchlist_filter"].includes(key) && <option value={info.value}>{String(info.value)}</option>}
                          </select>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

export default AdminPage;
