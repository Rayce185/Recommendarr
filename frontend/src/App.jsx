import { useState, useEffect, useCallback, useRef } from "react";
import { Search, Film, Tv, Zap, Heart, BarChart3, Settings, Play, Download, Star, Clock, TrendingUp, Sparkles, ChevronRight, X, ExternalLink, Loader2, AlertCircle, RefreshCw, Users, Monitor, Database, Activity, CheckCircle2, XCircle, ThumbsUp, ThumbsDown, Minus, Eye, Palette, Menu, SlidersHorizontal, Save, Trash2, Bookmark, EyeOff, LogIn, LogOut, Globe, ChevronDown, Layers, RotateCcw, MapPin } from "lucide-react";

// ─── API Configuration ──────────────────────────────────────────
const API_BASE = "/api/v1";

// Token-aware fetch — attaches JWT to all API calls
let _authToken = null;
function setApiToken(token) { _authToken = token; }
function authFetch(url, opts = {}) {
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
    if (opts.hide_watched) params.set("hide_watched", "true");
    return authFetch(`${API_BASE}/recommend/${u}?${params}`).then(r => r.json());
  },
  moodPresets: () => authFetch(`${API_BASE}/mood/presets`).then(r => r.json()),
  moodParse: (q) => authFetch(`${API_BASE}/mood/parse?q=${encodeURIComponent(q)}`).then(r => r.json()),
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
    if (opts.days) params.set("days", opts.days);
    if (opts.page) params.set("page", opts.page);
    return authFetch(`${API_BASE}/discover/trending?${params}`).then(r => r.json());
  },
  trendingCountries: () => authFetch(`${API_BASE}/discover/countries`).then(r => r.json()),
  trendingProviders: (region = "CH") => authFetch(`${API_BASE}/discover/providers?country=${region}`).then(r => r.json()),
  getSchedule: (u) => authFetch(`${API_BASE}/schedule/${u}`).then(r => r.json()),
  suggestSchedule: (u, tz) => authFetch(`${API_BASE}/schedule/${u}/suggest?user_tz=${encodeURIComponent(tz)}`).then(r => r.json()),
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
  getOverrides: (u) => authFetch(`${API_BASE}/users/${u}/profile/overrides`).then(r => r.json()),
  saveOverrides: (u, data) => authFetch(`${API_BASE}/users/${u}/profile/overrides`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data)
  }).then(r => r.json()),
  similar: (id) => authFetch(`${API_BASE}/discover/similar/${id}?limit=6`).then(r => r.json()),
  genres: () => authFetch(`${API_BASE}/genres`).then(r => r.json()),
  request: (id, type) => authFetch(`${API_BASE}/request/${id}?media_type=${type || "movie"}`, {
    method: "POST",
  }).then(r => r.json()),
  userPeers: (u) => authFetch(`${API_BASE}/users/${u}/peers`).then(r => r.json()),
  submitFeedback: (u, data) => authFetch(`${API_BASE}/users/${u}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).then(r => r.json()),
  removeFeedback: (u, tmdbId) => authFetch(`${API_BASE}/users/${u}/feedback/${tmdbId}`, { method: "DELETE" }).then(r => r.json()),
  getFeedback: (u) => authFetch(`${API_BASE}/users/${u}/feedback`).then(r => r.json()),
};

// ─── Helpers ────────────────────────────────────────────────────
function fixPosterUrl(url) {
  if (!url) return null;
  const doubleHttps = url.indexOf("https://", 8);
  if (doubleHttps > 0) return url.substring(doubleHttps);
  return url;
}

function posterUrl(path, size = "w342") {
  const fixed = fixPosterUrl(path);
  if (!fixed) return null;
  if (fixed.startsWith("https://image.tmdb.org")) return fixed;
  if (fixed.startsWith("/")) return `https://image.tmdb.org/t/p/${size}${fixed}`;
  return fixed;
}

function scoreColor(score) {
  if (score >= 0.7) return "#22c55e";
  if (score >= 0.4) return "#eab308";
  return "#ef4444";
}

function scorePercent(score) {
  return Math.round(score * 100);
}

function formatHours(h) {
  if (h >= 1000) return `${(h / 1000).toFixed(1)}k hrs`;
  return `${Math.round(h)} hrs`;
}

