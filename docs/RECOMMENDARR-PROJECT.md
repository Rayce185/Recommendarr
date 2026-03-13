# RECOMMENDARR — Personal Recommendation Engine

**Version:** 0.1 (Project Definition)
**Created:** 2026-02-27
**Status:** SPEC LOCKED — Ready for Phase 1 Implementation
**UI Direction:** Plex/Overseerr hybrid aesthetic, dark theme, poster-centric, responsive PWA
**Owner:** Ray DiRenzo
**Infrastructure:** unRAID Server (192.168.0.111)

---

## 1. VISION

A self-hosted, AI-powered media recommendation engine that learns from actual viewing behavior across all Plex users. Unlike Trakt (which relies on manual ratings and social signals), Recommendarr uses completion rates, rewatch patterns, time-of-day habits, and embedded content similarity to generate explanations-first recommendations.

**Core differentiators over Trakt/Plex Discover/TMDB:**
- Behavior-based: completion rate > ratings (abandoned at 20 min = signal, no rating needed)
- Library-aware: knows what's on Plex AND what Radarr/Sonarr can grab
- Explainable: LLM generates "because you..." reasoning, not just "users also watched"
- Private: all data stays local, no external telemetry
- Multi-user: per-user taste profiles for all ~15 Plex users
- Actionable: recommendations link directly to Plex playback or Seerr request

---

## 2. ARCHITECTURE

```
┌──────────────────────────────────────────────────────────┐
│                    RECOMMENDARR                          │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Data Layer  │  │  Brain Layer │  │  Delivery Layer│  │
│  │             │  │              │  │                │  │
│  │ Tautulli ───┤  │ Taste Engine │  │ REST API ──────┤──┼─→ NCT Bot
│  │ Plex API ───┤  │ ChromaDB ────┤  │ WebSocket ─────┤──┼─→ Web GUI
│  │ Radarr API ─┤  │ Ollama/LLM ──┤  │ SSE ───────────┤──┼─→ Plex UI Plugin
│  │ Sonarr API ─┤  │ TMDB API ────┤  │                │  │
│  │ TMDB Cache ─┤  │              │  │                │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬───────┘  │
│         │                │                    │          │
│         └────────────────┴────────────────────┘          │
│                          │                               │
│                  ┌───────┴───────┐                        │
│                  │  PostgreSQL   │                        │
│                  │  (State DB)   │                        │
│                  └───────────────┘                        │
└──────────────────────────────────────────────────────────┘
```

### 2.1 Components

| Component | Role | Tech |
|-----------|------|------|
| **Data Ingestion** | Pull watch history, ratings, library state | Python async workers |
| **TMDB Cache** | Local metadata store (genres, cast, keywords, similar) | PostgreSQL + TMDB API |
| **Embedding Engine** | Vectorize movie/show metadata for similarity | nomic-embed-text via Ollama |
| **Taste Profiler** | Per-user weighted preference vectors per domain | ChromaDB + custom scoring |
| **Recommendation Engine** | Generate ranked suggestions with context | Python + ChromaDB queries |
| **Explanation Engine** | "Because you..." text (see §2.3) | Template engine + optional LLM |
| **API Server** | REST + WebSocket endpoints | FastAPI |
| **State DB** | Users, profiles, history cache, rec history | PostgreSQL (reuse LLM-PostgreSQL) |

### 2.2 Explanation Engine (Three-Tier)

Recommendations need human-readable explanations. The engine supports three tiers, each deployable independently:

**Tier 1 — Template Engine (default, zero external dependencies):**
- Structured fill-in-the-blanks from signal data
- Example: "Because you watched {movie1} and {movie2} to completion, and you tend to enjoy {genre} films by {director}."
- Covers ~80% of recommendation explanations cleanly
- Works offline, no GPU needed, suitable for all deployments
- Template library: ~50 templates covering all recommendation modes

**Tier 2 — Local LLM (optional, zero-config for Ollama users):**
- Polishes template output into natural conversational prose
- Powers "Mood Match" natural language query interpretation
- Drives "Cultural Pulse" thematic connection reasoning (event → movies)
- Generates "Why Not?" detailed negative explanations
- Generates Vibe Playlist names and descriptions
- **Auto-discovery:** Recommendarr queries `GET /api/tags` on Ollama at startup and
  periodically — any model pulled into Ollama appears in the settings dropdown automatically.
  No manual model name entry. Pull a model → it's available. Remove it → it disappears.
- **Settings UI:** dropdown lists all available models with size (GB) and parameter count.
  User picks one. Sensible default: prefer smallest model ≥7B, or largest available if all <7B.
- **Fallback chain:** selected model unavailable → next available model → Tier 3 → Tier 1.
- Ray's deployment: uses existing Ollama stack with auto-detected models

**Tier 3 — Remote LLM API (optional, for users without GPU):**
- Same capabilities as Tier 2, via cloud API
- Supported via LiteLLM: OpenRouter (free models), Groq (free tier), Google Gemini (free API), OpenAI, Anthropic
- User provides their own API key in config
- Fallback chain: Tier 2 → Tier 3 → Tier 1 (always degrades gracefully)

**No login or account linking required for any tier.**
Tier 1: zero dependencies, runs locally.
Tier 2: local Ollama, no external calls.
Tier 3: user puts an API key in `.env` — no OAuth, no account linking in the app.
(OpenRouter, Groq, Gemini free tiers: register once on their site, copy key, paste in config.)

**Default for public release:** Tier 1 (works out of the box).
**Recommended upgrade:** Tier 3 (best quality, no GPU needed, free API tiers available).
**Ray's deployment:** Tier 2 (local Ollama, already running).

**Configuration (docker-compose env):**
```
EXPLANATION_MODE=auto              # auto | template | llm
                                   # auto = detect Ollama → use it, else Tier 3 if key set, else templates
LLM_PROVIDER=ollama                # ollama | openrouter | groq | gemini | custom
LLM_MODEL=auto                    # auto = pick from Ollama dropdown in UI. Or hardcode: qwen2.5:7b
LLM_BASE_URL=http://ollama:11434   # provider endpoint (auto-detected if on same Docker network)
LLM_API_KEY=                       # only needed for Tier 3 (remote providers)
```

**Auto mode behavior:**
1. Check if Ollama reachable at `LLM_BASE_URL` → list models → Tier 2 (user picks in UI)
2. If Ollama unreachable but `LLM_API_KEY` set → Tier 3 (remote API)
3. If neither available → Tier 1 (templates, always works)
4. User can override in settings UI at any time — no restart needed


### 2.6 Internationalization (i18n)

Multi-language support without LLM dependency:

**GUI:** Standard `react-i18next` with JSON translation files. One-time setup.
- Default: English
- Bundled: English, German, French (Swiss audience)
- Community-contributed translations via GitHub PRs
- Language auto-detected from browser locale, overridable in settings

**Media metadata:** Already multi-language via TMDB + Plex.
- TMDB API: `language=de-DE` parameter returns German titles, overviews, genres
- Plex: serves metadata in user's configured language
- Recommendarr passes user's language preference to all TMDB/Plex API calls

**Recommendation explanations:**
- Tier 1 (templates): translated template sets per language. JSON files, community-contributable.
- Tier 2/3 (LLM): language hint injected into system prompt: "Respond in {user_language}."
  Most 7B+ models handle EN/DE/FR natively. No separate model needed.

**No LLM required for i18n.** The GUI, metadata, and template explanations are all standard
static translation. LLM is only involved if Tier 2/3 is active, and even then it's just a
prompt parameter.

### 2.7 Profile Export & Import

User data portability for server migration, backup, or sharing between instances.

**Export:** "Export My Data" button in profile settings.
Generates a JSON bundle containing:
- Taste profile (genre weights, personnel affinities, mood clusters)
- Watch history (TMDB IDs, completion rates, ratings — no file paths)
- Watchlists (all lists with items)
- Influence overrides (boosts, suppressions)
- Notification preferences
- Privacy settings
- Feedback history (thumbs up/down/dismiss)

**Import:** "Import Profile" in settings or during onboarding (Step 3).
- Upload JSON bundle → preview what will be imported → confirm
- Merge mode: combine with existing profile (for users switching servers)
- Replace mode: overwrite existing profile entirely
- Selective import: checkboxes for which sections to import

**Use cases:**
- Server migration (old Plex → new Plex, or Plex → Jellyfin)
- Backup/restore taste profile
- Share taste profile between household servers
- Bootstrap new user from existing profile ("my taste is similar to Ray's")


### 2.4 Local Model Management (Settings UI)

The settings page provides a complete model management interface:

**"Installed Models" section:**
- Lists all models currently in Ollama (auto-discovered via `/api/tags`)
- Each model shows: name, parameter count, VRAM usage, quantization level
- Radio button to select active model for Recommendarr
- "Active" badge on currently selected model

**"Recommended Models" section:**
Curated list of models tested and rated for Recommendarr's specific tasks
(short explanation generation, mood interpretation, thematic mapping).
Each recommendation shows: name, specs, suitability rating, and one-click install.

| Model | Params | VRAM | Quant | Speed | Quality | Best For | Install |
|-------|--------|------|-------|-------|---------|----------|---------|
| `qwen2.5:3b` | 3B | ~2.5 GB | Q4_K_M | ⚡⚡⚡⚡⚡ | ★★★☆☆ | Low-VRAM systems, basic explanations | [Add] |
| `qwen2.5:7b` | 7B | ~5 GB | Q4_K_M | ⚡⚡⚡⚡ | ★★★★☆ | **Best balance** — fast + good quality | [Add] |
| `gemma2:9b` | 9B | ~6 GB | Q4_K_M | ⚡⚡⚡ | ★★★★☆ | Strong short-form text, concise style | [Add] |
| `llama3.1:8b` | 8B | ~5.5 GB | Q4_K_M | ⚡⚡⚡⚡ | ★★★★☆ | All-rounder, good multilingual | [Add] |
| `mistral-nemo:12b` | 12B | ~8 GB | Q4_K_M | ⚡⚡⚡ | ★★★★☆ | Nuanced explanations, large vocab | [Add] |
| `qwen2.5:14b` | 14B | ~9 GB | Q4_K_M | ⚡⚡ | ★★★★★ | **Best quality** — rich explanations | [Add] |
| `phi-4:14b` | 14B | ~9 GB | Q4_K_M | ⚡⚡ | ★★★★★ | Strong reasoning, thematic connections | [Add] |
| `mistral-small:22b` | 22B | ~14 GB | Q4_K_M | ⚡ | ★★★★★ | Premium quality if VRAM allows | [Add] |

**Suitability notes displayed in UI:**
- ★★★★★ = Excellent for all features (Mood Match, Cultural Pulse, Why Not?, Vibe naming)
- ★★★★☆ = Great for explanations + mood match, adequate for thematic mapping
- ★★★☆☆ = Functional for basic explanations, limited for complex features (Mood Match may be weak)
- Models <3B not recommended — quality drops below template engine (Tier 1 is better)

**"Add Model" section:**
Two input modes:
1. **Recommended preselection:** Click [Add] on any recommended model → triggers `POST /api/pull` to Ollama
   - Shows download progress bar (Ollama streams progress via `/api/pull`)
   - Auto-selects model as active once download completes
   - Badge: "Downloading 4.2GB..." → "Ready ✓"
2. **Manual add:** Text input field for any Ollama model identifier
   - User pastes model name (e.g., `dolphin-mixtral:8x7b`) or full registry path
   - "Pull" button triggers download
   - No validation against recommended list — power users can use anything

**Pull API integration:**
```
POST http://ollama:11434/api/pull
Body: { "name": "qwen2.5:7b", "stream": true }
```
Recommendarr proxies this call and streams progress to the UI via WebSocket.
Shows: model name, total size, downloaded bytes, percentage, ETA.

**Model removal:**
- "Remove" button next to installed models (not currently active)
- Triggers `DELETE /api/delete` on Ollama
- Confirmation dialog: "Remove qwen2.5:7b (5.0 GB)? This frees VRAM and disk space."
- Cannot remove the currently active model — must switch first

**VRAM budget indicator:**
- Shows total GPU VRAM, currently used (by Ollama + other processes), and available
- Source: `nvidia-smi` or Ollama `/api/ps` endpoint
- Warning badge if selected model exceeds available VRAM
- Example: "P100: 16 GB total | 9.2 GB used | 6.8 GB free — qwen2.5:7b needs ~5 GB ✓"
- Example: "GT 730: 2 GB total | 1.8 GB used | 0.2 GB free — qwen2.5:7b needs ~5 GB ✗ (won't fit)"

