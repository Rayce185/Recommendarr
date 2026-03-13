/* ShareGroupModal — Save and share group night picks
 * Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
 */
import { useState, useRef, useEffect } from "react";
import "../styles/group-night-share.css";
import { Share2, Copy, Check, X, Link2 } from "lucide-react";
import { api } from "../api.js";

export default function ShareGroupModal({ picks, participants, domain, nicknames, onClose }) {
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [shareUrl, setShareUrl] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);
  const titleRef = useRef(null);

  useEffect(() => { titleRef.current?.focus(); }, []);

  const displayNames = participants.map(u => nicknames?.[u] || u).join(", ");

  const handleShare = async () => {
    setSaving(true); setError(null);
    try {
      const data = await api.createGroupSession({
        participants,
        domain,
        picks: picks.map(p => ({
          tmdb_id: p.tmdb_id, media_type: p.media_type,
          title: p.title, poster_path: p.poster_path,
          score: p.score, explanation: p.explanation,
        })),
        title: title.trim() || null,
      });
      const url = `${window.location.origin}${window.location.pathname}#group/${data.code}`;
      setShareUrl(url);
    } catch (e) {
      setError(e.message || "Failed to create share link");
    } finally {
      setSaving(false);
    }
  };

  const copyLink = () => {
    navigator.clipboard.writeText(shareUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="share-modal" onClick={e => e.stopPropagation()}>
        <div className="share-modal-header">
          <h3><Share2 size={18} /> Share Group Night</h3>
          <button className="btn-icon" onClick={onClose}><X size={18} /></button>
        </div>

        {!shareUrl ? (
          <div className="share-modal-body">
            <p className="share-modal-desc">
              Share these {picks.length} picks for {displayNames} with anyone on your server.
            </p>
            <div className="share-modal-field">
              <label>Session Name (optional)</label>
              <input ref={titleRef} value={title} onChange={e => setTitle(e.target.value)}
                placeholder={`Movie night with ${participants.length} people`} maxLength={200}
                onKeyDown={e => { if (e.key === "Enter") handleShare(); }} />
            </div>
            {error && <p className="share-modal-error">{error}</p>}
            <button className="btn btn-primary share-modal-go" onClick={handleShare} disabled={saving}>
              {saving ? "Creating link..." : "Create Share Link"}
            </button>
          </div>
        ) : (
          <div className="share-modal-body">
            <p className="share-modal-desc share-modal-success">Link created!</p>
            <div className="share-link-box">
              <Link2 size={14} />
              <span className="share-link-url">{shareUrl}</span>
              <button className="btn btn-sm" onClick={copyLink}>
                {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
              </button>
            </div>
            <p className="share-modal-hint">
              Anyone logged into your Recommendarr can view this link.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
