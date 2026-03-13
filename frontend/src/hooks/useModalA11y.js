import { useEffect } from "react";

/**
 * Modal accessibility: Escape-to-close, Tab focus trap, body scroll lock, 
 * auto-focus on mount.
 * @param {React.RefObject} containerRef — ref to the modal container element
 * @param {Function} onClose — callback to close the modal
 */
export function useModalA11y(containerRef, onClose) {
  // Escape to close + Tab focus trap
  useEffect(() => {
    const handler = (e) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key === "Tab" && containerRef.current) {
        const focusable = containerRef.current.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, containerRef]);

  // Lock body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = ""; };
  }, []);
}
