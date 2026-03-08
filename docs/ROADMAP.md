# RECOMMENDARR — Personal Recommendation Engine

**Version:** 0.5.0 (Phase 3 — Discovery + Social)
**Updated:** 2026-03-07 (260307_02)
**Status:** PHASE 3 NEARLY COMPLETE — 6/7 items done. Phase 2 complete.
**Owner:** Ray DiRenzo
**Infrastructure:** unRAID Server (192.168.0.111)

---

## 1. VISION

A self-hosted media recommendation engine that learns from viewing behavior across all Plex users. Uses completion rates, rewatch patterns, and content similarity to generate explainable recommendations. Library-aware, private, multi-user, actionable. Optional LLM integration for enhanced explanations and intelligent discovery. Designed for GitHub release.

---

## 2. CURRENT STATE (v0.3.0)

### 2.1 What's Running

| Component | Container | Port | Status |
|-----------|-----------|------|--------|
| Backend API | `recommendarr` | 30800 | ✅ Running |
| Frontend UI | `recommendarr-ui` | 30801 | ✅ Running |

Both containers on `src_default` Docker network. Frontend nginx proxies `/api/v1/*` to backend.

### 2.2 Working Features

**Authentication (NEW — Session 33):**
- Plex OAuth login — aligned 1:1 with Overseerr's proven flow
- Frontend creates PIN directly on plex.tv, polls plex.tv for claim
- Backend validates token via `plex.tv/users/account.json`
- Server access check via `plex.tv/api/users` (XML) + `machineIdentifier` match
- JWT sessions (30-day expiry, HS256, sessionStorage)
- Per-user Plex token embedded in JWT for watchlist operations
- Admin detection via plexId/email match against server owner
- 19/20 shared users validated against server

**Recommendation Modes:**
- **Watch Tonight** — In-library picks scored against user taste profile
- **Worth Grabbing** — Beyond-library discovery via Seerr/TMDB trending
- **Rediscover** — Previously watched + liked, stale for 6+ months
- **Mood Match** — Natural language mood → genre/keyword scoring (template-based, LLM-enhanced when configured)
- **Trending** — Currently: global TMDB trending via Seerr (expansion planned, see §4)

**Infrastructure:**
- 24 Plex users loaded from Tautulli
- User taste profiles (genre weights, keywords, personnel scoring)
- In-memory recommendation cache (15 min TTL) + library cache (30 min) + TMDB ID cache (24h)
- Mobile-responsive UI with collapsible hamburger sidebar
- Plex OAuth with welcome screen + avatar/username in sidebar

### 2.3 Current Data Flow

```
plex.tv ───→ OAuth authentication, user identity, server access check
Tautulli ──→ Watch history + user IDs
Radarr ────→ Movie library (titles, posters, genres, TMDB IDs)
Sonarr TV ─→ TV library
Sonarr Anime → Anime library
Seerr ─────→ TMDB discovery, trending, detail enrichment, request workflow
TMDB CDN ──→ Poster/backdrop images (via Radarr/Sonarr stored URLs)
```

### 2.4 Auth Implementation Detail

Aligned with Overseerr's flow (source-verified from sct/overseerr GitHub):

```
Frontend (browser)                    plex.tv                    Backend
─────────────────                    ────────                    ───────
POST /api/v2/pins?strong=true  ──→   Creates PIN         
                               ←──   {id, code}
Open popup auth#!?code=...     ──→   User approves
GET  /api/v2/pins/{id}         ──→   Poll (every 1s)
                               ←──   {authToken}
                                                          POST /auth/plex {authToken}
                                                            → GET /users/account.json
                                                            → GET /api/users (XML)
                                                            → machineIdentifier match
                                                            → Issue JWT
                               ←──────────────────────    {token, user}
Store in sessionStorage
Attach Authorization: Bearer on all requests
```

### 2.5 Known Issues / Gaps