**Recommendation logic (auto-select):**
When user first enables Tier 2 and has models installed:
1. Filter installed models to those in the recommended list
2. Pick the highest-quality model that fits in available VRAM
3. If no recommended model installed, suggest the best fit from the recommended table
4. If no models installed at all, prompt: "Pull a model to get started" with top 3 suggestions
   based on detected VRAM budget

### 2.5 Media Server Abstraction Layer

Recommendarr is designed media-server-agnostic. All media server interactions go through an
abstraction interface, enabling community contributions for additional platforms.

**Interface: `IMediaServer`**
```
get_libraries()              → List of libraries with metadata
get_library_items(lib_id)    → All items in a library
get_watch_history(user_id)   → Watch events with completion, duration, timestamps
get_user_ratings(user_id)    → User ratings/stars
get_users()                  → Server users with sharing permissions
get_clients()                → Active playback clients/devices
play_on_device(device, key)  → Start playback on a specific client
get_media_info(key)          → Codec, resolution, HDR, audio details
create_playlist(user, items) → Push recommendations as native playlist
create_collection(lib, items)→ Push recommendations as library collection
```

**Interface: `IWatchHistoryProvider`**
```
get_history(user_id, since)  → Watch events (start, stop, duration, completion %)
subscribe_events(callback)   → Real-time watch event webhook/stream
get_most_watched(user_id, n) → Top N most-watched items
```

**Implementations (Phase 1 = Plex, rest = community):**

| Platform | Media Server | Watch History | Status |
|----------|-------------|---------------|--------|
| **Plex** | `PlexMediaServer` | `TautulliProvider` (webhook, preferred) | Phase 1 |
| **Plex** | `PlexMediaServer` | `PlexDirectProvider` (API poll, no Tautulli) | Phase 1 |
| **Jellyfin** | `JellyfinMediaServer` | `JellyfinProvider` (built-in activity API) | Community |
| **Emby** | `EmbyMediaServer` | `EmbyProvider` (native activity log) | Community |
| **Kodi** | `KodiMediaServer` | `KodiProvider` (JSON-RPC) | Community |

**Tautulli webhook integration (Plex, real-time):**
- Tautulli → `POST /api/v1/webhook/tautulli` on play/stop/pause/resume events
- Instant profile updates — user finishes a movie → taste profile refreshed within seconds
- Webhook payload includes: user, media, duration, completion %, player info
- Fallback: if webhooks not configured, poll Tautulli API every 5 minutes

**Native playlist/collection push (Plex):**
- Plex playlists: per-user, cross-library → "Recommended For You" playlist
- Plex collections: per-library → "Recommendarr Picks" collection in Movies, TV, Anime
- Both appear as native shelves in Plex home screen on ALL clients (no custom UI needed)
- Updated on schedule (daily) or on-demand via API
- User toggle: "Push recommendations to Plex" on/off in settings

### 2.3 Data Flow

```
[Tautulli] ──watch event──→ [Ingestion Worker]
                                    │
                         ┌──────────┴──────────┐
                         ▼                      ▼
              [Update User Profile]    [Fetch TMDB Metadata]
                         │                      │
                         ▼                      ▼
              [ChromaDB: user taste    [ChromaDB: content
               vector updated]          embedding stored]
                         │                      │
                         └──────────┬───────────┘
                                    ▼
                         [Recommendation Engine]
                                    │
                         ┌──────────┴──────────┐
                         ▼                      ▼
              [In-Library Recs]        [Grab-Worthy Recs]
              (exists on Plex,         (not on Plex, high
               user hasn't seen)        similarity score)
                         │                      │
                         ▼                      ▼
                   [LLM Explains]        [LLM Explains]
                         │                      │
                         └──────────┬───────────┘
                                    ▼
                              [API Response]
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              [NCT Bot]       [Web GUI]      [Plex Plugin]
```

---

## 3. TASTE PROFILING

### 3.1 Signal Weights

| Signal | Weight | Source | Rationale |
|--------|--------|--------|-----------|
| Completion rate | 0.35 | Tautulli | Strongest behavioral signal — watching to the end means enjoyment |
| Rewatch count | 0.20 | Tautulli | Rewatching = strong positive signal |
| User rating (if set) | 0.15 | Plex API | Explicit signal, but rarely set |
| Genre frequency | 0.10 | Derived | Consistent genre preference over time |
| Time-to-start | 0.05 | Tautulli | How quickly after adding to watchlist did they watch? |
| Session time pattern | 0.05 | Tautulli | Late-night vs daytime viewing → genre correlation |
| Director/cast affinity | 0.05 | Derived | Tracks personnel preferences |
| Abandon velocity | 0.05 | Tautulli | How fast they quit = how strong the dislike |

### 3.2 Negative Signals

- Abandoned before 20% → strong negative
- Skipped in "Up Next" queue 3+ times → mild negative
- Genre never watched despite availability → implicit disinterest

### 3.3 Taste Vector Construction

**Sub-Profile Architecture:** Each user has separate taste profiles per media domain:

| Domain | Plex Libraries | Genre Taxonomy |
|--------|---------------|----------------|
| Movies | Movies, Kinderfilme | Standard TMDB genres (Action, Drama, Thriller, etc.) |
| TV | TV Series, Kinderserien | Standard TMDB TV genres |
| Anime | Anime, Anime-Ecchi, Anime-Hentai | Anime-specific (Shonen, Seinen, Isekai, Mecha, Slice-of-Life, etc.) |

Each sub-profile contains:
1. **Genre centroid** — weighted average of genre embeddings from watched content in that domain
2. **Personnel graph** — directors, actors, writers, studios with affinity scores
3. **Mood clusters** — k-means clusters from content embeddings of highly-rated watches
4. **Anti-profile** — embeddings of abandoned content (used as negative filter)

Query per domain: `similarity(content_embedding, user_centroid) - 0.3 * similarity(content_embedding, anti_profile)`

