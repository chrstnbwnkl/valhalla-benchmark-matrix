const fs = require("fs");
const path = require("path");

// ============================================================
// SCENARIOS — Edit / add your traffic patterns here
// ============================================================

const SCENARIOS = [
  {
    name: "log-normal",
    // title: "Tobler's first law of Geography",
    // description: "Log-normal across location count and geographical extent",
    points: [
      // { geo, loc, size }
      //   geo  = Geographical Extent (0–1, where 0=local, 1=global)
      //   loc  = Location Count     (0–1, where 0=few,   1=many)
      //   size = Relative request volume (normalized to bubble radius)
      { geo: 0.15, loc: 0.85, size: 17 },
      { geo: 0.5, loc: 0.85, size: 10 },
      { geo: 0.85, loc: 0.85, size: 3 },
      { geo: 0.15, loc: 0.5, size: 30 },
      { geo: 0.5, loc: 0.5, size: 17 },
      { geo: 0.85, loc: 0.5, size: 10 },
      { geo: 0.15, loc: 0.15, size: 50 },
      { geo: 0.5, loc: 0.15, size: 30 },
      { geo: 0.85, loc: 0.15, size: 17 },
    ],
  },
];

// ============================================================
// CHART SETTINGS — tweak visual appearance here
// ============================================================

const CHART = {
  width: 540, // plot area width
  height: 400, // plot area height
  padLeft: 110, // space for Y-axis title + tick labels
  padBottom: 80, // space for X-axis title + tick labels
  padTop: 50, // space for title + description
  padRight: 24,
  maxRadius: 48, // largest bubble radius (px)
  minRadius: 6, // smallest bubble radius (px)
  gridLines: 3,
  // Colors
  bubbleFill: "rgba(99, 153, 34, 0.55)",
  bubbleStroke: "rgba(99, 153, 34, 0.9)",
  axisColor: "#333",
  gridColor: "#999",
  textColor: "#333",
  textMuted: "#666",
  labelInBubble: "#222",
};

// ============================================================
// SVG GENERATION
// ============================================================

function generateSVG(scenario) {
  const C = CHART;
  const totalW = C.padLeft + C.width + C.padRight;
  const totalH = C.padTop + C.height + C.padBottom;

  const plotLeft = C.padLeft;
  const plotTop = C.padTop;
  const plotRight = plotLeft + C.width;
  const plotBottom = plotTop + C.height;

  const maxSize = Math.max(...scenario.points.map((p) => p.size), 1);
  const toRadius = (s) =>
    C.minRadius + (s / maxSize) * (C.maxRadius - C.minRadius);
  const toX = (geo) => plotLeft + geo * C.width;
  const toY = (loc) => plotTop + (1 - loc) * C.height;

  const geoLabels = ["Local", "Regional", "(Inter)national"];
  const locLabels = ["Few", "Moderate", "Many"];

  let svg = "";

  svg += `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${totalW} ${totalH}" width="${totalW}" height="${totalH}" font-family="system-ui, -apple-system, sans-serif">\n`;
  svg += `  <rect width="${totalW}" height="${totalH}" fill="white"/>\n`;

  // Title & description
  svg += `  <text x="${plotLeft}" y="22" font-size="16" font-weight="600" fill="${C.textColor}">${scenario.title ?? ""}</text>\n`;
  svg += `  <text x="${plotLeft}" y="40" font-size="12" fill="${C.textMuted}">${scenario.description ?? ""}</text>\n`;

  // Grid lines
  for (let i = 0; i <= C.gridLines; i++) {
    const frac = i / C.gridLines;
    const x = plotLeft + frac * C.width;
    const y = plotTop + frac * C.height;
    svg += `  <line x1="${x}" y1="${plotTop}" x2="${x}" y2="${plotBottom}" stroke="${C.gridColor}" stroke-width="0.5" opacity="0.5"/>\n`;
    svg += `  <line x1="${plotLeft}" y1="${y}" x2="${plotRight}" y2="${y}" stroke="${C.gridColor}" stroke-width="0.5" opacity="0.5"/>\n`;
  }

  // Axes
  svg += `  <line x1="${plotLeft}" y1="${plotBottom}" x2="${plotRight}" y2="${plotBottom}" stroke="${C.axisColor}" stroke-width="1"/>\n`;
  svg += `  <line x1="${plotLeft}" y1="${plotTop}" x2="${plotLeft}" y2="${plotBottom}" stroke="${C.axisColor}" stroke-width="1"/>\n`;

  // X-axis tick labels
  geoLabels.forEach((label, i) => {
    const x = plotLeft + ((i + 0.5) / geoLabels.length) * C.width;
    svg += `  <text x="${x}" y="${plotBottom + 24}" text-anchor="middle" font-size="13" fill="${C.textMuted}">${label}</text>\n`;
  });
  // X-axis title
  svg += `  <text x="${plotLeft + C.width / 2}" y="${plotBottom + 52}" text-anchor="middle" font-size="14" font-weight="500" fill="${C.textColor}">Geographical extent →</text>\n`;

  // Y-axis tick labels
  locLabels.forEach((label, i) => {
    const y = plotTop + C.height - ((i + 0.5) / locLabels.length) * C.height;
    svg += `  <text
  x="${plotLeft - 14}"
  y="${y}"
  text-anchor="end"
  dominant-baseline="central"
  font-size="13"
  fill="${C.textMuted}"
  transform="rotate(-45, ${plotLeft - 14}, ${y})"
>${label}</text>\n`;
  });
  // Y-axis title (rotated)
  svg += `  <text text-anchor="middle" font-size="14" font-weight="500" fill="${C.textColor}" transform="translate(${plotLeft - 80}, ${plotTop + C.height / 2}) rotate(-90)">Location count →</text>\n`;

  // Bubbles — largest first so small ones render on top
  [...scenario.points]
    .sort((a, b) => b.size - a.size)
    .forEach((pt) => {
      const cx = toX(pt.geo);
      const cy = toY(pt.loc);
      const r = toRadius(pt.size);
      svg += `  <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}" fill="${C.bubbleFill}" stroke="${C.bubbleStroke}" stroke-width="1"/>\n`;
      // if (r > 16) {
      //   svg += `  <text x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="500" fill="${C.labelInBubble}" opacity="0.8">${pt.size}</text>\n`;
      // }
    });

  svg += `</svg>\n`;
  return svg;
}

// ============================================================
// WRITE FILES
// ============================================================

const outDir = process.argv[2] || ".";
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

SCENARIOS.forEach((scenario) => {
  const svg = generateSVG(scenario);
  const filePath = path.join(outDir, `${scenario.name}.svg`);
  fs.writeFileSync(filePath, svg);
  console.log(`✓ ${filePath}`);
});

console.log(`\nDone — ${SCENARIOS.length} SVGs generated.`);