- ~~No authentication~~ → FIXED (Session 33)
- **User ID mismatch** — Tautulli uses numeric Plex IDs, Seerr uses email, Radarr/Sonarr don't know users. Resolved with `user_reverse_map` but fragile.
- **5 separate API keys** required in backend .env
- **Image fallback** — some Sonarr entries have TVDB URLs, some have TMDB, some have nothing
- **"Watch Tonight" exclusion** — recently watched items not properly excluded
- **Taste Profile slow** — first build per user can take 10-30s due to Seerr keyword enrichment
- **Taste Profile not editable** — display only, no user customization yet
- **Admin user switcher** — not implemented yet (logged in as self only)
- **System Status** — display only, needs to become System Settings

---

## 3. DESIGN DECISIONS (Locked — Session 33)

### 3.1 Global Refresh with Live ETA

A single "Refresh All" button at top of sidebar. Behavior:

- **Before press:** Shows estimate from last run duration: "Refresh (~12s)"
- **During refresh:** Backend runs as background job, reports progress via SSE
  - `POST /api/v1/cache/refresh` → returns `{job_id}`
  - `GET /api/v1/cache/refresh/{job_id}/stream` → SSE events
  - Event format: `{step, total, label, elapsed_ms}`
  - Frontend shows: progress bar + "~8s remaining" + current step label
- **After refresh:** "Last refreshed: 03 Mar 2026, 08:12" below button
- **Per-mode:** Each tab also stores `last_refresh_duration_ms` for individual estimates
- Global refresh chains all modes sequentially with cumulative progress

### 3.2 Per-Tab Freshness + Profile Change Indicator

Each tab header shows: "Updated 14 min ago"

If taste profile changed since recommendations were last generated for that mode, show yellow badge: "Profile changed — refresh recommended"

Backend tracks `profile_last_modified` per user vs `recommendations_last_generated` per user per mode.

### 3.3 Trending — Expanded to 15 Sources

Trending is no longer a single TMDB feed. It becomes a multi-source discovery hub with configurable subtabs displayed below the tab title.

**Sources that work without LLM (Tier 1):**
1. TMDB Today / This Week — global trending via Seerr proxy
2. Popular by Country — CH, DE, US, KR, JP, FR, UK, IN + configurable (TMDB `region` param)
3. Popular on Streaming — Netflix, Disney+, Prime, Apple TV+ etc (TMDB `watch_providers`)
4. New Releases — 30/90 day window, sorted by popularity
5. World Cinema Map — interactive globe, click country → charts, heat map of taste match

**Sources needing API keys or scraping (Tier 2):**
6. Trakt Trending — public API (free tier, 1000 calls/day)
7. Rotten Tomatoes — via OMDB for scores; trending page scraping
8. Letterboxd Popular — no API, RSS or scraping
9. IMDB Charts — scraping or OMDB top-rated
10. Talk of the Web — Reddit film subs, Film Twitter/X, Google Trends

**Sources requiring optional LLM (Tier 3 — Cultural Pulse):**
11. Weather-contextual — rainy weekend → cozy films, snow → winter cinema (weather API + mood mapping)
12. News-driven — RSS from Reuters/BBC/AP → LLM maps events to genres/themes
13. Sports/Festival calendar — Cannes, Venice, Berlin, TIFF, Sundance, Locarno + sports events
14. Celebrity tribute — auto-detect deaths from news → filmography collection
15. Seasonal/Holiday — Christmas, Halloween, summer blockbusters, Valentine's etc.

Each source is a subtab. Admin enables/disables sources in System Settings. Users see only enabled sources.

### 3.4 Taste Profile — Editable with Subtabs

Taste Profile returns to being an interactive editor, not just a display. Subtabs:

- **Overview** — genre affinity chart, top keywords, stats (total watched, avg completion, rewatches). Shows "Last edited: [date]"
- **Genre Tuning** — boost/suppress sliders per genre, "block" toggle (never recommend Romance). Domain toggles: Movies / TV / Anime
- **Keyword Preferences** — add/remove keywords from tag pool (Seerr keyword DB)
- **Personnel** — favorite/blocked directors, actors
- **History** — changelog of profile edits with timestamps

### 3.5 System Status → System Settings

Rename and expand into admin configuration panel:

