import { useState, useEffect, useCallback } from "react";
import { Film, Tv, Heart, BarChart3, Settings, Play, Download, TrendingUp,
  Sparkles, X, Loader2, RefreshCw, Users, Menu, Bookmark, LogIn, LogOut,
  Search, Globe, Layers, Eye, Upload, Activity, CalendarDays} from "lucide-react";
import { api, API_BASE } from "./api.js";
import { posterUrl } from "./utils.js";
import "./styles/index.css";
import { LoadingState } from "./components/StateDisplays.jsx";
import DetailModal from "./components/DetailModal.jsx";
import { ToastContainer, useToast } from "./components/Toast.jsx";
import { useAuth } from "./hooks/useAuth.js";
import { useRefresh } from "./hooks/useRefresh.js";
import { useDetailModal } from "./hooks/useDetailModal.js";
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
import SocialPage from "./pages/SocialPage.jsx";
import ListImportPage from "./pages/ListImportPage.jsx";
import PulsePage from "./pages/PulsePage.jsx";
import CalendarPage from "./pages/CalendarPage.jsx";
import WorldCinemaPage from "./pages/WorldCinemaPage.jsx";

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

  const setView = useCallback((newView, subtab) => {
    setViewRaw(newView);
    setHashSubtab(subtab || null);
    const hash = subtab ? `${newView}/${subtab}` : newView;
    window.location.hash = hash;
  }, []);

  const setSubtab = useCallback((subtab) => {
    setHashSubtab(subtab);
    const hash = subtab ? `${view}/${subtab}` : view;
    window.location.hash = hash;
  }, [view]);

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

  // ── Toast + Auth + Refresh hooks ──────────────────────────
  const { toasts, addToast } = useToast();
  const {
    authUser, authLoading, loginLoading,
    viewAsUser, setViewAsUser, allUsers,
    handlePlexLogin, handleLogout: authLogout,
  } = useAuth(addToast);
  const { refreshing, refreshProgress, lastRefreshAt, refreshEstimateMs, handleRefresh } = useRefresh(authUser, addToast);

  const selectedUser = viewAsUser || authUser?.username || null;
  const isViewingAsOther = viewAsUser && viewAsUser !== authUser?.username;

  const {
    modalItem, modalDetail, modalLoading,
    requesting, requestResult,
    openDetail, closeModal, handleRequest, handleFeedback: handleModalFeedback,
  } = useDetailModal(selectedUser, addToast);

  // ── Wrap logout to also reset view ──────────────────────────
  const handleLogout = useCallback(() => {
    authLogout();
    setView("tonight");
  }, [authLogout, setView]);

  const navItems = [
    { id: "tonight", label: "Watch Tonight", icon: Play, section: "Recommendations" },
    { id: "grab", label: "Worth Grabbing", icon: Download, section: "Recommendations" },
    { id: "rediscover", label: "Rediscover", icon: RefreshCw, section: "Recommendations" },
    { id: "mood", label: "Mood Match", icon: Sparkles, section: "Discovery" },
    { id: "trending", label: "Trending", icon: TrendingUp, section: "Discovery" },
    { id: "browse", label: "Browse & Search", icon: Search, section: "Discovery" },
    { id: "world-cinema", label: "World Cinema", icon: Globe, section: "Discovery" },
    { id: "collections", label: "Collections", icon: Layers, section: "Discovery" },
    { id: "group", label: "Group Night", icon: Users, section: "Discovery" },
    { id: "watchlist", label: "Watchlist", icon: Bookmark, section: "Discovery" },
    { id: "import", label: "List Import", icon: Upload, section: "Discovery" },
    { id: "pulse", label: "Cultural Pulse", icon: Activity, section: "Discovery" },
    { id: "calendar", label: "Coming Soon", icon: CalendarDays, section: "Discovery" },
    { id: "profile", label: "Taste Profile", icon: Heart, section: "Profile" },
    { id: "wrapped", label: "Plex Wrapped", icon: BarChart3, section: "Profile" },
    { id: "social", label: "Social", icon: Users, section: "Profile" },
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
      case "world-cinema":
        return <WorldCinemaPage user={selectedUser} onCardClick={openDetail} />;
      case "watchlist":
        return <WatchlistPage user={selectedUser} onCardClick={openDetail} />;
      case "profile":
        return <TasteProfilePage user={selectedUser} />;
      case "wrapped":
        return <WrappedPage user={selectedUser} />;
      case "social":
        return <SocialPage user={selectedUser} />;
      case "pulse":
        return <PulsePage isAdmin={authUser?.is_admin} />;
      case "calendar":
        return <CalendarPage onCardClick={openDetail} />;
      case "import":
        return <ListImportPage onCardClick={openDetail} />;
      case "admin":
        return <AdminPage subtab={hashSubtab} onSubtabChange={setSubtab} user={authUser?.username} />;
      default:
        return <RecommendationsPage user={selectedUser} mode="tonight" onCardClick={openDetail} />;
    }
  };

  return (
    <>

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

