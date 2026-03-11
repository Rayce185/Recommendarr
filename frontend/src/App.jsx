import { useState, useEffect, useCallback, useRef, lazy, Suspense } from "react";
import { Film, Loader2, LogIn, Eye } from "lucide-react";
import { api } from "./api.js";
import "./styles/index.css";
import { LoadingState } from "./components/StateDisplays.jsx";
import DetailModal from "./components/DetailModal.jsx";
import { ToastContainer, useToast } from "./components/Toast.jsx";
import { useAuth } from "./hooks/useAuth.js";
import { useRefresh } from "./hooks/useRefresh.js";
import { useDetailModal } from "./hooks/useDetailModal.js";
import Sidebar from "./components/Sidebar.jsx";
import OnboardingWizard from "./components/OnboardingWizard.jsx";
import { setup } from "./api.js";

const RecommendationsPage = lazy(() => import("./pages/RecommendationsPage.jsx"));
const MoodPage = lazy(() => import("./pages/MoodPage.jsx"));
const TrendingPage = lazy(() => import("./pages/TrendingPage.jsx"));
const TasteProfilePage = lazy(() => import("./pages/TasteProfilePage.jsx"));
const WrappedPage = lazy(() => import("./pages/WrappedPage.jsx"));
const GroupNightPage = lazy(() => import("./pages/GroupNightPage.jsx"));
const CollectionsPage = lazy(() => import("./pages/CollectionsPage.jsx"));
const WatchlistPage = lazy(() => import("./pages/WatchlistPage.jsx"));
const BrowsePage = lazy(() => import("./pages/BrowsePage.jsx"));
const AdminPage = lazy(() => import("./pages/AdminPage.jsx"));
const SocialPage = lazy(() => import("./pages/SocialPage.jsx"));
const ListImportPage = lazy(() => import("./pages/ListImportPage.jsx"));
const PulsePage = lazy(() => import("./pages/PulsePage.jsx"));
const CalendarPage = lazy(() => import("./pages/CalendarPage.jsx"));
const HistoryPage = lazy(() => import("./pages/HistoryPage.jsx"));
const WorldCinemaPage = lazy(() => import("./pages/WorldCinemaPage.jsx"));
const DiscoveryFeedPage = lazy(() => import("./pages/DiscoveryFeedPage.jsx"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage.jsx"));
const LibraryHealthPage = lazy(() => import("./pages/LibraryHealthPage.jsx"));
const TasteComparePage = lazy(() => import("./pages/TasteComparePage.jsx"));

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
    window.location.hash = subtab ? `${newView}/${subtab}` : newView;
  }, []);

  const setSubtab = useCallback((subtab) => {
    setHashSubtab(subtab);
    window.location.hash = subtab ? `${view}/${subtab}` : view;
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
  const [navBadges, setNavBadges] = useState({});
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape" && mobileMenuOpen) setMobileMenuOpen(false); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [mobileMenuOpen]);

  const [appVersion, setAppVersion] = useState("…");
  useEffect(() => {
    api.health().then(d => d?.version && setAppVersion(d.version)).catch(() => {});
  }, []);

  // ── Onboarding wizard ──────────────────────────────────────
  const [showWizard, setShowWizard] = useState(false);
  useEffect(() => {
    if (!authUser?.is_admin) { setShowWizard(false); return; }
    setup.status()
      .then(s => { if (!s.complete) setShowWizard(true); })
      .catch(() => {});
  }, [authUser]);

  // ── Toast + Auth + Refresh + Detail hooks ─────────────────
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

  const handleLogout = useCallback(() => {
    authLogout();
    setView("tonight");
  }, [authLogout, setView]);

  // ── Page router ─────────────────────────────────────────────
  const renderPage = () => {
    switch (view) {
      case "tonight": case "grab": case "rediscover":
        return <RecommendationsPage user={selectedUser} mode={view} onCardClick={openDetail} />;
      case "mood":       return <MoodPage user={selectedUser} onCardClick={openDetail} />;
      case "trending":   return <TrendingPage onCardClick={openDetail} subtab={hashSubtab} onSubtabChange={setSubtab} username={selectedUser} />;
      case "collections": return <CollectionsPage user={selectedUser} onCardClick={openDetail} />;
      case "group":      return <GroupNightPage user={selectedUser} allUsers={allUsers} onCardClick={openDetail} shareCode={hashSubtab} onSubtabChange={setSubtab} />;
      case "browse":     return <BrowsePage onCardClick={openDetail} />;
      case "world-cinema": return <WorldCinemaPage user={selectedUser} onCardClick={openDetail} />;
      case "watchlist":  return <WatchlistPage user={selectedUser} onCardClick={openDetail} />;
      case "profile":    return <TasteProfilePage user={selectedUser} />;
      case "compare":   return <TasteComparePage user={selectedUser} />;
      case "wrapped":    return <WrappedPage user={selectedUser} />;
      case "social":     return <SocialPage user={selectedUser} />;
      case "history":    return <HistoryPage user={selectedUser} onCardClick={openDetail} />;
      case "pulse":      return <PulsePage isAdmin={authUser?.is_admin} />;
      case "calendar":   return <CalendarPage onCardClick={openDetail} />;
      case "feed":       return <DiscoveryFeedPage user={selectedUser} onCardClick={openDetail} />;
      case "import":     return <ListImportPage onCardClick={openDetail} />;
      case "notifications": return <NotificationsPage onNavigate={setView} />;
      case "library-health": return <LibraryHealthPage subtab={hashSubtab} onSubtabChange={setSubtab} user={authUser} />;
      case "admin":      return <AdminPage subtab={hashSubtab} onSubtabChange={setSubtab} user={authUser?.username} />;
      default:           return <RecommendationsPage user={selectedUser} mode="tonight" onCardClick={openDetail} />;
    }
  };

  // Sidebar badge: fetch sunset count for Library Health nav item
  useEffect(() => {
    if (!authUser) { setNavBadges({}); return; }
    const fetchBadges = () => {
      api.healthStats().then(s => {
        const sunset = s?.zones?.sunset || 0;
        setNavBadges(prev => sunset !== prev["library-health"] ? { ...prev, "library-health": sunset } : prev);
      }).catch(() => {});
    };
    fetchBadges();
    const iv = setInterval(fetchBadges, 120000); // refresh every 2min
    return () => clearInterval(iv);
  }, [authUser]);

  return (
    <>
      <div className="app-layout">
        <Sidebar
          view={view} setView={setView} navBadges={navBadges}
          mobileMenuOpen={mobileMenuOpen} setMobileMenuOpen={setMobileMenuOpen}
          authUser={authUser} authLoading={authLoading} loginLoading={loginLoading}
          handlePlexLogin={handlePlexLogin} handleLogout={handleLogout}
          viewAsUser={viewAsUser} setViewAsUser={setViewAsUser} allUsers={allUsers}
          refreshing={refreshing} refreshProgress={refreshProgress}
          lastRefreshAt={lastRefreshAt} refreshEstimateMs={refreshEstimateMs}
          handleRefresh={handleRefresh} appVersion={appVersion}
        />

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
          ) : <Suspense fallback={<LoadingState />}>{renderPage()}</Suspense>}
        </main>
      </div>

      {modalItem && (
        <DetailModal
          item={modalItem} detail={modalDetail} loading={modalLoading}
          onClose={closeModal} onRequest={handleRequest}
          requesting={requesting} requestResult={requestResult}
          onFeedback={handleModalFeedback} user={selectedUser}
        />
      )}
      <ToastContainer toasts={toasts} />
      {showWizard && (
        <OnboardingWizard
          onComplete={() => setShowWizard(false)}
          onRefresh={handleRefresh}
        />
      )}
    </>
  );
}