- Connected services with status indicators (green/red/yellow)
- API endpoints + keys (masked) with "Test Connection" buttons
- Library counts + last sync times
- Cache statistics + manual invalidation
- LLM Integration settings (see §5)
- User management (import from Plex, set permissions)
- Trending source enable/disable toggles

### 3.6 Admin User Switcher

After login as admin, sidebar shows username + dropdown "View as: [other user]". Pulls from Plex shared users list. Admin can preview any user's recommendations, taste profile, and activity. Non-admin users don't see this control.

---

## 4. RECOMMENDATION MODES (Complete List from All Sessions)

### 4.1-4.5 — Core (Implemented)
Watch Tonight, Worth Grabbing, Rediscover, Mood Match, Trending

### 4.6 Auto-Grab (Predictive Curation)
Background job: when a "Worth Grabbing" candidate scores >0.85 for 3+ users, auto-add to Radarr/Sonarr. Per-user opt-in, daily limit, notification on availability.

### 4.7 Complete The Collection
Detects partially-watched filmographies, franchises, collections. "You've watched 7/11 Villeneuve films."

### 4.8 Group Night
Intersection of 2+ users' taste profiles. Finds titles everyone would enjoy.

### 4.9 Availability Alerts
Track unreleased/upcoming titles matching taste → notify when available.

### 4.10 Plex Wrapped (Monthly/Annual)
Auto-generated viewing stats: genre shifts, peak hours, most-watched-per-GB, user overlap matrix.

### 4.11 Vibe Playlists
Auto-generated mood collections: "Slow-Burn Sundays", "Late Night Comfort", "Date Night".

### 4.12 Why Not? (Negative Transparency)
User sees popular movie not in recs → "Why wasn't this recommended?" → structured breakdown.

### 4.13 List Import Engine
Paste any URL → LLM extracts titles → TMDB lookup → library cross-reference.

### 4.14 World Cinema Map
Interactive globe with per-country trending. Heat map of taste match per country.

### 4.15 Cultural Pulse
News/events → LLM thematic connections → recommendations. Sensitivity filter included.

### 4.16 Social Layer
Friend activity, server-wide trending, taste overlap scores, watched by other users (anonymized or friend-selected).

### 4.17 Quality Badges
HandBrake transcoding quality info displayed on recommendation cards.

---

## 5. LLM INTEGRATION (Optional — Locked Design)

### 5.1 Philosophy
Completely optional. App works fully without LLM (template-based explanations, keyword-based Mood Match). When configured, unlocks richer explanations, smarter mood parsing, Cultural Pulse, List Import, and news-driven trending.

### 5.2 Endpoint Configuration (in System Settings → LLM Integration)

```
Enable/Disable toggle
├── LLM Endpoint URL:  [http://IP:PORT/v1]  (OpenAI-compatible)
│   Supports: Ollama, LiteLLM, OpenAI API, any compatible endpoint
├── Model Name:        [gemma3:4b / gpt-4o / etc]
├── API Key:           [optional, for remote APIs]
├── Vector DB:         [Embedded SQLite ▾] / [External ChromaDB]
│   └── ChromaDB URL:  [http://192.168.0.111:20002]
│   └── Collection:    [recommendarr_embeddings]
├── Test Connection    — verifies both LLM and vector DB
└── Quality Compare    — subtab (see §5.4)
```

### 5.3 Data Storage — Three-Tier Architecture

| Tier | When | How |
|------|------|-----|
| **Embedded SQLite** | Default (GitHub users) | Ships inside Docker container. Stores taste vectors, Cultural Pulse events, cached LLM responses. Zero config. |
| **External ChromaDB** | Power users | Point to existing ChromaDB instance. Recommendarr creates its own collection (`recommendarr_embeddings`). Enables semantic search for Mood Match, Cultural Pulse. |
| **No DB** | LLM disabled | Template engine only, all data ephemeral cache. Still fully functional for core recommendations. |

Ray's setup: ChromaDB at `192.168.0.111:20002`, LiteLLM at `192.168.0.111:20004`. Recommendarr connects to both, creates own collection, reuses existing infra.

GitHub users: `docker-compose.yml` includes optional `chromadb` and `ollama` services (commented out by default). Uncomment to spin up local LLM stack.

