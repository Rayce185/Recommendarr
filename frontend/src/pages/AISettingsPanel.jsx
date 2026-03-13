import { useState, useEffect, useCallback } from "react";
import { Loader2, Save, CheckCircle2, XCircle, Sparkles, Eye, EyeOff, RefreshCw, Trash2, ChevronDown, Zap, AlertCircle } from "lucide-react";
import { api } from "../api.js";

function AISettingsPanel() {
  const [aiCfg, setAiCfg] = useState(null);
  const [providers, setProviders] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [models, setModels] = useState([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [showKey, setShowKey] = useState(false);

  // Local edit state
  const [llmProvider, setLlmProvider] = useState("disabled");
  const [llmEndpoint, setLlmEndpoint] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmTemp, setLlmTemp] = useState(0.7);
  const [llmMaxTokens, setLlmMaxTokens] = useState(500);
  const [featMood, setFeatMood] = useState(false);
  const [featExplanations, setFeatExplanations] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, prov] = await Promise.all([api.aiConfig(true), api.aiProviders()]);
      setAiCfg(cfg);
      setProviders(prov);
      // Populate local state from config
      setLlmProvider(cfg.llm?.provider || "disabled");
      setLlmEndpoint(cfg.llm?.endpoint || "");
      setLlmApiKey(cfg.llm?.api_key || "");
      setLlmModel(cfg.llm?.model || "");
      setLlmTemp(cfg.llm?.temperature ?? 0.7);
      setLlmMaxTokens(cfg.llm?.max_tokens ?? 500);
      setFeatMood(cfg.features?.ai_mood || false);
      setFeatExplanations(cfg.features?.ai_explanations || false);
      setExpanded(cfg.llm?.provider !== "disabled");
    } catch (e) { console.error("AI config load failed:", e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const providerInfo = providers?.llm_providers?.find(p => p.id === llmProvider);
  const needsEndpoint = providerInfo?.needs_endpoint ?? false;
  const needsKey = providerInfo?.needs_key ?? false;
  const isEnabled = llmProvider !== "disabled";

  const handleProviderChange = (val) => {
    setLlmProvider(val);
    setDirty(true);
    setTestResult(null);
    setModels([]);
    setLlmModel("");
    // Pre-fill endpoint from placeholder
    const pInfo = providers?.llm_providers?.find(p => p.id === val);
    if (pInfo?.endpoint_placeholder && !llmEndpoint) setLlmEndpoint(pInfo.endpoint_placeholder);
  };

  const handleFetchModels = async () => {
    setFetchingModels(true);
    try {
      const result = await api.aiModels({ provider: llmProvider, endpoint: llmEndpoint, api_key: llmApiKey });
      setModels(result.models || []);
      if (result.models?.length === 0) setTestResult({ status: "warning", message: "Connected but no models found." });
    } catch (e) { setTestResult({ status: "error", message: e.message }); }
    setFetchingModels(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.aiTest({ provider: llmProvider, endpoint: llmEndpoint, api_key: llmApiKey, model: llmModel });
      setTestResult(result);
    } catch (e) { setTestResult({ status: "error", message: e.message }); }
    setTesting(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const result = await api.aiUpdateConfig({
        llm: { provider: llmProvider, endpoint: llmEndpoint, api_key: llmApiKey, model: llmModel, temperature: llmTemp, max_tokens: llmMaxTokens },
        features: { ai_mood: featMood, ai_explanations: featExplanations },
      });
      setSaveMsg({ type: "ok", text: "AI configuration saved." });
      setDirty(false);
    } catch (e) { setSaveMsg({ type: "err", text: e.message || "Save failed" }); }
    setSaving(false);
  };

  const inputStyle = { background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "6px 10px", color: "var(--text)", fontSize: 12, fontFamily: "'JetBrains Mono', monospace", width: "100%" };
  const selectStyle = { ...inputStyle, appearance: "none", cursor: "pointer", colorScheme: "dark", backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")", backgroundRepeat: "no-repeat", backgroundPosition: "right 8px center", paddingRight: 28 };
  const labelStyle = { fontSize: 12, color: "var(--text-muted)", minWidth: 110, flexShrink: 0 };
  const rowStyle = { display: "flex", alignItems: "center", gap: 10, padding: "5px 0" };

  if (loading) return <div className="admin-card" style={{ marginBottom: 12 }}><h4><Sparkles size={15} /> AI Integration</h4><div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</div></div>;

  return (
    <div className="admin-card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }} onClick={() => setExpanded(!expanded)}>
        <h4 style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
          <Sparkles size={15} /> AI Integration
          {isEnabled && <span style={{ fontSize: 10, background: "var(--accent)", color: "#fff", borderRadius: 8, padding: "1px 7px", marginLeft: 6 }}>ON</span>}
          {!isEnabled && <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: 6 }}>Disabled</span>}
        </h4>
        <ChevronDown size={14} style={{ color: "var(--text-muted)", transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
      </div>

      {expanded && (
        <div style={{ marginTop: 12 }}>
          {/* Provider selector */}
          <div style={rowStyle}>
            <span style={labelStyle}>LLM Provider</span>
            <select value={llmProvider} onChange={e => handleProviderChange(e.target.value)} style={{ ...selectStyle, maxWidth: 320 }}>
              {providers?.llm_providers?.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>

          {isEnabled && (
            <>
              {/* Endpoint */}
              {needsEndpoint && (
                <div style={rowStyle}>
                  <span style={labelStyle}>Endpoint URL</span>
                  <input type="text" value={llmEndpoint} onChange={e => { setLlmEndpoint(e.target.value); setDirty(true); }}
                    placeholder={providerInfo?.endpoint_placeholder || ""} style={{ ...inputStyle, maxWidth: 320 }} />
                </div>
              )}

              {/* API Key */}
              {needsKey && (
                <div style={rowStyle}>
                  <span style={labelStyle}>API Key</span>
                  <div style={{ display: "flex", gap: 4, flex: 1, maxWidth: 320 }}>
                    <input type={showKey ? "text" : "password"} value={llmApiKey} onChange={e => { setLlmApiKey(e.target.value); setDirty(true); }}
                      placeholder="sk-..." style={{ ...inputStyle }} />
                    <button onClick={() => setShowKey(!showKey)} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 6px", cursor: "pointer", color: "var(--text-muted)" }}>
                      {showKey ? <EyeOff size={12} /> : <Eye size={12} />}
                    </button>
                  </div>
                </div>
              )}

              {/* Model */}
              <div style={rowStyle}>
                <span style={labelStyle}>Model</span>
                <div style={{ display: "flex", gap: 4, flex: 1, maxWidth: 320 }}>
                  {models.length > 0 ? (
                    <select value={llmModel} onChange={e => { setLlmModel(e.target.value); setDirty(true); }} style={{ ...selectStyle }}>
                      <option value="">Select a model...</option>
                      {models.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <input type="text" value={llmModel} onChange={e => { setLlmModel(e.target.value); setDirty(true); }}
                      placeholder="e.g. gemma3:4b, gpt-4o-mini" style={{ ...inputStyle }} />
                  )}
                  <button onClick={handleFetchModels} disabled={fetchingModels || (!needsEndpoint && !needsKey)} className="test-btn"
                    style={{ whiteSpace: "nowrap", fontSize: 11, padding: "4px 8px" }}>
                    {fetchingModels ? <><Loader2 size={11} className="spin" /> Loading</> : <><RefreshCw size={11} /> Fetch Models</>}
                  </button>
                </div>
              </div>

              {/* Temperature & Max Tokens */}
              <div style={rowStyle}>
                <span style={labelStyle} title="Controls randomness: 0 = deterministic, 1 = creative, 2 = wild. Default 0.7 works well for recommendations.">Temperature ⓘ</span>
                <input type="number" value={llmTemp} min={0} max={2} step={0.1} onChange={e => { setLlmTemp(parseFloat(e.target.value) || 0); setDirty(true); }}
                  style={{ ...inputStyle, maxWidth: 80 }} />
                <span style={{ ...labelStyle, minWidth: 80, textAlign: "right" }} title="Maximum length of AI responses. Higher = more detailed explanations but slower. Default 500 is a good balance.">Max tokens ⓘ</span>
                <input type="number" value={llmMaxTokens} min={50} max={4096} step={50} onChange={e => { setLlmMaxTokens(parseInt(e.target.value) || 500); setDirty(true); }}
                  style={{ ...inputStyle, maxWidth: 80 }} />
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", padding: "2px 0 4px", lineHeight: 1.4 }}>
                Temperature: creativity level (0=focused, 2=wild). Max tokens: AI response length limit.
              </div>

              {/* Test + Result */}
              <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 0", flexWrap: "wrap" }}>
                <button onClick={handleTest} disabled={testing || !llmModel} className="test-btn" style={{ fontSize: 11, gap: 4 }}>
                  {testing ? <><Loader2 size={11} className="spin" /> Testing...</> : <><Zap size={11} /> Test Connection</>}
                </button>
                {testResult && (
                  <span style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4, color: testResult.status === "ok" ? "var(--green)" : testResult.status === "warning" ? "var(--accent)" : "var(--red)" }}>
                    {testResult.status === "ok" ? <CheckCircle2 size={12} /> : testResult.status === "warning" ? <AlertCircle size={12} /> : <XCircle size={12} />}
                    {testResult.message}
                  </span>
                )}
              </div>

              {/* Divider */}
              <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

              {/* Feature toggles */}
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Features</div>
              {providers?.features?.map(f => (
                <div key={f.id} style={{ ...rowStyle, cursor: "pointer" }} onClick={() => { if (f.id === "ai_mood") { setFeatMood(!featMood); } else { setFeatExplanations(!featExplanations); } setDirty(true); }}>
                  <div style={{ width: 34, height: 18, borderRadius: 9, background: (f.id === "ai_mood" ? featMood : featExplanations) ? "var(--accent)" : "var(--border)", position: "relative", transition: "background 0.2s", flexShrink: 0 }}>
                    <div style={{ width: 14, height: 14, borderRadius: 7, background: "#fff", position: "absolute", top: 2, left: (f.id === "ai_mood" ? featMood : featExplanations) ? 18 : 2, transition: "left 0.2s" }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{f.label}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{f.description}</div>
                  </div>
                </div>
              ))}

              {/* Save */}
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
                <button onClick={handleSave} disabled={saving} className="test-btn" style={{ background: "var(--accent)", color: "#fff", fontSize: 12, gap: 4 }}>
                  {saving ? <><Loader2 size={12} className="spin" /> Saving...</> : <><Save size={12} /> Save AI Config</>}
                </button>
                {saveMsg && <span style={{ fontSize: 12, color: saveMsg.type === "ok" ? "var(--green)" : "var(--red)" }}>{saveMsg.text}</span>}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}



export default AISettingsPanel;
