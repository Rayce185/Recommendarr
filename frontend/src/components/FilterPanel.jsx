import { useState, useEffect } from "react";
import { SlidersHorizontal, Save, Trash2, XCircle, CheckCircle2, EyeOff, Eye } from "lucide-react";
import { api } from "../api.js";
import CustomSelect from "./CustomSelect.jsx";

const FILTER_STORAGE_KEY = "recommendarr_filters";
const PRESET_STORAGE_KEY = "recommendarr_filter_presets";

function loadSavedFilters() {
  try { return JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY)) || {}; }
  catch { return {}; }
}

function saveFilters(filters) {
  localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
}

function loadPresets() {
  try { return JSON.parse(localStorage.getItem(PRESET_STORAGE_KEY)) || []; }
  catch { return []; }
}

function savePresets(presets) {
  localStorage.setItem(PRESET_STORAGE_KEY, JSON.stringify(presets));
}

function FilterPanel({ filters, onChange, onApply }) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState({ genres: [], libraries: [] });
  const [presets, setPresets] = useState(loadPresets);
  const [presetName, setPresetName] = useState("");

  useEffect(() => {
    api.filterOptions().then(setOptions).catch(() => {});
  }, []);

  const toggle = (set, item) => {
    const next = new Set(set);
    next.has(item) ? next.delete(item) : next.add(item);
    return [...next];
  };

  const activeCount = (filters.excludeGenres?.length || 0)
    + (filters.includeGenres?.length || 0)
    + (filters.excludeLibraries?.length || 0)
    + (filters.minYear ? 1 : 0) + (filters.maxYear ? 1 : 0)
    + (filters.minRating ? 1 : 0);

  const handleSavePreset = () => {
    if (!presetName.trim()) return;
    const next = [...presets, { name: presetName.trim(), filters: { ...filters } }];
    setPresets(next);
    savePresets(next);
    setPresetName("");
  };

  const handleLoadPreset = (preset) => {
    onChange(preset.filters);
    onApply(preset.filters);
  };

  const handleDeletePreset = (idx) => {
    const next = presets.filter((_, i) => i !== idx);
    setPresets(next);
    savePresets(next);
  };

  const handleClear = () => {
    const empty = { excludeGenres: [], includeGenres: [], excludeLibraries: [], minYear: null, maxYear: null, minRating: null };
    onChange(empty);
    onApply(empty);
  };

  return (
    <div className="filter-panel">
      <button
        className={`btn ${activeCount > 0 ? "btn-primary" : "btn-secondary"}`}
        style={{ fontSize: 13, padding: "6px 12px", display: "flex", alignItems: "center", gap: 6 }}
        onClick={() => setOpen(!open)}
      >
        <SlidersHorizontal size={14} />
        Filters {activeCount > 0 && <span className="filter-badge">{activeCount}</span>}
      </button>

      {open && (
        <div className="filter-dropdown">
          {/* Presets */}
          {presets.length > 0 && (
            <div className="filter-section">
              <div className="filter-section-title">Saved Presets</div>
              <div className="filter-presets">
                {presets.map((p, i) => (
                  <div key={i} className="preset-row">
                    <button className="preset-btn" onClick={() => handleLoadPreset(p)}>
                      {p.name}
                    </button>
                    <button className="preset-delete" onClick={() => handleDeletePreset(i)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Exclude Libraries */}
          <div className="filter-section">
            <div className="filter-section-title">Exclude Libraries</div>
            <div className="filter-chips">
              {options.libraries.map(lib => {
                const active = (filters.excludeLibraries || []).includes(lib.title);
                return (
                  <button
                    key={lib.key}
                    className={`filter-chip ${active ? "chip-exclude" : ""}`}
                    onClick={() => {
                      const next = { ...filters, excludeLibraries: toggle(new Set(filters.excludeLibraries || []), lib.title) };
                      onChange(next);
                    }}
                  >
                    {active && <XCircle size={12} />} {lib.title}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Exclude Genres */}
          <div className="filter-section">
            <div className="filter-section-title">Exclude Genres</div>
            <div className="filter-chips">
              {options.genres.map(g => {
                const active = (filters.excludeGenres || []).includes(g);
                return (
                  <button
                    key={g}
                    className={`filter-chip ${active ? "chip-exclude" : ""}`}
                    onClick={() => {
                      const next = { ...filters, excludeGenres: toggle(new Set(filters.excludeGenres || []), g) };
                      onChange(next);
                    }}
                  >
                    {active && <XCircle size={12} />} {g}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Include Genres (Only) */}
          <div className="filter-section">
            <div className="filter-section-title">Only These Genres <span style={{fontSize:11,opacity:0.6}}>(empty = all)</span></div>
            <div className="filter-chips">
              {options.genres.map(g => {
                const active = (filters.includeGenres || []).includes(g);
                return (
                  <button
                    key={g}
                    className={`filter-chip ${active ? "chip-include" : ""}`}
                    onClick={() => {
                      const next = { ...filters, includeGenres: toggle(new Set(filters.includeGenres || []), g) };
                      onChange(next);
                    }}
                  >
                    {active && <CheckCircle2 size={12} />} {g}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Watched Status */}
          <div className="filter-section">
            <div className="filter-section-title">Watched Status</div>
            <div className="filter-chips">
              {[
                { value: "all", label: "Showing all", icon: null },
                { value: "unseen", label: "Unseen only", icon: null },
                { value: "seen", label: "Seen only", icon: null },
              ].map(opt => (
                <button
                  key={opt.value}
                  className={`filter-chip ${(filters.watchedFilter || "all") === opt.value ? "chip-active" : ""}`}
                  onClick={() => {
                    const next = { ...filters, watchedFilter: opt.value };
                    delete next.hideWatched;
                    onChange(next);
                  }}
                >
                  {opt.value === "unseen" && <EyeOff size={12} />}
                  {opt.value === "seen" && <Eye size={12} />}
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Year Range */}
          <div className="filter-section">
            <div className="filter-section-title">Year Range</div>
            <div className="filter-range-row">
              <input
                type="number"
                className="filter-number-input"
                placeholder="From"
                min={1900}
                max={2030}
                value={filters.minYear || ""}
                onChange={e => onChange({ ...filters, minYear: e.target.value ? parseInt(e.target.value) : null })}
              />
              <span style={{ color: "var(--text-muted)" }}>—</span>
              <input
                type="number"
                className="filter-number-input"
                placeholder="To"
                min={1900}
                max={2030}
                value={filters.maxYear || ""}
                onChange={e => onChange({ ...filters, maxYear: e.target.value ? parseInt(e.target.value) : null })}
              />
            </div>
          </div>

          {/* Minimum Rating */}
          <div className="filter-section">
            <div className="filter-section-title">Minimum Rating: {filters.minRating ? `${filters.minRating}/10` : "Any"}</div>
            <input
              type="range"
              className="filter-slider"
              min={0}
              max={9}
              step={0.5}
              value={filters.minRating || 0}
              onChange={e => {
                const v = parseFloat(e.target.value);
                onChange({ ...filters, minRating: v > 0 ? v : null });
              }}
            />
            <div className="filter-range-labels">
              <span>Any</span><span>5</span><span>9+</span>
            </div>
          </div>

          {/* Actions */}
          <div className="filter-actions">
            <div style={{ display: "flex", gap: 6, flex: 1 }}>
              <input
                className="filter-preset-input"
                placeholder="Preset name..."
                value={presetName}
                onChange={e => setPresetName(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSavePreset()}
              />
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={handleSavePreset} disabled={!presetName.trim()}>
                <Save size={12} /> Save
              </button>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-secondary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={handleClear}>
                Clear All
              </button>
              <button className="btn btn-primary" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => { saveFilters(filters); onApply(filters); setOpen(false); }}>
                Apply
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { FilterPanel, loadSavedFilters, saveFilters };