### 5.4 Quality Comparison Benchmark

Subtab in Settings → LLM Integration. On-demand benchmark that runs 5-10 sample recommendations through both paths:

**Side-by-side comparison:**
- Template explanation vs LLM explanation
- Keyword Mood Match vs LLM Mood Match
- Response time comparison

**Automated scoring:**
- Explanation richness (word count, signal diversity)
- Mood Match accuracy (5 test phrases, compare parsed genres)
- Latency delta

**Manual scoring:**
- Show both versions side-by-side, user picks preferred one

Results displayed as scorecard. Also serves as "see the difference" demo for GitHub README.

### 5.5 What LLM Enables (Feature Matrix)

| Feature | Without LLM | With LLM |
|---------|-------------|----------|
| Watch Tonight | ✅ Full | ✅ + richer explanations |
| Worth Grabbing | ✅ Full | ✅ + richer explanations |
| Mood Match | ✅ Keyword parser | ✅ + natural language understanding |
| Trending (TMDB/country) | ✅ Full | ✅ Same |
| Cultural Pulse | ❌ Disabled | ✅ News → thematic recs |
| List Import | ❌ Disabled | ✅ URL → title extraction |
| Weather-contextual | ❌ Disabled | ✅ Weather → mood → recs |
| News-driven trending | ❌ Disabled | ✅ Headlines → genre mapping |
| Quality Benchmark | ❌ N/A | ✅ Compare mode |

---

## 6. FILE STRUCTURE

```
/mnt/user/system/claude/recommendarr/
├── RECOMMENDARR-PROJECT.md          ← This file
├── archive/                         ← Old versions
├── handoffs/                        ← Session continuity docs
└── src/
    ├── .env                         ← API keys + JWT_SECRET + PLEX_MACHINE_ID
    ├── docker-compose.yml        ← Both services defined
    ├── backend/
    │   ├── Dockerfile
    │   ├── requirements.txt         ← Includes PyJWT
    │   └── app/
    │       ├── main.py           ← FastAPI app + auth router
    │       ├── config.py            ← Includes jwt_secret, jwt_expiry_hours, plex_machine_id
    │       ├── auth/
    │       │   ├── __init__.py
    │       │   ├── plex_oauth.py    ← get_plex_user(), check_server_access() (Overseerr-aligned)
    │       │   └── jwt_handler.py   ← create_token(), decode_token(), get_current_user()
    │       ├── api/
    │       │   ├── auth.py          ← POST /auth/plex, GET /auth/me
    │       │   ├── health.py
    │       │   ├── users.py      ← Profile overrides (JWT-protected)
    │       │   ├── recommendations.py  ← Watchlist endpoints protected by JWT
    │       │   ├── refresh.py       ← SSE refresh + freshness
    │       │   └── feedback.py      ← Thumbs up/down/dismiss CRUD
    │       ├── clients/
    │       │   ├── base.py
    │       │   ├── plex.py          ← add/remove_from_watchlist with token_override
    │       │   ├── tautulli.py
    │       │   ├── seerr.py
    │       │   └── servarr.py
    │       └── services/
    │           ├── factory.py
    │           ├── cache.py
    │           ├── recommender.py
    │           ├── taste_profiler.py
    │           ├── explanations.py
    │           ├── profile_overrides.py
    │           └── feedback.py
    └── frontend/
        ├── Dockerfile
        ├── nginx.conf
        ├── package.json
        ├── vite.config.js
        ├── index.html
        └── src/
            ├── App.jsx              ← ~2,220 lines, Plex OAuth + all views
            └── main.jsx
```

---

## 7. IMPLEMENTATION ROADMAP

### Phase 1 — ✅ COMPLETE: Core MVP + Auth
- Backend API with 5 recommendation modes
- Frontend UI (React, mobile responsive)
- Plex OAuth authentication (Overseerr-aligned)
- JWT sessions with per-user Plex tokens
- In-memory caching layer
- Watchlist operations (add/remove) with user token isolation

