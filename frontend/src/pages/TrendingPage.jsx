import { useState, useEffect, useCallback } from "react";
import { TrendingUp, Globe, Tv, Sparkles } from "lucide-react";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";
import CustomSelect from "../components/CustomSelect.jsx";

const TRENDING_SUBTABS = [
  { id: "global", label: "Global Trending", icon: TrendingUp },
  { id: "country", label: "By Country", icon: Globe },
  { id: "streaming", label: "By Streaming", icon: Tv },
  { id: "new_releases", label: "New Releases", icon: Sparkles },
];

function TrendingPage({ onCardClick, subtab: initialSubtab, onSubtabChange }) {
  const [subtab, setSubtabRaw] = useState(initialSubtab || "global");
  const setSubtab = (t) => { setSubtabRaw(t); onSubtabChange?.(t); };
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mediaType, setMediaType] = useState("all");

  // Country state
  const [countries, setCountries] = useState([]);
  const [region, setRegion] = useState("CH");

  // Streaming state
  const [providers, setProviders] = useState([]);
  const [providerId, setProviderId] = useState(null);
  const [providerRegion, setProviderRegion] = useState("CH");

  // Load country list once
  useEffect(() => {
    api.trendingCountries().then(d => setCountries(d.countries || [])).catch(() => {});
  }, []);

  // Load providers when streaming tab or region changes
  useEffect(() => {
    if (subtab === "streaming") {
      api.trendingProviders(providerRegion).then(d => {
        const list = d.providers || [];
        setProviders(list);
        if (list.length > 0 && !providerId) setProviderId(list[0].id);
      }).catch(() => {});
    }
  }, [subtab, providerRegion]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    let source = subtab === "streaming" ? "provider" : subtab;
    const opts = { media_type: mediaType };
    if (subtab === "country") opts.region = region;
    if (subtab === "streaming") {
      opts.region = providerRegion;
      opts.provider_id = providerId;
    }
    api.trendingExpanded(source, opts)
      .then(data => setItems(data.results || []))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [subtab, mediaType, region, providerId, providerRegion]);

  useEffect(() => { load(); }, [load]);

  const currentProvider = providers.find(p => p.id === providerId);

  return (
    <>
      <div className="page-header">
        <h2>Trending</h2>
        <p>Discover what's popular across different sources</p>
      </div>
      <div className="page-body">
        <div className="trending-subtabs">
          {TRENDING_SUBTABS.map(t => (
            <button key={t.id} className={`trending-subtab ${subtab === t.id ? "active" : ""}`} onClick={() => setSubtab(t.id)}>
              <t.icon size={14} /> {t.label}
            </button>
          ))}
        </div>

        <div className="trending-filters">
          <div className="filter-group">
            <label>Type</label>
            <CustomSelect value={mediaType} onChange={setMediaType} options={[
              { value: "all", label: "All" },
              { value: "movie", label: "Movies" },
              { value: "tv", label: "TV Shows" },
              { value: "anime", label: "Anime" },
            ]} />
          </div>

          {subtab === "country" && (
            <div className="filter-group">
              <label>Country</label>
              <CustomSelect value={region} onChange={setRegion}
                options={countries.map(c => ({ value: c.code, label: c.name }))} />
            </div>
          )}

          {subtab === "streaming" && (
            <>
              <div className="filter-group">
                <label>Region</label>
                <CustomSelect value={providerRegion} onChange={v => { setProviderRegion(v); setProviderId(null); }}
                  options={countries.map(c => ({ value: c.code, label: c.name }))} />
              </div>
              <div className="filter-group">
                <label>Service</label>
                <CustomSelect value={providerId || ""} onChange={v => setProviderId(Number(v))}
                  options={providers.map(p => ({ value: p.id, label: p.name, logo: p.logo_url }))} />
              </div>
            </>
          )}
        </div>

        {currentProvider && subtab === "streaming" && (
          <div className="provider-badge">
            {currentProvider.logo_url && <img src={currentProvider.logo_url} alt="" style={{ width: 24, height: 24, borderRadius: 4 }} />}
            <span>Popular on {currentProvider.name}</span>
          </div>
        )}

        {loading ? <LoadingState message="Fetching trends..." /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         items.length === 0 ? <EmptyState icon={TrendingUp} title="Nothing trending for this filter" /> :
         <div className="card-grid">
           {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={{ ...item, score: null }} onClick={onCardClick} />)}
         </div>}
      </div>
    </>
  );
}

export default TrendingPage;
