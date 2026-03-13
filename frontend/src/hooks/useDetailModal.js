import { useState, useCallback } from "react";
import { api } from "../api.js";

/**
 * useDetailModal — Detail modal state and handlers
 * Handles opening/closing detail modal, Seerr requests, and user feedback
 */
export function useDetailModal(selectedUser, addToast) {
  const [modalItem, setModalItem] = useState(null);
  const [modalDetail, setModalDetail] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [requestResult, setRequestResult] = useState(null);

  const openDetail = useCallback((item) => {
    setModalItem(item);
    setModalDetail(null);
    setRequestResult(null);
    setModalLoading(true);
    api.detail(item.tmdb_id, item.media_type || "movie")
      .then(d => setModalDetail(d))
      .catch(() => {})
      .finally(() => setModalLoading(false));
  }, []);

  const closeModal = useCallback(() => {
    setModalItem(null);
    setModalDetail(null);
    setRequestResult(null);
  }, []);

  const handleRequest = useCallback((tmdbId, mediaType) => {
    setRequesting(true);
    api.addToLibrary(tmdbId, mediaType)
      .then(data => {
        setRequestResult({ success: true, already_exists: data.already_exists });
        const msg = data.already_exists ? `"${data.title}" already in library` : `Added "${data.title}" to ${data.instance}`;
        addToast(msg, data.already_exists ? "info" : "success");
      })
      .catch(err => {
        setRequestResult({ success: false, error: err.message });
        addToast(`Add failed: ${err.message}`, "error");
      })
      .finally(() => setRequesting(false));
  }, [addToast]);

  const handleFeedback = useCallback((item, action) => {
    if (!selectedUser || !item?.tmdb_id) return;
    if (action === null) {
      api.removeFeedback(selectedUser, item.tmdb_id).then(() => {
        setModalItem(prev => prev ? { ...prev, user_feedback: null } : prev);
        addToast("Feedback removed", "info");
      }).catch(() => {});
    } else {
      api.submitFeedback(selectedUser, {
        tmdb_id: item.tmdb_id,
        media_type: item.media_type || "movie",
        action,
        title: item.title || "",
        genres: (item.genres || []).map(g => typeof g === "string" ? g : g.name),
      }).then(() => {
        setModalItem(prev => prev ? { ...prev, user_feedback: action } : prev);
        addToast(action === "up" ? "Liked!" : "Disliked", action === "up" ? "success" : "info");
      }).catch(() => {});
    }
  }, [selectedUser, addToast]);

  return {
    modalItem, modalDetail, modalLoading,
    requesting, requestResult,
    openDetail, closeModal, handleRequest, handleFeedback,
  };
}