**Cross-Pollination (user-configurable):**
- Default: domains are isolated (anime taste doesn't influence movie recs)
- "Blend all": unified profile across all domains
- "Custom": toggle per pair (e.g., Movies↔TV blended, Anime isolated)
- Cross-pollination uses thematic/mood bridges, NOT raw genre mapping
  (binge-watching Attack on Titan ≠ recommend war movies, but DOES surface intense psychological thrillers if mood clusters align)

### 3.4 Watch History Depth
- User-selectable: 3 months / 6 months / 12 months / All time
- Default: 12 months
- Configurable per user in profile settings
- Shorter window = more responsive to taste changes, longer = more stable profile
- "All time" includes decay weighting: recent watches count more

### 3.5 Library Permission Enforcement

**Critical rule: Recommendarr MUST respect Plex per-user library sharing at every layer.**

Not all users have access to all Plex libraries. Example: User A has Movies + TV but NOT Anime-Hentai.
Recommendarr must never recommend, profile, or expose content from libraries a user cannot access.

**Plex API for permissions:**
```
GET https://plex.tv/api/servers/{machineId}/shared_servers
Header: X-Plex-Token: {admin_token}
```
Returns per-user, per-library sharing with `shared="1"` (accessible) or `shared="0"` (blocked).
Each entry includes: `sharing_id`, `key` (local section ID), `title`, `type`, `shared`.

**Verified library mapping (Ray's server):**

| Sharing ID | Local Key | Library | Type |
|------------|-----------|---------|------|
| 131296631 | 14 | Movies | movie |
| 141249024 | 20 | Kinderfilme | movie |
| 123602616 | 2 | TV Series | show |
| 123602612 | 10 | Anime | show |
| 131299488 | 15 | Anime-Ecchi | show |
| 139754268 | 17 | Anime-Hentai | show |
| 123602617 | 7 | Kinderserien | show |

**Enforcement points (every layer):**

| Layer | Enforcement |
|-------|-------------|
| **Taste Profiler** | Only build profiles from libraries with `shared=1` for that user |
| **Recommendation Engine** | Only return content from accessible libraries |
| **Filter Sidebar** | Only show libraries the user can access |
| **Watchlists** | Allow adding items from any source (TMDB), but flag "not in your library" |
| **Plex Connect playback** | Only allow play commands for accessible content |
| **Social/Collaborative** | Collaborative filtering excludes signals from libraries user can't see |
| **Collections** | Only detect completion for accessible libraries |
| **Vibe Playlists** | Only include content from accessible libraries |
| **Plex Wrapped** | Only count stats from accessible libraries |
| **World Cinema Map** | "In your library" badge only for accessible content |

**Sync frequency:** Library permissions checked on user login + every 6 hours via background job.
**Cache:** Per-user library access stored in PostgreSQL `user_library_access` table.
**Admin override:** Server owner (Ray) has access to ALL libraries regardless of sharing config.

---

## 4. RECOMMENDATION MODES

### 4.1 "Watch Tonight" (In-Library)
- Source: Plex library items the user hasn't seen
- Filter: Remove watched, in-progress, and anti-profile matches
- Rank: Similarity to taste profile, weighted by recency of similar watches
- Output: Top 5-10 with explanations

### 4.2 "Worth Grabbing" (Not In Library)
- Source: TMDB trending, new releases, similar-to-watched
- Filter: Remove already in Radarr/Sonarr, below similarity threshold
- Rank: Taste similarity × availability likelihood × freshness
- Output: Top 5-10 with one-click Seerr request link

### 4.3 "Rediscover" (Rewatch Suggestions)
- Source: Plex library items watched >6 months ago with high completion
- Rank: Original completion rate × time-since-watch × genre-mood match
- Output: "You loved this 8 months ago, might be time for a rewatch"

### 4.4 "Group Night" (Multi-User)
- Input: 2+ user IDs
- Method: Intersection of taste profiles — find content where ALL users score high
- Filter: Content none of the selected users have seen
- Output: Compromise picks with per-user explanations

### 4.5 "Mood Match" (Natural Language)
- Input: "something like Parasite but more funny" / "cozy rainy day movie"
- Method: LLM interprets intent → generates search embedding → ChromaDB query
- Filter: Standard taste profile + anti-profile
- Output: Matches ranked by semantic + taste similarity

### 4.6 "Auto-Grab" (Predictive Curation)
- Trigger: Background job runs daily after TMDB trending/new release sync
- Logic: When a "Worth Grabbing" candidate scores >0.85 confidence for 3+ server users,
  automatically add to Radarr/Sonarr without human request
- Per-user opt-in: users can enable/disable auto-grab and set personal threshold
- Per-user scope: "auto-grab movies only" / "movies + TV" / "everything including anime"
- Notification: push alert when auto-grabbed item becomes available
- Safeguard: daily grab limit (default 3/day), budget cap on storage consumption
- Result: library grows proactively based on collective taste — the server shops for its users

### 4.7 "Complete The Collection"
- Detects partially-watched filmographies, franchises, and collections
- Sources: director filmography, franchise membership, studio collections, cast careers
- Example: "You've watched 7/11 Villeneuve films. Here are the 4 you're missing."
- Example: "You've seen 5/8 A24 horror films from the 2020s."
- Includes franchise order awareness (don't recommend sequel before original)
- Completion percentage shown as progress bar per collection
- "Complete it" button → adds all missing entries to Radarr/watchlist in one click

### 4.8 "Availability Alert"
- User sees a "Worth Grabbing" rec → hits "Want This" (or auto-grabbed)
- System monitors Radarr/Sonarr for availability changes
- When item becomes available (downloaded, transcoded, ready to play):
  push notification → "Remember Anatomy of a Fall? It's ready to watch."
- Links back to the original recommendation context ("recommended because...")
- Also triggers for items on Plex watchlist that weren't available at time of adding

### 4.9 "Quality Badges" (Transcode Awareness)
- Tag each recommendation with playback quality info per target device
- Source: Plex media info (codecs, resolution, HDR metadata, audio tracks)
- Source: AI Handbrake workflow status (queued, processing, complete)
- Badges: "4K HDR Direct Play ✓", "Needs transcode for WebOS", "Atmos audio available"
- Device-aware: same movie shows different badges depending on selected playback target
- Integration with AI Handbrake pipeline — flag items being processed, ETA for completion

### 4.10 "Plex Wrapped" (Server Taste Analytics)
- Per-user and server-wide viewing analytics, generated monthly and annually
- Per-user stats:
  - Total hours watched, movies vs TV split
  - Genre distribution over time (how taste evolved month by month)
  - Top directors, actors, countries of origin
  - Longest binge streak, most-rewatched title
  - Completion rate trends (are you finishing more or fewer movies?)
  - "Taste shift" detection: "Your genre mix shifted from 60% Action to 45% Korean Drama in Q3"
  - Time-of-day and day-of-week viewing heatmap
- Server-wide stats:
  - Most popular titles across all users
  - Most divisive titles (loved by some, abandoned by others)
  - User taste overlap matrix ("You and Marco: 73% overlap")
  - Peak viewing hours, busiest days
  - Storage efficiency: most-watched-per-GB, least-watched titles
- Presentation: shareable card format (like Spotify Wrapped), exportable as image/PDF
- Schedule: auto-generated first week of each month + annual wrap in January

### 4.11 "Vibe Playlists" (Auto-Generated Mood Collections)
- Continuously updated, algorithmically generated collections per user
- Based on detected viewing pattern clusters, not static genre tags
- Examples:
  - "Slow-Burn Sundays" — arthouse dramas the user watches on weekends
  - "Late Night Comfort" — rewatches and familiar genres consumed after midnight
  - "Fei & Ray Date Night" — intersection of both profiles, filtered for shared mood
  - "Weekday Wind-Down" — shorter, lighter content watched on work nights
  - "Deep Dive Mode" — multi-part series/documentaries consumed in rapid succession
- Playlists update automatically as viewing patterns evolve
- Each playlist: name (auto-generated, user-renamable), cover art mosaic, item count
- Playable as queue via Plex Connect (shuffle or sequential)
- Like Spotify's Daily Mix, but for Plex

### 4.12 "Why Not?" (Negative Transparency)
- Inverse of recommendation explanations
- User sees a popular/trending movie not in their recs → clicks "Why wasn't this recommended?"
- Response: structured breakdown of negative signals
  - "Low genre match (0.31) — you rarely watch supernatural horror"
  - "Anti-profile hit: you abandoned The Lighthouse at 22%"
  - "Director has 0.15 affinity score based on 2 watched films, both below 50% completion"
- Override button: "Recommend it anyway" → bypasses signals for this one item
- "I actually liked this" feedback → system corrects profile for similar future content
- Builds user trust in the engine and helps them understand their own taste

### 4.13 "List Import Engine" (URL → Library)
- User pastes ANY URL containing movie/show references
- Pipeline: fetch page → LLM extracts titles/years → TMDB lookup → cross-reference library
- Supported sources:
  - Letterboxd lists (structured)
  - IMDB lists (structured)
  - Reddit posts (unstructured — LLM extraction)
  - Blog posts / articles (unstructured — LLM extraction)
  - YouTube video descriptions (unstructured)
  - Social media posts (unstructured)
- **Enhanced discovery modes (dropdown):**
  - "Popular on [Platform]" — curated lists from Letterboxd, IMDB, Rotten Tomatoes, Metacritic
  - "Popular in [Country]" — trending content by region (TMDB regional trending API)
    - Presets: Switzerland, Germany, USA, South Korea, Japan, France, UK, India
  - "Talk of the Web" — automated scraping of:
    - Film Twitter/X trending discussions
    - Reddit r/movies, r/television, r/anime hot posts
    - Major review aggregators (weekly new releases)
    - Festival circuit announcements (Cannes, Venice, Berlin, TIFF, Sundance)
    - "Oscar buzz" season tracking
  - Scraped lists refreshed daily, cached locally, de-duped against library
- Output: interactive checklist — user picks which to add → bulk Radarr/Sonarr import or watchlist
- History: tracks which lists were imported, when, what was added

### 4.14 "Contextual Awareness" (Zeitgeist Engine)

Ambient signals from the real world that subtly re-rank recommendations. Three layers:

**Layer 1: Temporal (always active)**
- Time of day:
  - Friday 9 PM → weight crowd-pleasers, new releases, group-friendly
  - Tuesday 2 PM → weight shorter, lighter content
  - Late night (11 PM+) → weight towards user's "Late Night Comfort" cluster
- Day of week:
  - Weekend → longer films, multi-episode binges
  - Weekday → tighter runtime, episodic content
- Season:
  - December → holiday-adjacent content surfaced (not forced)
  - Summer → lighter, adventure/comedy weighted
  - Awards season (Jan-Mar) → Oscar nominees and festival darlings boosted

**Layer 2: Environmental (local)**
- Weather (Schaffhausen weather API):
  - Rainy/cold → cozy comfort picks
  - Beautiful day → shorter recs ("watch this quick before going outside")
  - Heatwave → lighter escapism
  - Snow → winter/Nordic content nudge

**Layer 3: World Events (Zeitgeist Engine)**

The system monitors real-world events and maps them to relevant media via LLM interpretation.

- **Data sources:**
  - RSS feeds: Reuters, AP, BBC, NZZ (Swiss), Tagesschau (German)
  - Wikipedia Current Events portal (structured, daily updated)
  - Google Trends API (trending topics by region)
  - Sports calendars API (ESPN, Olympic.org — scheduled events are predictable)
  - Festival/awards calendars (Cannes, Oscars, TIFF — predictable dates)

- **Event → Content mapping pipeline:**
  ```
  [RSS/API] → [Event Classifier] → [LLM: "What media relates to this event?"]
                                         ↓
                               [Genre/keyword/theme queries]
                                         ↓
                               [ChromaDB semantic search]
                                         ↓
                               [Contextual boost to matching recs]
  ```

- **Event categories and example mappings:**

  | Event Type | Example | Mapped Media Themes |
  |------------|---------|---------------------|
  | **Sports: Olympics** | Summer/Winter Olympics | Sports docs, underdog stories, competition films, country-specific athletes |
  | **Sports: World Cup** | FIFA World Cup | Football/soccer films, national pride stories, hooliganism docs |
  | **Sports: X-Games** | X-Games, extreme sports events | Action sports, Jackass, stunt docs, adrenaline films |
  | **Geopolitics: Conflict** | War/military conflict in news | War dramas, journalism films, refugee stories, anti-war cinema |
  | **Geopolitics: Summit** | WEF Davos, G7, UN Assembly | Political thrillers, economics docs, conspiracy films (The International!) |
  | **Geopolitics: Election** | Major national elections | Political dramas, campaign docs, satire (Wag the Dog, The Candidate) |
  | **Science/Tech** | Space launch, AI breakthrough, pandemic | Sci-fi, tech thrillers, relevant docs |
  | **Natural Disaster** | Earthquake, hurricane, wildfire | Disaster films, survival stories, climate docs |
  | **Cultural** | Major celebrity death, anniversary | Filmography of deceased, era-specific content |
  | **Swiss Local** | Swiss National Day, Fasnacht, Sechseläuten | Swiss cinema, Alpine films, local culture docs |
  | **Awards** | Oscar noms announced, Cannes Palme d'Or | Nominated/winning films surfaced prominently |

- **LLM interpretation (the key differentiator):**
  - Raw events are fed to LLM with prompt: "Given this current event, what movie/TV genres,
    themes, keywords, directors, or specific titles would be culturally relevant to recommend?"
  - LLM returns structured JSON: genres, keywords, specific TMDB IDs, theme descriptors
  - These become embedding queries against ChromaDB
  - Results get a contextual boost weight (configurable, default 0.05-0.15)

- **Zeitgeist Feed (UI component):**
  - "In the world right now..." section on recommendation feed
  - Shows current events with their mapped recommendations
  - Example: "🏅 Olympics are underway → Here are sports stories you'd love"
  - Example: "🌧️ Rainy weekend in Schaffhausen → Perfect for a slow-burn marathon"
  - Example: "📰 WEF Davos this week → Political thrillers matching your taste"
  - User can dismiss individual event-recs or disable zeitgeist entirely

- **Caching & frequency:**
  - Event scraping: every 6 hours (news changes slowly enough)
  - LLM mapping: cached per event, regenerated only when event context changes
  - Sports calendars: synced weekly (dates are predictable months ahead)
  - Total API cost: minimal — RSS is free, Google Trends has generous free tier

**Weight rules for all contextual signals:**
- Temporal signals: weight 0.03-0.05 (very subtle nudge)
- Weather signals: weight 0.03-0.05
- Zeitgeist signals: weight 0.05-0.15 (slightly stronger, event-dependent)
  - Major global events (Olympics, World Cup): 0.15
  - Regional/political events: 0.10
  - Cultural/seasonal: 0.05
- All contextual weights combined NEVER exceed 0.20 of total recommendation score
- Contextual signals nudge, NEVER override taste profile
- User can disable each layer independently (temporal / weather / zeitgeist)
- Admin can set server-wide event overrides (e.g., force-boost Swiss National Day content)

### 4.15 "Social Layer" (Server Community)
- **"Watched by others on this server"** badge on recommendations
  - "3 other users watched this" / "Most-watched on server this week"
  - Anonymous by default — shows count, not names
- **Friend selection:** users can designate "taste friends" from server members
  - Opt-in mutual: both users must agree
  - Friends see each other's recent watches (anonymizable: "A friend watched Oppenheimer")
  - "Friend-boosted" recs: items that taste-friends loved, weighted into rec engine
- **Collaborative filtering (local):**
  - "Users on this server who loved X also loved Y"
  - Pure co-occurrence analysis across server population
  - Catches recommendations content-similarity misses (two movies with nothing in common
    in metadata but the same people love both — Netflix's bread and butter)
  - All computation local, no data leaves server
  - Minimum anonymity threshold: collaborative signals only surface when 3+ users
    contribute to the pattern (prevents de-anonymization of small groups)
- **Privacy controls:**
  - Users can opt out of social features entirely
  - Users can opt out of collaborative filtering contribution
  - Admin (Ray) controls: enable/disable social features server-wide
  - Swiss DSG compliant: no personal data shared without consent, opt-in only

### 4.16 "World Cinema Map" (Global Box Office & Trending)
- Interactive world map showing current cinema charts per country/region
- Data source: TMDB regional trending API (available for 50+ countries)
- Map visualization: clickable countries → shows top 10 trending/box office
- Each title on the map: "In your library ✓" / "Grab it" / "Add to watchlist"
- Regional discovery: "What's hot in South Korea right now?" without knowing what to search for
- Historical view: toggle past weeks/months to see trends over time
- Server overlay: highlight countries your Plex users are from (CH, DE, USA) — prioritize those regions
- Heat map mode: color countries by how much their trending content overlaps with user's taste profile
  (bright = "South Korea's top 10 are 80% match for you" → explore that cinema)
- Integration with §4.13 List Import: tap a country's chart → bulk-import to watchlist or Radarr

### 4.17 "Cultural Pulse" (Event-Reactive Recommendations)
- Monitors real-world events and surfaces thematically relevant content
- **Event sources:**
  - News headlines: RSS feeds from major outlets (Reuters, BBC, AP) — parsed daily
  - Sports calendar: Olympics, World Cup, X Games, Super Bowl, Tour de France
  - Cultural calendar: Oscar season, Cannes, Sundance, TIFF, Locarno
  - Political/economic events: WEF, elections, summits, G7/G20
  - Trending topics: Reddit front page, Twitter/X trending, Google Trends
- **LLM interpretation layer:**
  - Feed event headlines to local LLM via LiteLLM
  - LLM draws *thematic* connections, not just keyword matches:
    - Olympics → underdog stories, sports docs, relevant national cinema
    - X Games → Jackass, extreme sports, adrenaline cinema, Point Break
    - WEF Davos → political thrillers, financial conspiracy (The International, Margin Call, Inside Job)
    - War/conflict news → war films, affected-region cinema, relevant documentaries
    - Celebrity death → auto-generate tribute filmography collection
    - Tech news (AI milestone) → Ex Machina, Her, 2001, sci-fi recs
    - Climate summit → environmental docs, eco-thrillers, nature cinema
  - LLM generates the "because..." explanation tying event to recommendation
  - Thematic depth: "WEF" → "global finance power dynamics" → not just films with "bank" in the title
- **Presentation:**
  - "Cultural Pulse" card on home screen: "Happening now → Watch this"
  - Rotating 3-5 event-linked recommendations, refreshed daily
  - Each rec shows: event context, thematic connection, confidence
  - Expandable: "See all recommendations inspired by [event]"
  - Dismissable per event: "Not interested in Olympics-related recs"
- **Content matching pipeline:**
  1. Event detected (RSS/calendar/trending)
  2. LLM generates thematic keywords + mood descriptors
  3. Keywords embedded via nomic-embed-text → ChromaDB similarity search
  4. Results filtered through user taste profile + anti-profile
  5. LLM generates event↔movie explanation
  6. Ranked and delivered
- **Privacy note:** event data is public information only — no user behavior is sent to external APIs
- **Sensitivity filter:** LLM must flag potentially insensitive event↔movie pairings
  (e.g., don't recommend disaster movies during an actual disaster)

### 4.18 "Coming Soon" (Release Calendar)
- Shows upcoming content the user would likely enjoy, based on taste profile
- Data sources: Radarr (monitored movies with release dates), Sonarr (upcoming episodes/seasons)
- Also: TMDB upcoming releases filtered by taste similarity
- Calendar view: month/week/day with poster thumbnails on date cells
- List view: chronological with countdown ("3 days", "Next Tuesday")
- Per-item: confidence score, "because you..." explanation, "Notify me" button
- Ties into Availability Alerts — "Want This" items show their expected date
- Example: "The next Villeneuve film releases March 15 — you've watched 8/11 of his films"
- Example: "Season 3 of the show you binged drops next week"

### 4.19 "Trailer Preview"
- Inline trailer playback in recommendation cards
- Source: TMDB API provides YouTube trailer IDs in movie/show detail responses
- UI: "Preview" button on any rec card → modal with embedded YouTube player
- Also: trailer auto-play on hover (desktop, optional, muted) like Netflix browse
- Mobile: tap-to-play, standard video player
- Fallback: if no trailer on TMDB, link to YouTube search for "[title] official trailer"
- No external tracking: use youtube-nocookie.com embed domain

### 4.20 "Onboarding Wizard" (First-Run Setup)
Complete guided setup for new installations AND new users:

**Step 1: Server Connection (admin only, first install)**
- Media server type: Plex / Jellyfin / Emby (auto-detect if possible)
- Server URL + authentication
- Library selection: which libraries to index

**Step 2: Integration Setup (admin only)**
- Tautulli: URL + API key (or "Skip — use direct API")
- Radarr: URL + API key (or "Skip — no grab features")
- Sonarr: URL + API key (or "Skip")
- Seerr/Overseerr: URL + API key (or "Skip — no request proxy")
- TMDB API key (required — link to free registration)
- Ollama: URL (auto-detect on network) or "Skip — use templates"
- "Import settings from Radarr" button — pre-fill notifiers (see §4.21)

**Step 3: Taste Quiz (per user, on first login)**
- "Pick 5+ movies/shows you love" — poster grid of popular titles, searchable
- Genre preference sliders: how much do you like [Action|Comedy|Drama|Horror|Sci-Fi|...]
- Optional: "Import from Trakt" / "Import from Letterboxd" / "Paste a list URL"
  → bootstraps taste profile from external history
- Optional: "Import from Plex watch history" → auto-builds profile (if Tautulli connected)
- Skip option: "Just use my watch history" (cold start with popularity fallback)

**Step 4: Notification Preferences (per user)**
- Choose notification channels (see §4.21)
- Choose what to be notified about: new recs, availability, wrapped, auto-grab

**Step 5: Privacy Settings (per user)**
- Social features opt-in/out
- Collaborative filtering participation
- Activity visibility

### 4.21 "Notification Hub" (Unified Notification System)
Centralized notification delivery using **Apprise** (Python library, 90+ services):

**Supported channels:**
- Discord (webhook)
- Telegram (bot)
- Slack (webhook)
- Pushover
- Gotify (self-hosted)
- Email (SMTP)
- Nextcloud Talk (via existing NCT bot)
- PWA push notifications (web push API)
- Webhook (generic, for custom integrations)
- ...and 80+ more via Apprise

**Import from existing *arr stack:**
- "Import from Radarr" / "Import from Sonarr" / "Import from Seerr" button in settings
- Reads notification agent configs from *arr APIs:
  - Radarr: `GET /api/v3/notification` → extracts Discord webhooks, Telegram bots, etc.
  - Sonarr: same endpoint pattern
  - Seerr: notification settings from config
- Pre-fills Recommendarr notification config — user just confirms
- One-time import, not live sync (user can diverge after import)

**Notification types (user-configurable per channel):**

| Event | Default Channel | Description |
|-------|----------------|-------------|
| New high-confidence rec | PWA push | "New recommendation: Oppenheimer (92% match)" |
| Availability alert | PWA push + Discord | "Movie X is now ready to watch!" |
| Auto-grab completed | Discord | "Auto-grabbed 2 movies based on server taste" |
| Plex Wrapped ready | Discord + Email | "Your February Wrapped is ready!" |
| Cultural Pulse alert | PWA push | "Olympics starting → here are 5 films you'd love" |
| Friend activity | PWA push | "A friend just watched Anatomy of a Fall" |
| Coming Soon reminder | PWA push | "Releasing tomorrow: The next Villeneuve film" |

**Notification center (Web GUI):**
- Bell icon in header → dropdown with recent notifications
- Read/unread state, mark all read, dismiss individual
- Notification history page (searchable, filterable by type)
- Click notification → navigates to relevant content (rec detail, availability, wrapped)

### 4.22 "Plugin System" (Community Extensions)

Extensible architecture for community-contributed data sources, recommendation modes, and integrations.

**Plugin interfaces:**

| Interface | Purpose | Example Plugins |
|-----------|---------|-----------------|
| `IMediaServer` | Media server backends | Jellyfin, Emby, Kodi |
| `IWatchHistoryProvider` | Watch data sources | Jellystat, Simkl, custom |
| `IListSource` | External list importers | Letterboxd scraper, IMDB parser, MyAnimeList |
| `IEventSource` | Cultural Pulse feeds | Custom RSS, sports API, regional news |
| `INotifier` | Notification channels | Custom webhook, Matrix, XMPP |
| `IRecommendationMode` | New rec algorithms | Collaborative filter variant, content-based variant |
| `IExplanationProvider` | Explanation generators | Custom LLM provider, translation service |

**Plugin structure:**
```
/plugins/
  my-plugin/
    manifest.json    # name, version, author, interfaces implemented
    plugin.py        # implementation
    README.md        # docs
```

**Plugin lifecycle:**
- Drop folder into `/plugins/` → auto-discovered on restart
- Enable/disable per plugin in admin settings
- Plugin marketplace: curated list on GitHub repo wiki
- Plugins run in sandboxed context — no direct DB access, only via provided APIs
- Version pinning: plugins declare compatible Recommendarr version range

---

## 5. API DESIGN

### 5.1 Base URL
`http://192.168.0.111:<PORT>/api/v1`

### 5.2 Endpoints

```
# ── Auth (Plex OpenID) ──────────────────────────────────────────
GET  /auth/login                      → Redirect to Plex OAuth2 flow
GET  /auth/callback                   → Plex OAuth callback, issues JWT session
POST /auth/logout                     → Invalidate session
GET  /auth/me                         → Current user + Plex profile + linked devices

# ── Users & Profiles ────────────────────────────────────────────
GET  /users                           → List Plex users with profile status
GET  /users/{id}/profile              → User taste profile summary
GET  /users/{id}/history              → Watch history with signals

# ── Recommendations ─────────────────────────────────────────────
GET  /users/{id}/recommendations      → Filtered recommendation list
     ?mode=tonight|grab|rediscover|mood|shuffle
     &mood=<natural language query>    (for mode=mood)
     &limit=10
     &library=movies|tv|anime|all     (filter by Plex library section)
     &genres=thriller,drama            (include genres — Plex genre tags)
     &exclude_genres=horror,romance    (exclude genres)
     &tags=4k,dolby-vision,hdr        (Plex label/collection tags)
     &year_min=2020&year_max=2025     (release year range)
     &language=en,ko,ja               (original language filter)
     &min_confidence=0.7              (minimum rec confidence score)
     &influenced_by=movie:872585,genre:thriller,director:nolan
                                       (show only recs influenced by these signals)
     &exclude_influence=series:12345   (exclude recs driven by specific content)
POST /users/{id}/feedback             → Thumbs up/down/dismiss on rec

# ── Watchlists ──────────────────────────────────────────────────
GET  /users/{id}/watchlists           → List all user watchlists
POST /users/{id}/watchlists           → Create new watchlist (name, icon, color)
GET  /users/{id}/watchlists/{wl_id}   → Get watchlist contents
PUT  /users/{id}/watchlists/{wl_id}   → Update watchlist metadata
DELETE /users/{id}/watchlists/{wl_id} → Delete watchlist
POST /users/{id}/watchlists/{wl_id}/items    → Add item(s) to watchlist
DELETE /users/{id}/watchlists/{wl_id}/items  → Remove item(s) from watchlist
POST /users/{id}/watchlists/toggle    → Bulk toggle item across multiple watchlists
     Body: { "tmdb_id": 872585, "lists": [1,3], "action": "add"|"remove"|"toggle" }

# ── Filtering & Discovery ──────────────────────────────────────
GET  /filters/genres                  → Available genres (synced from Plex library metadata)
GET  /filters/libraries               → Plex library sections with item counts
GET  /filters/tags                    → Available tags/labels/collections from Plex
GET  /filters/languages               → Available original languages
GET  /filters/influences/{user_id}    → User's top recommendation drivers
     Response: { "genres": [...], "directors": [...], "titles": [...], "actors": [...] }
     (shows what's shaping recs — user can toggle these on/off to refine)

# ── Playback Control (Plex Connect) ────────────────────────────
GET  /playback/devices                → List active Plex clients/players
     Response: [{ "id": "abc", "name": "LG OLED G4", "platform": "webos",
                  "state": "idle"|"playing", "controllable": true,
                  "capabilities": ["playback","navigation","timeline"] }]
POST /playback/play                   → Start playback on target device
     Body: { "device_id": "abc", "plex_key": "/library/metadata/12345",
             "resume": false }
POST /playback/play-list              → Play a recommendation list or watchlist
     Body: { "device_id": "abc", "source": "recommendations"|"watchlist",
             "source_id": "wl_3", "shuffle": true|false,
             "filters": { same filter params as /recommendations } }
POST /playback/queue                  → Queue items on target device
     Body: { "device_id": "abc", "plex_keys": [...], "position": "next"|"end" }
POST /playback/control                → Transport controls
     Body: { "device_id": "abc", "action": "pause"|"resume"|"stop"|"next"|"prev" }
GET  /playback/now-playing/{device}   → Current playback state on device

# ── Auto-Grab ───────────────────────────────────────────────────
GET  /auto-grab/config                → User's auto-grab settings
PUT  /auto-grab/config                → Update auto-grab settings (threshold, scope, daily limit)
GET  /auto-grab/history               → Items auto-grabbed and why
GET  /auto-grab/pending               → Items approaching auto-grab threshold

# ── Collections & Completions ───────────────────────────────────
GET  /users/{id}/collections          → Detected incomplete filmographies/franchises
     ?type=director|franchise|studio|actor|collection
     &min_completion=0.5              (only show >50% started collections)
GET  /users/{id}/collections/{coll_id} → Detail: what's watched, what's missing
POST /users/{id}/collections/{coll_id}/complete → Add all missing to Radarr + watchlist

# ── Availability Alerts ─────────────────────────────────────────
POST /users/{id}/alerts/want          → Mark "Want This" on unavailable rec
GET  /users/{id}/alerts               → List pending availability alerts
DELETE /users/{id}/alerts/{alert_id}  → Cancel alert

# ── Plex Wrapped / Analytics ────────────────────────────────────
GET  /users/{id}/wrapped              → User's wrapped stats (current period)
     ?period=month|year|all
GET  /wrapped/server                  → Server-wide stats
GET  /wrapped/overlap?users=id1,id2   → Taste overlap between users

# ── Vibe Playlists ──────────────────────────────────────────────
GET  /users/{id}/vibes                → Auto-generated mood playlists
GET  /users/{id}/vibes/{vibe_id}      → Playlist contents
PUT  /users/{id}/vibes/{vibe_id}      → Rename/customize vibe playlist
POST /users/{id}/vibes/{vibe_id}/play → Send vibe playlist to device (Plex Connect)

# ── Why Not? ────────────────────────────────────────────────────
GET  /users/{id}/why-not/{tmdb_id}    → Explain why item wasn't recommended
POST /users/{id}/why-not/{tmdb_id}/override → "Recommend it anyway" bypass

# ── Zeitgeist / Contextual ───────────────────────────────────────
GET  /zeitgeist                       → Current active world events with mapped media
GET  /zeitgeist/feed/{user_id}        → Personalized zeitgeist recs (events × taste profile)
PUT  /zeitgeist/dismiss/{event_id}    → Dismiss a specific event from user's feed
GET  /zeitgeist/config                → User's contextual awareness settings
PUT  /zeitgeist/config                → Toggle layers: temporal / weather / zeitgeist
POST /zeitgeist/admin/override        → Admin: manually inject event with mapped themes

# ── List Import Engine ──────────────────────────────────────────
POST /import/url                      → Submit URL for title extraction
     Body: { "url": "https://...", "auto_add": false }
GET  /import/{job_id}                 → Check import job status + extracted titles
POST /import/{job_id}/confirm         → Confirm which titles to add to Radarr/watchlist
GET  /import/discover                 → Curated discovery sources
     ?source=letterboxd|imdb|rt|metacritic|reddit|festival
     &region=ch|de|us|kr|jp|fr|gb|in
     &type=trending|weekly|talk-of-web|oscar-buzz|festival-circuit
GET  /import/history                  → Past imports with results

# ── World Cinema Map ─────────────────────────────────────────────
GET  /map/trending                    → All countries with available trending data
     ?limit_per_country=10
GET  /map/trending/{country_code}     → Trending/box office for specific country (ISO 3166-1)
     ?period=day|week
     &annotate=true                    (adds in_library, taste_match, grab_available flags)
GET  /map/heatmap/{user_id}           → Per-country taste overlap scores for map coloring
GET  /map/history/{country_code}      → Historical trending for country
     ?weeks_back=4

# ── Cultural Pulse ──────────────────────────────────────────────
GET  /pulse                           → Current event-reactive recommendations
     ?limit=10
GET  /pulse/events                    → Active events being tracked with linked rec counts
GET  /pulse/events/{event_id}         → All recommendations linked to specific event
POST /pulse/events/{event_id}/dismiss → "Not interested in this event's recs"
GET  /pulse/calendar                  → Upcoming events on radar (sports, festivals, political)
POST /pulse/sources                   → Admin: add/remove RSS feeds, toggle event categories

# ── Social / Community ──────────────────────────────────────────
GET  /users/{id}/friends              → User's taste friends
POST /users/{id}/friends/{friend_id}  → Send friend request
PUT  /users/{id}/friends/{friend_id}  → Accept/decline friend request
GET  /users/{id}/social/feed          → Friend activity feed (anonymizable)
GET  /social/trending                 → Server-wide trending (anonymous counts)
GET  /users/{id}/privacy              → User privacy settings
PUT  /users/{id}/privacy              → Update privacy settings

# ── Group & Social ──────────────────────────────────────────────
GET  /group?users=id1,id2,id3         → "Group Night" recs (all filters apply)

# ── Webhooks (real-time event ingestion) ──────────────────────────
POST /webhook/tautulli              → Tautulli webhook receiver (play/stop/pause/resume)
POST /webhook/radarr                → Radarr webhook (grab/download/rename complete)
POST /webhook/sonarr                → Sonarr webhook (grab/download/rename complete)
POST /webhook/jellyfin              → Jellyfin activity webhook (play/stop events)

# ── Onboarding ──────────────────────────────────────────────────
GET  /setup/status                  → Setup wizard state (which steps completed)
POST /setup/server                  → Step 1: media server connection test + save
POST /setup/integrations            → Step 2: save integration configs (Radarr, Sonarr, etc.)
POST /setup/integrations/import     → Step 2: import notifier config from Radarr/Sonarr/Seerr
     Body: { "source": "radarr", "url": "...", "api_key": "..." }
POST /setup/integrations/test       → Step 2: test connection to any integration
     Body: { "type": "radarr|sonarr|tautulli|ollama|tmdb", "url": "...", "api_key": "..." }
POST /users/{id}/onboarding/quiz    → Step 3: taste quiz results (selected movies + genre prefs)
POST /users/{id}/onboarding/import  → Step 3: import from Trakt/Letterboxd/URL
     Body: { "source": "trakt|letterboxd|url", "data": "..." }
POST /users/{id}/onboarding/skip    → Step 3: skip quiz, use watch history only

# ── Coming Soon (Release Calendar) ─────────────────────────────
GET  /users/{id}/coming-soon        → Upcoming releases matching taste profile
     ?months_ahead=3
     &source=radarr|sonarr|tmdb|all
GET  /users/{id}/coming-soon/calendar → Calendar format (month/week view data)
POST /users/{id}/coming-soon/{tmdb_id}/notify → "Notify me on release"

# ── Notifications ───────────────────────────────────────────────
GET  /users/{id}/notifications      → Notification history (paginated)
     ?unread_only=true&type=recommendation|availability|autograb|wrapped|pulse|social
PUT  /users/{id}/notifications/read → Mark notifications as read
     Body: { "ids": [1,2,3] | "all": true }
GET  /users/{id}/notifications/settings → Per-channel, per-type notification preferences
PUT  /users/{id}/notifications/settings → Update notification preferences
GET  /notifications/channels        → Available notification channels (from Apprise)
POST /notifications/channels/test   → Send test notification to specific channel
POST /notifications/import          → Import notifiers from *arr stack
     Body: { "source": "radarr", "url": "...", "api_key": "..." }

# ── Profile Export/Import ───────────────────────────────────────
GET  /users/{id}/export             → Export user profile as JSON bundle
POST /users/{id}/import             → Import profile from JSON bundle
     Body: { "data": {...}, "mode": "merge|replace", "sections": ["watchlists","taste","feedback"] }
POST /users/{id}/import/preview     → Preview what an import would change (dry run)

# ── Plugins ─────────────────────────────────────────────────────
GET  /admin/plugins                 → Installed plugins with status
PUT  /admin/plugins/{id}            → Enable/disable plugin
GET  /admin/plugins/marketplace     → Available plugins from curated list
POST /admin/plugins/{id}/install    → Install plugin from marketplace

# ── LLM Model Management ────────────────────────────────────────
GET  /settings/llm                    → Current LLM config (tier, active model, provider)
PUT  /settings/llm                    → Update LLM settings (tier, model selection, provider)
GET  /settings/llm/models             → Installed Ollama models (auto-discovered)
GET  /settings/llm/recommended        → Recommended models with specs + install status
POST /settings/llm/models/pull        → Pull a model into Ollama (proxied, streamed progress)
     Body: { "name": "qwen2.5:7b" }
DELETE /settings/llm/models/{name}    → Remove model from Ollama
GET  /settings/llm/vram               → GPU VRAM status (total, used, free, active model load)
WS   /ws/model-pull                   → Stream download progress during model pull

# ── System ──────────────────────────────────────────────────────
GET  /health                          → Service status
GET  /stats                           → System stats (profiles, embeddings, etc.)
POST /refresh                         → Trigger full data sync
POST /recommend/{tmdb_id}/request     → Proxy to Seerr to request movie/show

# ── WebSocket ───────────────────────────────────────────────────
WS   /ws/recommendations/{user_id}    → Live rec updates after watch events
WS   /ws/playback/{device_id}         → Live playback state (position, state changes)
```

### 5.3 Response Format

```json
{
  "recommendations": [
    {
      "tmdb_id": 872585,
      "title": "Oppenheimer",
      "year": 2023,
      "poster": "https://image.tmdb.org/...",
      "similarity_score": 0.87,
      "source": "library",           // "library" | "tmdb" | "rediscover"
      "plex_key": "/library/metadata/12345",
      "plex_deep_link": "plex://play?...",
      "seerr_request_url": null,     // populated for "grab" mode
      "explanation": "You watched 3 Nolan films to completion this year and rated Tenet 5 stars. Oppenheimer is his highest-rated work and matches your preference for long-form historical dramas.",
      "confidence": "high",          // "high" | "medium" | "low"
      "signals": {
        "genre_match": 0.92,
        "director_affinity": 0.95,
        "mood_cluster": 0.78,
        "anti_profile_distance": 0.85
      },
      "influenced_by": [
        { "type": "movie", "id": 577922, "title": "Tenet", "weight": 0.4 },
        { "type": "genre", "id": "drama", "weight": 0.3 },
        { "type": "director", "id": "nolan", "name": "Christopher Nolan", "weight": 0.3 }
      ],
      "playback": {
        "available_on": ["Rayce_HTPC", "LG OLED G4", "iPhone"],
        "quality": "4K HDR",
        "audio": "TrueHD 7.1 Atmos"
      }
    }
  ],
  "meta": {
    "user": "Ray",
    "mode": "tonight",
    "generated_at": "2026-02-27T20:30:00Z",
    "profile_freshness": "2026-02-27T18:00:00Z",
    "total_candidates": 2755,
    "filtered_to": 10
  }
}
```

---

## 6. DELIVERY INTERFACES

### Phase 1: API + NCT Bot (MVP)
- FastAPI server with REST endpoints
- Nextcloud Talk bot integration via existing NCT bot framework
- Commands: `/recommend`, `/recommend grab`, `/recommend mood <query>`, `/recommend group @user1 @user2`
- Bot posts recommendations as rich cards with poster thumbnails

### Phase 2: Web GUI

**Authentication:**
- Plex OAuth2 (OpenID) — users log in with their Plex account
- No separate registration or passwords; Plex identity = Recommendarr identity
- JWT session tokens after OAuth callback, stored in httpOnly cookie
- User permissions inherited from Plex server sharing (only users with server access)

**Main Views:**

**Recommendation Feed** (home screen):
- Scrollable card grid with poster, title, year, confidence score, explanation snippet
- Mode tabs: Tonight / Worth Grabbing / Rediscover / Mood / Shuffle
- "Shuffle" mode: randomized selection from rec pool, one-click refresh for new set
- Each card: click → detail panel, long-press/right-click → add to watchlist(s)
- Inline "Play on..." button → device picker dropdown (Plex Connect)
- "Request" button on non-library items → Seerr proxy

**Recommendation Filters** (sidebar/drawer — mirrors Plex client filters):
- Library: Movies / TV Shows / Anime (multi-select toggle)
- Genres: Plex genre tags (Action, Comedy, Drama, etc.) — include/exclude toggle per genre
- Tags: Plex labels and collections (4K, Dolby Vision, HDR, Oscar Winner, etc.)
- Year range: slider or min/max inputs
- Language: original language filter
- Confidence threshold: slider (0.5 → 1.0)

**Influence Tuning** (unique feature):
- "Why these recs?" panel showing what's driving recommendations
- Lists: top genre influences, director/actor affinities, specific titles that shaped the profile
- Each influence item has a toggle: ON = keep influencing, OFF = suppress from rec engine
- "Add influence" — manually boost a genre, director, or movie as a preference signal
- "Remove influence" — exclude specific series, movies, or genres from driving recs
- Changes feed back into taste profile in real-time (re-ranks recs on toggle)

**Watchlists:**
- Multiple named watchlists per user (e.g., "Weekend Binge", "Watch with Fei", "Oscar Homework")
- Customizable: name, color, icon
- Quick-toggle: from any recommendation card, checkboxes to add/remove from multiple lists
- Watchlist view: grid or list layout, sortable, filterable with same filters as rec feed
- "Play Watchlist" button → sends entire list to device as queue (shuffle optional)

**Playback Control (Plex Connect):**
- Device picker: shows all active Plex clients with status (idle/playing/paused)
- "Play on [Device]" from any card, any list, any rec
- Queue management: drag-reorder, add next, add to end
- Now Playing bar (bottom of screen): current track, device name, play/pause/skip
- List play mode: play entire rec list or watchlist as continuous queue
- Shuffle play: randomize order of any list before sending to device
- Cross-device: start on HTPC, switch to WebOS TV, continue on iPhone (session handoff)

**Profile / Taste View:**
- Genre radar chart — visual taste fingerprint
- Top directors, actors, writers with affinity scores
- Watch history timeline (completion rates visible)
- Mood clusters visualization
- Anti-profile: "You don't like..." section

**Admin Panel:**
- System stats: embedding count, profile freshness, last sync time
- User overview: all profiles, activity levels
- Sync triggers: manual refresh, TMDB cache status
- Recommendation quality metrics: click-through, watch-through, feedback ratios

**Design Language:**
- Visual reference: Plex Web + Overseerr/Jellyseerr hybrid
- Dark theme (near-black background, subtle gray cards, accent color highlights)
- Poster-centric: large movie/show posters are the primary visual element
- Card-based layout: rounded corners, subtle shadows, hover effects with backdrop blur
- Typography: clean sans-serif (Inter or system font stack), hierarchy via weight not size
- Color accents: recommendation confidence mapped to color (green=high, amber=medium, gray=low)
- Glassmorphism touches on overlays/modals (like Plex's detail view backdrop blur)
- Smooth transitions: page transitions, card hover scales, skeleton loading states
- Dense information: tooltips, expandable cards, slide-out panels (not new pages)

**Responsive / Mobile:**
- Mobile-first responsive design (not a separate app for Phase 3 — responsive SPA covers it)
- Breakpoints: mobile (<640px), tablet (640-1024px), desktop (>1024px)
- Mobile: bottom tab navigation (Home, Discover, Watchlists, Map, Profile)
- Mobile: swipe gestures on rec cards (right=watchlist, left=dismiss, up=play)
- Mobile: Plex Connect device picker as bottom sheet
- Tablet: sidebar navigation, 3-column poster grid
- Desktop: full sidebar, 5-6 column poster grid, persistent Now Playing bar
- PWA manifest: installable on iOS/Android home screen (eliminates need for Phase 7 native apps)
- Offline: service worker caches poster images and last recommendation set

**Component Library:** shadcn/ui + Tailwind CSS (matches Overseerr's component approach)
**Framework:** Vite + React + TypeScript
**URL:** `recommendarr.mydirenzo.ch` via NPM reverse proxy

### Phase 3: Plex Integration (Windows HTPC)
- Custom Plex plugin or overlay for Plex HTPC
- "Recommended For You" virtual shelf on home screen
- Keyboard/gamepad navigable within Steam BPM workflow
- Pulls from Recommendarr API, renders as Plex-styled cards
- Direct play integration — select rec → plays immediately on HTPC

### Phase 4: Mobile/TV Apps
- WebOS app for LG OLED G4 (web wrapper around Phase 2 GUI, optimized for remote navigation)
- iOS/Android companion app (React Native or PWA wrapper)
- Displays recs, allows one-tap Seerr requests, shows "now playing" context
- Push notifications for high-confidence new recommendations
- Plex Connect: phone as remote — browse recs on phone, play on TV

---

## 7. INFRASTRUCTURE

### 7.1 Container Spec

| Parameter | Value |
|-----------|-------|
| Image | Custom (Python 3.12 + FastAPI) |
| Container name | `recommendarr` |
| Port | `30800` (external) → `8000` (internal) |
| Network | Bridge |
| Appdata | `/mnt/user/system/appdata/recommendarr` |
| Dependencies | `ollama`, `chroma`, `LLM-PostgreSQL`, `Plex-Media-Server` |
| GPU | P100 access for embedding generation |
| Restart | `unless-stopped` |

### 7.2 Resource Estimates

| Resource | Estimate | Notes |
|----------|----------|-------|
| VRAM | ~600MB (nomic-embed-text) | Shared with Ollama, already loaded |
| RAM | ~512MB | FastAPI + workers + cache |
| Disk (appdata) | ~2GB | Config, TMDB cache, logs |
| Disk (ChromaDB) | ~500MB additional | Content embeddings for ~40K media items |
| CPU | Low (burst during sync) | Mostly I/O bound |

### 7.3 External Dependencies

| Service | Endpoint | Purpose | Rate Limit | Status |
|---------|----------|---------|------------|--------|
| Tautulli | `http://localhost:30181/api/v2` | Watch history, user activity | Local | ✅ VERIFIED |
| Plex | `http://localhost:32400` | Library state, ratings, users | Local | ✅ VERIFIED |
| Radarr | `http://localhost:30878/api/v3` | Movie library, availability | Local | ✅ VERIFIED |
| Sonarr TV | `http://localhost:30989/api/v3` | TV library | Local | ✅ VERIFIED |
| Sonarr Anime | `http://localhost:30990/api/v3` | Anime library | Local | ✅ VERIFIED |
| Seerr | `http://localhost:30055/api/v1` | Request proxy | Local | ✅ VERIFIED |
| Ollama | `http://localhost:11434` | Embeddings + LLM inference (optional) | Local | ✅ VERIFIED |
| LiteLLM | `http://localhost:20004` | LLM routing (optional) | Local | ✅ VERIFIED |
| ChromaDB | `http://localhost:20002` | Vector storage | Local | ✅ VERIFIED |
| TMDB API | `api.themoviedb.org/3` | Metadata enrichment | 40 req/s (free) | needs key |
| PostgreSQL | `localhost:5432` | State DB (reuse LLM-PostgreSQL) | Local | ✅ VERIFIED |

**Plex Libraries (verified):**

| ID | Type | Name |
|----|------|------|
| 14 | movie | Movies |
| 20 | movie | Kinderfilme |
| 2 | show | TV Series |
| 10 | show | Anime |
| 15 | show | Anime-Ecchi |
| 17 | show | Anime-Hentai |
| 7 | show | Kinderserien |

**API Keys:** Stored in environment variables, never in code. See `.env.example` in repo.
For Ray's deployment: keys extracted from existing container configs (Radarr, Seerr, Tautulli).

---

## 8. DATA MODEL (PostgreSQL)

```sql
-- User profiles synced from Plex
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    plex_user_id INTEGER UNIQUE NOT NULL,
    username VARCHAR(100),
    display_name VARCHAR(200),
    taste_vector_id VARCHAR(100),      -- ChromaDB collection ref
    profile_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Per-user library access (synced from Plex sharing config)
CREATE TABLE user_library_access (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    plex_section_key INTEGER NOT NULL,   -- local library section ID (2, 7, 10, 14, 15, 17, 20)
    plex_sharing_id BIGINT,              -- plex.tv sharing ID
    library_title VARCHAR(200),
    library_type VARCHAR(10),            -- 'movie' | 'show'
    is_accessible BOOLEAN DEFAULT TRUE,  -- shared=1 from Plex API
    last_synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, plex_section_key)
);
CREATE INDEX idx_library_access_user ON user_library_access(user_id, is_accessible);

-- Cached watch history from Tautulli
CREATE TABLE watch_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,   -- 'movie' | 'episode'
    plex_rating_key VARCHAR(50),
    started_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    total_duration_seconds INTEGER,
    completion_pct DECIMAL(5,2),
    watch_count INTEGER DEFAULT 1,
    user_rating DECIMAL(3,1),          -- Plex rating if set
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TMDB metadata cache
CREATE TABLE tmdb_cache (
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,
    title VARCHAR(500),
    year INTEGER,
    genres JSONB,
    keywords JSONB,
    cast_crew JSONB,
    overview TEXT,
    vote_average DECIMAL(4,2),
    popularity DECIMAL(10,2),
    poster_path VARCHAR(200),
    similar_ids INTEGER[],
    embedding_id VARCHAR(100),          -- ChromaDB ref
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tmdb_id, media_type)
);

-- Recommendation log (track what was shown, what was acted on)
CREATE TABLE recommendation_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tmdb_id INTEGER NOT NULL,
    mode VARCHAR(20),                   -- tonight|grab|rediscover|mood|group
    score DECIMAL(5,4),
    explanation TEXT,
    was_clicked BOOLEAN DEFAULT FALSE,
    was_watched BOOLEAN DEFAULT FALSE,
    was_requested BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User feedback on recommendations
CREATE TABLE feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tmdb_id INTEGER NOT NULL,
    feedback VARCHAR(10),               -- 'up' | 'down' | 'dismiss'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Named watchlists per user (multiple per user, togglable)
CREATE TABLE watchlists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    icon VARCHAR(50),                    -- emoji or icon key
    color VARCHAR(7),                    -- hex color
    sort_order INTEGER DEFAULT 0,
    is_default BOOLEAN DEFAULT FALSE,    -- one default "Watch Later" per user
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Watchlist ↔ media items (many-to-many)
CREATE TABLE watchlist_items (
    id SERIAL PRIMARY KEY,
    watchlist_id INTEGER REFERENCES watchlists(id) ON DELETE CASCADE,
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,     -- 'movie' | 'tv'
    added_at TIMESTAMPTZ DEFAULT NOW(),
    notes TEXT,                          -- user notes on why they added it
    UNIQUE(watchlist_id, tmdb_id, media_type)
);

-- Influence overrides (user tuning of what drives their recs)
CREATE TABLE influence_overrides (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    influence_type VARCHAR(20) NOT NULL, -- 'genre' | 'director' | 'actor' | 'movie' | 'series'
    influence_key VARCHAR(200) NOT NULL, -- genre name, person ID, tmdb_id
    action VARCHAR(10) NOT NULL,         -- 'boost' | 'suppress' | 'block'
    weight_modifier DECIMAL(3,2),        -- +/- adjustment to signal weight
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, influence_type, influence_key)
);

-- Playback sessions (for Plex Connect tracking)
CREATE TABLE playback_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    device_id VARCHAR(200),
    device_name VARCHAR(200),
    plex_key VARCHAR(100),
    tmdb_id INTEGER,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    source VARCHAR(20),                  -- 'recommendation' | 'watchlist' | 'direct'
    recommendation_id INTEGER REFERENCES recommendation_log(id)
);

-- Auto-grab configuration per user
CREATE TABLE auto_grab_config (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) UNIQUE,
    enabled BOOLEAN DEFAULT FALSE,
    confidence_threshold DECIMAL(3,2) DEFAULT 0.85,
    scope VARCHAR(20) DEFAULT 'movies',  -- 'movies' | 'movies_tv' | 'all'
    daily_limit INTEGER DEFAULT 3,
    notify_on_grab BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-grab history
CREATE TABLE auto_grab_log (
    id SERIAL PRIMARY KEY,
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,
    title VARCHAR(500),
    triggered_by_users INTEGER,          -- how many users drove the grab
    avg_confidence DECIMAL(5,4),
    radarr_id INTEGER,                   -- Radarr/Sonarr internal ID after add
    grabbed_at TIMESTAMPTZ DEFAULT NOW(),
    available_at TIMESTAMPTZ             -- when download completed
);

-- Availability alerts ("Want This" tracking)
CREATE TABLE availability_alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,
    title VARCHAR(500),
    source_recommendation_id INTEGER REFERENCES recommendation_log(id),
    status VARCHAR(20) DEFAULT 'waiting', -- 'waiting' | 'available' | 'notified' | 'cancelled'
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    available_at TIMESTAMPTZ,
    notified_at TIMESTAMPTZ
);

-- Vibe playlists (auto-generated mood collections)
CREATE TABLE vibe_playlists (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(200) NOT NULL,          -- auto-generated, user-renamable
    auto_name VARCHAR(200),              -- original generated name
    description TEXT,
    pattern_type VARCHAR(50),            -- 'time_of_day' | 'genre_cluster' | 'mood' | 'social'
    pattern_params JSONB,                -- clustering parameters for regeneration
    cover_tmdb_ids INTEGER[],            -- poster mosaic source
    is_active BOOLEAN DEFAULT TRUE,
    last_refreshed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE vibe_playlist_items (
    id SERIAL PRIMARY KEY,
    vibe_id INTEGER REFERENCES vibe_playlists(id) ON DELETE CASCADE,
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,
    score DECIMAL(5,4),                  -- fit score within this vibe
    position INTEGER,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

-- Collection/filmography completion tracking
CREATE TABLE collections (
    id SERIAL PRIMARY KEY,
    collection_type VARCHAR(20) NOT NULL, -- 'director' | 'franchise' | 'studio' | 'actor' | 'tmdb_collection'
    collection_key VARCHAR(200) NOT NULL, -- person_id, franchise_id, etc.
    name VARCHAR(500),
    total_items INTEGER,
    tmdb_ids INTEGER[],                   -- all items in collection
    last_synced_at TIMESTAMPTZ,
    UNIQUE(collection_type, collection_key)
);

CREATE TABLE user_collection_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    collection_id INTEGER REFERENCES collections(id),
    watched_ids INTEGER[],
    completion_pct DECIMAL(5,2),
    last_updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, collection_id)
);

-- Social: friend connections
CREATE TABLE friendships (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    friend_user_id INTEGER REFERENCES users(id),
    status VARCHAR(20) DEFAULT 'pending', -- 'pending' | 'accepted' | 'declined'
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    accepted_at TIMESTAMPTZ,
    UNIQUE(user_id, friend_user_id)
);

-- Social: privacy settings per user
CREATE TABLE privacy_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) UNIQUE,
    show_activity_to_friends BOOLEAN DEFAULT TRUE,
    anonymize_activity BOOLEAN DEFAULT FALSE,    -- show as "A friend" instead of name
    contribute_to_collaborative BOOLEAN DEFAULT TRUE,
    show_in_server_stats BOOLEAN DEFAULT TRUE,
    allow_friend_requests BOOLEAN DEFAULT TRUE
);

-- List import jobs
CREATE TABLE import_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    source_url TEXT,
    source_type VARCHAR(50),             -- 'letterboxd' | 'imdb' | 'reddit' | 'article' | 'manual'
    status VARCHAR(20) DEFAULT 'processing', -- 'processing' | 'ready' | 'confirmed' | 'failed'
    extracted_titles JSONB,              -- [{title, year, tmdb_id, in_library, confidence}]
    confirmed_tmdb_ids INTEGER[],
    added_to_radarr INTEGER DEFAULT 0,
    added_to_watchlist INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Curated discovery sources (cached external lists)
CREATE TABLE discovery_cache (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,         -- 'letterboxd_popular' | 'imdb_top' | 'tmdb_trending_ch' | 'reddit_hot' | 'festival_cannes'
    region VARCHAR(5),                   -- 'ch' | 'de' | 'us' | etc.
    title VARCHAR(200),                  -- "Trending in Switzerland" | "Reddit r/movies Hot This Week"
    tmdb_ids INTEGER[],
    item_count INTEGER,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ               -- cache TTL
);

-- World Cinema Map: regional trending cache
CREATE TABLE regional_trending (
    id SERIAL PRIMARY KEY,
    country_code VARCHAR(5) NOT NULL,    -- ISO 3166-1 alpha-2
    country_name VARCHAR(100),
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,
    title VARCHAR(500),
    position INTEGER,                    -- chart position (1 = #1)
    period_type VARCHAR(10),             -- 'day' | 'week'
    period_date DATE,
    in_library BOOLEAN DEFAULT FALSE,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(country_code, tmdb_id, period_type, period_date)
);

-- Cultural Pulse: tracked events
CREATE TABLE cultural_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(30) NOT NULL,     -- 'sports' | 'political' | 'cultural' | 'news' | 'trending'
    event_name VARCHAR(500) NOT NULL,
    event_description TEXT,
    source_url TEXT,
    source_type VARCHAR(30),             -- 'rss' | 'calendar' | 'reddit' | 'google_trends'
    thematic_keywords JSONB,             -- LLM-generated thematic connections
    thematic_embedding_id VARCHAR(100),  -- ChromaDB ref for similarity search
    sensitivity_flag BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ               -- auto-deactivate after event passes
);

-- Cultural Pulse: event ↔ recommendation links
CREATE TABLE cultural_event_recommendations (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES cultural_events(id) ON DELETE CASCADE,
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,
    title VARCHAR(500),
    thematic_connection TEXT,            -- LLM explanation of why this relates
    similarity_score DECIMAL(5,4),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Cultural Pulse: user dismissals
CREATE TABLE cultural_event_dismissals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_id INTEGER REFERENCES cultural_events(id),
    dismissed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, event_id)
);

-- Cultural Pulse: RSS/calendar source configuration
CREATE TABLE pulse_sources (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(30) NOT NULL,    -- 'rss' | 'sports_calendar' | 'festival_calendar' | 'reddit_sub' | 'google_trends'
    source_name VARCHAR(200),
    source_url TEXT,
    category VARCHAR(30),                -- 'sports' | 'politics' | 'culture' | 'tech' | 'world'
    is_enabled BOOLEAN DEFAULT TRUE,
    check_interval_hours INTEGER DEFAULT 24,
    last_checked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Plex Wrapped snapshots
CREATE TABLE wrapped_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,                     -- NULL for server-wide
    period_type VARCHAR(10) NOT NULL,    -- 'month' | 'year'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    stats JSONB NOT NULL,                -- full stats payload
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Notifications
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    type VARCHAR(30) NOT NULL,           -- 'recommendation' | 'availability' | 'autograb' | 'wrapped' | 'pulse' | 'social' | 'coming_soon'
    title VARCHAR(500),
    body TEXT,
    data JSONB,                          -- payload (tmdb_id, event_id, etc.)
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_notifications_user_unread ON notifications(user_id, is_read, created_at DESC);

-- Notification channel config per user
CREATE TABLE notification_channels (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    channel_type VARCHAR(30) NOT NULL,   -- 'discord' | 'telegram' | 'pushover' | 'gotify' | 'email' | 'pwa' | 'webhook' | 'nct'
    channel_config JSONB NOT NULL,       -- Apprise URL or config params (encrypted at rest)
    enabled_events JSONB,                -- ['recommendation','availability','wrapped'] etc.
    is_enabled BOOLEAN DEFAULT TRUE,
    imported_from VARCHAR(30),           -- 'radarr' | 'sonarr' | 'seerr' | null (manual)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Onboarding taste quiz responses
CREATE TABLE onboarding_quiz (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) UNIQUE,
    selected_tmdb_ids INTEGER[],
    genre_preferences JSONB,             -- {"action": 0.8, "horror": 0.2, ...}
    imported_from VARCHAR(30),           -- 'trakt' | 'letterboxd' | 'url' | null
    completed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Coming Soon: user release notifications
CREATE TABLE release_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tmdb_id INTEGER NOT NULL,
    media_type VARCHAR(10) NOT NULL,
    title VARCHAR(500),
    expected_date DATE,
    source VARCHAR(20),                  -- 'radarr' | 'sonarr' | 'tmdb'
    status VARCHAR(20) DEFAULT 'waiting', -- 'waiting' | 'released' | 'notified'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, tmdb_id, media_type)
);

-- Plugin registry
CREATE TABLE plugins (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE,
    version VARCHAR(20),
    author VARCHAR(200),
    interfaces JSONB,                    -- ['IMediaServer', 'IListSource'] etc.
    is_enabled BOOLEAN DEFAULT FALSE,
    config JSONB,
    installed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contextual signals log (for tuning/debugging)
CREATE TABLE contextual_signals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    signal_type VARCHAR(30),             -- 'temporal' | 'weather' | 'zeitgeist'
    signal_value VARCHAR(200),           -- 'friday_night' | 'rainy' | 'olympics_2026'
    event_id INTEGER REFERENCES zeitgeist_events(id),
    weight_applied DECIMAL(4,3),
    recommendation_id INTEGER REFERENCES recommendation_log(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Zeitgeist: tracked world events
CREATE TABLE zeitgeist_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,     -- 'sports_olympics' | 'geopolitics_conflict' | 'awards_oscars' | etc.
    title VARCHAR(500) NOT NULL,         -- "2026 Winter Olympics — Milano Cortina"
    description TEXT,
    source_url TEXT,                     -- original news source
    source_feed VARCHAR(100),            -- 'reuters_rss' | 'wikipedia_current' | 'sports_calendar' | 'admin_manual'
    region VARCHAR(50),                  -- 'global' | 'europe' | 'switzerland' | 'usa' | etc.
    start_date DATE,                     -- event start (for scheduled events)
    end_date DATE,                       -- event end
    is_active BOOLEAN DEFAULT TRUE,
    priority VARCHAR(10) DEFAULT 'normal', -- 'low' | 'normal' | 'high' (affects weight)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ               -- auto-deactivate after this time
);

-- Zeitgeist: LLM-generated media mappings per event
CREATE TABLE zeitgeist_mappings (
    id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES zeitgeist_events(id) ON DELETE CASCADE,
    mapped_genres VARCHAR(200)[],        -- ['sports documentary', 'competition drama']
    mapped_keywords VARCHAR(200)[],      -- ['underdog', 'athlete', 'olympics']
    mapped_themes TEXT[],                -- ['overcoming adversity', 'national pride']
    mapped_tmdb_ids INTEGER[],           -- specific title recommendations
    embedding_query TEXT,                -- ChromaDB search query generated by LLM
    weight_boost DECIMAL(4,3) DEFAULT 0.10,
    llm_model VARCHAR(100),              -- which model generated this mapping
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Zeitgeist: user dismissals (don't show this event anymore)
CREATE TABLE zeitgeist_dismissals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_id INTEGER REFERENCES zeitgeist_events(id),
    dismissed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, event_id)
);

-- Zeitgeist: user-level contextual settings
CREATE TABLE contextual_config (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) UNIQUE,
    enable_temporal BOOLEAN DEFAULT TRUE,
    enable_weather BOOLEAN DEFAULT TRUE,
    enable_zeitgeist BOOLEAN DEFAULT TRUE,
    max_contextual_weight DECIMAL(4,3) DEFAULT 0.20  -- cap on total contextual influence
);
```

---

## 9. IMPLEMENTATION PHASES

### Phase 1: Foundation (MVP) — Target: 2-3 sessions
**Goal:** Working API that returns recommendations for one user (Ray)

- [ ] Docker container setup (Python 3.12 + FastAPI + PostgreSQL schema)
- [ ] Tautulli API integration — pull full watch history
- [ ] Plex API integration — library contents, user ratings, media info
- [ ] TMDB metadata fetcher + PostgreSQL cache
- [ ] Content embedding pipeline (nomic-embed-text → ChromaDB)
- [ ] Basic taste profiler (completion-weighted genre + personnel + mood clusters)
- [ ] Anti-profile implementation (negative signals from abandons)
- [ ] "Watch Tonight" endpoint — working recommendations with explanations
- [ ] "Worth Grabbing" endpoint — TMDB trending filtered by taste
- [ ] `/health`, `/users`, `/users/{id}/recommendations` endpoints
- [ ] Quality badges: playback info per device from Plex media metadata
- [ ] Basic logging and error handling

- [ ] Tautulli webhook endpoint (`POST /webhook/tautulli`) for real-time history updates
- [ ] Onboarding wizard: server connection + integration setup (Steps 1-2)
- [ ] Onboarding: taste quiz for first user (Step 3)
- [ ] i18n scaffold: react-i18next with EN base, TMDB language passthrough

**Success criteria:** `curl http://localhost:30800/api/v1/users/1/recommendations` returns a ranked list with explanations and quality badges. Tautulli webhook fires on watch events. Onboarding wizard completes successfully.

### Phase 2: Multi-User + Social + NCT Bot — Target: 2-3 sessions
**Goal:** All Plex users profiled, social features, NCT bot delivery

- [ ] Multi-user profile sync from Plex
- [ ] Background worker: continuous Tautulli webhook ingestion
- [ ] "Rediscover" mode (rewatch suggestions)
- [ ] "Group Night" mode (multi-user intersection)
- [ ] Collaborative filtering: "users on this server who loved X also loved Y"
- [ ] Social layer: friend selection, anonymized activity feed
- [ ] Privacy settings: opt-out controls per user (DSG compliant)
- [ ] "Watched by others" badges on recommendations
- [ ] Recommendation feedback loop (track clicked, watched, requested)
- [ ] NCT bot commands: `/recommend`, `/recommend grab`, `/recommend mood <query>`, `/recommend group`
- [ ] NCT bot: rich cards with poster thumbnails

- [ ] Notification hub: Apprise integration, per-user channel config
- [ ] "Import notifiers from Radarr/Sonarr/Seerr" in settings
- [ ] Notification types: new rec, availability, auto-grab, friend activity
- [ ] Radarr/Sonarr webhook endpoints for download completion events

**Success criteria:** Any Plex user can ask NCT bot `/recommend` and get personalized results. Social features visible. Privacy controls functional. Notifications delivered via user's chosen channels.

### Phase 3: Web GUI Core — Target: 3-5 sessions
**Goal:** Full-featured browser app with Plex auth, filters, watchlists, Plex Connect

- [ ] Plex OAuth2 integration (login with Plex account, JWT sessions)
- [ ] React SPA scaffold (Vite + React + Tailwind)
- [ ] Recommendation feed: card grid, mode tabs (Tonight/Grab/Rediscover/Mood/Shuffle)
- [ ] Filter sidebar (mirrors Plex client): library, genre, tags, year, language, confidence
- [ ] Influence tuning panel: view/toggle what drives recs, add/remove influences
- [ ] "Why Not?" panel: click any title → explains why it wasn't recommended + override
- [ ] Watchlist system: multiple named lists, color/icon, quick-toggle from any card
- [ ] Watchlist views: grid/list, sortable, filterable, "Play Watchlist" button
- [ ] Plex Connect: device picker, "Play on [Device]" from any card or list
- [ ] Queue management: play list, shuffle mode, drag-reorder, add next/end
- [ ] Now Playing bar: current track, device name, transport controls
- [ ] Taste profile dashboard: genre radar, director/actor affinities, mood clusters
- [ ] Watch history timeline with completion rates
- [ ] "Complete the Collection" view: filmography/franchise progress bars + one-click complete
- [ ] Social feed: friend activity, server trending, taste overlap scores
- [ ] World Cinema Map: interactive globe/map with per-country trending charts
- [ ] Map: click country → trending list with library status + grab/watchlist buttons
- [ ] Map: heat map mode showing taste overlap per country
- [ ] Cultural Pulse card: "Happening now → Watch this" on home screen
- [ ] Admin panel: system stats, sync triggers, embedding health, user overview
- [ ] NPM reverse proxy at `recommendarr.mydirenzo.ch`

- [ ] Trailer preview: TMDB trailer ID → YouTube embed modal on rec cards
- [ ] Coming Soon calendar: Radarr/Sonarr release dates + TMDB upcoming filtered by taste
- [ ] Notification center: bell icon, dropdown, read/unread, history page
- [ ] Profile export/import: JSON bundle download/upload in settings
- [ ] i18n: German + French translation files, language picker in settings
- [ ] Plex native push: create "Recommended For You" playlist per user in Plex
- [ ] Plex native push: create "Recommendarr Picks" collection per library

**Success criteria:** User logs in with Plex → sees recs → watches trailer inline → filters by genre → adds to watchlist → hits "Play on LG OLED G4" → movie starts on TV. "Why Not?" works. Collections show progress. "Recommended For You" playlist appears in Plex home.

### Phase 4: Intelligence Layer — Target: 2-3 sessions
**Goal:** Natural language, contextual awareness, auto-grab, list import

- [ ] "Mood Match": LLM interprets natural language → embedding query → taste-filtered results
- [ ] Contextual awareness: temporal (time/day/season), weather (Schaffhausen), zeitgeist engine
- [ ] Zeitgeist data pipeline: RSS feeds (Reuters, NZZ, BBC), Wikipedia Current Events, sports calendars
- [ ] Zeitgeist LLM mapping: event → genre/keyword/theme → ChromaDB boost
- [ ] Zeitgeist UI: "In the world right now..." feed section with event-mapped recs
- [ ] Admin: manual event injection, weight overrides
- [ ] Auto-Grab Pipeline: daily job, confidence threshold, per-user config, daily limit
- [ ] Availability Alerts: "Want This" → monitor Radarr → notify when available
- [ ] List Import Engine: URL → LLM title extraction → TMDB lookup → library cross-reference
- [ ] Discovery sources: "Popular on [Platform]", "Popular in [Country]", "Talk of the Web"
- [ ] "Talk of the Web" scraper: Reddit, Film Twitter, review aggregators, festival circuit
- [ ] Auto-tuning: signal weight optimization based on feedback data
- [ ] Recommendation quality metrics dashboard
- [ ] World Cinema Map backend: TMDB regional trending ingestion (50+ countries), daily cache refresh
- [ ] Cultural Pulse: RSS ingestion pipeline (Reuters, BBC, AP, Reddit, Google Trends)
- [ ] Cultural Pulse: sports/festival/political calendar integration
- [ ] Cultural Pulse: LLM thematic connection pipeline (event → keywords → embeddings → recs)
- [ ] Cultural Pulse: sensitivity filter (LLM flags insensitive event↔movie pairings)
- [ ] Cultural Pulse: admin panel for source management

**Success criteria:** "Mood match: cozy rainy day movie" returns relevant results. Auto-grab adds a movie overnight. User pastes Letterboxd URL → bulk import works. "Talk of the Web" shows current film discourse.

### Phase 4.5: Extensibility — Target: 1-2 sessions
**Goal:** Plugin system + media server abstraction finalized

- [ ] Plugin interface definitions (`IMediaServer`, `IWatchHistoryProvider`, `IListSource`, etc.)
- [ ] Plugin auto-discovery from `/plugins/` directory
- [ ] Plugin admin UI: installed list, enable/disable, marketplace link
- [ ] Jellyfin `IMediaServer` reference implementation (community kickstarter)
- [ ] Jellyfin `IWatchHistoryProvider` (built-in activity API)
- [ ] Plugin documentation + contribution guide for GitHub

### Phase 5: Vibe Playlists + Plex Wrapped — Target: 2-3 sessions
**Goal:** Auto-generated mood collections and analytics

- [ ] Vibe Playlists: k-means clustering of viewing patterns → auto-named collections
- [ ] Vibe examples: "Slow-Burn Sundays", "Late Night Comfort", "Fei & Ray Date Night"
- [ ] Vibe playlists: playable via Plex Connect, shuffle, auto-refresh
- [ ] Vibe UI: mosaic cover art, rename/customize, play/queue buttons
- [ ] Plex Wrapped (monthly): per-user stats card generation
- [ ] Plex Wrapped (annual): comprehensive year-in-review
- [ ] Server-wide stats: most popular, most divisive, taste overlap matrix
- [ ] Wrapped presentation: shareable cards, exportable as image/PDF
- [ ] Storage efficiency report: most-watched-per-GB, dead weight detection

**Success criteria:** Ray opens app → sees "Late Night Comfort" vibe playlist with 15 items → hits shuffle play on HTPC. Monthly Wrapped auto-generates with shareable card.

### Phase 6: Plex Integration (HTPC + Native) — Target: 2-3 sessions
**Goal:** Native-feeling experience on Plex HTPC and Windows

- [ ] Custom Plex plugin or overlay for Plex HTPC
- [ ] "Recommended For You" virtual shelf on home screen
- [ ] Keyboard/gamepad navigable within Steam BPM workflow
- [ ] Direct play: select rec → plays immediately on HTPC
- [ ] Windows app (Electron wrapper or dedicated)
- [ ] AI Handbrake integration: quality badges reflect transcode pipeline status + ETA

### Phase 7: TV Apps + PWA Polish — Target: TBD
**Goal:** Every screen in the house

- [ ] PWA polish: push notifications, offline rec cache, install prompts
- [ ] WebOS app for LG OLED G4 (web wrapper around PWA, D-pad navigation optimized)
- [ ] 10-foot UI mode: large text, focus-ring navigation, gamepad/remote compatible
- [ ] Cross-device session handoff (start on HTPC, continue on phone/TV)
- [ ] Native apps only if PWA proves insufficient (React Native as fallback)

---

## 10. OPEN QUESTIONS

1. ~~**TMDB API key**~~ — ✅ RESOLVED: Register at themoviedb.org (free). Required dependency for all users.
2. ~~**Tautulli API key**~~ — ✅ RESOLVED: Extracted. Key=`a7e73d977d234fb6965ddf63acf82249`, port=30181.
3. ~~**Sonarr ports**~~ — ✅ RESOLVED: sonarr-tv=30989, sonarr-anime=30990.
4. **ChromaDB collection strategy** — Separate collection for content embeddings vs. reuse existing RAG collection?
5. ~~**LLM model for explanations**~~ — ✅ RESOLVED: Three-tier system. Tier 1 (templates) default. Tier 3 (remote API, no login) recommended. Tier 2 (Ollama) for Ray's deployment.
6. ~~**PostgreSQL**~~ — ✅ RESOLVED: Reuse LLM-PostgreSQL for Ray. Dedicated container for public GitHub release.
7. ~~**Anime handling**~~ — ✅ RESOLVED: Sub-profiles per domain (Movies/TV/Anime) with optional cross-pollination. See §3.3.
8. **Privacy per user** — Should users be able to opt out of profiling? (Swiss DSG consideration)
9. ~~**History depth**~~ — ✅ RESOLVED: User-selectable (3mo/6mo/12mo/all). Default 12 months. See §3.4.
10. **Embedding granularity** — Embed at movie level, or also at scene/review level for richer similarity?
11. **Plex Connect scope** — Plex's `/player/playback/playMedia` works on active clients. Should we also support waking sleeping devices (Wake-on-LAN for HTPC)?
12. **Watchlist sync** — Sync Recommendarr watchlists back to Plex watchlist, or keep them independent?
13. **Shuffle algorithm** — Pure random, or weighted random (higher confidence recs more likely in shuffle)?
14. **Talk of the Web frequency** — How often should Reddit/Twitter/festival scraping run? Daily? Hourly?
15. **Vibe playlist count** — Auto-generate up to how many vibes per user? Cap at 5-10 to avoid clutter?
16. **Auto-grab notification channel** — NCT bot message? Push notification? Email? All of the above?
17. **Wrapped sharing** — Generate shareable image/card? Post to NCT channel? Both?
18. **AI Handbrake integration** — How does the Handbrake workflow expose queue/status? API? File-based? Need to define interface.
19. **Weather API** — OpenWeatherMap free tier (1000 calls/day) sufficient? Or MeteoSwiss for local accuracy?
20. **Festival tracking scope** — Which festivals? Cannes, Venice, Berlin, TIFF, Sundance, Locarno (local!), others?
21. **World Map granularity** — Country-level only, or also regional (US states, Chinese provinces, Indian states)?
22. **Cultural Pulse RSS sources** — Starting set of RSS feeds? Reuters + BBC + AP baseline, or more specialized film/entertainment feeds?
23. **Sensitivity filter strictness** — How aggressive should the LLM be at filtering event↔movie pairings? Conservative (block anything potentially tasteless) or trust the user to dismiss?
24. **Sports calendar source** — ESPN API? Manual calendar? Wikipedia event lists?
25. **Celebrity tribute automation** — Auto-detect celebrity deaths from news feed and generate filmography collections? Or too morbid for automation?
21. **Zeitgeist news sources** — Reuters + BBC + NZZ + Tagesschau baseline? Add others?
22. **Zeitgeist sensitivity** — Conflict/war events: surface anti-war cinema and journalism films, or too heavy-handed? User preference toggle?
23. **Sports calendar source** — ESPN API, Olympic.org, or manual calendar for major events?
24. **Google Trends API** — Requires Serpapi or similar paid wrapper. Worth the cost, or Wikipedia Current Events sufficient for trend detection?

---

## 11. RISK ASSESSMENT

| Risk | Severity | Mitigation |
|------|----------|------------|
| Cold start (new users with no history) | Medium | Fall back to popularity + genre diversity until 10+ watches |
| TMDB rate limiting | Low | Local cache with 7-day TTL, batch fetches during off-peak |
| ChromaDB memory pressure | Medium | Separate collection, monitor VRAM sharing with other Ollama loads |
| Stale taste profiles | Low | Background worker updates profiles after each watch event |
| LLM explanation quality | Medium | Template-hybrid approach: structured signals + LLM polish |
| False positive recs | Medium | Feedback loop + anti-profile refinement over time |

---

## 12. PUBLIC RELEASE (GitHub)

**Repository:** `github.com/rayce185/recommendarr` (planned)
**License:** TBD (MIT or AGPLv3)

### 12.1 Architecture for Public Release

The project must be self-contained and deployable by anyone with a Plex server:

**Docker Compose (standalone):**
- `recommendarr` — FastAPI app (Python 3.12)
- `recommendarr-db` — PostgreSQL 16 (dedicated, NOT shared)
- `recommendarr-chromadb` — ChromaDB (dedicated)
- All services in a single `docker-compose.yml`
- `.env.example` with all configurable values

**Ray's deployment (unRAID):**
- Reuses existing `LLM-PostgreSQL` and `ChromaDB` containers
- Connects to existing `Ollama` for embeddings + LLM
- Configured via unRAID Docker template or env overrides
- Same codebase, different compose profile: `docker compose --profile unraid up`

**Required by user:**
- Plex server + Plex account (for OAuth + library access)
- Tautulli (for watch history — without it, falls back to Plex-only history, less detailed)
- TMDB API key (free registration at themoviedb.org)

**Optional:**
- Radarr/Sonarr (for "Worth Grabbing" + auto-grab features)
- Seerr/Overseerr/Jellyseerr (for request proxy)
- Ollama or LLM API (for Tier 2/3 explanations, Mood Match, Cultural Pulse)

### 12.2 Configuration Philosophy
- Sane defaults: works with just Plex + Tautulli + TMDB key
- Progressive enhancement: each additional integration unlocks more features
- Feature flags: disable any feature that requires unavailable dependencies
- No hardcoded IPs, ports, or keys — everything via environment variables

---

## 13. RELATED PROJECTS

- **unRAID Master Project** — Recommendarr is a sub-system of the broader LLM automation stack
- **NCT Bot** — Primary Phase 1 delivery interface
- **Seerr** — Request proxy for "Worth Grabbing" recommendations
- **Tdarr** — Transcoding pipeline affects what's playable (format availability)
- **AnimeAIDub** — Future integration: recommend anime that has AI dubs available

---

*This document is the project definition. Implementation begins with Phase 1 upon Ray's approval.*
