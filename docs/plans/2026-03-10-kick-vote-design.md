# Kick-Vote / Library Pruning — Design Document

**Date:** 2026-03-10
**Status:** Approved
**Scope:** Full §10.4 implementation including re-download ETA prediction model
**Branch:** dev/1.1.0

---

## 1. Overview

Democratic library pruning system that continuously scores every library item
on a "vitality" metric. Items below threshold enter a "Sunset Zone" where
active users vote to keep or remove. Kicked items are removed from Radarr/Sonarr
but all metadata preserved for one-click re-download.

## 2. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Execution authority | Hybrid: auto-delete below hard floor, admin confirm for borderline | Safety rails on borderline, no babysitting truly dead items |
| Re-download ETA | Heuristic baseline + live indexer probe on demand | Instant UI feedback + ground truth when user clicks |
| Active user quorum | Configurable threshold (admin sets days-since-last-watch) | Flexibility for different server sizes/activity levels |
| Vitality calc frequency | Daily scheduled task | Consistent freshness without excessive load |
| Metadata preservation | SQLite primary + JSON export backup | Queryable + disaster recovery |
| Voting visibility | All active users can see + vote (democratic) | Community ownership of library health |

## 3. Data Model

### 3.1 vitality_scores
Daily snapshot of every library item's health score.

| Column | Type | Purpose |
|--------|------|---------|
| id | PK | |
| tmdb_id | int, not null | Library item identifier |
| media_type | str(10), not null | movie / show |
| servarr_id | int | Radarr/Sonarr internal ID |
| title | str(500) | Display title |
| composite_score | float | Final vitality 0-100 |
| recency_score | float | Signal 1 |
| velocity_score | float | Signal 2 |
| breadth_score | float | Signal 3 |
| rec_frequency_score | float | Signal 4 |
| niche_score | float | Signal 5 |
| zone | str(20) | healthy / sunset / dead |
| calculated_at | datetime(tz) | |
| Unique: tmdb_id + media_type | | One score per item |

### 3.2 sunset_items
State machine for items in the sunset pipeline.

| Column | Type | Purpose |
|--------|------|---------|
| id | PK | |
| tmdb_id | int, not null | |
| media_type | str(10), not null | |
| servarr_id | int | Radarr/Sonarr ID |
| title | str(500) | |
| entered_sunset_at | datetime(tz) | When vitality first dropped |
| grace_expires_at | datetime(tz) | entered + grace_period |
| status | str(20) | voting / pending_admin / approved / kicked / reprieved |
| votes_keep | int, default 0 | Cached tally |
| votes_kick | int, default 0 | Cached tally |
| kick_method | str(20) | auto / vote / admin |
| immune_until | datetime(tz) | Reprieve immunity expiry |
| resolved_at | datetime(tz) | |
| Unique: tmdb_id + media_type | | |

### 3.3 sunset_votes
Per-user votes on sunset zone items.

| Column | Type | Purpose |
|--------|------|---------|
| id | PK | |
| tmdb_id | int, not null | |
| media_type | str(10), not null | |
| user_id | FK→users | |
| vote | str(10) | keep / kick |
| voted_at | datetime(tz) | |
| Unique: tmdb_id + media_type + user_id | | One vote per user per item |

### 3.4 kicked_items
Metadata snapshot for one-click re-download.

| Column | Type | Purpose |
|--------|------|---------|
| id | PK | |
| tmdb_id | int | |
| media_type | str(10) | |
| title | str(500) | |
| servarr_id | int | Original Radarr/Sonarr ID |
| servarr_type | str(10) | radarr / sonarr |
| quality_profile_id | int | |
| quality_profile_name | str(100) | |
| root_folder | str(500) | |
| tags | JSON | Original tag IDs |
| poster_path | str(200) | |
| year | int | |
| genres | JSON | |
| overview | text | |
| vitality_at_kick | float | Score when kicked |
| kicked_at | datetime(tz) | |
| kicked_by | str(20) | auto / vote / admin |
| redownloaded_at | datetime(tz) | Null until re-added |
| redownload_eta_tier | str(20) | instant/hours/days/weeks/rare |

## 4. Vitality Scoring Algorithm

Five signals, each normalized 0→100, weighted composite:

### Signal 1: Recency Decay (30%)
```
recency = 100 × e^(-days_since_last_play / 90)
```
Half-life 90 days. Played yesterday ≈ 99, 90 days = 50, 365 days ≈ 2.

