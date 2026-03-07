import { useState, useCallback } from "react";
import { Upload, Link, Loader2, CheckCircle2, XCircle, Download, Bookmark,
  Sparkles, Search, ChevronDown, ChevronUp, Star, Film, Tv } from "lucide-react";
import { api } from "../api.js";

function ListImportPage({ onCardClick }) {
  const [mode, setMode] = useState("text"); // "text" or "url"
  const [inputText, setInputText] = useState("");
  const [inputUrl, setInputUrl] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [bulkAction, setBulkAction] = useState(null); // "requesting" | "watchlisting"
  const [bulkResult, setBulkResult] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  const handleExtract = useCallback(async () => {
    setExtracting(true);
    setError(null);
    setResults(null);
    setSelected(new Set());
    setBulkResult(null);
    try {
      const payload = mode === "url" ? { url: inputUrl } : { text: inputText };
      const data = await api.importExtract(payload);
      setResults(data);
      // Auto-select all matched items
      const matched = new Set();
      data.titles?.forEach((t, i) => { if (t.matched) matched.add(i); });
      setSelected(matched);
    } catch (e) {
      setError(e.message || "Extraction failed");
    }
    setExtracting(false);
  }, [mode, inputText, inputUrl]);

  const toggleSelect = (idx) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const selectAll = () => {
    const all = new Set();
    results?.titles?.forEach((t, i) => { if (t.matched) all.add(i); });
    setSelected(all);
  };

  const selectNone = () => setSelected(new Set());

  const getSelectedItems = () => {
    return [...selected].map(i => results.titles[i]).filter(t => t.matched).map(t => ({
      tmdb_id: t.tmdb_id, media_type: t.tmdb_type === "tv" ? "tv" : "movie",
    }));
  };

  const handleBulkRequest = async () => {
    const items = getSelectedItems();
    if (!items.length) return;
    setBulkAction("requesting");
    setBulkResult(null);
    try {
      const data = await api.importBulkRequest(items);
      setBulkResult({ type: "request", ...data });
    } catch (e) {
      setBulkResult({ type: "error", message: e.message });
    }
    setBulkAction(null);
  };

  const handleBulkWatchlist = async () => {
    const items = getSelectedItems();
    if (!items.length) return;
    setBulkAction("watchlisting");
    setBulkResult(null);
    try {
      const data = await api.importBulkWatchlist(items);
      setBulkResult({ type: "watchlist", ...data });
    } catch (e) {
      setBulkResult({ type: "error", message: e.message });
    }
    setBulkAction(null);
  };

  const selectedCount = [...selected].filter(i => results?.titles?.[i]?.matched).length;
  const canSubmit = mode === "url" ? inputUrl.trim().length > 5 : inputText.trim().length > 10;

  return (
    <div style={{ padding: "0 4px" }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
          <Upload size={20} /> List Import
        </h2>
        <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "6px 0 0" }}>
          Paste a URL or text containing movie/TV recommendations. AI extracts titles and matches them on TMDB.
        </p>
      </div>

      {/* Input area */}
      <div className="admin-card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button onClick={() => setMode("text")} className={`btn btn-sm ${mode === "text" ? "btn-primary" : "btn-secondary"}`}
            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
            <Search size={13} /> Paste Text
          </button>
          <button onClick={() => setMode("url")} className={`btn btn-sm ${mode === "url" ? "btn-primary" : "btn-secondary"}`}
            style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
            <Link size={13} /> From URL
          </button>
        </div>

        {mode === "text" ? (
          <textarea
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            placeholder={"Paste any text with movie/TV titles...\n\nExamples:\n• A Reddit post with recommendations\n• A \"top 10\" list from a blog\n• A Letterboxd export\n• Even casual text like \"I loved Dune Part Two, Oppenheimer was great too\""}
            style={{
              width: "100%", minHeight: 140, padding: 12, fontSize: 13,
              background: "var(--bg-secondary)", border: "1px solid var(--border)",
              borderRadius: 6, color: "var(--text)", fontFamily: "'JetBrains Mono', monospace",
              resize: "vertical", lineHeight: 1.5,
            }}
          />
        ) : (
          <input
            type="text"
            value={inputUrl}
            onChange={e => setInputUrl(e.target.value)}
            placeholder="https://letterboxd.com/user/list/... or any article URL"
            style={{
              width: "100%", padding: "10px 12px", fontSize: 13,
              background: "var(--bg-secondary)", border: "1px solid var(--border)",
              borderRadius: 6, color: "var(--text)", fontFamily: "'JetBrains Mono', monospace",
            }}
          />
        )}

        <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}>
          <button onClick={handleExtract} disabled={extracting || !canSubmit}
            className="btn btn-primary" style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            {extracting ? <><Loader2 size={14} className="spinning" /> Extracting...</> :
             <><Sparkles size={14} /> Extract Titles</>}
          </button>
          {error && (
            <span style={{ fontSize: 12, color: "var(--red)", display: "flex", alignItems: "center", gap: 4 }}>
              <XCircle size={13} /> {error}
            </span>
          )}
        </div>
      </div>

      {/* Results */}
      {results && (
        <div className="admin-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>
              Found {results.count} title{results.count !== 1 ? "s" : ""}
              <span style={{ fontWeight: 400, color: "var(--text-muted)", marginLeft: 8, fontSize: 12 }}>
                {results.matched_count} matched on TMDB
                {results.ai_used && <span style={{ marginLeft: 6, color: "var(--accent)" }}><Sparkles size={10} style={{ verticalAlign: "middle" }} /> AI</span>}
              </span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={selectAll} className="btn btn-sm btn-secondary" style={{ fontSize: 11 }}>Select All</button>
              <button onClick={selectNone} className="btn btn-sm btn-secondary" style={{ fontSize: 11 }}>Select None</button>
            </div>
          </div>

          {/* Title list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {results.titles.map((t, i) => (
              <ImportResultRow
                key={i}
                item={t}
                index={i}
                isSelected={selected.has(i)}
                isExpanded={expandedId === i}
                onToggleSelect={() => toggleSelect(i)}
                onToggleExpand={() => setExpandedId(expandedId === i ? null : i)}
                onCardClick={onCardClick}
              />
            ))}
          </div>

          {/* Bulk actions */}
          {selectedCount > 0 && (
            <div style={{ marginTop: 16, padding: "12px 0 0", borderTop: "1px solid var(--border)", display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontSize: 13, color: "var(--text-muted)", marginRight: 4 }}>{selectedCount} selected:</span>
              <button onClick={handleBulkRequest} disabled={!!bulkAction}
                className="btn btn-primary" style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
                {bulkAction === "requesting" ? <><Loader2 size={13} className="spinning" /> Requesting...</> :
                 <><Download size={13} /> Add to Library</>}
              </button>
              <button onClick={handleBulkWatchlist} disabled={!!bulkAction}
                className="btn btn-secondary" style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12 }}>
                {bulkAction === "watchlisting" ? <><Loader2 size={13} className="spinning" /> Adding...</> :
                 <><Bookmark size={13} /> Add to Watchlist</>}
              </button>
              {bulkResult && bulkResult.type !== "error" && (
                <span style={{ fontSize: 12, color: "var(--green)", display: "flex", alignItems: "center", gap: 4 }}>
                  <CheckCircle2 size={13} /> {bulkResult.success}/{bulkResult.processed} succeeded
                </span>
              )}
              {bulkResult?.type === "error" && (
                <span style={{ fontSize: 12, color: "var(--red)" }}>{bulkResult.message}</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


function ImportResultRow({ item, index, isSelected, isExpanded, onToggleSelect, onToggleExpand, onCardClick }) {
  const matched = item.matched;
  const confidence = item.confidence;

  return (
    <div style={{
      background: isSelected ? "rgba(99,102,241,0.08)" : "var(--bg-secondary)",
      border: `1px solid ${isSelected ? "rgba(99,102,241,0.3)" : "var(--border)"}`,
      borderRadius: 6, padding: "8px 10px", transition: "all 0.15s",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {/* Checkbox */}
        <div onClick={onToggleSelect} style={{
          width: 18, height: 18, borderRadius: 4, flexShrink: 0, cursor: "pointer",
          border: `2px solid ${isSelected ? "var(--accent)" : "var(--border)"}`,
          background: isSelected ? "var(--accent)" : "transparent",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          {isSelected && <CheckCircle2 size={12} color="#fff" />}
        </div>

        {/* Poster thumbnail */}
        {item.poster_url ? (
          <img src={item.poster_url} alt="" loading="lazy" style={{ width: 32, height: 48, borderRadius: 4, objectFit: "cover", flexShrink: 0 }} />
        ) : (
          <div style={{ width: 32, height: 48, borderRadius: 4, background: "var(--bg-elevated)", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Film size={14} color="var(--text-muted)" />
          </div>
        )}

        {/* Title info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {matched ? item.tmdb_title : item.extracted_title}
            </span>
            {item.tmdb_type === "tv" && <Tv size={12} color="var(--accent)" title="TV Series" />}
            {item.tmdb_year && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>({item.tmdb_year})</span>}
            {!matched && <span style={{ fontSize: 10, color: "var(--red)", padding: "1px 5px", border: "1px solid var(--red)", borderRadius: 4 }}>No match</span>}
          </div>
          {matched && item.tmdb_title !== item.extracted_title && (
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>from: "{item.extracted_title}"</div>
          )}
        </div>

        {/* Rating + confidence */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          {item.vote_average > 0 && (
            <span style={{ fontSize: 12, display: "flex", alignItems: "center", gap: 3, color: item.vote_average >= 7 ? "var(--green)" : "var(--text-muted)" }}>
              <Star size={11} /> {item.vote_average.toFixed(1)}
            </span>
          )}
          <div style={{
            width: 6, height: 6, borderRadius: 3, flexShrink: 0,
            background: confidence > 0.7 ? "var(--green)" : confidence > 0.4 ? "var(--accent)" : "var(--red)",
          }} title={`Confidence: ${Math.round(confidence * 100)}%`} />
          <button onClick={onToggleExpand} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-muted)", padding: 2 }}>
            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Expanded details */}
      {isExpanded && matched && (
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border)", fontSize: 12, color: "var(--text-secondary)" }}>
          {item.overview && <p style={{ margin: "0 0 6px", lineHeight: 1.5 }}>{item.overview}</p>}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <span>TMDB: {item.tmdb_id}</span>
            <span>Type: {item.tmdb_type}</span>
            <span>Confidence: {Math.round(confidence * 100)}%</span>
          </div>
        </div>
      )}
    </div>
  );
}


export default ListImportPage;
