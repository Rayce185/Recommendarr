import { useState, useEffect, useCallback, useRef } from "react";
import { Film, Tv, Heart, BarChart3, Settings, Play, Download, TrendingUp,
  Sparkles, X, Loader2, RefreshCw, Users, Menu, Bookmark, LogIn, LogOut,
  Search, Globe, Layers } from "lucide-react";
import { api, setApiToken, authFetch, API_BASE } from "./api.js";
import { posterUrl } from "./utils.js";
import { cssText } from "./styles.js";
import { LoadingState } from "./components/StateDisplays.jsx";
import DetailModal from "./components/DetailModal.jsx";
import { ToastContainer, useToast } from "./components/Toast.jsx";
import RecommendationsPage from "./pages/RecommendationsPage.jsx";
import MoodPage from "./pages/MoodPage.jsx";
import TrendingPage from "./pages/TrendingPage.jsx";
import TasteProfilePage from "./pages/TasteProfilePage.jsx";
import WrappedPage from "./pages/WrappedPage.jsx";
import GroupNightPage from "./pages/GroupNightPage.jsx";
import CollectionsPage from "./pages/CollectionsPage.jsx";
import WatchlistPage from "./pages/WatchlistPage.jsx";
import BrowsePage from "./pages/BrowsePage.jsx";
import AdminPage from "./pages/AdminPage.jsx";

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
    { id: "browse", label: "Browse & Search", icon: Search, section: "Discovery" },
    { id: "collections", label: "Collections", icon: Layers, section: "Discovery" },
    { id: "group", label: "Group Night", icon: Users, section: "Discovery" },
    { id: "watchlist", label: "Watchlist", icon: Bookmark, section: "Discovery" },
    { id: "profile", label: "Taste Profile", icon: Heart, section: "Profile" },
    { id: "wrapped", label: "Plex Wrapped", icon: BarChart3, section: "Profile" },
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
      case "group":
        return <GroupNightPage user={selectedUser} allUsers={allUsers} onCardClick={openDetail} />;
      case "browse":
        return <BrowsePage onCardClick={openDetail} />;
      case "watchlist":
        return <WatchlistPage user={selectedUser} onCardClick={openDetail} />;
      case "profile":
        return <TasteProfilePage user={selectedUser} />;
      case "wrapped":
        return <WrappedPage user={selectedUser} />;
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
          loading={modalLoading}
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

