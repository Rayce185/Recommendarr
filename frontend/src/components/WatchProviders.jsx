/**
 * WatchProviders — streaming/rent/buy availability display.
 * Extracted from DetailModal for §7.7 compliance.
 */

const CATEGORY_LABELS = { flatrate: "Stream", rent: "Rent", buy: "Buy", free: "Free" };

function WatchProviders({ providers, link }) {
  if (!providers || Object.keys(providers).length === 0) return null;

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>Where to Watch</div>
      {["flatrate", "rent", "buy", "free"].map(cat => {
        const items = providers[cat];
        if (!items || items.length === 0) return null;
        return (
          <div key={cat} style={{ marginBottom: 8 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", marginRight: 8 }}>{CATEGORY_LABELS[cat]}:</span>
            <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
              {items.map((p, i) => (
                <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "var(--bg-card)", padding: "3px 8px", borderRadius: 6, fontSize: 12, color: "var(--text-secondary)" }}>
                  {p.logo_path && <img src={`https://image.tmdb.org/t/p/w45${p.logo_path}`} alt="" style={{ width: 16, height: 16, borderRadius: 3 }} />}
                  {p.provider_name}
                </span>
              ))}
            </span>
          </div>
        );
      })}
      {link && (
        <a href={link} target="_blank" rel="noopener noreferrer"
           style={{ fontSize: 11, color: "var(--accent)", textDecoration: "none" }}>
          View all options on TMDB →
        </a>
      )}
    </div>
  );
}

export default WatchProviders;
