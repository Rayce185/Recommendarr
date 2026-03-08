import { useState, useEffect, useCallback, useRef } from "react";
import { Globe, MapPin, Film, ChevronDown, ChevronUp, TrendingUp, Pin, Loader2 } from "lucide-react";
import { api } from "../api.js";
import { LoadingState, EmptyState, ErrorState } from "../components/StateDisplays.jsx";
import MediaCard from "../components/MediaCard.jsx";
import CustomSelect from "../components/CustomSelect.jsx";

function matchColor(score) {
  if (score === null || score === undefined) return "rgba(255,255,255,0.06)";
  if (score < 0.3) return `rgba(100, 140, 200, ${0.15 + score})`;
  if (score < 0.5) return `rgba(140, 160, 100, ${0.2 + score * 0.6})`;
  if (score < 0.7) return `rgba(200, 170, 60, ${0.3 + score * 0.5})`;
  return `rgba(240, 160, 40, ${0.4 + score * 0.4})`;
}

function matchLabel(score) {
  if (score === null || score === undefined) return "";
  const pct = Math.round(score * 100);
  if (pct >= 70) return "Strong match";
  if (pct >= 50) return "Good match";
  if (pct >= 30) return "Some overlap";
  return "New territory";
}

function CountryCard({ country, isSelected, isPinned, onClick, onPin }) {
  const match = country.taste_match;
  const pct = match !== null ? Math.round(match * 100) : null;
  return (
    <button className={`wc-country-card ${isSelected ? "selected" : ""}`}
      onClick={onClick} style={{ borderColor: isSelected ? "var(--accent)" : matchColor(match) }}>
      <div className="wc-card-top">
        <span className="wc-flag">{country.flag}</span>
        <span className="wc-name">{country.name}</span>
        <span className={`wc-pin-btn ${isPinned ? "pinned" : ""}`}
          onClick={e => { e.stopPropagation(); onPin(country.code); }}
          title={isPinned ? "Unpin country" : "Pin to top"}>
          <Pin size={12} />
        </span>
      </div>
      {pct !== null && (
        <div className="wc-match-bar-wrap">
          <div className="wc-match-bar" style={{ width: `${pct}%`, background: matchColor(match) }} />
          <span className="wc-match-pct">{pct}%</span>
        </div>
      )}
      {country.labels?.length > 0 && (
        <div className="wc-labels">
          {country.labels.slice(0, 2).map(l => <span key={l} className="wc-label">{l}</span>)}
        </div>
      )}
      <div className="wc-notable">{country.notable}</div>
    </button>
  );
}