### Phase 2 — NEXT: UX Polish + Feature Depth
- [x] Global refresh button with live SSE ETA (S33a)
- [x] Per-tab freshness display + "profile changed" indicator (S33a/S34)
- [x] Taste Profile → editable (genre sliders, keyword prefs, blocks) (S33a)
- [x] System Status → System Settings (AdminPage with AI settings, service config) (S34+)
- [x] Admin user switcher ("View as" dropdown) (S33a)
- [x] Trending expansion: country, streaming provider, new releases subtabs (S38+)
- [x] Feedback loop: thumbs up/down/dismiss on recommendations (S34)

### Phase 3 — Discovery + Social
- [ ] Trending Tier 2: Trakt, Rotten Tomatoes, Letterboxd, IMDB charts (needs API keys)
- [x] Talk of the Web: Reddit buzz (8 subreddits, TMDB enrichment) (260307_02)
- [x] World Cinema Map: geographic layout, taste matching, 36 countries (260307_02)
- [x] Social layer: taste overlap, server trending, genre chips (260307_01)
- [x] Group Night: multi-user intersection, per-user score breakdown (260307_01)
- [x] Complete The Collection: franchise/filmography detection (S38+)
- [x] Plex Wrapped: per-user stats, charts, SVG visualization (260307_01)

### Phase 4 — LLM Enhancement (Optional)
- [ ] LLM endpoint configuration in System Settings
- [ ] Vector DB connection (embedded SQLite or external ChromaDB)
- [ ] Quality Comparison Benchmark subtab
- [ ] Enhanced Mood Match with LLM
- [ ] Cultural Pulse: RSS → LLM → thematic recommendations
- [ ] List Import Engine: URL → LLM extraction → TMDB lookup
- [ ] Weather-contextual recommendations
- [ ] News-driven trending
- [ ] Celebrity tribute auto-detection

### Phase 5 — Automation + Polish
- [ ] Auto-Grab pipeline (predictive curation)
- [ ] Availability alerts for upcoming titles
- [ ] Vibe Playlists (auto-generated mood collections)
- [ ] Why Not? (negative transparency)
- [ ] Quality Badges (HandBrake integration)
- [ ] Seasonal/Holiday themed recommendations

### Phase 6 — GitHub Release
- [ ] Dead code cleanup, unified docker-compose
- [ ] git init, .gitignore, README with screenshots
- [ ] docker-compose with optional LLM services (commented out)
- [ ] Environment variable documentation
- [ ] First public release

### Phase 7 — Platform Expansion
- [ ] NCT Bot integration (Nextcloud Talk delivery)
- [ ] Mobile optimization / PWA
- [ ] Plex UI integration (web client)
- [ ] TV apps (WebOS, Android TV, Apple TV)

---

## 8. API ENDPOINTS

### Auth
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /auth/plex | None | Receive authToken, validate, return JWT |
| GET | /auth/me | JWT | Return current user from token |

### Recommendations
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /recommend/{username} | JWT | Recommendations (mode=tonight/grab/rediscover/mood/group) |
| GET | /discover/trending | JWT | Trending with source/country/provider filters |

### Users + Profiles
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /users | JWT | All server users |
| GET | /users/{id}/profile | JWT | Taste profile |
| PUT | /users/{id}/profile | JWT | Update taste profile (genre boosts, blocks, keywords) |
| GET | /users/{id}/history | JWT | Watch history |
| GET | /users/{id}/peers | JWT | Collaborative filtering peers |

### Watchlist (Protected — per-user Plex token)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /watchlist/add/{tmdb_id} | JWT | Add to user's Plex watchlist |
| POST | /watchlist/remove/{tmdb_id} | JWT | Remove from user's Plex watchlist |

### Feedback
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /users/{id}/feedback | JWT | thumbs up/down/dismiss on recommendation |

### Cache + Refresh
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /cache/stats | Admin | Cache hit/miss statistics |
| POST | /cache/invalidate | Admin | Clear all caches |
| POST | /cache/refresh | Admin | Start refresh job, returns {job_id} |
| GET | /cache/refresh/{job_id}/stream | Admin | SSE progress events |

