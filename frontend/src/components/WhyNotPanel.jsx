import { useState } from "react";
import { HelpCircle, ChevronDown, ChevronUp, Loader2, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { api } from "../api.js";

const levelColors = {
  strong_match: "#2ecc71",
  moderate_match: "#f59e0b",
  weak_match: "#e67e22",
  no_match: "#ef4444",
};

export default function WhyNotPanel({ tmdbId, mediaType, user }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(null);

  const handleClick = async () => {
    if (data) { setOpen(o => !o); return; }
    setLoading(true);
    setError(null);
    try {
      const result = await api.whyNot(tmdbId, user, mediaType);
      setData(result);
      setOpen(true);
    } catch (e) {
      setError(e.message || "Failed to analyze");
    }
    setLoading(false);
  };

  return (
    <div style={{ marginBottom: 16 }}>
      <button
        className="btn btn-sm btn-secondary"
        onClick={handleClick}
        disabled={loading}
        style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, padding: "5px 12px" }}
      >
        {loading ? <Loader2 size={13} className="spinner" /> : <HelpCircle size={13} />}
        Why wasn't this recommended?
        {data && (open ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
      </button>

      {error && (
        <div style={{ marginTop: 8, fontSize: 12, color: "#ef4444", display: "flex", alignItems: "center", gap: 6 }}>
          <AlertTriangle size={13} /> {error}
        </div>
      )}

      {data && open && (
        <div style={{ marginTop: 10, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 10, padding: 14 }}>
          {/* Verdict */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12, padding: "8px 12px",
            borderRadius: 8, background: data.verdict === "above" ? "rgba(46,204,113,0.08)" : "rgba(239,68,68,0.08)",
            border: `1px solid ${data.verdict === "above" ? "rgba(46,204,113,0.2)" : "rgba(239,68,68,0.2)"}` }}>
            {data.verdict === "above" ? <CheckCircle2 size={15} color="#2ecc71" /> : <XCircle size={15} color="#ef4444" />}
            <div style={{ fontSize: 12, lineHeight: 1.5 }}>
              <div style={{ fontWeight: 600, color: "var(--text)" }}>
                Score: {(data.total_score * 100).toFixed(0)}% (threshold: {(data.threshold * 100).toFixed(0)}%)
              </div>
              <div style={{ color: "var(--text-muted)" }}>{data.verdict_text}</div>
            </div>
          </div>

          {/* Signal breakdown */}
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Signal Breakdown
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 12 }}>
            {data.signals.map((sig, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                <span style={{ width: 20, textAlign: "center" }}>{sig.emoji}</span>
                <span style={{ flex: 1, color: "var(--text-secondary)" }}>{sig.label}</span>
                <div style={{ width: 80, height: 6, borderRadius: 3, background: "var(--bg-elevated)", overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(sig.raw_score * 100, 100)}%`, height: "100%", borderRadius: 3,
                    background: levelColors[sig.level] || "var(--text-muted)", transition: "width 0.3s" }} />
                </div>
                <span style={{ width: 36, textAlign: "right", fontWeight: 600, color: levelColors[sig.level] }}>
                  {(sig.raw_score * 100).toFixed(0)}%
                </span>
                <span style={{ width: 24, textAlign: "right", fontSize: 10, color: "var(--text-muted)" }}>
                  ×{(sig.weight * 100).toFixed(0)}
                </span>
              </div>
            ))}
          </div>

          {/* Reasons */}
          {data.reasons.length > 0 && (
            <>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Key Factors
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 12, color: "var(--text-secondary)" }}>
                {data.reasons.map((r, i) => <div key={i}>{r}</div>)}
              </div>
            </>
          )}

          {/* User top genres vs title genres */}
          {data.user_top_genres?.length > 0 && (
            <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-muted)" }}>
              <span style={{ fontWeight: 600 }}>Your top genres:</span>{" "}
              {data.user_top_genres.map(g => g.genre).join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
