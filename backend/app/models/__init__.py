"""Re-export all SQLAlchemy models for import convenience."""

from app.models.tables import (  # noqa: F401
    User, UserLibraryAccess, WatchHistory, TmdbCache,
    RecommendationLog, Feedback, Watchlist, WatchlistItem,
    InfluenceOverride, PlaybackSession,
    AutoGrabConfig, AutoGrabLog, AvailabilityAlert,
    VibePlaylist, VibePlaylistItem,
    Collection, UserCollectionProgress,
    Friendship, PrivacySettings,
    ImportJob, DiscoveryCache,
    RegionalTrending,
    CulturalEvent, CulturalEventRecommendation, CulturalEventDismissal, PulseSource,
    ZeitgeistEvent, ZeitgeistMapping, ZeitgeistDismissal,
    ContextualConfig, ContextualSignal,
    WrappedSnapshot,
    Notification, NotificationChannel,
    OnboardingQuiz, ReleaseNotification,
    Plugin,
    # Active tables (currently wired up)
    AppSetting, UserPreference, RoutingRule, RequestLog, AiSetting,
)
