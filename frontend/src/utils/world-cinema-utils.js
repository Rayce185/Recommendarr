/* Shared World Cinema helpers — used by WorldCinemaPage + WorldMapView
 * Copyright (c) 2026 VAASSEN GmbH / Ray Vaassen
 */

export function matchColor(score) {
  if (score === null || score === undefined) return "rgba(255,255,255,0.06)";
  if (score < 0.3) return `rgba(100, 140, 200, ${0.15 + score})`;
  if (score < 0.5) return `rgba(140, 160, 100, ${0.2 + score * 0.6})`;
  if (score < 0.7) return `rgba(200, 170, 60, ${0.3 + score * 0.5})`;
  return `rgba(240, 160, 40, ${0.4 + score * 0.4})`;
}

export function matchLabel(score) {
  if (score === null || score === undefined) return "";
  const pct = Math.round(score * 100);
  if (pct >= 70) return "Strong match";
  if (pct >= 50) return "Good match";
  if (pct >= 30) return "Some overlap";
  return "New territory";
}

/* ISO 3166-1 numeric -> alpha-2 for our 37 supported countries */
export const ISO_NUM_TO_A2 = {
  "840": "US", "124": "CA", "484": "MX", "826": "GB", "250": "FR",
  "276": "DE", "380": "IT", "724": "ES", "752": "SE", "208": "DK",
  "578": "NO", "246": "FI", "528": "NL", "616": "PL", "642": "RO",
  "300": "GR", "410": "KR", "392": "JP", "156": "CN", "344": "HK",
  "158": "TW", "356": "IN", "764": "TH", "608": "PH", "360": "ID",
  "364": "IR", "792": "TR", "376": "IL", "566": "NG", "710": "ZA",
  "818": "EG", "036": "AU", "554": "NZ", "076": "BR", "032": "AR",
  "170": "CO", "152": "CL"
};
