import { useState, useEffect, useCallback } from "react";
import { Activity, Film, Tv, Clock, Loader2 } from "lucide-react";
import { authFetch, API_BASE } from "../api.js";

function timeAgo(timestamp) {
  if (!timestamp) return "";
  const diff = Math.floor(Date.now() / 1000) - timestamp;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(timestamp * 1000).toLocaleDateString();
}

function FriendActivityFeed({ user }) {
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [friendCount, setFriendCount] = useState(0);

  const load = useCallback(async () => {
    if (!user?.username) return;
    setLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/friends/activity?limit=30`);
      const data = await res.json();
      setActivity(data.activity || []);
      setFriendCount(data.friend_count || 0);
    } catch (err) {
      console.error("Failed to load friend activity:", err);
    } finally {
      setLoading(false);
    }
  }, [user?.username]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 30, color: "var(--text-muted)" }}>
        <Loader2 size={20} className="spin" /> Loading friend activity...
      </div>
    );
  }

  if (friendCount === 0) {
    return (
      <div style={{ textAlign: "center", padding: 30, color: "var(--text-muted)", fontSize: 13 }}>
        Add some friends from the Taste Neighbors section to see what they're watching!
      </div>
    );
  }

  if (activity.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 30, color: "var(--text-muted)", fontSize: 13 }}>
        No recent activity from your {friendCount} friend{friendCount !== 1 ? "s" : ""}.
      </div>
    );
  }

  return (
    <div className="wrapped-chart-section">
      <h3><Activity size={16} style={{ verticalAlign: "text-bottom", marginRight: 4 }} />
        Friend Activity
        <span style={{ fontSize: 11, fontWeight: 400, color: "var(--text-muted)", marginLeft: 6 }}>
          {friendCount} friend{friendCount !== 1 ? "s" : ""}
        </span>
      </h3>
      <div className="friend-activity-list">
        {activity.map((a, i) => (
          <div key={`${a.username}-${a.rating_key}-${i}`} className="friend-activity-item">
            <div className="friend-activity-avatar">
              {a.user_thumb ? (
                <img src={a.user_thumb} alt="" className="group-user-avatar" />
              ) : (
                <div className="group-user-avatar group-user-avatar-placeholder">
                  {(a.friendly_name || a.username).charAt(0).toUpperCase()}
                </div>
              )}
            </div>
            <div className="friend-activity-body">
              <span className="friend-activity-user">{a.friendly_name || a.username}</span>
              <span className="friend-activity-action">
                {a.percent_complete >= 90 ? "watched" : a.percent_complete > 0 ? "started" : "played"}
              </span>
              <span className="friend-activity-title">
                {a.media_type === "episode" ? <Tv size={11} style={{ verticalAlign: "text-bottom" }} /> :
                 <Film size={11} style={{ verticalAlign: "text-bottom" }} />}
                {" "}{a.title}{a.year ? ` (${a.year})` : ""}
              </span>
            </div>
            <div className="friend-activity-meta">
              <Clock size={10} /> {timeAgo(a.watched_at)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default FriendActivityFeed;
