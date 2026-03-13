import { Loader2, AlertCircle, Film } from "lucide-react";

export function LoadingState({ message = "Loading..." }) {
  return (
    <div className="state-container">
      <Loader2 size={32} className="spinner" />
      <p>{message}</p>
    </div>
  );
}

export function EmptyState({ icon: Icon = Film, title, message }) {
  return (
    <div className="state-container">
      <Icon size={40} />
      <h3>{title || "Nothing here"}</h3>
      <p>{message || "No results to display."}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="state-container error">
      <AlertCircle size={32} />
      <h3>Something went wrong</h3>
      <p>{message}</p>
      {onRetry && <button className="btn btn-secondary" onClick={onRetry}>Try Again</button>}
    </div>
  );
}
