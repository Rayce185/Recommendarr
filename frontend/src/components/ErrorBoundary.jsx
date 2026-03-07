import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 40, maxWidth: 800, margin: "40px auto",
          background: "#1a1a2e", borderRadius: 12, color: "#e0e0e0",
          fontFamily: "monospace", fontSize: 14
        }}>
          <h2 style={{ color: "#ff6b6b", marginBottom: 16 }}>Something went wrong</h2>
          <pre style={{
            background: "#0d0d1a", padding: 16, borderRadius: 8,
            overflow: "auto", maxHeight: 300, whiteSpace: "pre-wrap"
          }}>
            {this.state.error?.toString()}
            {"\n\n"}
            {this.state.errorInfo?.componentStack}
          </pre>
          <button
            onClick={() => { this.setState({ hasError: false, error: null, errorInfo: null }); window.location.hash = "tonight"; window.location.reload(); }}
            style={{
              marginTop: 16, padding: "8px 20px", background: "#e5a00d",
              color: "#000", border: "none", borderRadius: 6, cursor: "pointer", fontWeight: 600
            }}
          >
            Reload App
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
