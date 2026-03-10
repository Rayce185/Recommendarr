"""Re-export all SQLAlchemy models for import convenience.

Models are split across domain modules:
  core.py     — User, WatchHistory, TmdbCache, Recommendations, Feedback, Watchlists, Playback
  features.py — Vibes, Collections, Social, Imports, Discovery, Regional
  pulse.py    — Cultural events, Zeitgeist, Contextual, Wrapped
  admin.py    — Notifications, Onboarding, Plugins, Settings, Routing, AI config
"""

from app.models.core import (  # noqa: F401
    User, UserLibraryAccess, WatchHistory, TmdbCache,
    RecommendationLog, Feedback, Watchlist, WatchlistItem,
    InfluenceOverride, PlaybackSession,
    AutoGrabConfig, AutoGrabLog, AvailabilityAlert,
)

from app.models.features import (  # noqa: F401
    VibePlaylist, VibePlaylistItem,
    Collection, UserCollectionProgress,
    Friendship, PrivacySettings,
    ImportJob, DiscoveryCache,
    RegionalTrending, GroupNightSession,
)

from app.models.pulse import (  # noqa: F401
    CulturalEvent, CulturalEventRecommendation, CulturalEventDismissal, PulseSource,
    ZeitgeistEvent, ZeitgeistMapping, ZeitgeistDismissal,
    ContextualConfig, ContextualSignal,
    WrappedSnapshot,
)

from app.models.admin import (  # noqa: F401
    Notification, NotificationChannel,
    OnboardingQuiz, ReleaseNotification,
    Plugin,
    AppSetting, UserPreference, RoutingRule, RequestLog, AiSetting,
    RefreshSchedule,
)

from app.models.library_health import (  # noqa: F401
    VitalityScore, SunsetItem, SunsetVote, KickedItem,
)