### System (Admin only)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /system/settings | Admin | Current configuration |
| PUT | /system/settings | Admin | Update service endpoints, LLM config |
| POST | /system/test-connection | Admin | Test specific service connection |

---

## 9. SESSION HISTORY

| Session | Date | Focus | Key Outcomes |
|---------|------|-------|-------------|
| A-B | 2026-02-27 | Project spec + architecture | Spec locked, data flow designed |
| C-E | 2026-02-27 | Backend implementation | FastAPI backend, 5 rec modes, all clients |
| F | 2026-02-27 | API routes + container | Backend container running on port 30800 |
| G | 2026-02-27 | Frontend build start | React UI component structure |
| H | 2026-02-28 | Frontend code transfer | App.jsx transfer interrupted |
| I | 2026-02-28/03-01 | Frontend deploy + bugfixes | Full deployment, 5 backend bugs fixed, mobile responsive, caching |
| J | 2026-03-02 | Handoff prep | Architecture pivot documented |
| S32 | 2026-03-02 | Plex OAuth implementation | Auth backend + frontend, JWT sessions, watchlist protection |
| S33 | 2026-03-03 | OAuth bugfix + design lock | Fixed Overseerr-aligned OAuth, locked 7 design decisions, LLM strategy, trending expansion, project doc v0.3 |
| S33a | 2026-03-03 | Phase 2 build | Admin switcher, SSE refresh, per-tab freshness, taste editor (all 4 deployed) |
| S34 | 2026-03-03 | Fixes + feedback | JWT auth on overrides, startup race fix, profile change badge, feedback loop (up/down/dismiss + scoring) |

---

## 10. POST-1.0 ROADMAP

Features below are scoped for after 1.0 stabilization. Ordered by tier (impact + feasibility), not implementation sequence. Each item includes architectural notes for future sessions.

---

### TIER 1 — Transforms How You Use Plex

#### 10.1 Smart Auto-Grab
**What:** Recommendarr silently monitors taste profiles and auto-adds titles above a confidence threshold to Radarr/Sonarr.
**UX:** Configurable per user — aggressiveness slider (conservative/moderate/aggressive), genre/language filters, budget cap (max N grabs/week). Notification on grab: "Added 3 titles overnight — 92%+ match."
**Availability Prediction:** Track historical Radarr/Sonarr completion times per indexer, quality profile, and popularity tier. Feed this into grab decisions: "This title will be available in ~2 hours (Usenet, popular)" vs "Niche release, 3-5 days (torrent)." Model: `{title_popularity_tier, indexer_type, quality_profile} → median_completion_hours` from historical import timestamps.
**Architecture:** Background scheduler task (like existing refresh), reads taste profiles, queries TMDB trending + new releases, scores against profiles, filters by threshold, calls Radarr/Sonarr API to add. Separate `auto_grab_config` and `auto_grab_log` tables already exist in the DB schema.

#### 10.2 Plex Webhook → Real-Time Recs
**What:** Plex fires webhooks on play/stop/rate events. Recommendarr catches them, incrementally updates taste profiles, pushes fresh recs via WebSocket.
**UX:** Dashboard updates in real-time as you watch. "Because you just finished X, here's what to watch next" appears without page refresh.
**Architecture:** `POST /webhooks/plex` receiver (already have `webhooks.py` route file). WebSocket endpoint for frontend push. Incremental profile update (append event, recalculate genre weights) instead of full rebuild. PlaybackSession model already exists.

#### 10.3 "What's Next" Per-Series Intelligence
**What:** After finishing an episode/season, Recommendarr pushes contextual info about what's ahead.
**UX:** "You finished Breaking Bad S3E7. At your pace, you'll finish S3 by Thursday. S4 is widely considered the peak — here's why." Combines series progress tracking (already built) with LLM commentary.
**Architecture:** Plex webhook (10.2) detects episode completion. Query TMDB for season metadata. LLM generates brief, spoiler-free commentary on upcoming seasons. Push via notification system. Requires 10.2 as a prerequisite.

