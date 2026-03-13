import { useState, useEffect, useCallback, useRef } from "react";
import { api, setApiToken } from "../api.js";

/**
 * useAuth — Plex OAuth authentication hook
 * Handles session hydration, Plex PIN-based login, logout, and user list for admin "View as"
 */
export function useAuth(addToast) {
  const [authUser, setAuthUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [loginLoading, setLoginLoading] = useState(false);
  const [viewAsUser, setViewAsUser] = useState(null);
  const [allUsers, setAllUsers] = useState([]);
  const pollRef = useRef(null);
  const popupRef = useRef(null);

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

  // ── Plex OAuth login (matches Overseerr flow) ───────────────
  const handlePlexLogin = useCallback(async () => {
    setLoginLoading(true);
    try {
      let clientId = sessionStorage.getItem("plex-client-id");
      if (!clientId) {
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

      const pinResp = await fetch("https://plex.tv/api/v2/pins?strong=true", {
        method: "POST",
        headers: plexHeaders,
      });
      if (!pinResp.ok) throw new Error("Failed to create PIN");
      const pinData = await pinResp.json();
      const pinId = pinData.id;
      const pinCode = pinData.code;

      const authUrl = `https://app.plex.tv/auth#!?clientID=${encodeURIComponent(clientId)}&code=${pinCode}&context%5Bdevice%5D%5Bproduct%5D=Recommendarr`;
      const popup = window.open(authUrl, "PlexAuth", "width=600,height=700,scrollbars=yes");
      popupRef.current = popup;

      pollRef.current = setInterval(async () => {
        try {
          const checkResp = await fetch(`https://plex.tv/api/v2/pins/${pinId}`, {
            headers: plexHeaders,
          });
          if (!checkResp.ok) return;
          const checkData = await checkResp.json();

          if (checkData.authToken) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            if (popupRef.current && !popupRef.current.closed) popupRef.current.close();

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
            clearInterval(pollRef.current);
            pollRef.current = null;
            setLoginLoading(false);
          }
        } catch (err) { /* keep polling */ }
      }, 1000);

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
    addToast("Signed out.", "success");
  }, [addToast]);

  return {
    authUser, authLoading, loginLoading,
    viewAsUser, setViewAsUser, allUsers,
    handlePlexLogin, handleLogout,
  };
}