### Signal 2: Play Velocity (25%)
```
velocity = min(100, (plays_per_month / expected) × 50)
trend_bonus = +20 growing, 0 flat, -20 declining
velocity = clamp(velocity + trend_bonus, 0, 100)
```
Expected: movies 0.5/mo, shows 1.5/mo.

### Signal 3: User Breadth (20%)
```
breadth = min(100, (unique_watchers / active_users) × 200)
```

### Signal 4: Recommendation Frequency (10%)
```
rec_freq = min(100, rec_appearances_30d × 10)
```

### Signal 5: Niche Adjustment (15%)
```
genre_rarity = 1.0 - (genre_count_on_server / total_library)
niche_bonus = genre_rarity × 50
niche_score = min(100, base_play_score + niche_bonus)
```

### Composite
```
vitality = (recency × 0.30) + (velocity × 0.25) + (breadth × 0.20)
         + (rec_freq × 0.10) + (niche × 0.15)
```

### Zone Thresholds (admin-configurable)
- Healthy: ≥ 40
- Sunset: 15–39 → enters voting
- Dead: < 15 → auto-eligible (hybrid rule)

## 5. Vote Flow State Machine

```
HEALTHY (vitality ≥ 40)
    │ drops below 40 (and not immune)
    ▼
VOTING (grace period, default 7 days)
    │ grace expires
    ▼
RESOLUTION:
  IF vitality < 15 → AUTO-APPROVED → KICKED
  IF kick ≥ 60% of voters (min 3 votes) → PENDING_ADMIN → admin confirm/veto
  IF keep wins → REPRIEVED (30 day immunity) → HEALTHY
```

## 6. Re-download ETA Model

### Heuristic Tier (instant, always available)
Based on TMDB popularity + age + original language + quality profile:
- **instant**: popularity > 50, age < 2yr, English, any quality
- **hours**: popularity > 20, age < 5yr
- **days**: popularity > 5, age < 15yr
- **weeks**: popularity > 1, or non-English with moderate demand
- **rare**: everything else (very old, very niche, non-English low-popularity)

### Live Probe (on-demand)
Calls Radarr/Sonarr search API with original params → returns actual indexer
results count + best available quality. Displayed as "X results found, best: [quality]".

## 7. API Endpoints

All under `/api/v1/library-health/`:

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /vitality | user | Paginated scores, filterable by zone |
| GET | /vitality/{tmdb_id}/{media_type} | user | Single item detail |
| POST | /vitality/recalculate | admin | Force recalc |
| GET | /sunset | user | Current sunset zone items |
| POST | /sunset/{tmdb_id}/{media_type}/vote | user | Cast vote |
| GET | /sunset/{tmdb_id}/{media_type}/votes | user | Vote tally |
| GET | /pending | admin | Items awaiting confirmation |
| POST | /pending/{tmdb_id}/{media_type}/confirm | admin | Approve kick |
| POST | /pending/{tmdb_id}/{media_type}/veto | admin | Veto → reprieve |
| GET | /graveyard | user | Kicked items |
| POST | /graveyard/{id}/redownload | admin | Re-add to Radarr/Sonarr |
| POST | /graveyard/{id}/check-availability | user | Live indexer probe |
| GET | /config | admin | Thresholds + weights |
| PUT | /config | admin | Update config |
| GET | /stats | user | Dashboard stats |

## 8. Backend File Structure

```
backend/app/
├── api/
│   └── library_health.py         # Routes (~200 lines)
├── models/
│   └── library_health.py         # 4 SQLAlchemy models (~120 lines)
├── services/
│   ├── vitality_scoring.py       # Scoring algorithm (~200 lines)
│   ├── vitality_scheduler.py     # Daily recalc task (~80 lines)
│   ├── sunset_manager.py         # Vote flow state machine (~250 lines)
│   ├── kick_executor.py          # Deletion + snapshot (~200 lines)
│   └── redownload_eta.py         # Heuristic + probe (~150 lines)
```

## 9. Frontend

New sidebar entry: **Library Health**

Sub-tabs:
- **Overview**: vitality distribution chart, zone counts, storage stats
- **Sunset Zone**: cards with vitality breakdown, vote buttons, grace timer
- **Graveyard**: kicked items, re-download button, availability check
- **Admin** (admin only): pending confirmations, config panel, force recalc

## 10. Implementation Order

1. Models (Alembic migration)
2. Vitality scoring service
3. Vitality scheduler (hook into existing scheduler)
4. Sunset manager (state machine)
5. Kick executor (Radarr/Sonarr deletion + snapshot + JSON export)
6. Re-download ETA service
7. API routes
8. Frontend: Library Health page + sub-tabs
9. Integration test