#### 10.4 Democratic Library Pruning ("Kick-Vote")
**What:** Continuously score every library item on a "vitality" metric. Items below threshold enter a "Sunset Zone" where active users vote to keep or remove. Kicked items are removed from Radarr/Sonarr but all metadata preserved for one-click re-download.
**Vitality Scoring:** Composite of: last played date, total plays (all users), play velocity trend (declining/growing), recommendation frequency (how often it appears in anyone's recs), genre/niche weight (a Korean art film with 2 plays from 2 Korean fans = healthy; a Marvel film with 2 plays from 24 users = dead).
**Kick-Vote Flow:** Items below vitality threshold → appear on dedicated "Sunset Zone" page. Active users vote keep/kick. Configurable threshold (e.g., 60% of active users vote kick). Grace period (7 days). Removal via Radarr/Sonarr API. Full metadata preserved: release info, indexer source, quality profile, NZB/torrent data. One-click re-download respects original parameters.
**Re-download ETA:** Uses availability prediction model from 10.1 — "If kicked, re-download ETA: ~4 hours" vs "Rare release, may take weeks." This context is shown during voting to inform decisions.
**UX Architecture:** Dedicated "Library Health" page (separate tab in sidebar). Subtle "stale" badge on cards in Browse/Library when vitality is low. Sidebar counter for items in sunset zone. Voting interface with vitality breakdown + re-download ETA.
**Mainstream vs Niche:** Popularity-adjusted vitality. A niche title needs fewer plays to be "healthy" than a mainstream blockbuster. Calibrated from server-wide genre distribution.

---

### TIER 2 — Social Features That Matter

#### 10.5 Friend-Powered Recommendations ("Because [Friend] Loved It")
**What:** Inject friend watch data as a signal into the recommendation scoring engine. Not just "friends watched this" (already built) but "this title scores higher *because* your friend Sarah watched it 3 times and your overlap is 78%."
**UX:** Recommendation cards show friend endorsement badges: "Sarah watched 3x · 78% overlap." Works across all rec modes (Watch Tonight, Worth Grabbing, etc.).
**Architecture:** Add `friend_signal_bonus` to `rec_scoring.py`. Query friend watch history, weight by overlap percentage, add to composite score. The friend system (Phase 1+2, session 25) provides the data layer.
**Combines with:** Existing friend tab (activity feed, overlap). This adds friend data to the *scoring engine*, not just the social display.

#### 10.6 Shared Watchlists with Voting
**What:** Create shared watchlists between friends. Both add candidates, both vote. Recommendarr resolves optimal pick using both taste profiles + votes.
**UX:** "Movie Night with Fei" — both add titles, both thumbs-up/down, algorithm picks the winner. Extends Group Night concept with persistent shared lists.
**Architecture:** New `SharedWatchlist` model + `SharedWatchlistVote`. Frontend: sub-tab of Group Night or standalone page accessible from friend profile.

#### 10.7 Taste Profile Diff
**What:** Rolling taste change tracking. "This month: +15% thriller, -8% comedy, discovered Korean cinema."
**UX:** Monthly taste diff on Taste Profile page. Visual genre weight change chart. Shareable "taste shift" card.
**Architecture:** Snapshot taste profile monthly into `WrappedSnapshot` (already exists). Diff current vs. previous. Can feed into Plex Wrapped for year-end summaries.

---

### TIER 3 — Power User / Advanced

#### 10.8 Custom Scoring Formulas
**What:** Users override automatic recommendation weights. "I follow directors, not genres — set director weight to 60%."
**UX:** Advanced section on Taste Profile page. Sliders for: genre weight, director/cast weight, recency, friend signal, popularity, keyword match. Presets: "Director-focused", "Genre explorer", "Trending chaser", "Friend-driven."
**Architecture:** `UserScoringWeights` model. `rec_scoring.py` reads per-user weights, falls back to defaults. This is the *manual override* layer on top of automatic taste profiling.
**Difference from Taste Profiling:** Profiling = automatic (machine observes behavior). Custom scoring = explicit (user tells machine what matters). Both coexist — profiling fills in what the user doesn't specify.

#### 10.9 "Why This Score?" Transparency
**What:** Full scoring breakdown on every recommendation card. Tap to see: "Genre match: 85%, Director affinity: 72%, Friend signal: +12%, Freshness: -5%."
**UX:** Expand button on recommendation cards → scoring breakdown panel. Extends existing Why Not? pattern to all recs.
**Architecture:** `rec_trace.py` already exists. Extend to return per-factor scores in rec response payload. Frontend: scoring breakdown component, reusable across all rec views.

#### 10.10 Federation (Multi-Instance Recommendarr)
**What:** Multiple Recommendarr instances share anonymized taste vectors. "Popular among servers like yours" without exposing individual watch history.
**Legality:** Clean — shares mathematical vectors derived from Tautulli (local), not Plex API data. No auth tokens, no usernames, no watch history. Like sharing Spotify Wrapped stats, not playlists.
**Protocol:** Anonymized genre/keyword weight vectors + aggregate popularity scores. Trust model: opt-in federation with instance verification. No PII crosses instance boundaries.
**Architecture:** REST federation API. Instance registration + key exchange. Periodic vector sync (daily). Scoring bonus for "federated popular" titles. Complex — Phase 7+ scope.

---

### TIER 4 — Cross-Project Integration

#### 10.11 AnimeAIDub On-Demand
**What:** When a title lacks the user's preferred language and no fitting release is available, user can request AI dubbing directly from Recommendarr. AnimeAIDub pipeline on HTPC handles the work.
**UX:** DetailModal shows "Request AI Dub" button when: (a) title not available in user's language, (b) Sonarr/Radarr show no matching release available or estimated availability exceeds threshold. Button fires job, progress tracked in notifications. One click, no separate interface needed.
**Combines with:** DetailModal (button placement), notification system (progress/completion), user language preferences (already in User model).
**Architecture:** API contract between Recommendarr and AnimeAIDub: `POST /aidub/request {tmdb_id, target_language, source_file_path}` → `{job_id}`. Status polling: `GET /aidub/status/{job_id}`. AnimeAIDub exposes REST API on HTPC. Recommendarr fires and tracks.

#### 10.12 Proactive AI Dubbing
**What:** Recommendarr detects titles it wants to recommend but that lack the user's language. Pre-queues AI dub *before the user asks*. User opens recs, title is already dubbed.
**Release Lag Intelligence:** Track `{series_id, language, historical_release_lag_days}` from Sonarr import timestamps. "Demon Slayer episodes get German dubs 14 days after JP air on average. AnimeAIDub delivers in ~90 minutes." If `historical_lag > threshold` (configurable, e.g., 48 hours), AnimeAIDub auto-triggers.
**Safety:** Always check Sonarr first for incoming releases. Only trigger AIDub when: (a) no release in target language exists, (b) no release is expected within threshold based on historical lag, (c) source material (JP audio) is available locally.
**Architecture:** Background scheduler monitors recommendation queue + language gaps. Queries Sonarr for release availability. Fires AnimeAIDub jobs proactively. Requires 10.11 API contract. `ProactiveDubLog` table for tracking requests + outcomes.

---

### Implementation Priority (suggested)

| Priority | Item | Prereqs | Effort |
|----------|------|---------|--------|
| P1 | 10.2 Plex Webhooks | None | Medium |
| P2 | 10.1 Smart Auto-Grab | None (but better with 10.2) | Large |
| P3 | 10.5 Friend-Powered Recs | Friend system (done) | Small |
| P4 | 10.4 Kick-Vote | 10.1 availability model | Large |
| P5 | 10.3 What's Next | 10.2 webhooks | Medium |
| P6 | 10.9 Why This Score | rec_trace (exists) | Small |
| P7 | 10.7 Taste Profile Diff | WrappedSnapshot (exists) | Small |
| P8 | 10.8 Custom Scoring | None | Medium |
| P9 | 10.6 Shared Watchlists | Friend system (done) | Medium |
| P10 | 10.11 AIDub On-Demand | AnimeAIDub API ready | Medium |
| P11 | 10.12 Proactive Dubbing | 10.11 + scheduler | Large |
| P12 | 10.10 Federation | Everything else stable | Very Large |