// ─── Styles ─────────────────────────────────────────────────────
const cssText = `
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    color-scheme: dark;
    --bg-deep: #0a0b0f;
    --bg-primary: #10111a;
    --bg-surface: #181a27;
    --bg-elevated: #1e2035;
    --bg-hover: #252840;
    --border: #2a2d45;
    --border-subtle: #1e2035;
    --text-primary: #e8e9f0;
    --text-secondary: #8b8fa3;
    --text-muted: #5a5e75;
    --accent: #e5a00d;
    --accent-hover: #f0b429;
    --accent-dim: rgba(229,160,13,0.12);
    --accent-glow: rgba(229,160,13,0.25);
    --green: #22c55e;
    --green-dim: rgba(34,197,94,0.12);
    --red: #ef4444;
    --red-dim: rgba(239,68,68,0.12);
    --blue: #3b82f6;
    --blue-dim: rgba(59,130,246,0.12);
    --yellow: #eab308;
    --yellow-dim: rgba(234,179,8,0.12);
    --purple: #a855f7;
    --purple-dim: rgba(168,85,247,0.12);
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-xl: 20px;
    --shadow-card: 0 2px 12px rgba(0,0,0,0.3);
    --shadow-modal: 0 24px 80px rgba(0,0,0,0.6);
    --transition: 200ms cubic-bezier(0.4,0,0.2,1);
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }
  
  body, #root {
    font-family: 'Outfit', -apple-system, sans-serif;
    background: var(--bg-deep);
    color: var(--text-primary);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* Global dark select/option — prevents white dropdown on any <select> */
  select, select option { color-scheme: dark; background: var(--surface, #161828); color: var(--text, #e8e8f0); }
  .app-layout {
    display: flex;
    min-height: 100vh;
  }

  /* ── Sidebar ── */
  .sidebar {
    width: 240px;
    background: var(--bg-primary);
    border-right: 1px solid var(--border-subtle);
    display: flex;
    flex-direction: column;
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 40;
  }
  .sidebar-brand {
    padding: 20px 18px;
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .sidebar-brand h1 {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, var(--accent), #f0b429);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .sidebar-brand .logo-icon {
    width: 28px;
    height: 28px;
    background: linear-gradient(135deg, var(--accent), #f0b429);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--bg-deep);
    flex-shrink: 0;
  }
  .sidebar-user {
    padding: 14px 18px;
    border-bottom: 1px solid var(--border-subtle);
  }
  .sidebar-user select {
    width: 100%;
    background: var(--bg-surface);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 8px 10px;
    font-family: inherit;
    font-size: 13px;
    cursor: pointer;
    outline: none;
    transition: border-color var(--transition);
  }
  .sidebar-user select:hover { border-color: var(--accent); }
  .sidebar-user select:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
  .plex-login-btn {
    width: 100%;
    padding: 10px 14px;
    border: none;
    border-radius: 8px;
    background: #e5a00d;
    color: #000;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: background 0.2s, opacity 0.2s;
  }
  .plex-login-btn:hover:not(:disabled) { background: #f5b82e; }
  .plex-login-btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .auth-loading {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-muted);
    font-size: 0.82rem;
    padding: 4px 0;
  }
  .auth-user-info {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .auth-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
  }
  .auth-avatar-placeholder {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--accent-dim);
    color: var(--accent);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 0.9rem;
    flex-shrink: 0;
  }
  .auth-user-details {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .auth-username {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .auth-logout-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    font-size: 0.72rem;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0;
    transition: color 0.2s;
  }
  .auth-logout-btn:hover { color: var(--accent); }
  .view-as-switcher {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border-subtle);
  }
  .view-as-switcher label {
    display: block;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: 4px;
    font-weight: 600;
  }
  .view-as-switcher select {
    width: 100%;
    background: var(--bg-surface);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 6px 8px;
    font-family: inherit;
    font-size: 12px;
    cursor: pointer;
    outline: none;
    transition: border-color var(--transition);
  }
  .view-as-switcher select:hover { border-color: var(--accent); }
  .view-as-switcher select:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
  .view-as-banner {
    background: var(--accent-dim);
    color: var(--accent);
    font-size: 0.75rem;
    font-weight: 600;
    padding: 6px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border-subtle);
  }
  .view-as-banner button {
    background: none;
    border: 1px solid var(--accent);
    color: var(--accent);
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 4px;
    cursor: pointer;
    font-family: inherit;
  }
  .view-as-banner button:hover { background: var(--accent); color: var(--bg-deep); }
  .refresh-section {
    padding: 10px 12px;
    border-top: 1px solid var(--border-subtle);
  }
  .refresh-btn {
    width: 100%;
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
    color: var(--text);
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    transition: all 0.2s;
    font-family: inherit;
  }
  .refresh-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); background: var(--bg-elevated); }
  .refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }
  .refresh-btn.refreshing { border-color: var(--accent); color: var(--accent); }
  .refresh-progress {
    margin-top: 8px;
  }
  .refresh-progress-bar {
    width: 100%;
    height: 3px;
    background: var(--bg-elevated);
    border-radius: 2px;
    overflow: hidden;
    margin-bottom: 4px;
  }
  .refresh-progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .refresh-progress-label {
    font-size: 0.68rem;
    color: var(--text-muted);
    display: flex;
    justify-content: space-between;
  }
  .refresh-last {
    font-size: 0.68rem;
    color: var(--text-dim);
    margin-top: 4px;
    text-align: center;
  }
  .profile-tabs {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
  }
  .profile-tab {
    padding: 10px 18px;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--text-muted);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
    background: none;
    border-top: none;
    border-left: none;
    border-right: none;
    font-family: inherit;
  }
  .profile-tab:hover { color: var(--text); }
  .profile-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .genre-tuning-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
    border-bottom: 1px solid var(--border-subtle);
  }
  .genre-tuning-row:last-child { border-bottom: none; }
  .genre-tuning-name {
    width: 120px;
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--text);
    flex-shrink: 0;
  }
  .genre-tuning-slider {
    flex: 1;
    -webkit-appearance: none;
    appearance: none;
    height: 4px;
    border-radius: 2px;
    background: var(--bg-elevated);
    outline: none;
  }
  .genre-tuning-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: 2px solid var(--bg-deep);
  }
  .genre-tuning-value {
    width: 40px;
    text-align: center;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-muted);
    font-family: "JetBrains Mono", monospace;
  }
  .genre-tuning-block {
    padding: 3px 8px;
    font-size: 0.68rem;
    border-radius: 4px;
    cursor: pointer;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    font-family: inherit;
    transition: all 0.2s;
    flex-shrink: 0;
  }
  .genre-tuning-block.blocked { background: #ef4444; color: white; border-color: #ef4444; }
  .genre-tuning-block:hover { border-color: #ef4444; }
  .keyword-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
  }
  .keyword-chip {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.78rem;
    border: 1px solid var(--border);
    background: var(--bg-surface);
    color: var(--text);
  }
  .keyword-chip.boost { border-color: var(--green); color: var(--green); }
  .keyword-chip.block { border-color: #ef4444; color: #ef4444; }
  .keyword-chip button {
    background: none;
    border: none;
    cursor: pointer;
    color: inherit;
    padding: 0;
    display: flex;
    opacity: 0.7;
  }
  .keyword-chip button:hover { opacity: 1; }
  .keyword-add-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .keyword-add-row input {
    flex: 1;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
    color: var(--text);
    font-size: 0.82rem;
    font-family: inherit;
    outline: none;
  }
  .keyword-add-row input:focus { border-color: var(--accent); }
  .keyword-add-row button {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--bg-surface);
    color: var(--text);
    font-size: 0.78rem;
    cursor: pointer;
    font-family: inherit;
    white-space: nowrap;
  }
  .keyword-add-row button:hover { border-color: var(--accent); color: var(--accent); }
  .profile-save-bar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    padding: 12px 0;
    border-top: 1px solid var(--border-subtle);
    margin-top: 16px;
  }
  .profile-save-bar .changes-badge {
    font-size: 0.75rem;
    color: var(--accent);
    font-weight: 500;
  }
  .watchlist-disabled-hint {
    font-size: 0.7rem;
    color: var(--text-muted);
    font-style: italic;
    padding: 4px 0 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spin { animation: spin 1s linear infinite; }
  .sidebar-user label {
    display: block;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: 6px;
    font-weight: 600;
  }
  .sidebar-nav {
    flex: 1;
    padding: 10px 8px;
    overflow-y: auto;
  }
  .nav-section-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    padding: 12px 10px 6px;
    font-weight: 600;
  }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 10px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 13.5px;
    font-weight: 450;
    transition: all var(--transition);
    border: 1px solid transparent;
  }
  .nav-item:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }
  .nav-item.active {
    background: var(--accent-dim);
    color: var(--accent);
    border-color: rgba(229,160,13,0.15);
  }
  .nav-item svg { width: 17px; height: 17px; flex-shrink: 0; opacity: 0.75; }
  .nav-item.active svg { opacity: 1; }
  .sidebar-footer {
    padding: 14px 18px;
    border-top: 1px solid var(--border-subtle);
    font-size: 11px;
    color: var(--text-muted);
  }

  /* ── Main Content ── */
  .main-content {
    margin-left: 240px;
    flex: 1;
    min-height: 100vh;
    background: var(--bg-deep);
  }
  .page-header {
    padding: 28px 32px 20px;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-primary);
  }
  .page-header h2 {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .page-header p {
    color: var(--text-secondary);
    font-size: 13.5px;
    margin-top: 4px;
  }
  .page-body {
    padding: 24px 32px 40px;
  }

  /* ── Cards Grid ── */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(165px, 1fr));
    gap: 18px;
  }
  .media-card {
    cursor: pointer;
    border-radius: var(--radius-md);
    overflow: hidden;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    transition: all var(--transition);
    position: relative;
  }
  .media-card:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-card);
    border-color: var(--border);
  }
  .media-card:hover .card-overlay { opacity: 1; }
  .card-poster {
    aspect-ratio: 2/3;
    background: var(--bg-elevated);
    position: relative;
    overflow: hidden;
  }
  .card-poster img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .card-poster .no-poster {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
  }
  .card-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 50%);
    opacity: 0;
    transition: opacity var(--transition);
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: 12px;
  }
  .card-overlay .play-btn {
    background: var(--accent);
    color: var(--bg-deep);
    border: none;
    border-radius: 50%;
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: transform var(--transition);
  }
  .card-overlay .play-btn:hover { transform: scale(1.1); }
  .card-score {
    position: absolute;
    top: 8px;
    right: 8px;
    border-radius: 20px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
    background: rgba(0,0,0,0.7);
    backdrop-filter: blur(4px);
    border: 1.5px solid;
  }
  .card-badge {
    position: absolute;
    top: 8px;
    left: 8px;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .badge-library { background: var(--green-dim); color: var(--green); }
  .badge-grab { background: var(--blue-dim); color: var(--blue); }
  .badge-watched { background: rgba(255,255,255,0.12); color: var(--text-muted); }
  .badge-liked { background: rgba(34, 197, 94, 0.25); color: var(--green); }
  .badge-disliked { background: rgba(239, 68, 68, 0.25); color: var(--red); }
  .card-actions-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .card-action-btn {
    background: rgba(255,255,255,0.12);
    border: none;
    border-radius: 6px;
    width: 30px;
    height: 30px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    color: #fff;
    transition: background 0.15s;
  }
  .card-action-btn:hover { background: rgba(255,255,255,0.25); }
  .card-feedback-row {
    display: flex;
    gap: 4px;
    margin-top: 6px;
  }
  .card-fb-btn {
    background: rgba(255,255,255,0.08);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 5px;
    width: 28px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    color: rgba(255,255,255,0.5);
    transition: all 0.15s;
  }
  .card-fb-btn:hover { color: #fff; background: rgba(255,255,255,0.15); }
  .card-fb-btn.fb-up.active { background: rgba(34, 197, 94, 0.3); color: var(--green); border-color: var(--green); }
  .card-fb-btn.fb-down.active { background: rgba(239, 68, 68, 0.3); color: var(--red); border-color: var(--red); }
  .card-fb-btn.fb-dismiss.active { background: rgba(234, 179, 8, 0.3); color: var(--yellow); border-color: var(--yellow); }
  .card-info {
    padding: 10px 11px;
  }
  .card-info h3 {
    font-size: 13px;
    font-weight: 600;
    line-height: 1.3;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .card-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 3px;
    font-size: 11.5px;
    color: var(--text-secondary);
  }
  .card-meta .type-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  /* ── Loading / Empty / Error States ── */
  .state-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;
    color: var(--text-secondary);
    gap: 12px;
  }
  .state-container svg { color: var(--text-muted); }
  .state-container h3 { color: var(--text-primary); font-size: 16px; }
  .state-container p { font-size: 13px; max-width: 320px; text-align: center; }
  .spinner { animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Mood Panel ── */
  .mood-search-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
  }
  .mood-search-bar input {
    flex: 1;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 14px;
    outline: none;
    transition: border-color var(--transition);
  }
  .mood-search-bar input::placeholder { color: var(--text-muted); }
  .mood-search-bar input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
  .mood-search-bar button {
    padding: 0 20px;
    background: var(--accent);
    color: var(--bg-deep);
    border: none;
    border-radius: var(--radius-md);
    font-family: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .mood-search-bar button:hover { background: var(--accent-hover); }
  .mood-search-bar button:disabled { opacity: 0.5; cursor: not-allowed; }
  .mood-presets {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 24px;
  }
  .preset-chip {
    padding: 7px 14px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    font-size: 12.5px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all var(--transition);
    font-family: inherit;
  }
  .preset-chip:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
    border-color: var(--accent);
  }
  .preset-chip.active {
    background: var(--accent-dim);
    color: var(--accent);
    border-color: var(--accent);
  }
  .mood-explanation {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 14px 16px;
    margin-bottom: 20px;
    font-size: 13px;
    color: var(--text-secondary);
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .mood-explanation svg { color: var(--accent); flex-shrink: 0; margin-top: 1px; }

  /* ── Taste Profile ── */
  .profile-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 14px;
    margin-bottom: 28px;
  }
  .stat-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 16px;
  }
  .stat-card .stat-value {
    font-size: 26px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .stat-card .stat-label {
    font-size: 11px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 2px;
  }
  .genre-bar-container {
    margin-bottom: 10px;
  }
  .genre-bar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
    font-size: 13px;
  }
  .genre-bar-header .genre-name { font-weight: 500; }
  .genre-bar-header .genre-stats { color: var(--text-muted); font-size: 11.5px; }
  .genre-bar-track {
    height: 6px;
    background: var(--bg-elevated);
    border-radius: 3px;
    overflow: hidden;
  }
  .genre-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.6s cubic-bezier(0.4,0,0.2,1);
  }

  /* ── Admin Panel ── */
  .admin-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
  }
  .admin-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 18px;
  }
  .admin-card h4 {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .admin-card h4 svg { width: 15px; height: 15px; }

  /* Trending subtabs */
  .trending-subtabs {
    display: flex; gap: 4px; margin-bottom: 16px; padding: 4px;
    background: var(--surface); border-radius: 10px; overflow-x: auto;
  }
  .trending-subtab {
    display: flex; align-items: center; gap: 6px; padding: 8px 14px;
    border: none; border-radius: 8px; background: transparent;
    color: var(--text-secondary); font-size: 13px; font-weight: 500;
    cursor: pointer; white-space: nowrap; transition: all 0.2s;
  }
  .trending-subtab:hover { background: rgba(255,255,255,0.05); color: var(--text); }
  .trending-subtab.active { background: var(--accent); color: #fff; }
  .trending-filters {
    display: flex; gap: 12px; align-items: flex-end; margin-bottom: 16px; flex-wrap: wrap;
  }
  .filter-group { display: flex; flex-direction: column; gap: 4px; }
  .filter-group label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); font-weight: 600; }
  .filter-group select {
    padding: 7px 10px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface); color: var(--text); font-size: 13px;
    cursor: pointer; min-width: 120px;
    color-scheme: dark;
  }
  .filter-group select option { background: var(--surface); color: var(--text); }
  .filter-group select:focus { border-color: var(--accent); outline: none; }
  .provider-badge {
    display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px;
    background: var(--surface); border-radius: 8px; margin-bottom: 12px;
    font-size: 13px; color: var(--text-secondary);
  }
  /* Custom select dropdown */
  .csel { position: relative; min-width: 120px; }
  .csel-trigger {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface); color: var(--text); font-size: 13px;
    cursor: pointer; text-align: left;
  }
  .csel-trigger:hover { border-color: var(--text-secondary); }
  .csel-chev { transition: transform 0.2s; flex-shrink: 0; }
  .csel-chev.open { transform: rotate(180deg); }
  .csel-menu {
    position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 50;
    background: var(--bg-elevated, #1e2035); border: 1px solid var(--border);
    border-radius: 8px; padding: 4px; max-height: 240px; overflow-y: auto;
    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  }
  .csel-opt {
    display: flex; align-items: center; gap: 8px;
    padding: 7px 10px; border-radius: 5px; font-size: 13px;
    color: var(--text-secondary); cursor: pointer; transition: all 0.1s;
  }
  .csel-opt:hover { background: rgba(255,255,255,0.07); color: var(--text); }
  .csel-opt.active { background: var(--accent); color: #fff; }
  .csel-menu::-webkit-scrollbar { width: 6px; }
  .csel-menu::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  /* Collections */
  .coll-list { display: flex; flex-direction: column; gap: 12px; }
  .coll-card {
    background: var(--surface); border-radius: 12px; overflow: hidden;
    border: 1px solid var(--border); transition: border-color 0.2s;
  }
  .coll-card:hover { border-color: var(--accent); }
  .coll-header {
    display: flex; align-items: center; gap: 14px; padding: 14px; cursor: pointer;
  }
  .coll-poster {
    width: 50px; height: 75px; object-fit: cover; border-radius: 6px; flex-shrink: 0;
  }
  .coll-info { flex: 1; min-width: 0; }
  .coll-info h3 { margin: 0 0 6px; font-size: 15px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .coll-meta { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }
  .coll-pct { color: var(--accent); font-weight: 600; }
  .coll-bar {
    height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; margin-bottom: 6px;
  }
  .coll-bar-fill { height: 100%; background: var(--accent); border-radius: 2px; transition: width 0.5s; }
  .coll-missing-summary { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .coll-chev { transition: transform 0.2s; color: var(--text-muted); flex-shrink: 0; }
  .coll-chev.open { transform: rotate(180deg); }
  .coll-parts {
    padding: 0 14px 14px; display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 8px;
  }
  .coll-part {
    display: flex; align-items: center; gap: 10px; padding: 8px 10px;
    border-radius: 8px; background: var(--bg-elevated); cursor: pointer;
    transition: background 0.2s;
  }
  .coll-part:hover:not(.watched) { background: rgba(255,255,255,0.06); }
  .coll-part.watched { opacity: 0.5; cursor: default; }
  .coll-part-poster { width: 32px; height: 48px; object-fit: cover; border-radius: 4px; flex-shrink: 0; }
  .coll-part-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .coll-part-title { font-size: 13px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .coll-part-status { font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 4px; }
  .coll-part-score { font-size: 12px; font-weight: 600; color: var(--accent); flex-shrink: 0; }
  @media (max-width: 768px) {
    .coll-parts { grid-template-columns: 1fr; }
    .coll-poster { width: 40px; height: 60px; }
  }
  /* Settings tabs */
  .settings-tabs {
    display: flex; gap: 4px; margin-bottom: 16px; padding: 4px;
    background: var(--surface); border-radius: 10px;
  }
  .settings-tab {
    display: flex; align-items: center; gap: 6px; padding: 8px 14px;
    border: none; border-radius: 8px; background: transparent;
    color: var(--text-secondary); font-size: 13px; font-weight: 500;
    cursor: pointer; transition: all 0.2s;
  }
  .settings-tab:hover { background: rgba(255,255,255,0.05); color: var(--text); }
  .settings-tab.active { background: var(--accent); color: #fff; }
  .test-btn {
    padding: 4px 10px; border-radius: 5px; border: 1px solid var(--border);
    background: var(--surface); color: var(--text-secondary); font-size: 11px;
    cursor: pointer; display: inline-flex; align-items: center; gap: 4px; transition: all 0.15s;
  }
  .test-btn:hover { border-color: var(--accent); color: var(--accent); }
  .test-btn.testing { opacity: 0.6; pointer-events: none; }
  .test-result { font-size: 11px; margin-left: 8px; }
  .test-result.ok { color: var(--green); }
  .test-result.err { color: var(--red); }
  .service-detail { font-size: 11px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; margin-top: 2px; }
  .cache-stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 12px; }
  .cache-stat-card {
    padding: 12px; background: var(--surface); border-radius: 8px;
    border: 1px solid var(--border);
  }
  .cache-stat-card .label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .cache-stat-card .value { font-size: 20px; font-weight: 600; color: var(--text); margin-top: 4px; font-variant-numeric: tabular-nums; }
  @media (max-width: 600px) {
    .trending-subtabs { gap: 2px; }
    .trending-subtab { padding: 6px 10px; font-size: 12px; }
    .trending-filters { flex-direction: column; }
    .filter-group select { width: 100%; }
  }
  .service-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--border-subtle);
    font-size: 13px;
  }
  .service-row:last-child { border-bottom: none; }
  .service-status {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
  }
  .status-ok { color: var(--green); }
  .status-err { color: var(--red); }

  /* ── Detail Modal ── */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.75);
    backdrop-filter: blur(6px);
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    animation: fadeIn 0.2s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .modal-container {
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    max-width: 780px;
    width: 100%;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: var(--shadow-modal);
    animation: slideUp 0.25s ease;
  }
  @keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
  .modal-backdrop {
    position: relative;
    height: 260px;
    overflow: hidden;
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }
  .modal-backdrop img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .modal-backdrop .backdrop-gradient {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, var(--bg-primary) 0%, transparent 60%);
  }
  .modal-close {
    position: absolute;
    top: 14px;
    right: 14px;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: rgba(0,0,0,0.5);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.15);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background var(--transition);
    z-index: 2;
  }
  .modal-close:hover { background: rgba(0,0,0,0.7); }
  .modal-body {
    padding: 0 28px 28px;
    margin-top: -60px;
    position: relative;
  }
  .modal-top-row {
    display: flex;
    gap: 20px;
    margin-bottom: 20px;
  }
  .modal-poster {
    width: 130px;
    flex-shrink: 0;
    border-radius: var(--radius-md);
    overflow: hidden;
    box-shadow: 0 8px 30px rgba(0,0,0,0.4);
    border: 2px solid var(--border);
  }
  .modal-poster img {
    width: 100%;
    aspect-ratio: 2/3;
    object-fit: cover;
    display: block;
  }
  .modal-title-block {
    padding-top: 70px;
    flex: 1;
    min-width: 0;
  }
  .modal-title-block h2 {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  .modal-title-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 6px;
    font-size: 13px;
    color: var(--text-secondary);
    flex-wrap: wrap;
  }
  .modal-title-meta .sep { color: var(--text-muted); }
  .modal-genres {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }
  .genre-tag {
    padding: 3px 10px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 20px;
    font-size: 11.5px;
    color: var(--text-secondary);
  }
  .modal-overview {
    font-size: 14px;
    line-height: 1.65;
    color: var(--text-secondary);
    margin-bottom: 20px;
  }
  .modal-explanation {
    background: var(--accent-dim);
    border: 1px solid rgba(229,160,13,0.2);
    border-radius: var(--radius-md);
    padding: 12px 16px;
    margin-bottom: 20px;
    font-size: 13px;
    color: var(--accent);
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .modal-explanation svg { flex-shrink: 0; margin-top: 1px; }

  .modal-collection-badge {
    display: flex; align-items: center; gap: 8px; padding: 8px 12px;
    background: color-mix(in srgb, var(--accent) 12%, transparent); border-radius: 8px;
    font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; flex-wrap: wrap;
  }
  .modal-collection-badge svg { color: var(--accent); flex-shrink: 0; }
  .coll-name { color: var(--text-primary); font-weight: 600; }
  .coll-progress { color: var(--text-muted); font-size: 12px; }
  .coll-bar { flex: 1; min-width: 60px; height: 4px; background: var(--bg-elevated); border-radius: 2px; }
  .coll-bar-fill { height: 100%; background: var(--accent); border-radius: 2px; transition: width 0.3s; }

  .modal-collection-missing { margin-top: 16px; }
  .modal-collection-missing h4 {
    display: flex; align-items: center; gap: 6px; font-size: 14px;
    color: var(--text-secondary); margin: 0 0 10px 0; font-weight: 600;
  }
  .modal-collection-missing h4 svg { color: var(--accent); }
  .coll-missing-grid { display: flex; flex-direction: column; gap: 8px; }
  .coll-missing-item {
    display: flex; align-items: center; gap: 10px; padding: 8px;
    background: var(--bg-elevated); border-radius: 8px;
  }
  .coll-missing-item img { width: 40px; height: 60px; object-fit: cover; border-radius: 4px; flex-shrink: 0; }
  .coll-missing-noposter { width: 40px; height: 60px; background: var(--surface); border-radius: 4px; flex-shrink: 0; }
  .coll-missing-info { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .coll-missing-title { font-size: 13px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .coll-missing-year { font-size: 11px; color: var(--text-muted); }
  .btn-sm { padding: 4px 10px; font-size: 11px; gap: 4px; }

  .watchlist-subtabs {
    display: flex; gap: 4px; padding: 0 24px; margin-bottom: 16px;
  }
  .wl-subtab {
    padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 500;
    background: var(--bg-elevated); color: var(--text-secondary); border: none; cursor: pointer;
    display: flex; align-items: center; gap: 6px; transition: all 0.15s;
  }
  .wl-subtab:hover { background: var(--surface); color: var(--text-primary); }
  .wl-subtab.active { background: var(--accent); color: #000; }
  .wl-count { font-size: 11px; opacity: 0.7; }

  .library-badge {
    position: absolute; top: 6px; left: 6px; font-size: 9px; font-weight: 700;
    padding: 2px 6px; border-radius: 4px; background: var(--green); color: #000;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .watched-badge {
    position: absolute; top: 6px; right: 6px; font-size: 9px; font-weight: 600;
    padding: 2px 6px; border-radius: 4px; background: rgba(0,0,0,0.7); color: var(--text-muted);
    display: flex; align-items: center; gap: 3px;
  }
  .dismiss-btn { background: rgba(239, 68, 68, 0.3) !important; }
  .dismiss-btn:hover { background: rgba(239, 68, 68, 0.5) !important; }

  .settings-device-section { margin-top: 16px; padding: 12px; background: var(--bg-elevated); border-radius: 8px; }
  .settings-device-section h4 { font-size: 14px; margin: 0 0 8px 0; display: flex; align-items: center; gap: 6px; }
  .settings-device-section h4 svg { color: var(--accent); }
  .device-select { width: 100%; padding: 8px 10px; border-radius: 6px; background: var(--surface); color: var(--text-primary); border: 1px solid var(--border); font-size: 13px; }

  .global-prefs-section { margin-top: 20px; }
  .global-prefs-section h4 { font-size: 14px; margin: 0 0 12px 0; display: flex; align-items: center; gap: 6px; }
  .pref-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); }
  .pref-row:last-child { border-bottom: none; }
  .pref-label { font-size: 13px; color: var(--text-primary); }
  .pref-source { font-size: 10px; padding: 1px 6px; border-radius: 10px; margin-left: 6px; }
  .pref-source.user { background: var(--accent); color: #000; }
  .pref-source.global { background: var(--blue); color: #fff; }
  .pref-source.default { background: var(--bg-elevated); color: var(--text-muted); }
  .pref-control { display: flex; align-items: center; gap: 8px; }
  .pref-control input[type="range"] { width: 80px; }
  .pref-control select { padding: 4px 8px; font-size: 12px; }
  .modal-score-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 20px;
  }
  .score-pill {
    padding: 4px 10px;
    background: var(--bg-elevated);
    border-radius: 20px;
    font-size: 11.5px;
    color: var(--text-secondary);
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .score-pill .score-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .modal-trailer {
    border-radius: var(--radius-md);
    overflow: hidden;
    margin-bottom: 20px;
    aspect-ratio: 16/9;
  }
  .modal-trailer iframe {
    width: 100%;
    height: 100%;
    border: none;
  }
  .modal-keywords {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-bottom: 20px;
  }
  .keyword-tag {
    padding: 2px 8px;
    background: var(--bg-surface);
    border-radius: 4px;
    font-size: 11px;
    color: var(--text-muted);
  }
  .modal-actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
  .btn {
    padding: 10px 20px;
    border-radius: var(--radius-md);
    font-family: inherit;
    font-size: 13.5px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all var(--transition);
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .btn svg { width: 16px; height: 16px; }
  .btn-primary {
    background: var(--accent);
    color: var(--bg-deep);
  }
  .btn-primary:hover { background: var(--accent-hover); }
  .btn-secondary {
    background: var(--bg-elevated);
    color: var(--text-primary);
    border: 1px solid var(--border);
  }
  .btn-secondary:hover { background: var(--bg-hover); }
  .btn-success {
    background: var(--green);
    color: white;
  }
  .btn-danger {
    background: var(--red-dim);
    color: var(--red);
    border: 1px solid rgba(239,68,68,0.2);
  }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .toast-container {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 200;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .toast {
    padding: 12px 18px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    font-size: 13px;
    box-shadow: var(--shadow-card);
    display: flex;
    align-items: center;
    gap: 8px;
    animation: slideIn 0.3s ease;
    max-width: 360px;
  }
  @keyframes slideIn { from { transform: translateX(40px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
  .toast-success { border-color: var(--green); }
  .toast-error { border-color: var(--red); }

  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  .section-header h3 {
    font-size: 16px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .section-header h3 svg { width: 18px; height: 18px; color: var(--accent); }
  .section-divider {
    margin: 32px 0 24px;
    border: none;
    border-top: 1px solid var(--border-subtle);
  }

  /* Scrollbar */
  /* Filter Panel */
  .filter-panel { position: relative; margin-bottom: 16px; }
  .filter-badge {
    background: var(--accent);
    color: white;
    border-radius: 10px;
    padding: 0 6px;
    font-size: 11px;
    font-weight: 600;
    min-width: 18px;
    text-align: center;
  }
  .filter-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-top: 8px;
    z-index: 50;
    max-height: 70vh;
    overflow-y: auto;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  .filter-section { margin-bottom: 16px; }
  .filter-section-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }
  .filter-chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .filter-chip {
    padding: 4px 10px;
    border-radius: 16px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    transition: all 0.15s;
  }
  .filter-chip:hover { border-color: var(--text-secondary); }
  .filter-chip.chip-exclude {
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.5);
    color: #ef4444;
  }
  .filter-chip.chip-include {
    background: rgba(34, 197, 94, 0.15);
    border-color: rgba(34, 197, 94, 0.5);
    color: #22c55e;
  }
  .filter-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  .filter-preset-input {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    color: var(--text);
    flex: 1;
    min-width: 0;
  }
  .filter-preset-input::placeholder { color: var(--text-muted); }
  .filter-presets { display: flex; flex-wrap: wrap; gap: 6px; }
  .preset-row { display: flex; align-items: center; gap: 2px; }
  .preset-btn {
    padding: 4px 10px;
    border-radius: 16px;
    border: 1px solid var(--accent);
    background: rgba(136, 107, 255, 0.1);
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
  }
  .preset-btn:hover { background: rgba(136, 107, 255, 0.25); }
  .preset-delete {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 2px;
    opacity: 0.5;
  }
  .preset-delete:hover { opacity: 1; color: #ef4444; }

  @media (max-width: 768px) {
    .filter-dropdown { left: 0; right: 0; }
    .filter-actions { flex-direction: column; }
  }

  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  .spinning { animation: spin 1s linear infinite; }

  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

  /* ── Mobile Hamburger Button ── */
  .mobile-menu-btn {
    display: none;
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 60;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 8px;
    color: var(--text-primary);
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .mobile-menu-btn svg { display: block; }

  /* ── Mobile Overlay ── */
  .sidebar-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    z-index: 35;
    -webkit-tap-highlight-color: transparent;
  }

  /* ── Mobile Responsive ── */
  @media (max-width: 768px) {
    .mobile-menu-btn { display: block; }
    .sidebar-overlay.open { display: block; }

    .sidebar {
      transform: translateX(-100%);
      transition: transform 0.25s ease;
    }
    .sidebar.open {
      transform: translateX(0);
    }

    .main-content {
      margin-left: 0 !important;
      width: 100%;
    }
    .page-header {
      padding: 16px 16px 14px;
      padding-top: 56px;
    }
    .page-body {
      padding: 16px 12px 32px;
    }
    .card-grid {
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 12px;
    }

    /* Modal responsive */
    .modal-overlay .modal-content {
      width: 95vw;
      max-height: 90vh;
      margin: 5vh auto;
    }
    .modal-body {
      flex-direction: column !important;
    }
    .modal-poster {
      width: 100% !important;
      max-height: 260px !important;
    }

    /* Taste profile responsive */
    .profile-grid, .stat-grid {
      grid-template-columns: 1fr !important;
    }
  }
`;

