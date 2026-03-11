import { Monitor, RefreshCw, Globe, CheckCircle2, Loader2, Clock, Sparkles, Bell } from "lucide-react";
import { api } from "../../api.js";
import PushNotificationToggle from "../../components/PushNotificationToggle.jsx";

const PREF_DESCRIPTIONS = {
  rec_count: "Number of recommendations to generate per mode (higher = slower but more variety)",
  freshness_weight: "How much to prioritize recent content over older titles (0=ignore, 1=strong bias)",
  diversity_weight: "How much to vary genres and styles in results (0=pure taste match, 1=maximum variety)",
  include_anime: "Include anime titles in all recommendation modes",
  include_adult: "Include adult-rated (18+) content in results",
  auto_request: "Automatically send grab-mode recommendations to Radarr/Sonarr via Seerr",
  language: "Default content language filter for recommendations",
  watchlist_sort: "Default sort order for the Watchlist page",
  watchlist_filter: "Default media type filter for the Watchlist page",
};

const WATCHLIST_SORTS = [
  { value: "added_desc", label: "Recently Added" },
  { value: "added_asc", label: "Oldest Added" },
  { value: "title_asc", label: "Title A-Z" },
  { value: "title_desc", label: "Title Z-A" },
  { value: "year_desc", label: "Newest Release" },
  { value: "year_asc", label: "Oldest Release" },
];

export default function PrefsTab({
  userPrefs, setUserPrefs, globalPrefs, setGlobalPrefs,
  prefsSaving, setPrefsSaving, devicesList, setDevicesList,
  schedule, setSchedule, schedSaving, setSchedSaving, schedSuggestion,
}) {
  return (
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
                setPrefsSaving("device");
                setTimeout(() => setPrefsSaving(false), 1500);
              } catch (err) { console.error("Failed to save device preference:", err); setPrefsSaving(false); }
            }}
          >
            <option value="">\u2014 No device selected \u2014</option>
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
            {prefsSaving === "device" && <span style={{ marginLeft: 8, color: "var(--green)", fontWeight: 600 }}><CheckCircle2 size={11} style={{ verticalAlign: -1 }} /> Saved!</span>}
          </div>
        )}
      </div>

      {/* Push Notifications */}
      <div style={{ background: "var(--bg-elevated)", borderRadius: 8, padding: 16 }}>
        <h4 style={{ margin: "0 0 8px" }}><Bell size={15} /> Push Notifications</h4>
        <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
          Receive native push notifications for new recommendations, sunset votes, and group nights.
        </p>
        <PushNotificationToggle />
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
                  {schedule.last_error && <span style={{ color: "var(--red)" }}> \u2014 Error: {schedule.last_error}</span>}
                </div>
              )}
            </div>
          );
        })()}
        {!schedule && <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading schedule...</div>}
      </div>

      {/* Global Defaults (Admin only) */}
      {globalPrefs && (
        <div className="global-prefs-section">
          <h4><Globe size={15} /> Global Defaults (all users)</h4>
          <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "-4px 0 12px 0" }}>
            These apply to all Plex users unless they\'ve overridden a specific setting.
          </p>
          <div style={{ background: "var(--bg-elevated)", borderRadius: 8, padding: 12 }}>
            {Object.entries(globalPrefs).map(([key, info]) => (
              <div className="pref-row" key={key}>
                <div>
                  <span className="pref-label">{key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</span>
                  {PREF_DESCRIPTIONS[key] && <div style={{ fontSize: 11, color: "var(--text-dim, var(--text-muted))", marginTop: 2, opacity: 0.7 }}>{PREF_DESCRIPTIONS[key]}</div>}
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
  );
}
