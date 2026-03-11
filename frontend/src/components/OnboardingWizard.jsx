import { useState, useCallback } from "react";
import { Loader2, CheckCircle2, XCircle, ChevronRight, ChevronLeft, Sparkles, ArrowRight } from "lucide-react";
import { setup } from "../api.js";
import WizardSteps from "./WizardSteps.jsx";

const STEPS = ["Welcome", "TMDB", "Integrations", "Ready"];

export default function OnboardingWizard({ onComplete, onRefresh }) {
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);

  // TMDB state
  const [tmdbKey, setTmdbKey] = useState("");
  const [tmdbTest, setTmdbTest] = useState(null); // null | "testing" | "ok" | "fail"

  // Integration state — each: { url, key, status: null|testing|ok|fail }
  const [integrations, setIntegrations] = useState({
    tautulli: { url: "", key: "", status: null },
    radarr: { url: "", key: "", status: null },
    sonarr: { url: "", key: "", status: null },
    seerr: { url: "", key: "", status: null },
  });

  const updateIntegration = useCallback((name, field, value) => {
    setIntegrations(prev => ({
      ...prev,
      [name]: { ...prev[name], [field]: value, status: null },
    }));
  }, []);

  const testTmdb = useCallback(async () => {
    if (!tmdbKey.trim()) return;
    setTmdbTest("testing");
    try {
      const res = await setup.testIntegration({
        type: "tmdb", url: "https://api.themoviedb.org", api_key: tmdbKey.trim(),
      });
      setTmdbTest(res.reachable && res.authenticated ? "ok" : "fail");
    } catch { setTmdbTest("fail"); }
  }, [tmdbKey]);

  const testIntegration = useCallback(async (name) => {
    const svc = integrations[name];
    if (!svc.url.trim()) return;
    updateIntegration(name, "status", "testing");
    try {
      const res = await setup.testIntegration({
        type: name, url: svc.url.trim(), api_key: svc.key.trim(),
      });
      updateIntegration(name, "status", res.reachable && res.authenticated ? "ok" : "fail");
    } catch {
      updateIntegration(name, "status", "fail");
    }
  }, [integrations, updateIntegration]);

  const handleComplete = useCallback(async () => {
    setSaving(true);
    try {
      // Collect all non-empty settings
      const settings = {};
      if (tmdbKey.trim()) settings.tmdb_api_key = tmdbKey.trim();
      Object.entries(integrations).forEach(([name, svc]) => {
        if (svc.url.trim()) settings[`${name}_url`] = svc.url.trim();
        if (svc.key.trim()) settings[`${name}_api_key`] = svc.key.trim();
      });

      if (Object.keys(settings).length > 0) {
        await setup.save(settings);
      }
      await setup.complete();
      if (onRefresh) onRefresh();
      onComplete();
    } catch (e) {
      console.error("Setup complete failed:", e);
    } finally {
      setSaving(false);
    }
  }, [tmdbKey, integrations, onComplete, onRefresh]);

  const canAdvance = () => {
    if (step === 1) return tmdbTest === "ok";
    return true;
  };

  const configuredCount = Object.values(integrations).filter(s => s.status === "ok").length;

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-wizard">
        {/* Progress bar */}
        <div className="wizard-progress">
          {STEPS.map((s, i) => (
            <div key={s} className={`wizard-step-dot ${i <= step ? "active" : ""} ${i < step ? "done" : ""}`}>
              {i < step ? <CheckCircle2 size={16} /> : <span>{i + 1}</span>}
              <span className="step-label">{s}</span>
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="wizard-content">
          <WizardSteps
            step={step}
            tmdbKey={tmdbKey} setTmdbKey={setTmdbKey}
            tmdbTest={tmdbTest} testTmdb={testTmdb}
            integrations={integrations}
            updateIntegration={updateIntegration}
            testIntegration={testIntegration}
            configuredCount={configuredCount}
          />
        </div>

        {/* Navigation */}
        <div className="wizard-nav">
          {step > 0 && (
            <button className="wizard-btn secondary" onClick={() => setStep(s => s - 1)}>
              <ChevronLeft size={14} /> Back
            </button>
          )}
          <div style={{ flex: 1 }} />
          {step < 3 ? (
            <button
              className="wizard-btn primary"
              onClick={() => setStep(s => s + 1)}
              disabled={!canAdvance()}
            >
              {step === 0 ? "Get Started" : "Next"} <ChevronRight size={14} />
            </button>
          ) : (
            <button
              className="wizard-btn primary"
              onClick={handleComplete}
              disabled={saving}
            >
              {saving ? <><Loader2 size={14} className="spin" /> Saving...</>
                : <><Sparkles size={14} /> Launch Recommendarr</>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
