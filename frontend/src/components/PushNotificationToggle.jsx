/**
 * Push notification toggle component.
 *
 * Handles service worker registration, permission requests,
 * and subscribe/unsubscribe flow. Self-contained — just drop in.
 *
 * VAASSEN GmbH / Ray Vaassen
 */

import { useState } from "react";
import { Bell, BellOff, BellRing, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { usePushNotifications } from "../hooks/usePushNotifications.js";

export default function PushNotificationToggle() {
  const { supported, permission, subscribed, loading, subscribe, unsubscribe, sendTest } = usePushNotifications();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  if (!supported) {
    return (
      <div className="pref-row" style={{ opacity: 0.5 }}>
        <div className="pref-label">
          <BellOff size={14} /> Push Notifications
        </div>
        <div className="pref-value">Not supported in this browser</div>
      </div>
    );
  }

  const handleToggle = async () => {
    setTestResult(null);
    if (subscribed) {
      await unsubscribe();
    } else {
      const ok = await subscribe();
      if (!ok && permission === "denied") {
        setTestResult({ ok: false, msg: "Permission denied — check browser settings" });
      }
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const r = await sendTest();
      setTestResult({ ok: true, msg: `Sent to ${r.sent} device${r.sent !== 1 ? "s" : ""}` });
    } catch (err) {
      setTestResult({ ok: false, msg: err.message || "Failed" });
    }
    setTesting(false);
  };

  return (
    <div className="push-toggle-section">
      <div className="pref-row">
        <div className="pref-label">
          {subscribed ? <BellRing size={14} /> : <Bell size={14} />}
          {" "}Push Notifications
        </div>
        <div className="pref-value" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button
            className={`toggle-btn ${subscribed ? "active" : ""}`}
            onClick={handleToggle}
            disabled={loading}
          >
            {loading ? <Loader2 size={12} className="spin" /> : subscribed ? "Enabled" : "Disabled"}
          </button>
          {subscribed && (
            <button
              className="lh-action-btn"
              onClick={handleTest}
              disabled={testing}
              style={{ fontSize: 12, padding: "3px 8px" }}
            >
              {testing ? <Loader2 size={11} className="spin" /> : "Test"}
            </button>
          )}
        </div>
      </div>
      {testResult && (
        <div className={`push-test-result ${testResult.ok ? "ok" : "err"}`}>
          {testResult.ok ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
          {" "}{testResult.msg}
        </div>
      )}
      {permission === "denied" && (
        <div className="push-test-result err">
          <XCircle size={12} /> Browser notifications are blocked. Enable in browser settings.
        </div>
      )}
    </div>
  );
}
