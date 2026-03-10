import { useState, useEffect, useCallback } from "react";
import { HeartPulse, BarChart3, Sunset, Skull, Shield, Loader2 } from "lucide-react";
import Skeleton from "../components/Skeleton.jsx";
import { ErrorState } from "../components/StateDisplays.jsx";
import { api } from "../api.js";
import OverviewTab from "./library-health/OverviewTab.jsx";
import SunsetTab from "./library-health/SunsetTab.jsx";
import GraveyardTab from "./library-health/GraveyardTab.jsx";
import HealthAdminTab from "./library-health/HealthAdminTab.jsx";

function LibraryHealthPage({ subtab: initialSubtab, onSubtabChange, user }) {
  const [activeTab, setActiveTabRaw] = useState(initialSubtab || "overview");
  const setActiveTab = (t) => { setActiveTabRaw(t); onSubtabChange?.(t); };
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await api.healthStats();
      setStats(s);
    } catch (err) {
      setError(err.message || "Failed to load library health data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const isAdmin = user?.is_admin === true;

  const tabs = [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "sunset", label: "Sunset Zone", icon: Sunset, badge: stats?.zones?.sunset },
    { id: "graveyard", label: "Graveyard", icon: Skull, badge: stats?.items_kicked },
    ...(isAdmin ? [{ id: "admin", label: "Admin", icon: Shield }] : []),
  ];

  if (loading) return (
    <>
      <div className="page-header"><h2><HeartPulse size={20} /> Library Health</h2></div>
      <div className="page-body">
        <div className="skeleton-admin-panel">
          <Skeleton.Line width="60%" height="1.2rem" />
          <Skeleton.Table rows={4} cols={3} />
        </div>
      </div>
    </>
  );

  if (error) return (
    <>
      <div className="page-header"><h2><HeartPulse size={20} /> Library Health</h2></div>
      <div className="page-body"><ErrorState message={error} onRetry={load} /></div>
    </>
  );

  return (
    <>
      <div className="page-header">
        <h2><HeartPulse size={20} /> Library Health</h2>
        <p>{stats?.total_items || 0} items tracked &middot; {stats?.scored_items || 0} scored &middot; avg vitality {stats?.avg_score ?? "—"}</p>
      </div>
      <div className="page-body">
        <div className="settings-tabs">
          {tabs.map(t => (
            <button key={t.id} className={`settings-tab ${activeTab === t.id ? "active" : ""}`} onClick={() => setActiveTab(t.id)}>
              <t.icon size={14} /> {t.label}
              {t.badge > 0 && <span className="lh-tab-badge">{t.badge}</span>}
            </button>
          ))}
        </div>

        {activeTab === "overview" && <OverviewTab stats={stats} onRefresh={load} />}
        {activeTab === "sunset" && <SunsetTab user={user} />}
        {activeTab === "graveyard" && <GraveyardTab isAdmin={isAdmin} />}
        {activeTab === "admin" && isAdmin && <HealthAdminTab onStatsRefresh={load} />}
      </div>
    </>
  );
}

export default LibraryHealthPage;