function WorldCinemaPage({ user, onCardClick }) {
  const [mapData, setMapData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pinned, setPinned] = useState([]);

  const [selectedCountry, setSelectedCountry] = useState(null);
  const [trending, setTrending] = useState([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendPage, setTrendPage] = useState(1);
  const [trendTotalPages, setTrendTotalPages] = useState(1);
  const [loadingMore, setLoadingMore] = useState(false);
  const [mediaType, setMediaType] = useState("all");
  const [collapsed, setCollapsed] = useState({});
  const trendRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    const username = user?.username || user;
    Promise.all([
      api.worldCinemaMap(username),
      username ? api.worldCinemaPinned(username).catch(() => ({ pinned: [] })) : Promise.resolve({ pinned: [] }),
    ]).then(([data, pins]) => {
      setMapData(data);
      setPinned(pins.pinned || []);
    }).catch(err => setError(err.message)).finally(() => setLoading(false));
  }, [user]);

  const loadTrending = useCallback((code, page = 1, append = false) => {
    if (page === 1) setTrendLoading(true);
    else setLoadingMore(true);
    api.trendingExpanded("country", { region: code, media_type: mediaType, page })
      .then(data => {
        setTrending(prev => append ? [...prev, ...(data.results || [])] : (data.results || []));
        setTrendPage(page);
        setTrendTotalPages(data.total_pages || 1);
      })
      .catch(() => { if (!append) setTrending([]); })
      .finally(() => { setTrendLoading(false); setLoadingMore(false); });
  }, [mediaType]);

  const selectCountry = (country) => {
    setSelectedCountry(country);
    setTrendPage(1);
    loadTrending(country.code, 1);
    setTimeout(() => trendRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
  };

  useEffect(() => {
    if (selectedCountry) { setTrendPage(1); loadTrending(selectedCountry.code, 1); }
  }, [mediaType]);

  const togglePin = useCallback((code) => {
    const username = user?.username || user;
    if (!username) return;
    const next = pinned.includes(code) ? pinned.filter(c => c !== code) : [...pinned, code].slice(0, 10);
    setPinned(next);
    api.worldCinemaSetPinned(username, next).catch(() => {});
  }, [pinned, user]);

  const toggleRegion = (name) => setCollapsed(p => ({ ...p, [name]: !p[name] }));

  const allCountries = mapData ? mapData.regions.flatMap(r => r.countries) : [];
  const pinnedCountries = allCountries.filter(c => pinned.includes(c.code));
  const topMatches = allCountries.filter(c => c.taste_match !== null)
    .sort((a, b) => b.taste_match - a.taste_match).slice(0, 5);

  if (loading) return <LoadingState message="Building your cinema world map..." />;
  if (error) return <ErrorState message={error} />;
  if (!mapData) return <EmptyState icon={Globe} title="No data available" />;

  return (
    <>
      <div className="page-header">
        <h2><Globe size={20} style={{ marginRight: 8 }} />World Cinema Map</h2>
        <p>Discover films and shows from around the world, ranked by your taste profile.
          Click a country to browse trending content — pin your favorites for quick access.</p>
      </div>
      <div className="page-body">
        {pinnedCountries.length > 0 && (
          <div className="wc-pinned-section">
            <h3><Pin size={14} /> Pinned Countries</h3>
            <div className="wc-country-grid">
              {pinnedCountries.map(c => (
                <CountryCard key={c.code} country={c} isSelected={selectedCountry?.code === c.code}
                  isPinned onClick={() => selectCountry(c)} onPin={togglePin} />
              ))}
            </div>
          </div>
        )}

        {topMatches.length > 0 && (
          <div className="wc-top-matches">
            <h3><Film size={16} /> Your Top Cinema Matches</h3>
            <div className="wc-top-row">
              {topMatches.map(c => (
                <button key={c.code} className="wc-top-chip" onClick={() => selectCountry(c)}
                  style={{ background: matchColor(c.taste_match) }}>
                  <span>{c.flag}</span><span>{c.name}</span>
                  <span className="wc-top-pct">{Math.round(c.taste_match * 100)}%</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {mapData.regions.map(region => (
          <div key={region.name} className="wc-region">
            <button className="wc-region-header" onClick={() => toggleRegion(region.name)}>
              <MapPin size={14} /><span>{region.name}</span>
              <span className="wc-region-count">{region.countries.length} countries</span>
              {collapsed[region.name] ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            </button>
            {!collapsed[region.name] && (
              <div className="wc-country-grid">
                {region.countries.map(c => (
                  <CountryCard key={c.code} country={c} isSelected={selectedCountry?.code === c.code}
                    isPinned={pinned.includes(c.code)} onClick={() => selectCountry(c)} onPin={togglePin} />
                ))}
              </div>
            )}
          </div>
        ))}

        {selectedCountry && (
          <div className="wc-trending-section" ref={trendRef}>
            <div className="wc-trending-header">
              <h3><TrendingUp size={16} />
                <span>{selectedCountry.flag} Trending in {selectedCountry.name}</span></h3>
              <CustomSelect value={mediaType} onChange={setMediaType} options={[
                { value: "all", label: "All" }, { value: "movie", label: "Movies" }, { value: "tv", label: "TV Shows" },
              ]} />
            </div>
            {selectedCountry.taste_match !== null && (
              <div className="wc-match-summary">
                <span className="wc-match-dot" style={{ background: matchColor(selectedCountry.taste_match) }} />
                <span>{matchLabel(selectedCountry.taste_match)} ({Math.round(selectedCountry.taste_match * 100)}%)</span>
                <span className="wc-match-genres">
                  Top genres: {Object.entries(selectedCountry.genres).sort((a, b) => b[1] - a[1])
                    .slice(0, 4).map(([g]) => g).join(", ")}
                </span>
              </div>
            )}
            {trendLoading ? <LoadingState message={`Loading ${selectedCountry.name} trending...`} /> :
             trending.length === 0 ? <EmptyState icon={Globe} title={`No trending content for ${selectedCountry.name}`} /> : (
              <>
                <div className="card-grid">
                  {trending.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={{ ...item, score: null }} onClick={onCardClick} />)}
                </div>
                {trendPage < trendTotalPages && (
                  <div className="wc-load-more">
                    <button className="btn btn-secondary" disabled={loadingMore}
                      onClick={() => loadTrending(selectedCountry.code, trendPage + 1, true)}>
                      {loadingMore ? <><Loader2 size={14} className="spin" /> Loading...</> : "Load More"}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}

export default WorldCinemaPage;
