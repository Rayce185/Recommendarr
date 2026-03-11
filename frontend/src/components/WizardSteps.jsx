import { Loader2, CheckCircle2, XCircle, Film, Key, Server, Rocket } from "lucide-react";

function StatusIcon({ status }) {
  if (status === "testing") return <Loader2 size={14} className="spin" />;
  if (status === "ok") return <CheckCircle2 size={14} style={{ color: "var(--green)" }} />;
  if (status === "fail") return <XCircle size={14} style={{ color: "var(--red)" }} />;
  return null;
}

function IntegrationRow({ name, label, desc, svc, onChange, onTest }) {
  return (
    <div className="wizard-integration">
      <div className="wizard-integ-header">
        <span className="wizard-integ-name">{label}</span>
        <StatusIcon status={svc.status} />
      </div>
      <p className="wizard-integ-desc">{desc}</p>
      <div className="wizard-integ-fields">
        <input
          placeholder={`${label} URL (e.g. http://192.168.0.x:port)`}
          value={svc.url}
          onChange={e => onChange(name, "url", e.target.value)}
        />
        <input
          type="password"
          placeholder="API Key"
          value={svc.key}
          onChange={e => onChange(name, "key", e.target.value)}
        />
        <button
          className="wizard-btn small"
          onClick={() => onTest(name)}
          disabled={!svc.url.trim() || svc.status === "testing"}
        >
          {svc.status === "testing" ? "Testing..." : "Test"}
        </button>
      </div>
    </div>
  );
}

export default function WizardSteps({
  step, tmdbKey, setTmdbKey, tmdbTest, testTmdb,
  integrations, updateIntegration, testIntegration, configuredCount,
}) {
  if (step === 0) {
    return (
      <div className="wizard-step-content">
        <Film size={48} style={{ color: "var(--accent)", marginBottom: 16 }} />
        <h2>Welcome to Recommendarr</h2>
        <p>Let's get your instance configured. This wizard will walk you through
        connecting your media stack so Recommendarr can deliver personalized
        recommendations to your Plex users.</p>
        <div className="wizard-checklist">
          <div><Key size={14} /> TMDB API key for metadata</div>
          <div><Server size={14} /> Tautulli, Radarr, Sonarr, Seerr connections</div>
          <div><Rocket size={14} /> First library sync</div>
        </div>
        <p className="wizard-note">Your Plex connection is already verified — you're signed in.</p>
      </div>
    );
  }

  if (step === 1) {
    return (
      <div className="wizard-step-content">
        <h2>TMDB API Key</h2>
        <p>Recommendarr uses The Movie Database for metadata, posters, and
        recommendations. Get a free API key at
        <a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noreferrer"> themoviedb.org</a>.</p>
        <div className="wizard-field-group">
          <label>TMDB API Key (v3 auth)</label>
          <div className="wizard-input-row">
            <input
              type="password"
              placeholder="Paste your TMDB API key here"
              value={tmdbKey}
              onChange={e => { setTmdbKey(e.target.value); }}
              autoFocus
            />
            <button
              className="wizard-btn small"
              onClick={testTmdb}
              disabled={!tmdbKey.trim() || tmdbTest === "testing"}
            >
              {tmdbTest === "testing" ? <><Loader2 size={12} className="spin" /> Testing</> : "Verify"}
            </button>
            <StatusIcon status={tmdbTest} />
          </div>
          {tmdbTest === "fail" && (
            <p className="wizard-error">Could not reach TMDB with this key. Check it and try again.</p>
          )}
          {tmdbTest === "ok" && (
            <p className="wizard-success">TMDB connected successfully!</p>
          )}
        </div>
      </div>
    );
  }

  if (step === 2) {
    return (
      <div className="wizard-step-content">
        <h2>Integrations</h2>
        <p>Connect your media management tools. All are optional but recommended
        for the full experience. You can always configure these later in Settings.</p>
        <div className="wizard-integrations-list">
          <IntegrationRow
            name="tautulli" label="Tautulli"
            desc="Watch history and statistics — enables personalized recommendations"
            svc={integrations.tautulli}
            onChange={updateIntegration} onTest={testIntegration}
          />
          <IntegrationRow
            name="radarr" label="Radarr"
            desc="Movie management — enables request tracking and library health"
            svc={integrations.radarr}
            onChange={updateIntegration} onTest={testIntegration}
          />
          <IntegrationRow
            name="sonarr" label="Sonarr"
            desc="TV show management — enables series tracking and requests"
            svc={integrations.sonarr}
            onChange={updateIntegration} onTest={testIntegration}
          />
          <IntegrationRow
            name="seerr" label="Overseerr / Jellyseerr"
            desc="Request management — enables one-click media requests from recommendations"
            svc={integrations.seerr}
            onChange={updateIntegration} onTest={testIntegration}
          />
        </div>
        {configuredCount > 0 && (
          <p className="wizard-success">{configuredCount} integration{configuredCount > 1 ? "s" : ""} connected</p>
        )}
      </div>
    );
  }

  if (step === 3) {
    const summary = Object.entries(integrations).filter(([, s]) => s.status === "ok");
    return (
      <div className="wizard-step-content">
        <Rocket size={48} style={{ color: "var(--accent)", marginBottom: 16 }} />
        <h2>You're All Set!</h2>
        <p>Recommendarr is ready to launch. Here's what we've configured:</p>
        <div className="wizard-summary">
          <div className="wizard-summary-row">
            <CheckCircle2 size={14} style={{ color: "var(--green)" }} />
            <span>Plex — connected (signed in)</span>
          </div>
          <div className="wizard-summary-row">
            {tmdbTest === "ok"
              ? <CheckCircle2 size={14} style={{ color: "var(--green)" }} />
              : <XCircle size={14} style={{ color: "var(--red)" }} />}
            <span>TMDB — {tmdbTest === "ok" ? "connected" : "not configured"}</span>
          </div>
          {summary.map(([name]) => (
            <div key={name} className="wizard-summary-row">
              <CheckCircle2 size={14} style={{ color: "var(--green)" }} />
              <span>{name.charAt(0).toUpperCase() + name.slice(1)} — connected</span>
            </div>
          ))}
          {Object.entries(integrations).filter(([, s]) => s.status !== "ok").map(([name]) => (
            <div key={name} className="wizard-summary-row skipped">
              <span style={{ width: 14, textAlign: "center" }}>—</span>
              <span>{name.charAt(0).toUpperCase() + name.slice(1)} — skipped</span>
            </div>
          ))}
        </div>
        <p className="wizard-note">Click "Launch Recommendarr" to save settings and start your first
        library sync. You can reconfigure any service later in the admin panel.</p>
      </div>
    );
  }

  return null;
}
