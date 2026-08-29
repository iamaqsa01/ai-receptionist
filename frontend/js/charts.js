/**
 * Minimal, dependency-free SVG chart helpers (Phase 11 — vanilla JS only,
 * no chart library). Each function returns an HTML string for an inline
 * <svg>, sized by its viewBox and stretched to fill its container via CSS.
 */
const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";

  function niceMax(max) {
    if (max <= 0) return 10;
    const pow = Math.pow(10, Math.floor(Math.log10(max)));
    const n = max / pow;
    const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
    return step * pow;
  }

  // -- Line/area chart ---------------------------------------------------------
  function lineChart(data, { width = 600, height = 220, color = "var(--chart-1)", fill = true, valueKey = "value" } = {}) {
    const pad = { top: 16, right: 12, bottom: 28, left: 12 };
    const w = width - pad.left - pad.right;
    const h = height - pad.top - pad.bottom;
    const max = niceMax(Math.max(...data.map((d) => d[valueKey])) * 1.15);
    const stepX = data.length > 1 ? w / (data.length - 1) : 0;

    const points = data.map((d, i) => {
      const x = pad.left + i * stepX;
      const y = pad.top + h - (d[valueKey] / max) * h;
      return [x, y];
    });

    const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${pad.top + h} L${points[0][0].toFixed(1)},${pad.top + h} Z`;

    const gridLines = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const y = pad.top + h - f * h;
      return `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${width - pad.right}" y2="${y.toFixed(1)}" class="chart-grid" />`;
    }).join("");

    const labels = data.map((d, i) => {
      const x = pad.left + i * stepX;
      return `<text x="${x.toFixed(1)}" y="${height - 8}" class="chart-axis-label" text-anchor="middle">${d.label}</text>`;
    }).join("");

    const dots = points.map((p, i) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3.5" class="chart-dot" data-tip="${data[i].label}: ${data[i][valueKey]}"></circle>`).join("");

    return `
      <svg viewBox="0 0 ${width} ${height}" class="chart-svg" preserveAspectRatio="none" role="img" aria-label="Line chart">
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="${color}" stop-opacity="0.35" />
            <stop offset="100%" stop-color="${color}" stop-opacity="0" />
          </linearGradient>
        </defs>
        ${gridLines}
        ${fill ? `<path d="${areaPath}" fill="url(#areaGrad)" stroke="none" />` : ""}
        <path d="${linePath}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" class="chart-line" />
        ${dots}
        ${labels}
      </svg>`;
  }

  // -- Grouped bar chart --------------------------------------------------------
  function barChart(data, { width = 600, height = 220, keys = ["value"], colors = ["var(--chart-1)"] } = {}) {
    const pad = { top: 16, right: 12, bottom: 28, left: 12 };
    const w = width - pad.left - pad.right;
    const h = height - pad.top - pad.bottom;
    const max = niceMax(Math.max(...data.map((d) => Math.max(...keys.map((k) => d[k] || 0)))) * 1.2);
    const groupW = w / data.length;
    const barW = Math.min(22, (groupW * 0.6) / keys.length);
    const gap = 4;

    const gridLines = [0, 0.25, 0.5, 0.75, 1].map((f) => {
      const y = pad.top + h - f * h;
      return `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${width - pad.right}" y2="${y.toFixed(1)}" class="chart-grid" />`;
    }).join("");

    const bars = data.map((d, i) => {
      const groupX = pad.left + i * groupW + groupW / 2 - (barW * keys.length + gap * (keys.length - 1)) / 2;
      const barsInGroup = keys.map((k, ki) => {
        const val = d[k] || 0;
        const bh = (val / max) * h;
        const x = groupX + ki * (barW + gap);
        const y = pad.top + h - bh;
        return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${bh.toFixed(1)}" rx="4" fill="${colors[ki % colors.length]}" class="chart-bar" data-tip="${d.label}: ${val}"></rect>`;
      }).join("");
      const labelX = pad.left + i * groupW + groupW / 2;
      return `${barsInGroup}<text x="${labelX.toFixed(1)}" y="${height - 8}" class="chart-axis-label" text-anchor="middle">${d.label}</text>`;
    }).join("");

    return `
      <svg viewBox="0 0 ${width} ${height}" class="chart-svg" preserveAspectRatio="none" role="img" aria-label="Bar chart">
        ${gridLines}
        ${bars}
      </svg>`;
  }

  // -- Donut chart ----------------------------------------------------------------
  function donutChart(data, { size = 200, thickness = 26, valueKey = "value" } = {}) {
    const total = data.reduce((s, d) => s + d[valueKey], 0) || 1;
    const cx = size / 2, cy = size / 2;
    const r = size / 2 - thickness / 2 - 2;
    const circumference = 2 * Math.PI * r;
    let offset = 0;

    const segments = data.map((d) => {
      const frac = d[valueKey] / total;
      const dash = frac * circumference;
      const seg = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${d.color}" stroke-width="${thickness}"
        stroke-dasharray="${dash.toFixed(2)} ${(circumference - dash).toFixed(2)}"
        stroke-dashoffset="${(-offset).toFixed(2)}" transform="rotate(-90 ${cx} ${cy})" class="chart-donut-seg"
        data-tip="${d.label}: ${d[valueKey]} (${Math.round(frac * 100)}%)"></circle>`;
      offset += dash;
      return seg;
    }).join("");

    return `
      <svg viewBox="0 0 ${size} ${size}" class="chart-svg chart-donut" role="img" aria-label="Donut chart">
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--border)" stroke-width="${thickness}" opacity="0.25" />
        ${segments}
        <text x="${cx}" y="${cy - 4}" text-anchor="middle" class="chart-donut-total">${total}</text>
        <text x="${cx}" y="${cy + 16}" text-anchor="middle" class="chart-donut-caption">total</text>
      </svg>`;
  }

  // -- Sparkline (tiny inline trend line, no axes) -----------------------------
  function sparkline(values, { width = 120, height = 36, color = "var(--chart-1)" } = {}) {
    const max = Math.max(...values), min = Math.min(...values);
    const range = max - min || 1;
    const stepX = width / (values.length - 1);
    const points = values.map((v, i) => `${(i * stepX).toFixed(1)},${(height - ((v - min) / range) * height).toFixed(1)}`).join(" ");
    return `<svg viewBox="0 0 ${width} ${height}" class="sparkline" preserveAspectRatio="none">
      <polyline points="${points}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
    </svg>`;
  }

  return { lineChart, barChart, donutChart, sparkline };
})();
