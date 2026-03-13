# Changelog

All notable changes to Recommendarr are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-03-08

### Highlights

First stable release. Recommendarr is a self-hosted media recommendation engine
for Plex that learns from viewing behavior across all server users and generates
personalized, explainable recommendations.

### Added

- **5 Recommendation Modes**: Watch Tonight, Worth Grabbing, Rediscover, Mood Match, Group Night
- **AI-Powered Explanations**: Optional LLM generates natural language reasons for each recommendation (Ollama, OpenAI, Anthropic)
- **Smart Mood Matching**: Natural language input parsed into genre/keyword weights with LLM enhancement
- **Multi-Source Trending**: Global TMDB, by country, by streaming provider, new releases, anime
- **Collection Tracking**: Detects partially watched franchises with completion progress and one-click requests
- **Group Night**: Multi-user taste intersection recommendations
- **Plex Wrapped**: Per-user viewing statistics and insights
- **Friend System**: Send/accept/decline friend requests, activity feed, friend suggestions (≥30% taste overlap), privacy controls (visibility, anonymization, friend request blocking)
- **Friend Activity Feed**: See what friends are watching with relative timestamps and completion status
- **Group Night Friends**: Quick-select friends in Group Night user picker
- **Genre Filters**: Filter trending results by any of 27 genres across all tabs
- **User-Preferred Countries**: Auto-detected from watch history language distribution — quick-pick chips in By Country tab
- **Series Progress**: Completion progress bars on TV recommendation cards
- **Discovery Feed**: Personalized weekly mix based on taste profile
- **Social Layer**: Taste overlap scores and server-wide trending
- **World Cinema Map**: Geographic discovery with taste matching
- **Cultural Pulse**: RSS-powered trending theme detection
- **Talk of the Web**: Reddit-powered film buzz in Trending
- **List Import Engine**: LLM-powered title extraction from pasted lists
- **Coming Soon Calendar**: TMDB + Radarr/Sonarr release tracking
- **Notification Center**: Bell icon with compute-on-read notifications
- **Why Not?**: Negative transparency — explains why titles aren't recommended
- **Recommendation History**: Full logging with paginated browsing, stats, and mode breakdown
- **Advanced Filters**: Year range and rating threshold on recommendation pages
- **"Because You Watched X"**: Library-trace attribution on recommendation cards
- **External Ratings**: Badges and score breakdowns relabeled as "Why we recommended this"
- **Taste Profiles**: Auto-generated from watch history with manual genre/keyword tuning
- **Feedback Loop**: Thumbs up/down/dismiss adjusts future recommendations
- **Plex Watchlist Integration**: Add/remove from recommendation cards
- **Seerr Request Integration**: Request media not yet in library
- **Profile Export/Import**: Data portability for user profiles
- **Admin User Switcher**: Preview any user's recommendations
- **Plex OAuth Authentication**: Secure login with server access verification
- **Editable Settings Panel**: Runtime configuration via UI (Servarr, Routing, AI)
- **N-Instance Servarr Registry**: Multiple Radarr/Sonarr instances with auto-detected routing
- **Dark/Light Theme Toggle**: OS preference detection with manual override
- **PWA Manifest**: Mobile install support
- **Endpoint Caching Layer**: TTL-based caching for calendar and notifications

### Performance

- Persistent TMDB cache with parallel resolver and connection pooling
- Startup warming — profiles, library, and recs pre-computed in background
- User-countries endpoint cached (12s → instant on cache hit)
- Friend activity uses single server-wide Tautulli pull (efficient, no per-friend queries)
- 3-tier collection cache (SQLite + stale-while-revalidate)
- Parallel TMDB enrichment and user-filtered history
- Lazy AI explanations (compute on demand, not upfront)

### Architecture

- Single-container deployment (FastAPI + React + nginx + supervisor)
- SQLite database for persistent state
- Modular codebase — all files under 300 lines, zero dead code, zero import errors
- 46+ REST API endpoints with JWT authentication
- Docker image (amd64, arm64 planned)
- Docker Hub: `rayce185/recommendarr`
- GitHub Container Registry: `ghcr.io/rayce185/recommendarr`

## [0.5.0] — 2026-02-27

Initial tagged release. Core recommendation engine with Plex/Tautulli integration,
basic scoring, and single-page React frontend.
