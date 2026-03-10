import { useState, useCallback } from "react";
import { CheckCircle2, XCircle, Activity } from "lucide-react";

function useToast() {
  const [toasts, setToasts] = useState([]);
  const addToast = useCallback((message, type = "info") => {
    const id = Date.now();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
  }, []);
  return { toasts, addToast };
}

function ToastContainer({ toasts }) {
  if (toasts.length === 0) return null;
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          {t.type === "success" ? <CheckCircle2 size={15} style={{ color: "var(--green)" }} /> :
           t.type === "error" ? <XCircle size={15} style={{ color: "var(--red)" }} /> :
           <Activity size={15} style={{ color: "var(--accent)" }} />}
          {t.message}
        </div>
      ))}
    </div>
  );
}

export { useToast, ToastContainer };
