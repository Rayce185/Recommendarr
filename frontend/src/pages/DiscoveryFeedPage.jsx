import { useState, useEffect, useCallback } from "react";
import { Sparkles, Gem, Heart, RefreshCw } from "lucide-react";
import { api } from "../api.js";
import MediaCard from "../components/MediaCard.jsx";
import Skeleton from "../components/Skeleton.jsx";
import { ErrorState, EmptyState } from "../components/StateDisplays.jsx";

const SECTION_ICONS = {
  sparkles: Sparkles,
  gem: Gem,
  heart: Heart,
};

function FeedSection({ section, onCardClick, onFeedback }) {
  const Icon = SECTION_ICONS[section.icon] || Sparkles;
  return (
    <div className="feed-section">
      <div className="feed-section-header">
        <Icon size={20} className="feed-section-icon" />
        <div>
          <h3 className="feed-section-title">{section.title}</h3>
          <p className="feed-section-subtitle">{section.subtitle}</p>
        </div>
      </div>
      <div className="card-grid feed-grid">
        {section.items.map((item, i) => (
          <MediaCard
            key={`${item.tmdb_id}-${i}`}
            item={item}
            onClick={onCardClick}
            onFeedback={onFeedback}
          />
        ))}
      </div>
    </div>
  );
}

function DiscoveryFeedPage({ user, onCardClick }) {
  const [feed, setFeed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((refresh = false) => {
    if (!user) return;
    if (refresh) setRefreshing(true); else setLoading(true);
    setError(null);
    api.discoveryFeed(user, refresh)
      .then(data => setFeed(data))
      .catch(err => setError(err.message))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const handleFeedback = useCallback(async (item, action) => {
    if (!action) return;
    try {
      await api.submitFeedback(user, {
        tmdb_id: item.tmdb_id,
        media_type: item.media_type || "movie",
        action,
        title: item.title || "",
        genres: item.genres || [],
        keywords: item.keywords || [],
      });
    } catch (e) {}
  }, [user]);

  const sections = feed?.sections || [];

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2>Your Weekly Mix</h2>
          <button
            className="btn btn-secondary"
            style={{ padding: "6px 10px", fontSize: 12 }}
            onClick={() => load(true)}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? "spinning" : ""} />
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        <p>A personalized mix curated from your library and taste profile</p>
      </div>
      <div className="page-body">
        {loading ? <Skeleton.CardGrid count={6} /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         sections.length === 0 ? (
           <EmptyState
             icon={Sparkles}
             title="No feed yet"
             message="Watch a few things and check back — your mix builds over time."
           />
         ) : (
           <div className="feed-sections">
             {sections.map(section => (
               <FeedSection
                 key={section.id}
                 section={section}
                 onCardClick={onCardClick}
                 onFeedback={handleFeedback}
               />
             ))}
           </div>
         )}
      </div>
    </>
  );
}

export default DiscoveryFeedPage;
