/**
 * React hook for Web Push notification management.
 *
 * Handles: service worker registration, VAPID key fetch,
 * push subscription lifecycle, and server sync.
 *
 * VAASSEN GmbH / Ray Vaassen
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../api.js";

/**
 * Convert URL-safe base64 VAPID key to Uint8Array for PushManager.
 */
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

/**
 * @returns {{ supported, permission, subscribed, loading, subscribe, unsubscribe, sendTest }}
 */
export function usePushNotifications() {
  const [supported, setSupported] = useState(false);
  const [permission, setPermission] = useState("default");
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(true);
  const swRef = useRef(null);

  // ── Check support + existing subscription on mount ────────
  useEffect(() => {
    const check = async () => {
      const ok = "serviceWorker" in navigator && "PushManager" in window;
      setSupported(ok);
      if (!ok) {
        setLoading(false);
        return;
      }

      setPermission(Notification.permission);

      try {
        const reg = await navigator.serviceWorker.register("/sw.js");
        swRef.current = reg;
        const sub = await reg.pushManager.getSubscription();
        setSubscribed(!!sub);
      } catch (err) {
        console.error("SW registration failed:", err);
      }
      setLoading(false);
    };
    check();
  }, []);

  // ── Subscribe ─────────────────────────────────────────────
  const subscribe = useCallback(async () => {
    if (!swRef.current) return false;
    setLoading(true);
    try {
      // Request notification permission
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== "granted") {
        setLoading(false);
        return false;
      }

      // Get VAPID key from server
      const { public_key } = await api.pushVapidKey();
      const applicationServerKey = urlBase64ToUint8Array(public_key);

      // Subscribe via Push API
      const sub = await swRef.current.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey,
      });

      const subJson = sub.toJSON();

      // Send subscription to backend
      await api.pushSubscribe({
        endpoint: subJson.endpoint,
        p256dh: subJson.keys.p256dh,
        auth: subJson.keys.auth,
      });

      setSubscribed(true);
      return true;
    } catch (err) {
      console.error("Push subscribe failed:", err);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Unsubscribe ───────────────────────────────────────────
  const unsubscribe = useCallback(async () => {
    if (!swRef.current) return false;
    setLoading(true);
    try {
      const sub = await swRef.current.pushManager.getSubscription();
      if (sub) {
        const subJson = sub.toJSON();
        // Unsubscribe from browser
        await sub.unsubscribe();
        // Remove from backend
        await api.pushUnsubscribe({
          endpoint: subJson.endpoint,
          p256dh: subJson.keys.p256dh,
          auth: subJson.keys.auth,
        });
      }
      setSubscribed(false);
      return true;
    } catch (err) {
      console.error("Push unsubscribe failed:", err);
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Test Push ─────────────────────────────────────────────
  const sendTest = useCallback(async () => {
    try {
      return await api.pushTest({});
    } catch (err) {
      console.error("Test push failed:", err);
      throw err;
    }
  }, []);

  return { supported, permission, subscribed, loading, subscribe, unsubscribe, sendTest };
}
