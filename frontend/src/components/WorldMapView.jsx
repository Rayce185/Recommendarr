/* WorldMapView — Interactive SVG world map for World Cinema discovery
 * Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
 */
import { useState, useMemo, useCallback } from "react";
import "../styles/world-cinema-map.css";
import { ComposableMap, Geographies, Geography, ZoomableGroup } from "react-simple-maps";
import { Pin, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import { matchColor, ISO_NUM_TO_A2 } from "../utils/world-cinema-utils.js";

const GEO_URL = "/geo/countries-110m.json";
const DEFAULT_CENTER = [20, 10];
const DEFAULT_ZOOM = 1;
const UNMATCHED_FILL = "rgba(255,255,255,0.04)";
const UNMATCHED_STROKE = "rgba(255,255,255,0.08)";
const MATCHED_STROKE = "rgba(255,255,255,0.18)";
const SELECTED_STROKE = "var(--accent)";

const LEGEND_ITEMS = [
  { label: "Strong", range: "70-100%", color: "rgba(240, 160, 40, 0.8)" },
  { label: "Good", range: "50-69%", color: "rgba(200, 170, 60, 0.65)" },
  { label: "Some overlap", range: "30-49%", color: "rgba(140, 160, 100, 0.5)" },
  { label: "New territory", range: "0-29%", color: "rgba(100, 140, 200, 0.3)" },
  { label: "Not tracked", range: "", color: UNMATCHED_FILL },
];

function MapTooltip({ country, isPinned, x, y }) {
  const pct = country.taste_match !== null ? Math.round(country.taste_match * 100) : null;
  return (
    <div className="wc-map-tooltip" style={{ left: x + 12, top: y - 40 }}>
      <div className="wc-map-tooltip-header">
        <span className="wc-flag">{country.flag}</span>
        <span className="wc-name">{country.name}</span>
        {isPinned && <Pin size={10} className="wc-map-tooltip-pin" />}
      </div>
      {pct !== null && (
        <div className="wc-map-tooltip-match">
          <div className="wc-map-tooltip-bar">
            <div style={{ width: `${pct}%`, background: matchColor(country.taste_match) }} />
          </div>
          <span>{pct}% match</span>
        </div>
      )}
      {country.notable && <div className="wc-map-tooltip-note">{country.notable}</div>}
    </div>
  );
}

function MapLegend() {
  return (
    <div className="wc-map-legend">
      <span className="wc-map-legend-title">Taste Match</span>
      {LEGEND_ITEMS.map(item => (
        <div key={item.label} className="wc-map-legend-item">
          <span className="wc-map-legend-swatch" style={{ background: item.color }} />
          <span>{item.label}</span>
        </div>
      ))}
    </div>
  );
}

export default function WorldMapView({ countries, pinned, selectedCode, onSelect }) {
  const [tooltip, setTooltip] = useState(null);
  const [zoom, setZoom] = useState(DEFAULT_ZOOM);
  const [center, setCenter] = useState(DEFAULT_CENTER);

  const countryLookup = useMemo(() => {
    const map = {};
    (countries || []).forEach(c => { map[c.code] = c; });
    return map;
  }, [countries]);

  const handleGeoClick = useCallback((geo) => {
    const a2 = ISO_NUM_TO_A2[geo.id];
    const country = a2 ? countryLookup[a2] : null;
    if (country) onSelect(country);
  }, [countryLookup, onSelect]);

  const handleGeoMouse = useCallback((geo, evt) => {
    const a2 = ISO_NUM_TO_A2[geo.id];
    const country = a2 ? countryLookup[a2] : null;
    if (country) {
      setTooltip({ country, isPinned: pinned.includes(a2), x: evt.clientX, y: evt.clientY });
    }
  }, [countryLookup, pinned]);

  const handleGeoLeave = useCallback(() => setTooltip(null), []);

  const zoomIn = () => setZoom(z => Math.min(z * 1.5, 8));
  const zoomOut = () => setZoom(z => Math.max(z / 1.5, 1));
  const resetView = () => { setZoom(DEFAULT_ZOOM); setCenter(DEFAULT_CENTER); };

  return (
    <div className="wc-map-container">
      <div className="wc-map-controls">
        <button onClick={zoomIn} title="Zoom in"><ZoomIn size={16} /></button>
        <button onClick={zoomOut} title="Zoom out"><ZoomOut size={16} /></button>
        <button onClick={resetView} title="Reset view"><RotateCcw size={16} /></button>
      </div>

      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 160 }}
        className="wc-map-svg"
      >
        <ZoomableGroup
          zoom={zoom}
          center={center}
          onMoveEnd={({ coordinates, zoom: z }) => { setCenter(coordinates); setZoom(z); }}
          minZoom={1}
          maxZoom={8}
        >
          <Geographies geography={GEO_URL}>
            {({ geographies }) => geographies.map(geo => {
              const a2 = ISO_NUM_TO_A2[geo.id];
              const country = a2 ? countryLookup[a2] : null;
              const isSelected = a2 === selectedCode;
              const isPinned = a2 && pinned.includes(a2);
              const fill = country ? matchColor(country.taste_match) : UNMATCHED_FILL;

              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={fill}
                  stroke={isSelected ? SELECTED_STROKE : country ? MATCHED_STROKE : UNMATCHED_STROKE}
                  strokeWidth={isSelected ? 1.5 : isPinned ? 0.8 : 0.4}
                  onClick={() => handleGeoClick(geo)}
                  onMouseMove={(evt) => handleGeoMouse(geo, evt)}
                  onMouseLeave={handleGeoLeave}
                  style={{
                    default: { outline: "none", cursor: country ? "pointer" : "default",
                      transition: "fill 0.2s, stroke 0.2s" },
                    hover: { outline: "none", fill: country ? "var(--accent-dim, rgba(99,179,237,0.4))" : UNMATCHED_FILL,
                      stroke: country ? "var(--accent)" : UNMATCHED_STROKE, strokeWidth: country ? 1 : 0.4 },
                    pressed: { outline: "none" },
                  }}
                />
              );
            })}
          </Geographies>
        </ZoomableGroup>
      </ComposableMap>

      {tooltip && (
        <MapTooltip country={tooltip.country} isPinned={tooltip.isPinned}
          x={tooltip.x} y={tooltip.y} />
      )}

      <MapLegend />
    </div>
  );
}
