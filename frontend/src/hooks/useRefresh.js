import { useState, useEffect, useCallback, useRef } from "react";
import { api, API_BASE } from "../api.js";

/**
 * useRefresh — SSE-based recommendation refresh hook
 * Handles starting refresh jobs, streaming progress via SSE, and tracking last refresh time
 */
export function useRefresh(authUser, addToast) {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState(null);
  const [lastRefreshAt, setLastRefreshAt] = useState("");
  const [refreshEstimateMs, setRefreshEstimateMs] = useState(0);
  const refreshEventSourceRef = useRef(null);

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

  return { refreshing, refreshProgress, lastRefreshAt, refreshEstimateMs, handleRefresh };
}