// ─── Components ─────────────────────────────────────────────────

// ─── Custom Select (dark dropdown) ──────────────────────────────
function CustomSelect({ value, onChange, options, placeholder }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const selected = options.find(o => String(o.value) === String(value));

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div className="csel" ref={ref}>
      <button className="csel-trigger" onClick={() => setOpen(!open)} type="button">
        <span>{selected ? selected.label : placeholder || "Select..."}</span>
        <ChevronDown size={13} className={open ? "csel-chev open" : "csel-chev"} />
      </button>
      {open && (
        <div className="csel-menu">
          {options.map(o => (
            <div key={o.value} className={`csel-opt ${String(o.value) === String(value) ? "active" : ""}`}
              onClick={() => { onChange(o.value); setOpen(false); }}>
              {o.logo && <img src={o.logo} alt="" style={{ width: 18, height: 18, borderRadius: 3 }} />}
              {o.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function LoadingState({ message = "Loading..." }) {
  return (
    <div className="state-container">
      <Loader2 size={32} className="spinner" />
      <p>{message}</p>
    </div>
  );
}

function EmptyState({ icon: Icon = Film, title, message }) {
  return (
    <div className="state-container">
      <Icon size={40} />
      <h3>{title || "Nothing here"}</h3>
      <p>{message || "No results to display."}</p>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="state-container">
      <AlertCircle size={40} />
      <h3>Something went wrong</h3>
      <p>{message}</p>
      {onRetry && (
        <button className="btn btn-secondary" onClick={onRetry} style={{ marginTop: 8 }}>
          <RefreshCw size={14} /> Retry
        </button>
      )}
    </div>
  );
}

function MediaCard({ item, onClick, onFeedback }) {
  const poster = posterUrl(item.poster_url);
  const sc = item.score != null ? scorePercent(item.score) : null;
  const typeColor = item.media_type === "movie" ? "var(--blue)" : "var(--purple)";

  return (
    <div className="media-card" onClick={() => onClick(item)}>
      <div className="card-poster">
        {poster ? (
          <img src={poster} alt={item.title} loading="lazy" />
        ) : (
          <div className="no-poster"><Film size={32} /></div>
        )}
        <div className="card-overlay">
          <div className="card-actions-row">
            {item.plex_url && (
              <button className="card-action-btn plex-btn" title="Play in Plex" onClick={(e) => { e.stopPropagation(); window.open(item.plex_url, "_blank"); }}>
                <Play size={14} fill="currentColor" />
              </button>
            )}
            {!item.in_library && item.tmdb_id && (
              <button className="card-action-btn seerr-btn" title="Add to Library" onClick={async (e) => {
                e.stopPropagation();
                const btn = e.target.closest(".card-action-btn");
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border:2px solid transparent;border-top-color:currentColor;border-radius:50%;animation:spin .6s linear infinite;display:inline-block"></span>';
                try {
                  const res = await api.addToLibrary(item.tmdb_id, item.media_type || "movie");
                  btn.style.background = "var(--green)";
                  btn.innerHTML = res.already_exists ? "✓" : "✓";
                  btn.title = res.message;
                } catch (err) {
                  btn.style.background = "var(--red)";
                  btn.innerHTML = "✗";
                  btn.title = err.message;
                }
              }}>
                <Download size={14} />
              </button>
            )}
            <button className="card-action-btn watchlist-btn" title="Add to Plex Watchlist" onClick={(e) => {
              e.stopPropagation();
              api.watchlistAdd(item.tmdb_id, item.media_type || "movie").then(() => {
                e.target.closest(".card-action-btn").style.background = "var(--green)";
              });
            }}>
              <Bookmark size={14} />
            </button>
            <button className="card-action-btn info-btn" title="Details" onClick={(e) => { e.stopPropagation(); onClick(item); }}>
              <ExternalLink size={14} />
            </button>
          </div>
          {onFeedback && (
            <div className="card-feedback-row">
              <button
                className={`card-fb-btn fb-up ${item.user_feedback === "up" ? "active" : ""}`}
                title="Like — recommend more like this"
                onClick={(e) => { e.stopPropagation(); onFeedback(item, item.user_feedback === "up" ? null : "up"); }}
              ><ThumbsUp size={13} /></button>
              <button
                className={`card-fb-btn fb-down ${item.user_feedback === "down" ? "active" : ""}`}
                title="Dislike — recommend less like this"
                onClick={(e) => { e.stopPropagation(); onFeedback(item, item.user_feedback === "down" ? null : "down"); }}
              ><ThumbsDown size={13} /></button>
              <button
                className={`card-fb-btn fb-dismiss ${item.user_feedback === "dismiss" ? "active" : ""}`}
                title="Dismiss — hide this recommendation"
                onClick={(e) => { e.stopPropagation(); onFeedback(item, "dismiss"); }}
              ><EyeOff size={13} /></button>
            </div>
          )}
        </div>
        {sc != null && (
          <div className="card-score" style={{ color: scoreColor(item.score), borderColor: scoreColor(item.score) }}>
            {sc}%
          </div>
        )}
        {item.user_feedback === "up" && <div className="card-badge badge-liked"><ThumbsUp size={10} /></div>}
        {item.user_feedback === "down" && <div className="card-badge badge-disliked"><ThumbsDown size={10} /></div>}
        {item.is_watched && <div className="card-badge badge-watched"><Eye size={10} /> Seen</div>}
        {item.in_library === true && !item.is_watched && <div className="card-badge badge-library">In Library</div>}
        {item.in_library === false && <div className="card-badge badge-grab">Not in Library</div>}
      </div>
      <div className="card-info">
        <h3>{item.title}</h3>
        <div className="card-meta">
          <span className="type-dot" style={{ background: typeColor }} />
          <span>{item.media_type === "movie" ? "Movie" : "Series"}</span>
          {item.year && <><span>·</span><span>{item.year}</span></>}
        </div>
      </div>
    </div>
  );
}

function DetailModal({ item, detail, onClose, onRequest, requesting, requestResult, onFeedback, user }) {
  const d = detail || item;
  const poster = posterUrl(d.poster_url || item.poster_url, "w500");
  const backdrop = d.backdrop_url ? fixPosterUrl(d.backdrop_url) : null;
  const hasTrailer = d.trailer_url;
  const [collectionData, setCollectionData] = useState(null);
  const [collLoading, setCollLoading] = useState(false);
  const [collRequestingId, setCollRequestingId] = useState(null);

  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Fetch collection info for movies
  useEffect(() => {
    const tmdbId = d.tmdb_id || item.tmdb_id;
    const mediaType = item.media_type || d.media_type;
    if (mediaType !== "movie" || !tmdbId) return;
    setCollLoading(true);
    api.collectionFor(tmdbId)
      .then(data => setCollectionData(data))
      .catch(() => setCollectionData(null))
      .finally(() => setCollLoading(false));
  }, [d.tmdb_id, item.tmdb_id]);

  const handleCollectionRequest = async (partTmdbId) => {
    setCollRequestingId(partTmdbId);
    try {
      await api.addToLibrary(partTmdbId, "movie");
      setCollectionData(prev => prev ? {
        ...prev,
        parts: prev.parts.map(p => p.tmdb_id === partTmdbId ? { ...p, requested: true } : p),
        missing: prev.missing.map(p => p.tmdb_id === partTmdbId ? { ...p, requested: true } : p),
      } : null);
    } catch (e) { console.error("Collection request failed:", e); }
    setCollRequestingId(null);
  };

  const breakdownLabels = { genre: "Genre", keyword: "Keyword", rating: "Rating", personnel: "Cast/Crew", popularity: "Popular", mood: "Mood" };

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-container">
        <div className="modal-backdrop">
          {backdrop ? <img src={backdrop} alt="" /> : <div style={{ background: "var(--bg-elevated)", height: "100%" }} />}
          <div className="backdrop-gradient" />
          <button className="modal-close" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="modal-body">
          <div className="modal-top-row">
            <div className="modal-poster">
              {poster ? <img src={poster} alt={d.title} /> : <div style={{ background: "var(--bg-elevated)", aspectRatio: "2/3" }} />}
            </div>
            <div className="modal-title-block">
              <h2>{d.title}</h2>
              <div className="modal-title-meta">
                {d.year && <span>{d.year}</span>}
                {d.runtime && <><span className="sep">·</span><span>{d.runtime} min</span></>}
                {d.vote_average && <><span className="sep">·</span><span>★ {d.vote_average.toFixed(1)}</span></>}
                {d.media_type && <><span className="sep">·</span><span>{d.media_type === "movie" ? "Movie" : "Series"}</span></>}
              </div>
              <div className="modal-genres">
                {(d.genres || []).slice(0, 6).map((g, i) => <span className="genre-tag" key={i}>{typeof g === 'string' ? g : g.name}</span>)}
              </div>
            </div>
          </div>

          {collectionData && (
            <div className="modal-collection-badge">
              <Layers size={15} />
              <span className="coll-name">{collectionData.name}</span>
              <span className="coll-progress">{collectionData.watched_count}/{collectionData.total_parts} watched</span>
              <div className="coll-bar"><div className="coll-bar-fill" style={{ width: `${collectionData.completion_pct}%` }} /></div>
            </div>
          )}

          {item.explanation && (
            <div className="modal-explanation">
              <Sparkles size={16} />
              <span>{item.explanation}</span>
            </div>
          )}

          {item.score_breakdown && (
            <div className="modal-score-row">
              {Object.entries(item.score_breakdown).map(([key, val]) => (
                <div className="score-pill" key={key}>
                  <span className="score-dot" style={{ background: val > 0.5 ? "var(--green)" : val > 0 ? "var(--accent)" : "var(--text-muted)" }} />
                  {breakdownLabels[key] || key}: {Math.round(val * 100)}%
                </div>
              ))}
            </div>
          )}

          {d.overview && <p className="modal-overview">{d.overview}</p>}

          {hasTrailer && (
            <div className="modal-trailer">
              <iframe src={d.trailer_url} allow="autoplay; encrypted-media" allowFullScreen title="Trailer" />
            </div>
          )}

          {d.keywords && d.keywords.length > 0 && (
            <div className="modal-keywords">
              {d.keywords.slice(0, 15).map((kw, i) => <span className="keyword-tag" key={i}>{typeof kw === 'string' ? kw : kw.name}</span>)}
            </div>
          )}

          {(d.directors?.length > 0 || d.cast?.length > 0) && (
            <div style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 20 }}>
              {d.directors?.length > 0 && <div><strong>Director:</strong> {d.directors.join(", ")}</div>}
              {d.cast?.length > 0 && <div style={{ marginTop: 4 }}><strong>Cast:</strong> {d.cast.slice(0, 5).map(c => typeof c === "string" ? c : c.name || c.character || "").filter(Boolean).join(", ")}</div>}
            </div>
          )}

          {/* Watched / In Library badge */}
          {(item.in_library === true || d.in_library === true) && (
            <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 8, background: "rgba(46,204,113,0.12)", border: "1px solid rgba(46,204,113,0.3)", color: "#2ecc71", fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
              <CheckCircle2 size={14} /> In Your Library
            </div>
          )}

          {/* Feedback buttons */}
          {onFeedback && (
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button className={`btn btn-sm ${item.user_feedback === "up" ? "btn-success" : "btn-secondary"}`}
                onClick={() => onFeedback(item, item.user_feedback === "up" ? null : "up")}
                style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 14px", fontSize: 13 }}>
                <ThumbsUp size={14} /> {item.user_feedback === "up" ? "Liked" : "Like"}
              </button>
              <button className={`btn btn-sm ${item.user_feedback === "down" ? "btn-danger" : "btn-secondary"}`}
                onClick={() => onFeedback(item, item.user_feedback === "down" ? null : "down")}
                style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 14px", fontSize: 13, ...(item.user_feedback === "down" ? { background: "rgba(231,76,60,0.15)", borderColor: "rgba(231,76,60,0.3)", color: "#e74c3c" } : {}) }}>
                <ThumbsDown size={14} /> {item.user_feedback === "down" ? "Disliked" : "Dislike"}
              </button>
            </div>
          )}

          <div className="modal-actions">
            {(item.in_library === true || d.in_library === true) && (item.plex_url || d.plex_url) && (
              <button className="btn btn-primary" onClick={() => window.open(item.plex_url || d.plex_url, "_blank")}>
                <Play size={15} /> Play on Plex
              </button>
            )}
            {/* Add to Library — show unless explicitly in library */}
            {item.in_library !== true && d.in_library !== true && (
              <button
                className={`btn ${requestResult?.success ? "btn-success" : "btn-primary"}`}
                onClick={() => onRequest(d.tmdb_id || item.tmdb_id, item.media_type)}
                disabled={requesting || requestResult?.success}
              >
                {requesting ? <><Loader2 size={15} className="spinner" /> Adding...</> :
                 requestResult?.success ? <><CheckCircle2 size={15} /> {requestResult.already_exists ? "Already in Library" : "Added!"}</> :
                 <><Download size={15} /> Add to Library</>}
              </button>
            )}
            <button className="btn btn-secondary watchlist-modal-btn" onClick={() => {
              api.watchlistAdd(d.tmdb_id || item.tmdb_id, item.media_type || "movie").then(() => {
                const btn = document.querySelector(".watchlist-modal-btn");
                if (btn) { btn.innerHTML = "✓ Added!"; btn.disabled = true; btn.classList.add("btn-success"); }
              });
            }}>
              <Bookmark size={15} /> Plex Watchlist
            </button>
            <button className="btn btn-secondary" onClick={() => window.open(`https://www.themoviedb.org/${item.media_type || "movie"}/${d.tmdb_id || item.tmdb_id}`, "_blank")}>
              <ExternalLink size={15} /> TMDB
            </button>
          </div>

          {collectionData && collectionData.missing.length > 0 && (
            <div className="modal-collection-missing">
              <h4><Layers size={14} /> Missing from {collectionData.name}</h4>
              <div className="coll-missing-grid">
                {collectionData.missing.map(p => (
                  <div className="coll-missing-item" key={p.tmdb_id}>
                    {p.poster_url ? <img src={p.poster_url} alt={p.title} /> : <div className="coll-missing-noposter" />}
                    <div className="coll-missing-info">
                      <span className="coll-missing-title">{p.title}</span>
                      <span className="coll-missing-year">{p.year || "TBA"}{p.vote_average ? ` · ★ ${p.vote_average.toFixed(1)}` : ""}</span>
                    </div>
                    <button
                      className={`btn btn-sm ${p.requested ? "btn-success" : "btn-primary"}`}
                      onClick={() => handleCollectionRequest(p.tmdb_id)}
                      disabled={collRequestingId === p.tmdb_id || p.requested || p.in_library}
                    >
                      {p.in_library ? <><CheckCircle2 size={12} /> In Library</> :
                       p.requested ? <><CheckCircle2 size={12} /> Requested</> :
                       collRequestingId === p.tmdb_id ? <Loader2 size={12} className="spinner" /> :
                       <><Download size={12} /> Request</>}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Filter Panel ──────────────────────────────────────────────

const FILTER_STORAGE_KEY = "recommendarr_filters";
const PRESET_STORAGE_KEY = "recommendarr_filter_presets";

function loadSavedFilters() {
  try { return JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY)) || {}; }
  catch { return {}; }
}

function saveFilters(filters) {
  localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
}

function loadPresets() {
  try { return JSON.parse(localStorage.getItem(PRESET_STORAGE_KEY)) || []; }
  catch { return []; }
}

function savePresets(presets) {
  localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(presets));
}

function FilterPanel({ filters, onChange, onApply }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState({ genres: [], libraries: [] });
  const [presets, setPresets] = useState(loadPresets);
  const [presetName, setPresetName] = useState("");

  useEffect(() => {
    api.filterOptions().then(setOptions).catch(() => {});
  }, []);

  const toggle = (set, item) => {
    const next = new Set(set);
    next.has(item) ? next.delete(item) : next.add(item);
    return [...next];
  };

  const activeCount = (filters.excludeGenres?.length || 0)
    + (filters.includeGenres?.length || 0)
    + (filters.excludeLibraries?.length || 0);

  const handleSavePreset = () => {
    if (!presetName.trim()) return;
    const next = [...presets, { name: presetName.trim(), filters: { ...filters } }];
    setPresets(next);
    savePresets(next);
    setPresetName("");
  };

  const handleLoadPreset = (preset) => {
    onChange(preset.filters);
    onApply(preset.filters);
  };

  const handleDeletePreset = (idx) => {
    const next = presets.filter((_, i) => i !== idx);
    setPresets(next);
    savePresets(next);
  };

  const handleClear = () => {
    const empty = { excludeGenres: [], includeGenres: [], excludeLibraries: [] };
    onChange(empty);
    onApply(empty);
  };

  return (
    <div className="filter-panel">
      <button
        className={`btn ${activeCount > 0 ? "btn-primary" : "btn-secondary"}`}
        style={{ fontSize: 13, padding: "6px 12px", display: "flex", alignItems: "center", gap: 6 }}
        onClick={() => setOpen(!open)}
      >
        <SlidersHorizontal size={14} />
        Filters {activeCount > 0 && <span className="filter-badge">{activeCount}</span>}
      </button>

      {open && (
        <div className="filter-dropdown">
          {/* Presets */}
          {presets.length > 0 && (
            <div className="filter-section">
              <div className="filter-section-title">Saved Presets</div>
              <div className="filter-presets">
                {presets.map((p, i) => (
                  <div key={i} className="preset-row">
                    <button className="preset-btn" onClick={() => handleLoadPreset(p)}>
                      {p.name}
                    </button>
                    <button className="preset-delete" onClick={() => handleDeletePreset(i)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Exclude Libraries */}
          <div className="filter-section">
            <div className="filter-section-title">Exclude Libraries</div>
            <div className="filter-chips">
              {options.libraries.map(lib => {
                const active = (filters.excludeLibraries || []).includes(lib.title);
                return (
                  <button
                    key={lib.key}
                    className={`filter-chip ${active ? "chip-exclude" : ""}`}
                    onClick={() => {
                      const next = { ...filters, excludeLibraries: toggle(new Set(filters.excludeLibraries || []), lib.title) };
                      onChange(next);
                    }}
                  >
                    {active && <XCircle size={12} />} {lib.title}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Exclude Genres */}
          <div className="filter-section">
            <div className="filter-section-title">Exclude Genres</div>
            <div className="filter-chips">
              {options.genres.map(g => {
                const active = (filters.excludeGenres || []).includes(g);
                return (
                  <button
                    key={g}
                    className={`filter-chip ${active ? "chip-exclude" : ""}`}
                    onClick={() => {
                      const next = { ...filters, excludeGenres: toggle(new Set(filters.excludeGenres || []), g) };
                      onChange(next);
                    }}
                  >
                    {active && <XCircle size={12} />} {g}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Include Genres (Only) */}
          <div className="filter-section">
            <div className="filter-section-title">Only These Genres <span style={{fontSize:11,opacity:0.6}}>(empty = all)</span></div>
            <div className="filter-chips">
              {options.genres.map(g => {
                const active = (filters.includeGenres || []).includes(g);
                return (
                  <button
                    key={g}
                    className={`filter-chip ${active ? "chip-include" : ""}`}
                    onClick={() => {
                      const next = { ...filters, includeGenres: toggle(new Set(filters.includeGenres || []), g) };
                      onChange(next);
                    }}
                  >
                    {active && <CheckCircle2 size={12} />} {g}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Watched Toggle */}
          <div className="filter-section">
            <div className="filter-section-title">Watched Status</div>
            <div className="filter-chips">
              <button
                className={`filter-chip ${filters.hideWatched ? "chip-exclude" : ""}`}
                onClick={() => {
                  const next = { ...filters, hideWatched: !filters.hideWatched };
                  onChange(next);
                }}
              >
                {filters.hideWatched ? <><EyeOff size={12} /> Hiding watched</> : <><Eye size={12} /> Showing all</>}
              </button>
            </div>
          </div>

          {/* Actions */}
          <div className="filter-actions">
            <div style={{ display: "flex", gap: 6, flex: 1 }}>
              <input
                className="filter-preset-input"
                placeholder="Preset name..."
                value={presetName}
                onChange={e => setPresetName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSavePreset()}
              />
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={handleSavePreset} disabled={!presetName.trim()}>
                <Save size={12} /> Save
              </button>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={handleClear}>
                Clear All
              </button>
              <button className="btn btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { saveFilters(filters); onApply(filters); setOpen(false); }}>
                Apply
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Page: Recommendations (Tonight / Grab / Rediscover) ────────
function RecommendationsPage({ user, mode, onCardClick }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [cached, setCached] = useState(false);
  const [cacheAge, setCacheAge] = useState(null); // seconds
  const [profileModifiedAt, setProfileModifiedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [filters, setFilters] = useState(loadSavedFilters);

  const modeConfig = {
    tonight: { title: "Watch Tonight", desc: "In your library, matched to your taste", icon: Play },
    grab: { title: "Worth Grabbing", desc: "Not in your library yet — request via Seerr", icon: Download },
    rediscover: { title: "Rediscover", desc: "Rewatchable favorites from your history", icon: RefreshCw },
  };
  const cfg = modeConfig[mode] || modeConfig.tonight;

  const load = useCallback((forceRefresh = false, filterOverride = null) => {
    if (!user) return;
    if (forceRefresh) setRefreshing(true); else setLoading(true);
    setError(null);
    const f = filterOverride || filters;
    const opts = { limit: 30, refresh: forceRefresh || undefined };
    if (f.excludeGenres?.length) opts.exclude_genres = f.excludeGenres.join(",");
    if (f.includeGenres?.length) opts.include_genres = f.includeGenres.join(",");
    if (f.excludeLibraries?.length) opts.exclude_libraries = f.excludeLibraries.join(",");
    if (f.hideWatched) opts.hide_watched = true;
    api.recommend(user, mode, opts)
      .then(data => {
        const recs = data.recommendations || [];
        setItems(recs);
        setCached(data.meta?.cached || false);
        setCacheAge(data.meta?.cache_age_seconds || null);
        setProfileModifiedAt(data.meta?.profile_modified_at || null);
        // Lazy-load AI explanations if missing
        if (recs.length > 0 && !recs[0]?.explanation) {
          api.lazyExplain(user, mode).then(res => {
            if (res.status === "explained") {
              // Re-fetch from cache (now has explanations)
              api.recommend(user, mode, { ...opts, refresh: undefined })
                .then(d2 => { if (d2.recommendations?.length) setItems(d2.recommendations); });
            }
          }).catch(() => {}); // Non-fatal
        }
      })
      .catch(err => setError(err.message))
      .finally(() => { setLoading(false); setRefreshing(false); });
  }, [user, mode, filters]);

  useEffect(() => { load(); }, [load]);

  const handleFeedback = useCallback(async (item, action) => {
    if (action === null) {
      // Toggle off — remove feedback
      setItems(prev => prev.map(it => it.tmdb_id === item.tmdb_id ? { ...it, user_feedback: null } : it));
      try {
        await authFetch(`${API_BASE}/users/${user}/feedback/${item.tmdb_id}`, { method: "DELETE" });
      } catch (e) {}
      return;
    }
    // Optimistic update
    if (action === "dismiss") {
      setItems(prev => prev.filter(it => it.tmdb_id !== item.tmdb_id));
    } else {
      setItems(prev => prev.map(it => it.tmdb_id === item.tmdb_id ? { ...it, user_feedback: action } : it));
    }
    try {
      await api.submitFeedback(user, {
        tmdb_id: item.tmdb_id,
        media_type: item.media_type || "movie",
        action,
        title: item.title || "",
        genres: item.genres || [],
        keywords: item.keywords || [],
      });
    } catch (e) {
      // Revert on error
      if (action === "dismiss") load();
    }
  }, [user, load]);

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2>{cfg.title}</h2>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {cached && cacheAge != null && (
              <span style={{ fontSize: 11, color: "var(--text-muted)", opacity: 0.7 }}>
                Updated {cacheAge < 60 ? "just now" : `${Math.floor(cacheAge / 60)} min ago`}
              </span>
            )}
            {profileModifiedAt && cached && cacheAge != null && (() => {
              const modTime = new Date(profileModifiedAt).getTime();
              const recsTime = Date.now() - (cacheAge * 1000);
              return modTime > recsTime;
            })() && (
              <span style={{ fontSize: 11, color: "#eab308", fontWeight: 500, display: "flex", alignItems: "center", gap: 3 }}>
                <AlertCircle size={12} /> Profile changed — refresh recommended
              </span>
            )}
            <button
              className="btn btn-secondary"
              style={{ padding: "6px 10px", fontSize: 12 }}
              onClick={() => load(true)}
              disabled={refreshing}
              title="Force refresh recommendations"
            >
              <RefreshCw size={14} className={refreshing ? "spinning" : ""} /> {refreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
        <p>{cfg.desc}</p>
      </div>
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        onApply={(f) => { setFilters(f); saveFilters(f); load(true, f); }}
      />
      <div className="page-body">
        {loading ? <LoadingState message={`Finding ${mode === 'grab' ? 'new releases' : 'recommendations'}...`} /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         items.length === 0 ? <EmptyState icon={cfg.icon} title="No recommendations" message={`No ${mode} picks found for this user.`} /> :
         <div className="card-grid">
           {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={item} onClick={onCardClick} onFeedback={handleFeedback} />)}
         </div>}
      </div>
    </>
  );
}

// ─── Page: Mood Match ───────────────────────────────────────────
function MoodPage({ user, onCardClick }) {
  const [presets, setPresets] = useState([]);
  const [query, setQuery] = useState("");
  const [activePreset, setActivePreset] = useState(null);
  const [moodInfo, setMoodInfo] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [presetsLoading, setPresetsLoading] = useState(true);
  const [mediaFilter, setMediaFilter] = useState("all");
  const [hideWatched, setHideWatched] = useState(false);

  useEffect(() => {
    api.moodPresets()
      .then(data => setPresets(data.presets || []))
      .finally(() => setPresetsLoading(false));
  }, []);

  const search = useCallback((q) => {
    if (!user || !q) return;
    setLoading(true);
    setMoodInfo(null);
    const opts = { mood: q, limit: 30, domain: mediaFilter };
    if (hideWatched) opts.hide_watched = true;
    Promise.all([
      api.recommend(user, "mood", opts),
      api.moodParse(q)
    ]).then(([recData, parseData]) => {
      setItems(recData.recommendations || []);
      setMoodInfo(parseData);
    }).catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [user, mediaFilter, hideWatched]);

  const handlePreset = (preset) => {
    setActivePreset(preset.name);
    setQuery(preset.query);
    search(preset.query);
  };

  const handleSubmit = (e) => {
    e?.preventDefault();
    setActivePreset(null);
    search(query);
  };

  return (
    <>
      <div className="page-header">
        <h2>Mood Match</h2>
        <p>Describe what you're in the mood for — anything goes</p>
      </div>
      <div className="page-body">
        <div className="mood-search-bar">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSubmit()}
            placeholder='Try "cozy rainy day movie" or "intense sci-fi with plot twists"'
          />
          <button onClick={handleSubmit} disabled={!query.trim() || loading}>
            {loading ? <Loader2 size={16} className="spinner" /> : <Search size={16} />}
            Search
          </button>
        </div>

        <div className="mood-filters" style={{ display: "flex", gap: "12px", alignItems: "center", margin: "8px 0 4px" }}>
          <select value={mediaFilter} onChange={e => { setMediaFilter(e.target.value); if (query.trim()) search(query); }}
            style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px", fontSize: 13 }}>
            <option value="all">All Media</option>
            <option value="movies">Movies Only</option>
            <option value="tv">TV Shows Only</option>
            <option value="anime">Anime Only</option>
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "var(--text-muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={hideWatched} onChange={e => { setHideWatched(e.target.checked); if (query.trim()) search(query); }} />
            Hide watched
          </label>
        </div>

        {!presetsLoading && presets.length > 0 && (
          <div className="mood-presets">
            {presets.map((p, i) => (
              <button
                key={i}
                className={`preset-chip ${activePreset === p.name ? 'active' : ''}`}
                onClick={() => handlePreset(p)}
              >
                {p.name}
              </button>
            ))}
          </div>
        )}

        {moodInfo && (
          <div className="mood-explanation">
            <Sparkles size={16} />
            <span>{moodInfo.explanation || "Mood parsed successfully"}</span>
          </div>
        )}

        {loading ? <LoadingState message="Matching your mood..." /> :
         items.length > 0 ? (
          <div className="card-grid">
            {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={item} onClick={onCardClick} />)}
          </div>
         ) : !loading && query && items.length === 0 && moodInfo ? (
          <EmptyState icon={Sparkles} title="No mood matches" message="Try describing your mood differently." />
         ) : null}
      </div>
    </>
  );
}

// ─── Page: Trending ─────────────────────────────────────────────
const TRENDING_SUBTABS = [
  { id: "global", label: "Global Trending", icon: TrendingUp },
  { id: "country", label: "By Country", icon: Globe },
  { id: "streaming", label: "By Streaming", icon: Tv },
  { id: "new_releases", label: "New Releases", icon: Sparkles },
];

function TrendingPage({ onCardClick, subtab: initialSubtab, onSubtabChange }) {
  const [subtab, setSubtabRaw] = useState(initialSubtab || "global");
  const setSubtab = (t) => { setSubtabRaw(t); onSubtabChange?.(t); };
  const [items, setItems] = useState([]);
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

  // Load country list once
  useEffect(() => {
    api.trendingCountries().then(d => setCountries(d.countries || [])).catch(() => {});
  }, []);

  // Load providers when streaming tab or region changes
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

        {currentProvider && subtab === "streaming" && (
          <div className="provider-badge">
            {currentProvider.logo_url && <img src={currentProvider.logo_url} alt="" style={{ width: 24, height: 24, borderRadius: 4 }} />}
            <span>Popular on {currentProvider.name}</span>
          </div>
        )}

        {loading ? <LoadingState message="Fetching trends..." /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         items.length === 0 ? <EmptyState icon={TrendingUp} title="Nothing trending for this filter" /> :
         <div className="card-grid">
           {items.map((item, i) => <MediaCard key={`${item.tmdb_id}-${i}`} item={{ ...item, score: null }} onClick={onCardClick} />)}
         </div>}
      </div>
    </>
  );
}

// ─── Page: Taste Profile ────────────────────────────────────────
function TasteProfilePage({ user }) {
  const [profile, setProfile] = useState(null);
  const [overrides, setOverrides] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("overview");
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [newBoostKw, setNewBoostKw] = useState("");
  const [newBlockKw, setNewBlockKw] = useState("");

  const load = useCallback(() => {
    if (!user) return;
    setLoading(true);
    setError(null);
    Promise.all([api.userProfile(user), api.getOverrides(user)])
      .then(([p, o]) => { setProfile(p); setOverrides(o); setDirty(false); })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user]);

  useEffect(() => { load(); }, [load]);

  const updateOverrides = (patch) => {
    setOverrides(prev => ({ ...prev, ...patch }));
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await api.saveOverrides(user, overrides);
      setOverrides(result.overrides);
      setDirty(false);
    } catch (e) {}
    setSaving(false);
  };

  const setGenreBoost = (genre, val) => {
    const boosts = { ...(overrides?.genre_boosts || {}) };
    if (Math.abs(val) < 0.05) delete boosts[genre]; else boosts[genre] = val;
    updateOverrides({ genre_boosts: boosts });
  };

  const toggleGenreBlock = (genre) => {
    const blocks = [...(overrides?.genre_blocks || [])];
    const idx = blocks.indexOf(genre);
    if (idx >= 0) blocks.splice(idx, 1); else blocks.push(genre);
    updateOverrides({ genre_blocks: blocks });
  };

  const addKeyword = (kw, type) => {
    if (!kw.trim()) return;
    const key = type === "boost" ? "keyword_boosts" : "keyword_blocks";
    const list = [...(overrides?.[key] || [])];
    if (!list.includes(kw.trim())) list.push(kw.trim());
    updateOverrides({ [key]: list });
    if (type === "boost") setNewBoostKw(""); else setNewBlockKw("");
  };

  const removeKeyword = (kw, type) => {
    const key = type === "boost" ? "keyword_boosts" : "keyword_blocks";
    updateOverrides({ [key]: (overrides?.[key] || []).filter(k => k !== kw) });
  };

  if (loading) return <><div className="page-header"><h2>Taste Profile</h2></div><div className="page-body"><LoadingState message="Building taste profile..." /></div></>;
  if (error) return <><div className="page-header"><h2>Taste Profile</h2></div><div className="page-body"><ErrorState message={error} onRetry={load} /></div></>;
  if (!profile) return null;

  const genreColors = ["#e5a00d", "#3b82f6", "#22c55e", "#a855f7", "#ef4444", "#06b6d4", "#f97316", "#ec4899", "#84cc16", "#6366f1"];
  const allGenres = (profile.genres || []).map(g => g.genre);

  return (
    <>
      <div className="page-header">
        <h2>Taste Profile</h2>
        <p>Behavior analysis + manual tuning for {user}</p>
      </div>
      <div className="page-body">
        <div className="profile-tabs">
          {[["overview", "Overview"], ["genres", "Genre Tuning"], ["keywords", "Keywords"]].map(([id, label]) => (
            <button key={id} className={`profile-tab ${tab === id ? "active" : ""}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>

        {tab === "overview" && (
          <>
            <div className="profile-stats">
              <div className="stat-card">
                <div className="stat-value">{profile.stats?.total_watched?.toLocaleString() || 0}</div>
                <div className="stat-label">Total Watched</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: "var(--accent)" }}>{formatHours(profile.stats?.total_hours || 0)}</div>
                <div className="stat-label">Watch Time</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: "var(--green)" }}>{profile.stats?.avg_completion?.toFixed(0) || 0}%</div>
                <div className="stat-label">Avg Completion</div>
              </div>
              <div className="stat-card">
                <div className="stat-value" style={{ color: "var(--purple)" }}>{profile.stats?.rewatch_count?.toLocaleString() || 0}</div>
                <div className="stat-label">Rewatches</div>
              </div>
            </div>
            <div className="section-header"><h3><BarChart3 size={18} /> Genre Affinities</h3></div>
            {(profile.genres || []).slice(0, 12).map((g, i) => (
              <div className="genre-bar-container" key={g.genre}>
                <div className="genre-bar-header">
                  <span className="genre-name">{g.genre}</span>
                  <span className="genre-stats">{g.watch_count} titles · {g.total_hours?.toFixed(1) || 0}h</span>
                </div>
                <div className="genre-bar-track">
                  <div className="genre-bar-fill" style={{ width: `${g.score * 100}%`, background: genreColors[i % genreColors.length] }} />
                </div>
              </div>
            ))}
            {profile.keywords?.length > 0 && (
              <>
                <div className="section-header" style={{ marginTop: 24 }}><h3><Sparkles size={18} /> Top Keywords</h3></div>
                <div className="keyword-chips">
                  {profile.keywords.slice(0, 20).map(k => (
                    <span className="keyword-chip" key={k.keyword}>{k.keyword} <span style={{opacity: 0.5, fontSize: "0.7rem"}}>×{k.count}</span></span>
                  ))}
                </div>
              </>
            )}
          </>
        )}

        {tab === "genres" && (
          <>
            <div className="section-header"><h3><SlidersHorizontal size={18} /> Genre Boost / Suppress / Block</h3></div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 16 }}>
              Drag sliders to boost (right) or suppress (left) genres. Block to completely exclude.
            </p>
            {allGenres.map(genre => {
              const boost = overrides?.genre_boosts?.[genre] || 0;
              const blocked = (overrides?.genre_blocks || []).includes(genre);
              return (
                <div className="genre-tuning-row" key={genre}>
                  <span className="genre-tuning-name">{genre}</span>
                  <input
                    type="range" min="-1" max="1" step="0.1"
                    className="genre-tuning-slider"
                    value={blocked ? 0 : boost}
                    disabled={blocked}
                    onChange={e => setGenreBoost(genre, parseFloat(e.target.value))}
                    style={blocked ? { opacity: 0.3 } : {}}
                  />
                  <span className="genre-tuning-value">{blocked ? "—" : (boost > 0 ? "+" : "") + boost.toFixed(1)}</span>
                  <button
                    className={`genre-tuning-block ${blocked ? "blocked" : ""}`}
                    onClick={() => toggleGenreBlock(genre)}
                  >{blocked ? "Blocked" : "Block"}</button>
                </div>
              );
            })}
            {dirty && (
              <div className="profile-save-bar">
                <span className="changes-badge">Unsaved changes</span>
                <button className="btn btn-primary" style={{ padding: "6px 16px", fontSize: 13 }} onClick={handleSave} disabled={saving}>
                  {saving ? <><Loader2 size={14} className="spin" /> Saving...</> : <><Save size={14} /> Save Changes</>}
                </button>
              </div>
            )}
          </>
        )}

        {tab === "keywords" && (
          <>
            <div className="section-header"><h3><ThumbsUp size={18} /> Preferred Keywords</h3></div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 10 }}>
              Titles matching these keywords get a score boost.
            </p>
            <div className="keyword-chips">
              {(overrides?.keyword_boosts || []).map(kw => (
                <span className="keyword-chip boost" key={kw}>{kw} <button onClick={() => removeKeyword(kw, "boost")}><X size={12} /></button></span>
              ))}
              {(overrides?.keyword_boosts || []).length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-dim)" }}>None yet</span>}
            </div>
            <div className="keyword-add-row">
              <input placeholder="Add keyword..." value={newBoostKw} onChange={e => setNewBoostKw(e.target.value)} onKeyDown={e => e.key === "Enter" && addKeyword(newBoostKw, "boost")} />
              <button onClick={() => addKeyword(newBoostKw, "boost")}>+ Boost</button>
            </div>

            <div className="section-header" style={{ marginTop: 24 }}><h3><ThumbsDown size={18} /> Blocked Keywords</h3></div>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: 10 }}>
              Titles matching these keywords get a score penalty.
            </p>
            <div className="keyword-chips">
              {(overrides?.keyword_blocks || []).map(kw => (
                <span className="keyword-chip block" key={kw}>{kw} <button onClick={() => removeKeyword(kw, "block")}><X size={12} /></button></span>
              ))}
              {(overrides?.keyword_blocks || []).length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-dim)" }}>None yet</span>}
            </div>
            <div className="keyword-add-row">
              <input placeholder="Add keyword..." value={newBlockKw} onChange={e => setNewBlockKw(e.target.value)} onKeyDown={e => e.key === "Enter" && addKeyword(newBlockKw, "block")} />
              <button onClick={() => addKeyword(newBlockKw, "block")}>+ Block</button>
            </div>

            {dirty && (
              <div className="profile-save-bar">
                <span className="changes-badge">Unsaved changes</span>
                <button className="btn btn-primary" style={{ padding: "6px 16px", fontSize: 13 }} onClick={handleSave} disabled={saving}>
                  {saving ? <><Loader2 size={14} className="spin" /> Saving...</> : <><Save size={14} /> Save Changes</>}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}


// ─── Page: Collections ───────────────────────────────────────────
function CollectionsPage({ user, onCardClick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  const load = useCallback(() => {
    if (!user?.username) return;
    setLoading(true);
    setError(null);
    api.collections(user.username)
      .then(d => setData(d))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [user?.username]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <><div className="page-header"><h2>Complete The Collection</h2></div><div className="page-body"><LoadingState message="Scanning your watch history for franchise gaps..." /></div></>;
  if (error) return <><div className="page-header"><h2>Complete The Collection</h2></div><div className="page-body"><ErrorState message={error} onRetry={load} /></div></>;

  const collections = data?.collections || [];

  return (
    <>
      <div className="page-header">
        <h2>Complete The Collection</h2>
        <p>{collections.length} franchise{collections.length !== 1 ? "s" : ""} with missing entries</p>
      </div>
      <div className="page-body">
        {collections.length === 0 ? (
          <EmptyState icon={Layers} title="All caught up!" message="You've completed every franchise in your watch history." />
        ) : (
          <div className="coll-list">
            {collections.map(c => (
              <div key={c.collection_id} className="coll-card">
                <div className="coll-header" onClick={() => setExpanded(expanded === c.collection_id ? null : c.collection_id)}>
                  {c.poster_url && <img src={c.poster_url} alt="" className="coll-poster" />}
                  <div className="coll-info">
                    <h3>{c.name}</h3>
                    <div className="coll-meta">
                      <span className="coll-progress">{c.watched_count}/{c.total_parts} watched</span>
                      <span className="coll-pct">{c.completion_pct}%</span>
                    </div>
                    <div className="coll-bar">
                      <div className="coll-bar-fill" style={{ width: `${c.completion_pct}%` }} />
                    </div>
                    <div className="coll-missing-summary">
                      {c.missing.length} missing: {c.missing.slice(0, 3).map(m => m.title).join(", ")}
                      {c.missing.length > 3 && ` +${c.missing.length - 3} more`}
                    </div>
                  </div>
                  <ChevronDown size={18} className={expanded === c.collection_id ? "coll-chev open" : "coll-chev"} />
                </div>
                {expanded === c.collection_id && (
                  <div className="coll-parts">
                    {c.parts.map(p => (
                      <div key={p.tmdb_id} className={`coll-part ${p.watched ? "watched" : ""}`}
                           onClick={() => !p.watched && onCardClick && onCardClick({ tmdb_id: p.tmdb_id, media_type: "movie", title: p.title, year: p.year, poster_url: p.poster_url })}>
                        {p.poster_url && <img src={p.poster_url} alt="" className="coll-part-poster" />}
                        <div className="coll-part-info">
                          <span className="coll-part-title">{p.title} {p.year ? `(${p.year})` : ""}</span>
                          <span className="coll-part-status">
                            {p.watched ? <><CheckCircle2 size={12} style={{ color: "var(--green)" }} /> Watched</> :
                             p.in_library ? <><Film size={12} style={{ color: "var(--accent)" }} /> In Library</> :
                             <><XCircle size={12} style={{ color: "var(--text-muted)" }} /> Not in Library</>}
                          </span>
                        </div>
                        {p.vote_average > 0 && <span className="coll-part-score">{p.vote_average.toFixed(1)}</span>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}


// ─── AI Settings Panel (used inside Config tab) ─────────────────
function AISettingsPanel() {
  const [aiCfg, setAiCfg] = useState(null);
  const [providers, setProviders] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [models, setModels] = useState([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [showKey, setShowKey] = useState(false);

  // Local edit state
  const [llmProvider, setLlmProvider] = useState("disabled");
  const [llmEndpoint, setLlmEndpoint] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmTemp, setLlmTemp] = useState(0.7);
  const [llmMaxTokens, setLlmMaxTokens] = useState(500);
  const [featMood, setFeatMood] = useState(false);
  const [featExplanations, setFeatExplanations] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, prov] = await Promise.all([api.aiConfig(true), api.aiProviders()]);
      setAiCfg(cfg);
      setProviders(prov);
      // Populate local state from config
      setLlmProvider(cfg.llm?.provider || "disabled");
      setLlmEndpoint(cfg.llm?.endpoint || "");
      setLlmApiKey(cfg.llm?.api_key || "");
      setLlmModel(cfg.llm?.model || "");
      setLlmTemp(cfg.llm?.temperature ?? 0.7);
      setLlmMaxTokens(cfg.llm?.max_tokens ?? 500);
      setFeatMood(cfg.features?.ai_mood || false);
      setFeatExplanations(cfg.features?.ai_explanations || false);
      setExpanded(cfg.llm?.provider !== "disabled");
    } catch (e) { console.error("AI config load failed:", e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const providerInfo = providers?.llm_providers?.find(p => p.id === llmProvider);
  const needsEndpoint = providerInfo?.needs_endpoint ?? false;
  const needsKey = providerInfo?.needs_key ?? false;
  const isEnabled = llmProvider !== "disabled";

  const handleProviderChange = (val) => {
    setLlmProvider(val);
    setDirty(true);
    setTestResult(null);
    setModels([]);
    setLlmModel("");
    // Pre-fill endpoint from placeholder
    const pInfo = providers?.llm_providers?.find(p => p.id === val);
    if (pInfo?.endpoint_placeholder && !llmEndpoint) setLlmEndpoint(pInfo.endpoint_placeholder);
  };

  const handleFetchModels = async () => {
    setFetchingModels(true);
    try {
      const result = await api.aiModels({ provider: llmProvider, endpoint: llmEndpoint, api_key: llmApiKey });
      setModels(result.models || []);
      if (result.models?.length === 0) setTestResult({ status: "warning", message: "Connected but no models found." });
    } catch (e) { setTestResult({ status: "error", message: e.message }); }
    setFetchingModels(false);
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.aiTest({ provider: llmProvider, endpoint: llmEndpoint, api_key: llmApiKey, model: llmModel });
      setTestResult(result);
    } catch (e) { setTestResult({ status: "error", message: e.message }); }
    setTesting(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const result = await api.aiUpdateConfig({
        llm: { provider: llmProvider, endpoint: llmEndpoint, api_key: llmApiKey, model: llmModel, temperature: llmTemp, max_tokens: llmMaxTokens },
        features: { ai_mood: featMood, ai_explanations: featExplanations },
      });
      setSaveMsg({ type: "ok", text: "AI configuration saved." });
      setDirty(false);
    } catch (e) { setSaveMsg({ type: "err", text: e.message || "Save failed" }); }
    setSaving(false);
  };

  const inputStyle = { background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "6px 10px", color: "var(--text)", fontSize: 12, fontFamily: "'JetBrains Mono', monospace", width: "100%" };
  const selectStyle = { ...inputStyle, appearance: "none", cursor: "pointer", colorScheme: "dark", backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E\")", backgroundRepeat: "no-repeat", backgroundPosition: "right 8px center", paddingRight: 28 };
  const labelStyle = { fontSize: 12, color: "var(--text-muted)", minWidth: 110, flexShrink: 0 };
  const rowStyle = { display: "flex", alignItems: "center", gap: 10, padding: "5px 0" };

  if (loading) return <div className="admin-card" style={{ marginBottom: 12 }}><h4><Sparkles size={15} /> AI Integration</h4><div style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</div></div>;

  return (
    <div className="admin-card" style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }} onClick={() => setExpanded(!expanded)}>
        <h4 style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
          <Sparkles size={15} /> AI Integration
          {isEnabled && <span style={{ fontSize: 10, background: "var(--accent)", color: "#fff", borderRadius: 8, padding: "1px 7px", marginLeft: 6 }}>ON</span>}
          {!isEnabled && <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: 6 }}>Disabled</span>}
        </h4>
        <ChevronDown size={14} style={{ color: "var(--text-muted)", transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />
      </div>

      {expanded && (
        <div style={{ marginTop: 12 }}>
          {/* Provider selector */}
          <div style={rowStyle}>
            <span style={labelStyle}>LLM Provider</span>
            <select value={llmProvider} onChange={e => handleProviderChange(e.target.value)} style={{ ...selectStyle, maxWidth: 320 }}>
              {providers?.llm_providers?.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>

          {isEnabled && (
            <>
              {/* Endpoint */}
              {needsEndpoint && (
                <div style={rowStyle}>
                  <span style={labelStyle}>Endpoint URL</span>
                  <input type="text" value={llmEndpoint} onChange={e => { setLlmEndpoint(e.target.value); setDirty(true); }}
                    placeholder={providerInfo?.endpoint_placeholder || ""} style={{ ...inputStyle, maxWidth: 320 }} />
                </div>
              )}

              {/* API Key */}
              {needsKey && (
                <div style={rowStyle}>
                  <span style={labelStyle}>API Key</span>
                  <div style={{ display: "flex", gap: 4, flex: 1, maxWidth: 320 }}>
                    <input type={showKey ? "text" : "password"} value={llmApiKey} onChange={e => { setLlmApiKey(e.target.value); setDirty(true); }}
                      placeholder="sk-..." style={{ ...inputStyle }} />
                    <button onClick={() => setShowKey(!showKey)} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 6px", cursor: "pointer", color: "var(--text-muted)" }}>
                      {showKey ? <EyeOff size={12} /> : <Eye size={12} />}
                    </button>
                  </div>
                </div>
              )}

              {/* Model */}
              <div style={rowStyle}>
                <span style={labelStyle}>Model</span>
                <div style={{ display: "flex", gap: 4, flex: 1, maxWidth: 320 }}>
                  {models.length > 0 ? (
                    <select value={llmModel} onChange={e => { setLlmModel(e.target.value); setDirty(true); }} style={{ ...selectStyle }}>
                      <option value="">Select a model...</option>
                      {models.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <input type="text" value={llmModel} onChange={e => { setLlmModel(e.target.value); setDirty(true); }}
                      placeholder="e.g. gemma3:4b, gpt-4o-mini" style={{ ...inputStyle }} />
                  )}
                  <button onClick={handleFetchModels} disabled={fetchingModels || (!needsEndpoint && !needsKey)} className="test-btn"
                    style={{ whiteSpace: "nowrap", fontSize: 11, padding: "4px 8px" }}>
                    {fetchingModels ? <><Loader2 size={11} className="spin" /> Loading</> : <><RefreshCw size={11} /> Fetch Models</>}
                  </button>
                </div>
              </div>

              {/* Temperature & Max Tokens */}
              <div style={rowStyle}>
                <span style={labelStyle}>Temperature</span>
                <input type="number" value={llmTemp} min={0} max={2} step={0.1} onChange={e => { setLlmTemp(parseFloat(e.target.value) || 0); setDirty(true); }}
                  style={{ ...inputStyle, maxWidth: 80 }} />
                <span style={{ ...labelStyle, minWidth: 80, textAlign: "right" }}>Max tokens</span>
                <input type="number" value={llmMaxTokens} min={50} max={4096} step={50} onChange={e => { setLlmMaxTokens(parseInt(e.target.value) || 500); setDirty(true); }}
                  style={{ ...inputStyle, maxWidth: 80 }} />
              </div>

              {/* Test + Result */}
              <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 0", flexWrap: "wrap" }}>
                <button onClick={handleTest} disabled={testing || !llmModel} className="test-btn" style={{ fontSize: 11, gap: 4 }}>
                  {testing ? <><Loader2 size={11} className="spin" /> Testing...</> : <><Zap size={11} /> Test Connection</>}
                </button>
                {testResult && (
                  <span style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 4, color: testResult.status === "ok" ? "var(--green)" : testResult.status === "warning" ? "var(--accent)" : "var(--red)" }}>
                    {testResult.status === "ok" ? <CheckCircle2 size={12} /> : testResult.status === "warning" ? <AlertCircle size={12} /> : <XCircle size={12} />}
                    {testResult.message}
                  </span>
                )}
              </div>

              {/* Divider */}
              <div style={{ borderTop: "1px solid var(--border)", margin: "8px 0" }} />

              {/* Feature toggles */}
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Features</div>
              {providers?.features?.map(f => (
                <div key={f.id} style={{ ...rowStyle, cursor: "pointer" }} onClick={() => { if (f.id === "ai_mood") { setFeatMood(!featMood); } else { setFeatExplanations(!featExplanations); } setDirty(true); }}>
                  <div style={{ width: 34, height: 18, borderRadius: 9, background: (f.id === "ai_mood" ? featMood : featExplanations) ? "var(--accent)" : "var(--border)", position: "relative", transition: "background 0.2s", flexShrink: 0 }}>
                    <div style={{ width: 14, height: 14, borderRadius: 7, background: "#fff", position: "absolute", top: 2, left: (f.id === "ai_mood" ? featMood : featExplanations) ? 18 : 2, transition: "left 0.2s" }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{f.label}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{f.description}</div>
                  </div>
                </div>
              ))}

              {/* Save */}
              <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
                <button onClick={handleSave} disabled={saving} className="test-btn" style={{ background: "var(--accent)", color: "#fff", fontSize: 12, gap: 4 }}>
                  {saving ? <><Loader2 size={12} className="spin" /> Saving...</> : <><Save size={12} /> Save AI Config</>}
                </button>
                {saveMsg && <span style={{ fontSize: 12, color: saveMsg.type === "ok" ? "var(--green)" : "var(--red)" }}>{saveMsg.text}</span>}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}


// ─── Page: Watchlist ────────────────────────────────────────────

const WATCHLIST_SORTS = [
  { value: "addedAt:desc", label: "Recently Added" },
  { value: "addedAt:asc", label: "Oldest Added" },
  { value: "titleSort:asc", label: "Title A–Z" },
  { value: "titleSort:desc", label: "Title Z–A" },
  { value: "year:desc", label: "Newest Release" },
  { value: "year:asc", label: "Oldest Release" },
  { value: "rating:desc", label: "Highest Rated" },
];

function WatchlistPage({ user, onCardClick }) {
  const [items, setItems] = useState([]);
  const [libraries, setLibraries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState("addedAt:desc");
  const [filterLib, setFilterLib] = useState("all"); // "all" | library title
  const [removing, setRemoving] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [playResult, setPlayResult] = useState(null);

  const load = useCallback(() => {
    setLoading(true); setError(null);
    api.watchlist(sort, null)
      .then(data => {
        setItems(data.items || []);
        if (data.libraries) setLibraries(data.libraries);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [sort]);

  useEffect(() => { load(); }, [load]);

  const handleRemove = async (item) => {
    setRemoving(item.tmdb_id);
    try {
      await api.watchlistDelete(item.tmdb_id, item.media_type);
      setItems(prev => prev.filter(i => i.tmdb_id !== item.tmdb_id));
    } catch (e) { console.error("Remove failed:", e); }
    setRemoving(null);
  };

  const handlePlay = async (item) => {
    if (!item.in_library) return;
    setPlayingId(item.tmdb_id); setPlayResult(null);
    try {
      const result = await api.playOnDevice(item.tmdb_id, item.media_type);
      setPlayResult({ id: item.tmdb_id, ...result });
    } catch (e) {
      setPlayResult({ id: item.tmdb_id, success: false, message: e.message });
    }
    setTimeout(() => { setPlayingId(null); setPlayResult(null); }, 3000);
  };

  // Build subtabs from Plex libraries with item counts
  const libCounts = {};
  items.forEach(item => {
    const lib = item.library_name || "Uncategorized";
    libCounts[lib] = (libCounts[lib] || 0) + 1;
  });
  // Order: libraries in Plex order, then Uncategorized if any
  const libTabs = libraries
    .filter(l => libCounts[l.title])
    .map(l => ({ id: l.title, label: l.title, count: libCounts[l.title] }));
  if (libCounts["Uncategorized"]) {
    libTabs.push({ id: "Uncategorized", label: "Uncategorized", count: libCounts["Uncategorized"] });
  }

  return (
    <>
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <h2><Bookmark size={20} style={{ verticalAlign: -3, marginRight: 6 }} />Watchlist</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select value={sort} onChange={e => setSort(e.target.value)} style={{ fontSize: 12, padding: "4px 8px" }}>
              {WATCHLIST_SORTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: 12 }} onClick={load}>
              <RefreshCw size={13} />
            </button>
          </div>
        </div>
        <p>Your Plex watchlist — titles you want to watch later</p>
      </div>

      <div className="watchlist-subtabs">
        <button
          className={`wl-subtab ${filterLib === "all" ? "active" : ""}`}
          onClick={() => setFilterLib("all")}
        >
          All <span className="wl-count">{items.length}</span>
        </button>
        {libTabs.map(tab => (
          <button
            key={tab.id}
            className={`wl-subtab ${filterLib === tab.id ? "active" : ""}`}
            onClick={() => setFilterLib(tab.id)}
          >
            {tab.label} <span className="wl-count">{tab.count}</span>
          </button>
        ))}
      </div>

      <div className="page-body">
        {loading ? <LoadingState message="Loading watchlist..." /> :
         error ? <ErrorState message={error} onRetry={load} /> :
         items.length === 0 ? <EmptyState icon={Bookmark} title="Watchlist empty" message="Add titles to your Plex watchlist to see them here." /> :
         <div className="card-grid">
           {items
             .filter(item => filterLib === "all" || (item.library_name || "Uncategorized") === filterLib)
             .map((item, i) => (
             <div className="media-card watchlist-card" key={`${item.tmdb_id}-${i}`} onClick={() => onCardClick(item)}>
               <div className="card-poster">
                 {item.poster_url ? (
                   <img src={item.poster_url} alt={item.title} loading="lazy" />
                 ) : (
                   <div className="no-poster"><Film size={32} /></div>
                 )}
                 <div className="card-overlay">
                   <div className="card-actions-row">
                     {item.in_library && item.plex_url && (
                       <button className="card-action-btn plex-btn" title="Play in Plex" onClick={(e) => { e.stopPropagation(); window.open(item.plex_url, "_blank"); }}>
                         <Play size={14} fill="currentColor" />
                       </button>
                     )}
                     {item.in_library && (
                       <button
                         className={`card-action-btn ${playResult?.id === item.tmdb_id ? (playResult.success ? "plex-btn" : "dismiss-btn") : "info-btn"}`}
                         title="Watch Now on device"
                         disabled={playingId === item.tmdb_id}
                         onClick={(e) => { e.stopPropagation(); handlePlay(item); }}
                       >
                         {playingId === item.tmdb_id ? <Loader2 size={14} className="spinner" /> :
                          playResult?.id === item.tmdb_id && playResult.success ? <CheckCircle2 size={14} /> :
                          <Monitor size={14} />}
                       </button>
                     )}
                     <button
                       className="card-action-btn dismiss-btn"
                       title="Remove from Watchlist"
                       disabled={removing === item.tmdb_id}
                       onClick={(e) => { e.stopPropagation(); handleRemove(item); }}
                     >
                       {removing === item.tmdb_id ? <Loader2 size={14} className="spinner" /> : <XCircle size={14} />}
                     </button>
                   </div>
                 </div>
                 {item.in_library && <div className="card-badge library-badge">In Library</div>}
                 {item.is_watched && <div className="card-badge watched-badge"><Eye size={10} /> Watched</div>}
               </div>
               <div className="card-info">
                 <div className="card-title">{item.title}</div>
                 <div className="card-meta">
                   {item.year && <span>{item.year}</span>}
                   {item.vote_average > 0 && <><span className="sep">·</span><span>★ {item.vote_average.toFixed(1)}</span></>}
                   <span className="sep">·</span>
                   <span style={{ color: item.media_type === "movie" ? "var(--blue)" : "var(--purple)", fontSize: 10, textTransform: "uppercase", fontWeight: 600 }}>
                     {item.media_type === "movie" ? "Movie" : "TV"}
                   </span>
                 </div>
                 {item.genres?.length > 0 && (
                   <div className="card-genres">{item.genres.slice(0, 3).join(" · ")}</div>
                 )}
               </div>
             </div>
           ))}
         </div>}
      </div>
    </>
  );
}

// ─── Page: System Settings ───────────────────────────────────────
function AdminPage({ subtab: initialSubtab, onSubtabChange, user: currentUser }) {
  const [settingsTab, setSettingsTabRaw] = useState(initialSubtab || "services");
  const [devicesList, setDevicesList] = useState([]);
  const [globalPrefs, setGlobalPrefs] = useState(null);
  const [userPrefs, setUserPrefs] = useState(null);
  const [prefsSaving, setPrefsSaving] = useState(false);
  const setSettingsTab = (t) => { setSettingsTabRaw(t); onSubtabChange?.(t); };
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [sysSettings, setSysSettings] = useState(null);
  const [cacheInfo, setCacheInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [testResults, setTestResults] = useState({});
  const [testing, setTesting] = useState({});
  const [editMode, setEditMode] = useState(false);
  const [editValues, setEditValues] = useState({});
  const [schedule, setSchedule] = useState(null);
  const [schedSaving, setSchedSaving] = useState(false);
  const [schedSuggestion, setSchedSuggestion] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [showKeys, setShowKeys] = useState({});

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.health(),
      api.stats(),
      api.systemSettings().catch(() => null),
      api.cacheDetailed().catch(() => null),
    ])
      .then(([h, s, cfg, cache]) => { setHealth(h); setStats(s); setSysSettings(cfg); setCacheInfo(cache); })
      .then(() => {
        if (currentUser) {
          const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
          api.getSchedule(currentUser).then(s => {
            setSchedule(s);
            // If no schedule configured yet, auto-set timezone from browser
            if (!s.last_run_at && s.timezone === "UTC") s.timezone = browserTz;
          }).catch(() => {});
          api.suggestSchedule(currentUser, browserTz).then(setSchedSuggestion).catch(() => {});
        }
      })
      .then(() => {
        api.devices().then(r => setDevicesList(r.devices || [])).catch(() => {});
        api.preferences().then(r => setUserPrefs(r.preferences || {})).catch(() => {});
        api.globalPreferences().then(r => setGlobalPrefs(r.global_defaults || null)).catch(() => {});
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleTest = async (service) => {
    setTesting(p => ({ ...p, [service]: true }));
    setTestResults(p => ({ ...p, [service]: null }));
    try {
      const result = await api.testConnection(service);
      setTestResults(p => ({ ...p, [service]: result }));
    } catch (err) {
      setTestResults(p => ({ ...p, [service]: { status: "error", message: err.message } }));
    }
    setTesting(p => ({ ...p, [service]: false }));
  };

  const handleClearCache = async (scope) => {
    try {
      await api.cacheClear(scope);
      const cache = await api.cacheDetailed().catch(() => null);
      setCacheInfo(cache);
    } catch (err) {
      console.error(err);
    }
  };

  const enterEditMode = async () => {
    try {
      const data = await api.systemSettingsEdit();
      // Flatten all editable fields into a simple {field: value} map
      const flat = {};
      const extractFields = (obj) => {
        Object.values(obj).forEach(v => {
          if (v && typeof v === "object" && v.field) {
            flat[v.field] = v.value ?? "";
          } else if (v && typeof v === "object" && !v.field) {
            extractFields(v);
          }
        });
      };
      extractFields(data);
      setEditValues(flat);
      setEditMode(true);
      setSaveMsg(null);
    } catch (err) {
      console.error("Failed to load settings for editing:", err);
    }
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      const result = await api.updateSettings(editValues);
      setSaveMsg({ type: "ok", text: `Saved ${result.updated?.length || 0} setting(s)` });
      setEditMode(false);
      // Reload display data
      const cfg = await api.systemSettings().catch(() => null);
      setSysSettings(cfg);
    } catch (err) {
      setSaveMsg({ type: "err", text: err.message || "Save failed" });
    }
    setSaving(false);
  };

  const handleEditField = (field, value) => {
    setEditValues(prev => ({ ...prev, [field]: value }));
  };

  const toggleShowKey = (field) => {
    setShowKeys(prev => ({ ...prev, [field]: !prev[field] }));
  };

  if (loading) return <><div className="page-header"><h2>System Settings</h2></div><div className="page-body"><LoadingState /></div></>;
  if (error) return <><div className="page-header"><h2>System Settings</h2></div><div className="page-body"><ErrorState message={error} onRetry={load} /></div></>;

  const settingsTabs = [
    { id: "services", label: "Services", icon: Activity },
    { id: "library", label: "Library", icon: Database },
    { id: "cache", label: "Cache", icon: BarChart3 },
    { id: "config", label: "Configuration", icon: Settings },
    { id: "prefs", label: "Preferences", icon: SlidersHorizontal },
  ];

  return (
    <>
      <div className="page-header">
        <h2>System Settings</h2>
        <p>Recommendarr v{health?.version} &middot; {health?.architecture}</p>
      </div>
      <div className="page-body">
        <div className="settings-tabs">
          {settingsTabs.map(t => (
            <button key={t.id} className={`settings-tab ${settingsTab === t.id ? "active" : ""}`} onClick={() => setSettingsTab(t.id)}>
              <t.icon size={14} /> {t.label}
            </button>
          ))}
        </div>

        {settingsTab === "services" && (
          <div className="admin-grid">
            {health?.services && Object.entries(health.services).map(([name, svc]) => (
              <div className="admin-card" key={name}>
                <div className="service-row" style={{ marginBottom: 8 }}>
                  <h4 style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}>
                    {svc.status === "ok" ? <CheckCircle2 size={14} style={{ color: "var(--green)" }} /> : <XCircle size={14} style={{ color: "var(--red)" }} />}
                    {name}
                  </h4>
                  <button className={`test-btn ${testing[name] ? "testing" : ""}`} onClick={() => handleTest(name)}>
                    {testing[name] ? <><Loader2 size={11} className="spin" /> Testing...</> : <><Zap size={11} /> Test</>}
                  </button>
                </div>
                <div className="service-detail">{svc.url}</div>
                {testResults[name] && (
                  <div className={`test-result ${testResults[name].status === "ok" ? "ok" : "err"}`}>
                    {testResults[name].status === "ok" ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                    {" "}{testResults[name].message}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {settingsTab === "library" && (
          <div className="admin-grid">
            <div className="admin-card">
              <h4><Film size={15} /> Movies</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.movies?.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <h4><Tv size={15} /> TV Series</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.tv_series?.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <h4><Sparkles size={15} /> Anime</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.anime_series?.toLocaleString()}</div>
            </div>
            <div className="admin-card">
              <h4><Users size={15} /> Users</h4>
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{stats?.users}</div>
            </div>
          </div>
        )}

        {settingsTab === "cache" && (
          <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
              <button className="test-btn" onClick={() => handleClearCache("all")}><RotateCcw size={11} /> Clear All Caches</button>
              <button className="test-btn" onClick={() => handleClearCache("recommendations")}><RotateCcw size={11} /> Clear Recs Only</button>
            </div>
            {cacheInfo?.ttl && (
              <div className="admin-card" style={{ marginBottom: 12 }}>
                <h4><Clock size={15} /> TTL Settings</h4>
                {Object.entries(cacheInfo.ttl).map(([k, v]) => (
                  <div className="service-row" key={k}><span>{k}</span><span style={{ color: "var(--text-muted)", fontSize: 13 }}>{v}</span></div>
                ))}
              </div>
            )}
            {cacheInfo?.stats && (
              <div className="admin-card">
                <h4><BarChart3 size={15} /> Statistics</h4>
                {typeof cacheInfo.stats === "object" ? Object.entries(cacheInfo.stats).map(([k, v]) => (
                  <div className="service-row" key={k}><span>{k}</span><span style={{ fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{typeof v === "number" ? v.toLocaleString() : String(v)}</span></div>
                )) : <div style={{ color: "var(--text-muted)", fontSize: 13 }}>No detailed stats available</div>}
              </div>
            )}
          </div>
        )}

        {settingsTab === "config" && sysSettings && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              {!editMode ? (
                <button className="test-btn" onClick={enterEditMode} style={{ gap: 6 }}><SlidersHorizontal size={12} /> Edit Settings</button>
              ) : (
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="test-btn" onClick={handleSaveSettings} disabled={saving} style={{ background: "var(--accent)", color: "#fff", gap: 6 }}>
                    {saving ? <><Loader2 size={12} className="spin" /> Saving...</> : <><Save size={12} /> Save Changes</>}
                  </button>
                  <button className="test-btn" onClick={() => { setEditMode(false); setSaveMsg(null); }} style={{ gap: 6 }}><X size={12} /> Cancel</button>
                </div>
              )}
              {saveMsg && <span style={{ fontSize: 13, color: saveMsg.type === "ok" ? "var(--green)" : "var(--red)" }}>{saveMsg.text}</span>}
            </div>

            {/* Service Endpoints */}
            <div className="admin-card" style={{ marginBottom: 12 }}>
              <h4><Settings size={15} /> Service Endpoints</h4>
              {sysSettings.services && Object.entries(sysSettings.services).map(([name, svc]) => (
                <div key={name} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6, textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</div>
                  {Object.entries(svc).map(([propLabel, prop]) => {
                    if (!prop || !prop.field) return (
                      <div className="service-row" key={propLabel} style={{ padding: "3px 0" }}>
                        <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 80 }}>{propLabel}</span>
                        <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{prop?.value || "—"}</span>
                      </div>
                    );
                    const isKey = propLabel.includes("key") || propLabel.includes("token") || propLabel === "api_key";
                    const field = prop.field;
                    return (
                      <div className="service-row" key={propLabel} style={{ padding: "3px 0", gap: 8 }}>
                        <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 80 }}>
                          {propLabel.replace(/_/g, " ")}
                          {prop.overridden && <span title="Overridden from settings.json" style={{ color: "var(--accent)", marginLeft: 4, fontSize: 10 }}>●</span>}
                        </span>
                        {editMode ? (
                          <div style={{ display: "flex", gap: 4, flex: 1, justifyContent: "flex-end" }}>
                            <input
                              type={isKey && !showKeys[field] ? "password" : "text"}
                              value={editValues[field] ?? ""}
                              onChange={e => handleEditField(field, e.target.value)}
                              style={{ flex: 1, maxWidth: 360, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", color: "var(--text)", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}
                            />
                            {isKey && (
                              <button onClick={() => toggleShowKey(field)} style={{ background: "none", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 6px", cursor: "pointer", color: "var(--text-muted)", fontSize: 11 }}>
                                {showKeys[field] ? <EyeOff size={12} /> : <Eye size={12} />}
                              </button>
                            )}
                          </div>
                        ) : (
                          <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "var(--text-muted)" }}>{prop.value || "—"}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>

            {/* AI Integration */}
            <AISettingsPanel />

            {/* Auth & App */}
            <div className="admin-card" style={{ marginBottom: 12 }}>
              <h4><Clock size={15} /> Auth &amp; App</h4>
              {[...(sysSettings.auth ? Object.entries(sysSettings.auth) : []), ...(sysSettings.app ? Object.entries(sysSettings.app) : [])].map(([propLabel, prop]) => {
                if (!prop || !prop.field) return null;
                const field = prop.field;
                return (
                  <div className="service-row" key={propLabel} style={{ padding: "3px 0", gap: 8 }}>
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {propLabel.replace(/_/g, " ")}
                      {prop.overridden && <span title="Overridden" style={{ color: "var(--accent)", marginLeft: 4, fontSize: 10 }}>●</span>}
                    </span>
                    {editMode ? (
                      <input
                        type={typeof prop.value === "number" ? "number" : "text"}
                        value={editValues[field] ?? ""}
                        onChange={e => handleEditField(field, typeof prop.value === "number" ? parseInt(e.target.value) || 0 : e.target.value)}
                        style={{ maxWidth: 200, background: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px", color: "var(--text)", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}
                      />
                    ) : (
                      <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
                        {typeof prop.value === "boolean" ? (prop.value ? "true" : "false") : prop.value}
                        {propLabel === "jwt_expiry_hours" && ` (${Math.round((prop.value || 0) / 24)}d)`}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>

            {editMode && (
              <div style={{ fontSize: 12, color: "var(--text-muted)", padding: "8px 0" }}>
                <span style={{ color: "var(--accent)", marginRight: 4 }}>●</span> = overridden from settings.json (env var value replaced).
                Changes are live immediately. Service clients may need a connection test to verify new URLs/keys.
              </div>
            )}
          </div>
        )}

        {settingsTab === "prefs" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Device Selector */}
            <div className="settings-device-section">
              <h4><Monitor size={15} /> Default Playback Device</h4>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px 0" }}>
                Select where "Watch Now" plays media. Refresh to detect online devices.
              </p>
              <div style={{ display: "flex", gap: 8 }}>
                <select
                  className="device-select"
                  value={typeof userPrefs?.default_device_id === "object" ? userPrefs?.default_device_id?.value : userPrefs?.default_device_id || ""}
                  onChange={async (e) => {
                    const dev = devicesList.find(d => d.client_id === e.target.value);
                    try {
                      await api.updatePreferences({
                        default_device_id: e.target.value,
                        default_device_name: dev?.name || "",
                      });
                      setUserPrefs(prev => ({
                        ...prev,
                        default_device_id: e.target.value,
                        default_device_name: dev?.name || "",
                      }));
                    } catch (err) { console.error("Failed to save device preference:", err); }
                  }}
                >
                  <option value="">— No device selected —</option>
                  {devicesList.map(d => (
                    <option key={d.client_id} value={d.client_id}>
                      {d.name} ({d.product})
                    </option>
                  ))}
                </select>
                <button className="btn btn-secondary" style={{ padding: "6px 10px", fontSize: 12, whiteSpace: "nowrap" }}
                  onClick={async () => {
                    try { const r = await api.devices(); setDevicesList(r.devices || []); } catch (e) {}
                  }}
                >
                  <RefreshCw size={13} /> Refresh
                </button>
              </div>
              {devicesList.length > 0 && (
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
                  {devicesList.length} device{devicesList.length !== 1 ? "s" : ""} online
                </div>
              )}
            </div>

            {/* Auto-Refresh Schedule */}
            <div style={{ background: "var(--bg-elevated)", borderRadius: 8, padding: 16 }}>
              <h4 style={{ margin: "0 0 4px" }}><Clock size={15} /> Scheduled Refresh</h4>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 12px" }}>
                Automatically refresh recommendations daily. Runs at your local time so fresh picks are ready when you open the app.
              </p>
              {schedule && (() => {
                const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
                const updateSched = async (patch) => {
                  setSchedSaving(true);
                  try {
                    const res = await api.updateSchedule(schedule.username, patch);
                    setSchedule(res);
                  } catch (e) { console.error(e); }
                  setSchedSaving(false);
                };
                const applySuggestion = () => {
                  if (schedSuggestion) {
                    updateSched({
                      enabled: true,
                      timezone: schedSuggestion.timezone || browserTz,
                      hour: schedSuggestion.suggested_hour,
                      minute: schedSuggestion.suggested_minute || 0,
                    });
                  }
                };
                const isSuggested = schedSuggestion && schedule.hour === schedSuggestion.suggested_hour
                  && schedule.timezone === (schedSuggestion.timezone || browserTz);
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                      <input type="checkbox" checked={schedule.enabled} onChange={e => updateSched({ enabled: e.target.checked })} />
                      <span style={{ fontSize: 13 }}>Enable daily auto-refresh</span>
                      {schedSaving && <Loader2 size={13} className="spinner" />}
                    </label>
                    {schedSuggestion && schedSuggestion.confidence !== "low" && (
                      <div style={{ background: "var(--surface)", borderRadius: 6, padding: "8px 12px", fontSize: 12, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <Sparkles size={14} style={{ color: "var(--accent)", flexShrink: 0 }} />
                        <span style={{ color: "var(--text-muted)" }}>
                          Based on {schedSuggestion.total_plays} viewing sessions, your quietest time is{" "}
                          <strong style={{ color: "var(--text)" }}>{String(schedSuggestion.suggested_hour).padStart(2,"0")}:00 {schedSuggestion.timezone}</strong>
                          {" "}({schedSuggestion.confidence} confidence)
                        </span>
                        {!isSuggested && (
                          <button onClick={applySuggestion} style={{
                            background: "var(--accent)", color: "#fff", border: "none", borderRadius: 4,
                            padding: "3px 8px", fontSize: 11, cursor: "pointer", whiteSpace: "nowrap"
                          }}>Use suggested</button>
                        )}
                        {isSuggested && <CheckCircle2 size={14} style={{ color: "var(--green)" }} />}
                      </div>
                    )}
                    {schedule.enabled && (
                      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <label style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase" }}>Time</label>
                          <input type="time"
                            value={`${String(schedule.hour).padStart(2,"0")}:${String(schedule.minute).padStart(2,"0")}`}
                            onChange={e => {
                              const [h, m] = e.target.value.split(":").map(Number);
                              updateSched({ hour: h, minute: m });
                            }}
                            style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", fontSize: 13 }}
                          />
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <label style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase" }}>Timezone</label>
                          <select value={schedule.timezone} onChange={e => updateSched({ timezone: e.target.value })}
                            style={{ background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", fontSize: 13, maxWidth: 220 }}>
                            {["UTC","America/New_York","America/Chicago","America/Denver","America/Los_Angeles","Europe/Zurich","Europe/Berlin","Europe/London","Asia/Tokyo","Asia/Shanghai","Australia/Sydney"]
                              .map(tz => <option key={tz} value={tz}>{tz.replace(/_/g," ")}</option>)}
                          </select>
                        </div>
                      </div>
                    )}
                    {schedule.last_run_at && (
                      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        Last auto-refresh: {new Date(schedule.last_run_at).toLocaleString()}
                        {schedule.last_run_ms ? ` (${(schedule.last_run_ms/1000).toFixed(1)}s)` : ""}
                        {schedule.last_error && <span style={{ color: "var(--red)" }}> — Error: {schedule.last_error}</span>}
                      </div>
                    )}
                  </div>
                );
              })()}
              {!schedule && <div style={{ fontSize: 12, color: "var(--text-muted)" }}>Loading schedule...</div>}
            </div>

            {/* Global Defaults (Admin only) */}
            {globalPrefs && (
              <div className="global-prefs-section">
                <h4><Globe size={15} /> Global Defaults (all users)</h4>
                <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "-4px 0 12px 0" }}>
                  These apply to all Plex users unless they've overridden a specific setting.
                </p>
                <div style={{ background: "var(--bg-elevated)", borderRadius: 8, padding: 12 }}>
                  {Object.entries(globalPrefs).map(([key, info]) => (
                    <div className="pref-row" key={key}>
                      <div>
                        <span className="pref-label">{key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</span>
                        <span className={`pref-source ${info.source}`}>{info.source}</span>
                      </div>
                      <div className="pref-control">
                        {typeof info.value === "boolean" ? (
                          <label className="toggle-switch" style={{ position: "relative", width: 36, height: 20, display: "inline-block" }}>
                            <input type="checkbox" checked={info.value} onChange={async (e) => {
                              setPrefsSaving(true);
                              await api.updateGlobalPreferences({ [key]: e.target.checked });
                              const r = await api.globalPreferences();
                              setGlobalPrefs(r.global_defaults);
                              setPrefsSaving(false);
                            }} style={{ display: "none" }} />
                            <span style={{
                              position: "absolute", cursor: "pointer", inset: 0, borderRadius: 20,
                              background: info.value ? "var(--green)" : "var(--surface)", transition: "0.2s",
                            }}>
                              <span style={{
                                position: "absolute", height: 14, width: 14, left: info.value ? 18 : 4, bottom: 3,
                                background: "#fff", borderRadius: "50%", transition: "0.2s",
                              }} />
                            </span>
                          </label>
                        ) : typeof info.value === "number" ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <input type="range" min={0} max={1} step={0.1} value={info.value}
                              onChange={async (e) => {
                                const val = parseFloat(e.target.value);
                                await api.updateGlobalPreferences({ [key]: val });
                                const r = await api.globalPreferences();
                                setGlobalPrefs(r.global_defaults);
                              }}
                            />
                            <span style={{ fontSize: 12, color: "var(--text-muted)", minWidth: 28 }}>{info.value}</span>
                          </div>
                        ) : (
                          <select value={info.value} onChange={async (e) => {
                            await api.updateGlobalPreferences({ [key]: e.target.value });
                            const r = await api.globalPreferences();
                            setGlobalPrefs(r.global_defaults);
                          }} style={{ padding: "4px 8px", fontSize: 12 }}>
                            {key === "language" && [["en","English"],["de","Deutsch"]].map(([v,l]) => <option key={v} value={v}>{l}</option>)}
                            {key === "watchlist_sort" && WATCHLIST_SORTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                            {key === "watchlist_filter" && ["all","movie","tv"].map(v => <option key={v} value={v}>{v}</option>)}
                            {!["language","watchlist_sort","watchlist_filter"].includes(key) && <option value={info.value}>{String(info.value)}</option>}
                          </select>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

// ─── Toast System ───────────────────────────────────────────────
function useToast() {
  const [toasts, setToasts] = useState([]);
  const addToast = useCallback((message, type = "info") => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
  }, []);
  return { toasts, addToast };
}

function ToastContainer({ toasts }) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {t.type === "success" ? <CheckCircle2 size={15} style={{ color: "var(--green)" }} /> :
           t.type === "error" ? <XCircle size={15} style={{ color: "var(--red)" }} /> :
           <Activity size={15} style={{ color: "var(--accent)" }} />}
          {t.message}
        </div>
      ))}
    </div>
  );
}

// ─── Main App ───────────────────────────────────────────────────
export default function Recommendarr() {
  // ── Hash-based routing ──────────────────────────────────────
  const parseHash = () => {
    const hash = window.location.hash.replace("#", "") || "tonight";
    const parts = hash.split("/");
    return { view: parts[0], subtab: parts[1] || null };
  };
  const initialHash = parseHash();
  const [view, setViewRaw] = useState(initialHash.view);
  const [hashSubtab, setHashSubtab] = useState(initialHash.subtab);

  // Update hash when view changes
  const setView = useCallback((newView, subtab) => {
    setViewRaw(newView);
    setHashSubtab(subtab || null);
    const hash = subtab ? `${newView}/${subtab}` : newView;
    window.history.replaceState(null, "", `#${hash}`);
  }, []);

  // Update hash when subtab changes (settings, trending)
  const setSubtab = useCallback((subtab) => {
    setHashSubtab(subtab);
    const hash = subtab ? `${view}/${subtab}` : view;
    window.history.replaceState(null, "", `#${hash}`);
  }, [view]);

  // Handle browser back/forward
  useEffect(() => {
    const onHashChange = () => {
      const { view: v, subtab: s } = parseHash();
      setViewRaw(v);
      setHashSubtab(s);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [modalItem, setModalItem] = useState(null);
  const [modalDetail, setModalDetail] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [requestResult, setRequestResult] = useState(null);
  const { toasts, addToast } = useToast();

  // ── Auth state ──────────────────────────────────────────────
  const [authUser, setAuthUser] = useState(null);        // { username, email, thumb, is_admin, plex_user_id }
  const [authLoading, setAuthLoading] = useState(true);  // true while checking stored token on mount
  const [loginLoading, setLoginLoading] = useState(false);
  const pollRef = useRef(null);
  const popupRef = useRef(null);

  // ── Admin "View as" state ───────────────────────────────────
  const [viewAsUser, setViewAsUser] = useState(null);    // null = self, or username string
  const [allUsers, setAllUsers] = useState([]);           // [{username, thumb, friendly_name}]

  // ── Refresh state ────────────────────────────────────────────
  const [refreshing, setRefreshing] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState(null); // {step, total, label, elapsed_ms}
  const [lastRefreshAt, setLastRefreshAt] = useState("");
  const [refreshEstimateMs, setRefreshEstimateMs] = useState(0);
  const refreshEventSourceRef = useRef(null);

  // Derived: selectedUser respects admin "view as" override
  const selectedUser = viewAsUser || authUser?.username || null;
  const isViewingAsOther = viewAsUser && viewAsUser !== authUser?.username;

  // ── Session hydration on mount ──────────────────────────────
  useEffect(() => {
    const stored = sessionStorage.getItem("recommendarr_token");
    if (stored) {
      setApiToken(stored);
      api.authMe(stored)
        .then(user => { setAuthUser(user); setApiToken(stored); })
        .catch(() => { sessionStorage.removeItem("recommendarr_token"); setApiToken(null); })
        .finally(() => setAuthLoading(false));
    } else {
      setAuthLoading(false);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // ── Fetch all users for admin "View as" switcher ─────────────
  useEffect(() => {
    if (authUser?.is_admin) {
      api.users().then(data => {
        const sorted = (data.users || [])
          .filter(u => u.username)
          .sort((a, b) => a.username.localeCompare(b.username));
        setAllUsers(sorted);
      }).catch(() => {});
    } else {
      setAllUsers([]);
      setViewAsUser(null);
    }
  }, [authUser]);

  // ── Fetch refresh status on mount ────────────────────────────
  useEffect(() => {
    if (authUser) {
      api.refreshStatus().then(data => {
        if (data.last_refresh_at) setLastRefreshAt(data.last_refresh_at);
        if (data.last_refresh_ms) setRefreshEstimateMs(data.last_refresh_ms);
      }).catch(() => {});
    }
  }, [authUser]);

  // ── Handle refresh ─────────────────────────────────────────
  const handleRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    setRefreshProgress(null);

    try {
      const { job_id, estimate_ms } = await api.refreshStart();
      if (estimate_ms) setRefreshEstimateMs(estimate_ms);

      // Connect SSE stream
      const evtSource = new EventSource(`${API_BASE}/cache/refresh/${job_id}/stream`);
      refreshEventSourceRef.current = evtSource;

      evtSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setRefreshProgress(data);
          if (data.done) {
            evtSource.close();
            refreshEventSourceRef.current = null;
            setRefreshing(false);
            setLastRefreshAt(new Date().toISOString());
            setRefreshEstimateMs(data.elapsed_ms || 0);
            if (data.error) {
              addToast(`Refresh completed with errors: ${data.error}`, "warning");
            } else {
              addToast(`Data refreshed in ${(data.elapsed_ms / 1000).toFixed(1)}s`, "success");
            }
          }
        } catch (e) {}
      };

      evtSource.onerror = () => {
        evtSource.close();
        refreshEventSourceRef.current = null;
        setRefreshing(false);
        addToast("Refresh connection lost", "error");
      };
    } catch (err) {
      setRefreshing(false);
      addToast(`Refresh failed: ${err.message}`, "error");
    }
  }, [refreshing, addToast]);

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => { if (refreshEventSourceRef.current) refreshEventSourceRef.current.close(); };
  }, []);

  // ── Plex OAuth login (matches Overseerr flow) ───────────────
  // Frontend handles PIN dance directly with plex.tv, then sends
  // the resulting authToken to our backend for validation.
  const handlePlexLogin = useCallback(async () => {
    setLoginLoading(true);
    try {
      // Generate or reuse a persistent client identifier (same as Overseerr)
      let clientId = sessionStorage.getItem("plex-client-id");
      if (!clientId) {
        // crypto.randomUUID() requires HTTPS — use fallback for HTTP origins
        clientId = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
          const r = (Math.random() * 16) | 0;
          return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
        });
        sessionStorage.setItem("plex-client-id", clientId);
      }

      const plexHeaders = {
        "Accept": "application/json",
        "X-Plex-Product": "Recommendarr",
        "X-Plex-Version": "0.2.0",
        "X-Plex-Client-Identifier": clientId,
        "X-Plex-Device": navigator.platform || "Web",
        "X-Plex-Device-Name": "Recommendarr (Web)",
        "X-Plex-Model": "Plex OAuth",
        "X-Plex-Platform": "Web",
      };

      // Step 1: Create PIN on plex.tv
      const pinResp = await fetch("https://plex.tv/api/v2/pins?strong=true", {
        method: "POST",
        headers: plexHeaders,
      });
      if (!pinResp.ok) throw new Error("Failed to create PIN");
      const pinData = await pinResp.json();
      const pinId = pinData.id;
      const pinCode = pinData.code;

      // Step 2: Open Plex auth popup
      const authUrl = `https://app.plex.tv/auth#!?clientID=${encodeURIComponent(clientId)}&code=${pinCode}&context%5Bdevice%5D%5Bproduct%5D=Recommendarr`;
      const popup = window.open(authUrl, "PlexAuth", "width=600,height=700,scrollbars=yes");
      popupRef.current = popup;

      // Step 3: Poll plex.tv directly for PIN claim (every 1s, like Overseerr)
      pollRef.current = setInterval(async () => {
        try {
          const checkResp = await fetch(`https://plex.tv/api/v2/pins/${pinId}`, {
            headers: plexHeaders,
          });
          if (!checkResp.ok) return; // Keep polling
          const checkData = await checkResp.json();

          if (checkData.authToken) {
            // PIN claimed — stop polling, close popup
            clearInterval(pollRef.current);
            pollRef.current = null;
            if (popupRef.current && !popupRef.current.closed) popupRef.current.close();

            // Step 4: Send authToken to our backend for validation
            try {
              const result = await api.authPlex(checkData.authToken);
              sessionStorage.setItem("recommendarr_token", result.token);
              setApiToken(result.token);
              setAuthUser(result.user);
              addToast(`Welcome, ${result.user.username}!`, "success");
            } catch (backendErr) {
              addToast(backendErr.message || "Access denied.", "error");
            }
            setLoginLoading(false);
          } else if (popupRef.current?.closed) {
            // User closed popup without completing
            clearInterval(pollRef.current);
            pollRef.current = null;
            setLoginLoading(false);
          }
        } catch (err) {
          // Network hiccup — keep polling
        }
      }, 1000);

      // Timeout after 5 minutes
      setTimeout(() => {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          if (popupRef.current && !popupRef.current.closed) popupRef.current.close();
          setLoginLoading(false);
          addToast("Login timed out. Please try again.", "error");
        }
      }, 300000);

    } catch (err) {
      setLoginLoading(false);
      addToast("Failed to start Plex login. Try again.", "error");
    }
  }, [addToast]);

  // ── Logout ─────────────────────────────────────────────────
  const handleLogout = useCallback(() => {
    sessionStorage.removeItem("recommendarr_token");
    setApiToken(null);
    setAuthUser(null);
    setView("tonight");
    addToast("Signed out.", "success");
  }, [addToast]);

  // Open detail modal
  const openDetail = useCallback((item) => {
    setModalItem(item);
    setModalDetail(null);
    setRequestResult(null);
    setModalLoading(true);
    api.detail(item.tmdb_id, item.media_type || "movie")
      .then(d => setModalDetail(d))
      .catch(() => {})
      .finally(() => setModalLoading(false));
  }, []);

  // Close modal
  const closeModal = useCallback(() => {
    setModalItem(null);
    setModalDetail(null);
    setRequestResult(null);
  }, []);

  // Seerr request
  const handleRequest = useCallback((tmdbId, mediaType) => {
    setRequesting(true);
    api.addToLibrary(tmdbId, mediaType)
      .then(data => {
        setRequestResult({ success: true, already_exists: data.already_exists });
        const msg = data.already_exists ? `"${data.title}" already in library` : `Added "${data.title}" to ${data.instance}`;
        addToast(msg, data.already_exists ? "info" : "success");
      })
      .catch(err => {
        setRequestResult({ success: false, error: err.message });
        addToast(`Add failed: ${err.message}`, "error");
      })
      .finally(() => setRequesting(false));
  }, [addToast]);

  // Feedback from detail modal
  const handleModalFeedback = useCallback((item, action) => {
    if (!selectedUser || !item?.tmdb_id) return;
    const username = selectedUser;
    if (action === null) {
      // Remove feedback
      api.removeFeedback(username, item.tmdb_id).then(() => {
        setModalItem(prev => prev ? { ...prev, user_feedback: null } : prev);
        addToast("Feedback removed", "info");
      }).catch(() => {});
    } else {
      api.submitFeedback(username, {
        tmdb_id: item.tmdb_id,
        media_type: item.media_type || "movie",
        action,
        title: item.title || "",
        genres: (item.genres || []).map(g => typeof g === "string" ? g : g.name),
      }).then(() => {
        setModalItem(prev => prev ? { ...prev, user_feedback: action } : prev);
        addToast(action === "up" ? "Liked!" : "Disliked", action === "up" ? "success" : "info");
      }).catch(() => {});
    }
  }, [selectedUser, addToast]);

  const navItems = [
    { id: "tonight", label: "Watch Tonight", icon: Play, section: "Recommendations" },
    { id: "grab", label: "Worth Grabbing", icon: Download, section: "Recommendations" },
    { id: "rediscover", label: "Rediscover", icon: RefreshCw, section: "Recommendations" },
    { id: "mood", label: "Mood Match", icon: Sparkles, section: "Discovery" },
    { id: "trending", label: "Trending", icon: TrendingUp, section: "Discovery" },
    { id: "collections", label: "Collections", icon: Layers, section: "Discovery" },
    { id: "watchlist", label: "Watchlist", icon: Bookmark, section: "Discovery" },
    { id: "profile", label: "Taste Profile", icon: Heart, section: "Profile" },
    { id: "admin", label: "System Settings", icon: Settings, section: "Admin" },
  ];

  let currentSection = "";

  const renderPage = () => {
    switch (view) {
      case "tonight":
      case "grab":
      case "rediscover":
        return <RecommendationsPage user={selectedUser} mode={view} onCardClick={openDetail} />;
      case "mood":
        return <MoodPage user={selectedUser} onCardClick={openDetail} />;
      case "trending":
        return <TrendingPage onCardClick={openDetail} subtab={hashSubtab} onSubtabChange={setSubtab} />;
      case "collections":
        return <CollectionsPage user={selectedUser} onCardClick={openDetail} />;
      case "watchlist":
        return <WatchlistPage user={selectedUser} onCardClick={openDetail} />;
      case "profile":
        return <TasteProfilePage user={selectedUser} />;
      case "admin":
        return <AdminPage subtab={hashSubtab} onSubtabChange={setSubtab} user={authUser?.username} />;
      default:
        return <RecommendationsPage user={selectedUser} mode="tonight" onCardClick={openDetail} />;
    }
  };

  return (
    <>
      <style>{cssText}</style>
      <div className="app-layout">
        {/* Mobile hamburger */}
        <button className="mobile-menu-btn" onClick={() => setMobileMenuOpen(o => !o)}>
          {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
        <div className={`sidebar-overlay ${mobileMenuOpen ? 'open' : ''}`} onClick={() => setMobileMenuOpen(false)} />

        {/* Sidebar */}
        <nav className={`sidebar ${mobileMenuOpen ? 'open' : ''}`}>
          <div className="sidebar-brand">
            <div className="logo-icon"><Film size={16} /></div>
            <h1>Recommendarr</h1>
          </div>
          <div className="sidebar-user">
            {authLoading ? (
              <div className="auth-loading"><Loader2 size={16} className="spin" /> Checking session...</div>
            ) : authUser ? (
              <>
              <div className="auth-user-info">
                {authUser.thumb ? (
                  <img src={authUser.thumb} alt="" className="auth-avatar" />
                ) : (
                  <div className="auth-avatar-placeholder">{(authUser.username || "?")[0].toUpperCase()}</div>
                )}
                <div className="auth-user-details">
                  <span className="auth-username">{authUser.username}{authUser.is_admin ? " ★" : ""}</span>
                  <button className="auth-logout-btn" onClick={handleLogout}><LogOut size={13} /> Sign Out</button>
                </div>
              </div>
              {authUser.is_admin && allUsers.length > 0 && (
                <div className="view-as-switcher">
                  <label><Eye size={10} /> View as</label>
                  <select value={viewAsUser || ""} onChange={e => setViewAsUser(e.target.value || null)}>
                    <option value="">Myself ({authUser.username})</option>
                    {allUsers.filter(u => u.username !== authUser.username).map(u => (
                      <option key={u.username} value={u.username}>{u.friendly_name || u.username}</option>
                    ))}
                  </select>
                </div>
              )}
              </>
            ) : (
              <button className="plex-login-btn" onClick={handlePlexLogin} disabled={loginLoading}>
                {loginLoading ? <><Loader2 size={15} className="spin" /> Connecting...</> : <><LogIn size={15} /> Sign in with Plex</>}
              </button>
            )}
          </div>
          <div className="sidebar-nav">
            {navItems.map(item => {
              const showSection = item.section !== currentSection;
              if (showSection) currentSection = item.section;
              return (
                <div key={item.id}>
                  {showSection && <div className="nav-section-label">{item.section}</div>}
                  <div
                    className={`nav-item ${view === item.id ? 'active' : ''}`}
                    onClick={() => { setView(item.id); setMobileMenuOpen(false); }}
                  >
                    <item.icon size={17} />
                    {item.label}
                  </div>
                </div>
              );
            })}
          </div>
          {authUser && (
            <div className="refresh-section">
              <button
                className={`refresh-btn ${refreshing ? "refreshing" : ""}`}
                onClick={handleRefresh}
                disabled={refreshing}
              >
                {refreshing ? (
                  <><Loader2 size={14} className="spin" /> Refreshing...</>
                ) : (
                  <><RefreshCw size={14} /> Refresh{refreshEstimateMs ? ` (~${Math.ceil(refreshEstimateMs / 1000)}s)` : ""}</>
                )}
              </button>
              {refreshing && refreshProgress && (
                <div className="refresh-progress">
                  <div className="refresh-progress-bar">
                    <div className="refresh-progress-fill" style={{ width: `${(refreshProgress.step / refreshProgress.total) * 100}%` }} />
                  </div>
                  <div className="refresh-progress-label">
                    <span>{refreshProgress.label}</span>
                    <span>{refreshProgress.step}/{refreshProgress.total}</span>
                  </div>
                </div>
              )}
              {!refreshing && lastRefreshAt && (
                <div className="refresh-last">
                  Last: {new Date(lastRefreshAt).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}
                </div>
              )}
            </div>
          )}
          <div className="sidebar-footer">
            Recommendarr v0.5.0
          </div>
        </nav>

        {/* Main */}
        <main className="main-content">
          {isViewingAsOther && (
            <div className="view-as-banner">
              <span><Eye size={12} style={{marginRight: 4, verticalAlign: -2}} /> Viewing as: <strong>{viewAsUser}</strong> — watchlist actions use your own account</span>
              <button onClick={() => setViewAsUser(null)}>Back to self</button>
            </div>
          )}
          {authLoading ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh", color: "var(--text-muted)" }}>
              <Loader2 size={24} className="spin" style={{ marginRight: 10 }} /> Loading...
            </div>
          ) : !authUser ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "60vh", textAlign: "center", gap: 16 }}>
              <Film size={48} style={{ color: "var(--accent)", opacity: 0.7 }} />
              <h2 style={{ fontSize: "1.4rem", fontWeight: 600, color: "var(--text)" }}>Welcome to Recommendarr</h2>
              <p style={{ color: "var(--text-muted)", maxWidth: 360 }}>Sign in with your Plex account to get personalized recommendations.</p>
              <button className="plex-login-btn" onClick={handlePlexLogin} disabled={loginLoading} style={{ maxWidth: 240 }}>
                {loginLoading ? <><Loader2 size={15} className="spin" /> Connecting...</> : <><LogIn size={15} /> Sign in with Plex</>}
              </button>
            </div>
          ) : renderPage()}
        </main>
      </div>

      {/* Detail Modal */}
      {modalItem && (
        <DetailModal
          item={modalItem}
          detail={modalDetail}
          onClose={closeModal}
          onRequest={handleRequest}
          requesting={requesting}
          requestResult={requestResult}
          onFeedback={handleModalFeedback}
          user={selectedUser}
        />
      )}

      {/* Toasts */}
      <ToastContainer toasts={toasts} />
    </>
  );
}
