// ─── Application Styles ──────────────────────────────────────────
const cssText = `
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

  :root {
    color-scheme: dark;
    --bg-deep: #0a0b0f;
    --bg-primary: #10111a;
    --bg-surface: #181a27;
    --bg-elevated: #1e2035;
    --bg-hover: #252840;
    --bg-card: #1a1c2e;
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

  /* Group Night */
  .group-selector {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 24px;
  }
  .group-selector-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
  }
  .group-selector-label {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }
  .group-selector-count {
    font-size: 12px;
    color: var(--text-muted);
    background: var(--bg);
    padding: 2px 8px;
    border-radius: 10px;
  }
  .group-selector-actions {
    margin-left: auto;
    display: flex;
    gap: 8px;
  }
  .btn-text {
    background: none;
    border: none;
    color: var(--accent);
    font-size: 12px;
    cursor: pointer;
    padding: 2px 6px;
    border-radius: 4px;
  }
  .btn-text:hover { background: var(--accent-dim); }
  .group-user-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
  }
  .group-user-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg);
    cursor: pointer;
    transition: all 0.15s ease;
    user-select: none;
  }
  .group-user-chip:hover { border-color: var(--accent); background: rgba(99,102,241,0.05); }
  .group-user-chip.selected {
    border-color: var(--accent);
    background: var(--accent-dim);
  }
  .group-user-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
  }
  .group-user-avatar-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--surface);
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 600;
  }
  .group-user-name {
    font-size: 13px;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
  }
  .group-self-badge {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--accent);
    background: rgba(99,102,241,0.15);
    padding: 1px 5px;
    border-radius: 4px;
    font-weight: 600;
    flex-shrink: 0;
  }
  .group-check {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 2px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all 0.15s ease;
  }
  .group-check.checked {
    border-color: var(--accent);
    background: var(--accent);
    color: white;
  }
  .group-controls {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  .group-go-btn {
    flex: 1;
    padding: 10px 16px !important;
    font-size: 14px !important;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
  .group-results-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 16px;
  }
  .group-results-count {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }
  .group-results-hint {
    font-size: 11px;
    color: var(--text-muted);
  }
  .group-card-wrapper {
    display: flex;
    flex-direction: column;
  }
  .group-score-breakdown {
    background: var(--surface);
    border: 1px solid var(--border);
    border-top: none;
    border-radius: 0 0 8px 8px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .group-user-score {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .group-user-score-name {
    font-size: 10px;
    color: var(--text-muted);
    width: 55px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
  }
  .group-user-score-bar {
    flex: 1;
    height: 4px;
    background: var(--bg);
    border-radius: 2px;
    overflow: hidden;
  }
  .group-user-score-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
  }
  .group-user-score-pct {
    font-size: 10px;
    font-weight: 600;
    width: 28px;
    text-align: right;
    flex-shrink: 0;
  }
  @media (max-width: 768px) {
    .group-user-grid { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
    .group-controls { flex-direction: column; }
    .group-go-btn { width: 100%; }
    .group-results-header { flex-direction: column; gap: 4px; }
  }

  /* Plex Wrapped */
  .wrapped-hero {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }
  .wrapped-stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
  }
  .wrapped-stat-card.hero {
    grid-column: span 2;
    background: linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.1));
    border-color: var(--accent);
  }
  .wrapped-stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--text);
    line-height: 1.1;
  }
  .wrapped-stat-card.hero .wrapped-stat-value {
    font-size: 36px;
    color: var(--accent);
  }
  .wrapped-stat-label {
    font-size: 12px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 4px;
  }
  .wrapped-stat-sub {
    font-size: 11px;
    color: var(--text-muted);
    opacity: 0.7;
    margin-top: 2px;
  }
  .wrapped-insight-row {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 24px;
  }
  .wrapped-insight {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-muted);
    background: var(--surface);
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid var(--border);
  }
  .wrapped-insight strong { color: var(--text); }
  .wrapped-insight svg { color: var(--accent); flex-shrink: 0; }
  .wrapped-chart-section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
  }
  .wrapped-chart-section h3 {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    margin: 0 0 12px 0;
  }
  .wrapped-chart { overflow: hidden; }
  .wrapped-chart-row {
    display: flex;
    gap: 16px;
    margin-bottom: 0;
  }
  .wrapped-genre-bars { display: flex; flex-direction: column; gap: 8px; }
  .wrapped-genre-row { display: flex; align-items: center; gap: 10px; }
  .wrapped-genre-name {
    width: 100px;
    font-size: 12px;
    color: var(--text);
    text-align: right;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 0;
  }
  .wrapped-genre-bar-track {
    flex: 1;
    height: 8px;
    background: var(--bg);
    border-radius: 4px;
    overflow: hidden;
  }
  .wrapped-genre-bar-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 4px;
    transition: width 0.4s ease;
  }
  .wrapped-genre-count {
    width: 30px;
    font-size: 11px;
    color: var(--text-muted);
    text-align: right;
    flex-shrink: 0;
  }
  .wrapped-top-list { display: flex; flex-direction: column; gap: 8px; }
  .wrapped-top-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
  }
  .wrapped-top-item:last-child { border-bottom: none; }
  .wrapped-rank {
    font-size: 14px;
    font-weight: 700;
    color: var(--accent);
    width: 30px;
    text-align: center;
    flex-shrink: 0;
  }
  .wrapped-top-poster {
    width: 36px;
    height: 54px;
    border-radius: 4px;
    object-fit: cover;
    flex-shrink: 0;
  }
  .wrapped-top-info { flex: 1; }
  .wrapped-top-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text);
    display: block;
  }
  .wrapped-top-year {
    font-size: 11px;
    color: var(--text-muted);
  }
  .wrapped-top-plays {
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    flex-shrink: 0;
  }
  .wrapped-year-select {
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    cursor: pointer;
  }
  @media (max-width: 768px) {
    .wrapped-hero { grid-template-columns: 1fr 1fr; }
    .wrapped-stat-card.hero { grid-column: span 2; }
    .wrapped-chart-row { flex-direction: column; }
    .wrapped-insight-row { flex-direction: column; }
  }
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
    padding: 5px 12px;
    border-radius: 16px;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.04);
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    transition: all 0.15s;
    font-weight: 500;
  }
  .filter-chip:hover { border-color: rgba(255,255,255,0.3); background: rgba(255,255,255,0.08); }
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
  .filter-chip.chip-active {
    background: rgba(245, 158, 11, 0.15);
    border-color: rgba(245, 158, 11, 0.5);
    color: #f59e0b;
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


export { cssText };
