/**
 * Skeleton loading primitives — reusable pulsing placeholders.
 * Usage: <Skeleton.Line />, <Skeleton.Card />, <Skeleton.CardGrid count={6} />
 */
import "./skeleton.css";

function Line({ width = "100%", height = "1rem", style = {} }) {
  return <div className="skeleton-pulse" style={{ width, height, borderRadius: "4px", ...style }} />;
}

function Circle({ size = "3rem", style = {} }) {
  return <div className="skeleton-pulse" style={{ width: size, height: size, borderRadius: "50%", ...style }} />;
}

function Card() {
  return (
    <div className="skeleton-card">
      <div className="skeleton-pulse skeleton-card-poster" />
      <div className="skeleton-card-body">
        <Line width="75%" height="0.9rem" />
        <Line width="50%" height="0.7rem" style={{ marginTop: "0.5rem" }} />
        <Line width="90%" height="0.6rem" style={{ marginTop: "0.4rem" }} />
      </div>
    </div>
  );
}

function CardGrid({ count = 6 }) {
  return (
    <div className="skeleton-card-grid">
      {Array.from({ length: count }, (_, i) => <Card key={i} />)}
    </div>
  );
}

function Table({ rows = 4, cols = 3 }) {
  return (
    <div className="skeleton-table">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="skeleton-table-row">
          {Array.from({ length: cols }, (_, c) => (
            <Line key={c} width={c === 0 ? "40%" : "60%"} height="0.8rem" />
          ))}
        </div>
      ))}
    </div>
  );
}

const Skeleton = { Line, Circle, Card, CardGrid, Table };
export default Skeleton;
