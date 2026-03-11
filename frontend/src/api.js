// ─── API Client & Auth ───────────────────────────────────────────
const API_BASE = "/api/v1";

let _authToken = null;
export function setApiToken(token) { _authToken = token; }
export function authFetch(url, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (_authToken) headers["Authorization"] = `Bearer ${_authToken}`;
  return fetch(url, { ...opts, headers });
}

const api = {
  // Auth — backend only receives the final token (like Overseerr)
  authPlex: (authToken) => fetch(`${API_BASE}/auth/plex`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ authToken }),
  }).then(r => { if (!r.ok) return r.json().then(d => { throw new Error(d.detail || "Auth failed"); }); return r.json(); }),
  authMe: (token) => fetch(`${API_BASE}/auth/me`, { headers: { Authorization: `Bearer ${token}` } }).then(r => { if (!r.ok) throw new Error("Invalid token"); return r.json(); }),

  // Data (all use authFetch for JWT)
  health: () => authFetch(`${API_BASE}/health`).then(r => r.json()),
  stats: () => authFetch(`${API_BASE}/stats`).then(r => r.json()),
  users: () => authFetch(`${API_BASE}/users`).then(r => r.json()),
  userProfile: (u) => authFetch(`${API_BASE}/users/${u}/profile`).then(r => r.json()),
  userHistory: (u) => authFetch(`${API_BASE}/users/${u}/history`).then(r => r.json()),
  recommend: (u, mode, opts = {}) => {
    const params = new URLSearchParams({ mode, limit: opts.limit || 20 });
    if (opts.domain && opts.domain !== "all") params.set("domain", opts.domain);
    if (opts.mood) params.set("mood", opts.mood);
    if (opts.refresh) params.set("refresh", "true");
    if (opts.exclude_genres) params.set("exclude_genres", opts.exclude_genres);
    if (opts.include_genres) params.set("include_genres", opts.include_genres);
    if (opts.exclude_libraries) params.set("exclude_libraries", opts.exclude_libraries);
    if (opts.watched_filter) params.set("watched_filter", opts.watched_filter);
    if (opts.min_year) params.set("min_year", opts.min_year);
    if (opts.max_year) params.set("max_year", opts.max_year);
    if (opts.min_rating) params.set("min_rating", opts.min_rating);
    return authFetch(`${API_BASE}/recommend/${u}?${params}`).then(r => r.json());
  },
  lazyExplain: (u, mode) => authFetch(`${API_BASE}/recommend/${u}/explain?mode=${mode}`, { method: "POST" }).then(r => r.json()),
  moodPresets: () => authFetch(`${API_BASE}/mood/presets`).then(r => r.json()),
  moodParse: (q) => authFetch(`${API_BASE}/mood/parse?text=${encodeURIComponent(q)}`).then(r => r.json()),
  detail: (id, mediaType = "movie") => authFetch(`${API_BASE}/detail/${id}?media_type=${mediaType}`).then(r => r.json()),
  filterOptions: () => authFetch(`${API_BASE}/filters/options`).then(r => r.json()),
  watchlistAdd: (tmdbId, mediaType) => authFetch(`${API_BASE}/watchlist/add/${tmdbId}?media_type=${mediaType}`, { method: "POST" }).then(r => r.json()),
  watchlistRemove: (tmdbId, mediaType) => authFetch(`${API_BASE}/watchlist/remove/${tmdbId}?media_type=${mediaType}`, { method: "POST" }).then(r => r.json()),
  trending: (limit = 20) => authFetch(`${API_BASE}/discover/trending?limit=${limit}`).then(r => r.json()),
  trendingExpanded: (source, opts = {}) => {
    const params = new URLSearchParams({ source });
    if (opts.media_type) params.set("media_type", opts.media_type);
    if (opts.region) params.set("region", opts.region);
    if (opts.provider_id) params.set("provider_id", opts.provider_id);
    if (opts.genre_id) params.set("genre_id", opts.genre_id);
    if (opts.days) params.set("days", opts.days);
    if (opts.page) params.set("page", opts.page);
    return authFetch(`${API_BASE}/discover/trending?${params}`).then(r => r.json());
  },
  trendingGenres: () => authFetch(`${API_BASE}/discover/genres`).then(r => r.json()),
  userCountries: (username) => authFetch(`${API_BASE}/discover/user-countries/${encodeURIComponent(username)}`).then(r => r.json()),
  trendingCountries: () => authFetch(`${API_BASE}/discover/countries`).then(r => r.json()),
  trendingProviders: (region = "CH") => authFetch(`${API_BASE}/discover/providers?country=${region}`).then(r => r.json()),
  buzz: (subs) => authFetch(`${API_BASE}/discover/buzz${subs ? '?subreddits=' + encodeURIComponent(subs) : ''}`).then(r => r.json()),
  worldCinemaMap: (username) => authFetch(`${API_BASE}/discover/world-cinema${username ? "?username=" + encodeURIComponent(username) : ""}`).then(r => r.json()),
  worldCinemaPinned: (username) => authFetch(`${API_BASE}/discover/world-cinema/pinned?username=${encodeURIComponent(username)}`).then(r => r.json()),
  worldCinemaSetPinned: (username, countries) => authFetch(`${API_BASE}/discover/world-cinema/pinned?username=${encodeURIComponent(username)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ countries }) }).then(r => r.json()),
  getNicknames: (username) => authFetch(`${API_BASE}/users/${encodeURIComponent(username)}/nicknames`).then(r => r.json()),
  setNicknames: (username, nicknames) => authFetch(`${API_BASE}/users/${encodeURIComponent(username)}/nicknames`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nicknames }) }).then(r => r.json()),
  getSchedule: (u) => authFetch(`${API_BASE}/schedule/${u}`).then(r => r.json()),
  suggestSchedule: (u) => authFetch(`${API_BASE}/schedule/${u}/suggest`).then(r => r.json()),
  updateSchedule: (u, data) => authFetch(`${API_BASE}/schedule/${u}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  systemSettings: () => authFetch(`${API_BASE}/system/settings`).then(r => r.json()),
  systemSettingsEdit: () => authFetch(`${API_BASE}/system/settings?edit=true`).then(r => r.json()),
  updateSettings: (data) => authFetch(`${API_BASE}/system/settings`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings: data }) }).then(r => r.json()),
  aiConfig: (edit = false) => authFetch(`${API_BASE}/system/ai/config?edit=${edit}`).then(r => r.json()),
  aiProviders: () => authFetch(`${API_BASE}/system/ai/providers`).then(r => r.json()),
  aiUpdateConfig: (data) => authFetch(`${API_BASE}/system/ai/config`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  aiTest: (data) => authFetch(`${API_BASE}/system/ai/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  aiModels: (data) => authFetch(`${API_BASE}/system/ai/models`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  aiReset: () => authFetch(`${API_BASE}/system/ai/config/reset`, { method: "POST" }).then(r => r.json()),
  testConnection: (service) => authFetch(`${API_BASE}/system/settings/test-connection?service=${service}`, { method: "POST" }).then(r => r.json()),
  cacheDetailed: () => authFetch(`${API_BASE}/system/settings/cache`).then(r => r.json()),
  collections: (u) => authFetch(`${API_BASE}/recommend/${u}/collections`).then(r => r.json()),
  collectionFor: (tmdbId) => authFetch(`${API_BASE}/collection/for/${tmdbId}`).then(r => { if (r.status === 204) return null; return r.json(); }),
  whyNot: (tmdbId, username, mediaType = "movie") => authFetch(`${API_BASE}/why-not/${tmdbId}?username=${encodeURIComponent(username)}&media_type=${mediaType}`).then(r => { if (!r.ok) throw new Error("Analysis failed"); return r.json(); }),
  calendar: (days = 90, mediaType = "all", source = "all", startDate = null) => authFetch(`${API_BASE}/calendar?days=${days}&media_type=${mediaType}&source=${source}${startDate ? `&start_date=${startDate}` : ""}`).then(r => r.json()),
  exportProfile: (username) => authFetch(`${API_BASE}/users/${encodeURIComponent(username)}/profile/export`).then(r => r.json()),
  importProfile: (username, data, mode = "merge") => authFetch(`${API_BASE}/users/${encodeURIComponent(username)}/profile/import`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ data, mode }) }).then(r => r.json()),
  discoveryFeed: (username, refresh = false) => authFetch(`${API_BASE}/discover/feed/${encodeURIComponent(username)}${refresh ? "?refresh=true" : ""}`).then(r => r.json()),
  notifications: () => authFetch(`${API_BASE}/notifications`).then(r => r.json()),
  dismissNotification: (id) => authFetch(`${API_BASE}/notifications/dismiss`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) }).then(r => r.json()),
  dismissAllNotifications: () => authFetch(`${API_BASE}/notifications/dismiss-all`, { method: "POST" }).then(r => r.json()),
  clearDismissedNotifications: () => authFetch(`${API_BASE}/notifications/dismissed`, { method: "DELETE" }).then(r => r.json()),
  groupRecommend: (username, users, opts = {}) => {
    const params = new URLSearchParams({ users: users.join(","), limit: opts.limit || 30 });
    if (opts.domain && opts.domain !== "all") params.set("domain", opts.domain);
    if (opts.watched_filter) params.set("watched_filter", opts.watched_filter);
    return authFetch(`${API_BASE}/recommend/${username}/group?${params}`).then(r => r.json());
  },
  wrapped: (username, year = null) => {
    const params = year ? `?year=${year}` : "";
    return authFetch(`${API_BASE}/users/${username}/wrapped${params}`).then(r => r.json());
  },
  // Watchlist
  watchlist: (sort = "addedAt:desc", type = null) => {
    const params = new URLSearchParams({ sort });
    if (type) params.set("type", type);
    return authFetch(`${API_BASE}/watchlist?${params}`).then(r => r.json());
  },
  watchlistDelete: (tmdbId, mediaType = "movie") => authFetch(`${API_BASE}/watchlist/${tmdbId}?media_type=${mediaType}`, { method: "DELETE" }).then(r => r.json()),
  addToLibrary: (tmdbId, mediaType, opts = {}) => authFetch(`${API_BASE}/library/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tmdb_id: tmdbId, media_type: mediaType, ...opts }),
  }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Add failed"); return d; })),
  routePreview: (tmdbId, mediaType) => authFetch(`${API_BASE}/library/route-preview?tmdb_id=${tmdbId}&media_type=${mediaType}`, { method: "POST" }).then(r => r.json()),
  // Devices & Playback
  devices: () => authFetch(`${API_BASE}/devices`).then(r => r.json()),
  playOnDevice: (tmdbId, mediaType = "movie", deviceId = null) => {
    const params = new URLSearchParams({ media_type: mediaType });
    if (deviceId) params.set("device_id", deviceId);
    return authFetch(`${API_BASE}/play/${tmdbId}?${params}`, { method: "POST" }).then(r => r.json());
  },
  // User Preferences
  preferences: () => authFetch(`${API_BASE}/preferences`).then(r => r.json()),
  updatePreferences: (data) => authFetch(`${API_BASE}/preferences`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  resetPreference: (key) => authFetch(`${API_BASE}/preferences/${key}`, { method: "DELETE" }).then(r => r.json()),
  globalPreferences: () => authFetch(`${API_BASE}/preferences/global`).then(r => r.json()),
  updateGlobalPreferences: (data) => authFetch(`${API_BASE}/preferences/global`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  cacheClear: (scope = "all") => authFetch(`${API_BASE}/system/settings/cache/clear?scope=${scope}`, { method: "POST" }).then(r => r.json()),
  refreshStart: () => authFetch(`${API_BASE}/cache/refresh`, { method: "POST" }).then(r => r.json()),
  refreshStatus: () => authFetch(`${API_BASE}/cache/refresh/status`).then(r => r.json()),
  myStaleness: () => authFetch(`${API_BASE}/cache/my-staleness`).then(r => r.json()),
  seriesProgress: (username, tmdbIds = null) => authFetch(`${API_BASE}/users/${encodeURIComponent(username)}/series-progress${tmdbIds ? `?tmdb_ids=${tmdbIds.join(",")}` : ""}`).then(r => r.json()),
  getOverrides: (u) => authFetch(`${API_BASE}/users/${u}/profile/overrides`).then(r => r.json()),
  saveOverrides: (u, data) => authFetch(`${API_BASE}/users/${u}/profile/overrides`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data)
  }).then(r => r.json()),
  similar: (id) => authFetch(`${API_BASE}/discover/similar/${id}?limit=6`).then(r => r.json()),
  genres: () => authFetch(`${API_BASE}/genres`).then(r => r.json()),
  request: (id, type) => authFetch(`${API_BASE}/request/${id}?media_type=${type || "movie"}`, {
    method: "POST",
  }).then(r => r.json()),
  compareProfiles: (users, domain = "all") => authFetch(`${API_BASE}/compare?users=${encodeURIComponent(users.join(","))}&domain=${domain}`).then(r => { if (!r.ok) return r.json().then(d => { throw new Error(d.detail || "Compare failed"); }); return r.json(); }),
  userPeers: (u) => authFetch(`${API_BASE}/users/${u}/peers`).then(r => r.json()),
  submitFeedback: (u, data) => authFetch(`${API_BASE}/users/${u}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).then(r => r.json()),
  removeFeedback: (u, tmdbId) => authFetch(`${API_BASE}/users/${u}/feedback/${tmdbId}`, { method: "DELETE" }).then(r => r.json()),
  getFeedback: (u) => authFetch(`${API_BASE}/users/${u}/feedback`).then(r => r.json()),
  // Browse/search
  browseSearch: (q, page = 1, library = null) => {
    let url = `${API_BASE}/browse/search?q=${encodeURIComponent(q)}&page=${page}`;
    if (library) url += `&library=${encodeURIComponent(library)}`;
    return authFetch(url).then(r => r.json());
  },
  browseDiscover: (opts = {}) => {
    const p = new URLSearchParams();
    if (opts.media_type) p.set("media_type", opts.media_type);
    if (opts.genre_id) p.set("genre_id", opts.genre_id);
    if (opts.year_min) p.set("year_min", opts.year_min);
    if (opts.year_max) p.set("year_max", opts.year_max);
    if (opts.sort_by) p.set("sort_by", opts.sort_by);
    if (opts.page) p.set("page", opts.page);
    if (opts.library) p.set("library", opts.library);
    return authFetch(`${API_BASE}/browse/discover?${p}`).then(r => r.json());
  },
  browseGenres: () => authFetch(`${API_BASE}/browse/genres`).then(r => r.json()),
  browseLibraries: () => authFetch(`${API_BASE}/browse/libraries`).then(r => r.json()),
  // List Import
  importExtract: (data) => authFetch(`${API_BASE}/import/extract`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Extract failed"); return d; })),
  importBulkRequest: (tmdbIds) => authFetch(`${API_BASE}/import/bulk-request`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tmdb_ids: tmdbIds }) }).then(r => r.json()),
  importBulkWatchlist: (tmdbIds) => authFetch(`${API_BASE}/import/bulk-watchlist`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tmdb_ids: tmdbIds }) }).then(r => r.json()),
  // Cultural Pulse
  pulseThemes: (limit = 10) => authFetch(`${API_BASE}/pulse/themes?limit=${limit}`).then(r => r.json()),
  pulseRefresh: () => authFetch(`${API_BASE}/pulse/refresh`, { method: "POST" }).then(r => r.json()),
  pulseSources: () => authFetch(`${API_BASE}/pulse/sources`).then(r => r.json()),
  pulseAddSource: (data) => authFetch(`${API_BASE}/pulse/sources`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  pulseUpdateSource: (id, data) => authFetch(`${API_BASE}/pulse/sources/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  pulseDeleteSource: (id) => authFetch(`${API_BASE}/pulse/sources/${id}`, { method: "DELETE" }).then(r => r.json()),
  pulseDeactivateTheme: (id) => authFetch(`${API_BASE}/pulse/themes/${id}`, { method: "DELETE" }).then(r => r.json()),

  // Library Health
  healthStats: () => authFetch(`${API_BASE}/library-health/stats`).then(r => r.json()),
  healthVitality: (opts = {}) => {
    const p = new URLSearchParams();
    if (opts.zone) p.set("zone", opts.zone);
    if (opts.sort) p.set("sort", opts.sort);
    if (opts.page) p.set("page", opts.page);
    if (opts.per_page) p.set("per_page", opts.per_page);
    if (opts.media_type) p.set("media_type", opts.media_type);
    return authFetch(`${API_BASE}/library-health/vitality?${p}`).then(r => r.json());
  },
  healthVitalityDetail: (tmdbId, mediaType) => authFetch(`${API_BASE}/library-health/vitality/${tmdbId}/${mediaType}`).then(r => r.json()),
  healthRecalculate: () => authFetch(`${API_BASE}/library-health/vitality/recalculate`, { method: "POST" }).then(r => r.json()),
  healthSunset: () => authFetch(`${API_BASE}/library-health/sunset`).then(r => r.json()),
  healthVote: (tmdbId, mediaType, vote) => authFetch(`${API_BASE}/library-health/sunset/${tmdbId}/${mediaType}/vote`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vote }) }).then(r => r.json()),
  healthVoteTally: (tmdbId, mediaType) => authFetch(`${API_BASE}/library-health/sunset/${tmdbId}/${mediaType}/votes`).then(r => r.json()),
  healthPending: () => authFetch(`${API_BASE}/library-health/pending`).then(r => r.json()),
  healthConfirmKick: (tmdbId, mediaType) => authFetch(`${API_BASE}/library-health/pending/${tmdbId}/${mediaType}/confirm`, { method: "POST" }).then(r => r.json()),
  healthVetoKick: (tmdbId, mediaType) => authFetch(`${API_BASE}/library-health/pending/${tmdbId}/${mediaType}/veto`, { method: "POST" }).then(r => r.json()),
  healthGraveyard: () => authFetch(`${API_BASE}/library-health/graveyard`).then(r => r.json()),
  healthRedownload: (id) => authFetch(`${API_BASE}/library-health/graveyard/${id}/redownload`, { method: "POST" }).then(r => r.json()),
  healthCheckAvailability: (id) => authFetch(`${API_BASE}/library-health/graveyard/${id}/check-availability`, { method: "POST" }).then(r => r.json()),
  healthConfig: () => authFetch(`${API_BASE}/library-health/config`).then(r => r.json()),
  healthUpdateConfig: (data) => authFetch(`${API_BASE}/library-health/config`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),

  // Push notifications
  pushVapidKey: () => fetch(`${API_BASE}/push/vapid-key`).then(r => r.json()),
  pushSubscribe: (data) => authFetch(`${API_BASE}/push/subscribe`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  pushUnsubscribe: (data) => authFetch(`${API_BASE}/push/unsubscribe`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  pushStatus: () => authFetch(`${API_BASE}/push/status`).then(r => r.json()),
  pushTest: (data) => authFetch(`${API_BASE}/push/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),

  // History
  recHistory: (u, opts = {}) => {
    const params = new URLSearchParams({ limit: opts.limit || 50, offset: opts.offset || 0 });
    if (opts.mode) params.set("mode", opts.mode);
    if (opts.media_type) params.set("media_type", opts.media_type);
    return authFetch(`${API_BASE}/users/${u}/rec-history?${params}`).then(r => r.json());
  },
  recHistoryStats: (u) => authFetch(`${API_BASE}/users/${u}/rec-history/stats`).then(r => r.json()),
  recHistoryInteraction: (u, tmdbId, interaction) => authFetch(`${API_BASE}/users/${u}/rec-history/${tmdbId}/interaction?interaction=${interaction}`, { method: "POST" }).then(r => r.json()),

  /* Group Night sessions */
  createGroupSession: (data) => authFetch(`${API_BASE}/group-night/sessions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Create failed"); return d; })),
  getGroupSession: (code) => authFetch(`${API_BASE}/group-night/sessions/${code}`).then(r => r.json()),
  listGroupSessions: (limit = 10) => authFetch(`${API_BASE}/group-night/sessions?limit=${limit}`).then(r => r.json()),

  /* Admin user management */
  userStaleness: () => authFetch(`${API_BASE}/admin/users/staleness`).then(r => r.json()),
  warmUser: (username) => authFetch(`${API_BASE}/admin/users/${encodeURIComponent(username)}/warm`, { method: "POST" }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Warm failed"); return d; })),
};

export { api, API_BASE };

// ── Servarr Instances ───────────────────────────────────────────
const instances = {
  list: () => authFetch(`${API_BASE}/system/instances`).then(r => r.json()),
  detail: (name) => authFetch(`${API_BASE}/system/instances/${encodeURIComponent(name)}`).then(r => r.json()),
  add: (data) => authFetch(`${API_BASE}/system/instances`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Add failed"); return d; })),
  update: (name, data) => authFetch(`${API_BASE}/system/instances/${encodeURIComponent(name)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Update failed"); return d; })),
  remove: (name) => authFetch(`${API_BASE}/system/instances/${encodeURIComponent(name)}`, { method: "DELETE" }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Delete failed"); return d; })),
  test: (name) => authFetch(`${API_BASE}/system/instances/${encodeURIComponent(name)}/test`, { method: "POST" }).then(r => r.json()),
};

// ── Routing Rules ───────────────────────────────────────────────
const routing = {
  get: () => authFetch(`${API_BASE}/system/routing`).then(r => r.json()),
  update: (rules) => authFetch(`${API_BASE}/system/routing`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rules }) }).then(r => r.json().then(d => { if (!r.ok) throw new Error(d.detail || "Update failed"); return d; })),
  reset: () => authFetch(`${API_BASE}/system/routing/reset`, { method: "POST" }).then(r => r.json()),
  autoDetect: () => authFetch(`${API_BASE}/system/routing/auto-detect`, { method: "POST" }).then(r => r.json()),
  instanceInfo: () => authFetch(`${API_BASE}/system/instances`).then(r => r.json()),
};

export { instances, routing };

// ── Onboarding / Setup ──────────────────────────────────────────
const setup = {
  status: () => fetch(`${API_BASE}/setup/status`).then(r => r.json()),
  testIntegration: (data) => fetch(`${API_BASE}/setup/integrations/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }).then(r => r.json()),
  save: (settings) => authFetch(`${API_BASE}/setup/save`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ settings }) }).then(r => r.json()),
  complete: () => authFetch(`${API_BASE}/setup/complete`, { method: "POST" }).then(r => r.json()),
};

export { setup };
