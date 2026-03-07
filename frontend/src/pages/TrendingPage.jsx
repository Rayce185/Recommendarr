import { useState, useEffect, useCallback } from "react";
import { TrendingUp, Globe, Tv, Sparkles, MessageCircle, ExternalLink, ArrowUp, MessageSquare } from "lucide-react";
import Skeleton from "../components/Skeleton.jsx";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";
import CustomSelect from "../components/CustomSelect.jsx";

const TRENDING_SUBTABS = [
  { id: "global", label: "Global Trending", icon: TrendingUp },
  { id: "country", label: "By Country", icon: Globe },
  { id: "streaming", label: "By Streaming", icon: Tv },
  { id: "new_releases", label: "New Releases", icon: Sparkles },
  { id: "buzz", label: "Talk of the Web", icon: MessageCircle },
];

function BuzzCard({ item, onCardClick }) {
  const hasMedia = item.has_tmdb && item.tmdb_id;
  return (
    <div className={`buzz-card ${hasMedia ? "has-media" : ""}`}>
      {hasMedia && item.poster_url && (
        <img className="buzz-poster" src={item.poster_url} alt="" loading="lazy"
          onClick={() => onCardClick?.({ tmdb_id: item.tmdb_id, media_type: item.media_type, title: item.title })} />
      )}
      <div className="buzz-content">
        <div className="buzz-source">
          <span className="buzz-sub">r/{item.subreddit}</span>
          <span className="buzz-stats">
            <ArrowUp size={12} /> {item.reddit_score?.toLocaleString()}
            <MessageSquare size={12} style={{ marginLeft: 8 }} /> {item.num_comments?.toLocaleString()}
          </span>
        </div>
        <div className="buzz-title">{item.reddit_title}</div>
        {hasMedia && item.title !== item.reddit_title && (
          <div className="buzz-match">
            Matched: <strong>{item.title}</strong>
            {item.vote_average > 0 && <span className="buzz-rating">★ {item.vote_average?.toFixed(1)}</span>}
          </div>
        )}
        <a className="buzz-link" href={item.reddit_url} target="_blank" rel="noopener noreferrer">
          <ExternalLink size={12} /> View discussion
        </a>
      </div>
    </div>
  );
}

function TrendingPage({ onCardClick, subtab: initialSubtab, onSubtabChange }) {
  const [subtab, setSubtabRaw] = useState(initialSubtab || "global");
  const setSubtab = (t) => { setSubtabRaw(t); onSubtabChange?.(t); };
  const [items, setItems] = useState([]);
  const [buzzItems, setBuzzItems] = useState([]);
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

  // Buzz filter
  const [buzzFilter, setBuzzFilter] = useState("all");

  useEffect(() => {
    api.trendingCountries().then(d => setCountries(d.countries || [])).catch(() => {});
  }, []);

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

    if (subtab === "buzz") {
      api.buzz()
        .then(data => setBuzzItems(data.results || []))
        .catch(err => setError(err.message))
        .finally(() => setLoading(false));
      return;
    }

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

  const filteredBuzz = buzzFilter === "all"
    ? buzzItems
    : buzzFilter === "matched"
    ? buzzItems.filter(b => b.has_tmdb)
    : buzzItems.filter(b => b.category === buzzFilter);

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

        {subtab !== "buzz" && (
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
        )}

        {subtab === "buzz" && (
          <div className="trending-filters">
            <div className="filter-group">
              <label>Filter</label>
              <CustomSelect value={buzzFilter} onChange={setBuzzFilter} options={[
                { value: "all", label: "All Posts" },
                { value: "matched", label: "TMDB Matched" },
                { value: "movie", label: "Movies" },
                { value: "tv", label: "TV" },
                { value: "anime", label: "Anime" },
              ]} />
            </div>
          </div>
        )}

        {currentProvider && subtab === "streaming" && (
          <div className="provider-badge">
            {currentProvider.logo_url && <img src={currentProvider.logo_url} alt="" style={{ width: 24, height: 24, borderRadius: 4 }} />}
            <span>Popular on {currentProvider.name}</span>
          </div>
        )}

        {loading ? <Skeleton.CardGrid count={8} /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         subtab === "buzz" ? (
           filteredBuzz.length === 0 ? <EmptyState icon={MessageCircle} title="No buzz found" /> :
           <div className="buzz-list">
             {filteredBuzz.map((item, i) => <BuzzCard key={`${item.subreddit}-${i}`} item={item} onCardClick={onCardClick} />)}
           </div>
         ) : (
           items.length === 0 ? <EmptyState icon={TrendingUp} title="Nothing trending for this filter" /> :
           <div className="card-grid">
             {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={{ ...item, score: null }} onClick={onCardClick} />)}
           </div>
         )}
      </div>
    </>
  );
}

export default TrendingPage;
