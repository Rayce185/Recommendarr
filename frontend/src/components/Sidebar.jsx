import { Film, X, Loader2, RefreshCw, Menu, LogIn, LogOut, Eye } from "lucide-react";
import navItems from "../navConfig.js";
import NotificationBell from "./NotificationBell.jsx";
import ThemeToggle from "./ThemeToggle.jsx";

function Sidebar({
  view, setView, mobileMenuOpen, setMobileMenuOpen,
  authUser, authLoading, loginLoading,
  handlePlexLogin, handleLogout,
  viewAsUser, setViewAsUser, allUsers,
  refreshing, refreshProgress, lastRefreshAt, refreshEstimateMs, handleRefresh,
  appVersion, navBadges = {},
}) {
  let currentSection = "";

  return (
    <>
      <button className="mobile-menu-btn" onClick={() => setMobileMenuOpen(o => !o)}>
        {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      <div className={`sidebar-overlay ${mobileMenuOpen ? 'open' : ''}`} onClick={() => setMobileMenuOpen(false)} />

      <nav className={`sidebar ${mobileMenuOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <div className="logo-icon"><Film size={16} /></div>
          <h1>Recommendarr</h1>
          {authUser && <NotificationBell onNavigate={v => { setView(v); setMobileMenuOpen(false); }} />}
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
          {navItems.filter(item => item.section !== "Admin" || authUser?.is_admin).map(item => {
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
                  {navBadges[item.id] > 0 && <span className="nav-badge">{navBadges[item.id]}</span>}
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
                <><RefreshCw size={14} /> Refresh All{refreshEstimateMs ? ` (~${Math.ceil(refreshEstimateMs / 1000)}s)` : ""}</>
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
          <span>Recommendarr v{appVersion}</span>
          <ThemeToggle />
        </div>
      </nav>
    </>
  );
}

export default Sidebar;
