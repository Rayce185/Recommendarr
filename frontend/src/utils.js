// ─── Shared Utilities ────────────────────────────────────────────
function fixPosterUrl(url) {
  if (!url) return null;
  const doubleHttps = url.indexOf("https://", 8);
  if (doubleHttps > 0) return url.substring(doubleHttps);
  return url;
}

function posterUrl(path, size = "w342") {
  const fixed = fixPosterUrl(path);
  if (!fixed) return null;
  if (fixed.startsWith("https://image.tmdb.org")) return fixed;
  if (fixed.startsWith("/")) return `https://image.tmdb.org/t/p/${size}${fixed}`;
  return fixed;
}

function scoreColor(score) {
  if (score >= 0.7) return "#22c55e";
  if (score >= 0.4) return "#eab308";
  return "#ef4444";
}

function scorePercent(score) {
  return Math.round(score * 100);
}

function formatHours(h) {
  if (h >= 1000) return `${(h / 1000).toFixed(1)}k hrs`;
  return `${Math.round(h)} hrs`;
}

export { fixPosterUrl, posterUrl, scoreColor, scorePercent, formatHours };
