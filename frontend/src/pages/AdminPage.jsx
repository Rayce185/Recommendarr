import { useState, useEffect, useCallback } from "react";
import { Settings, Database, Activity, BarChart3, SlidersHorizontal, Loader2, CheckCircle2, XCircle,
  Zap, Clock, Sparkles, Film, Tv, Users, RotateCcw } from "lucide-react";
import { api } from "../api.js";
import { formatHours } from "../utils.js";
import ConfigTab from "./admin/ConfigTab.jsx";
import PrefsTab from "./admin/PrefsTab.jsx";

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


        {settingsTab === "config" && (
          <ConfigTab
            sysSettings={sysSettings} editMode={editMode} editValues={editValues}
            saving={saving} saveMsg={saveMsg} showKeys={showKeys}
            enterEditMode={enterEditMode} handleSaveSettings={handleSaveSettings}
            setEditMode={setEditMode} setSaveMsg={setSaveMsg}
            handleEditField={handleEditField} toggleShowKey={toggleShowKey}
          />
        )}

        {settingsTab === "prefs" && (
          <PrefsTab
            userPrefs={userPrefs} setUserPrefs={setUserPrefs}
            globalPrefs={globalPrefs} setGlobalPrefs={setGlobalPrefs}
            prefsSaving={prefsSaving} setPrefsSaving={setPrefsSaving}
            devicesList={devicesList} setDevicesList={setDevicesList}
            schedule={schedule} setSchedule={setSchedule}
            schedSaving={schedSaving} setSchedSaving={setSchedSaving}
            schedSuggestion={schedSuggestion}
          />
        )}
      </div>
    </>
  );
}

export default AdminPage;
