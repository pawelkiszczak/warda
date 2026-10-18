// Labelling dashboard: "Automated" charts use computed metrics for every document; "Human" charts use labels.
// Data: /api/viz (per-item automated fields + latest labels) and /api/stats (AUROC table, metric list, kappa).
// Plain SVG, no external libraries, so the page works offline.

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const fmt = (n) => (n == null || Number.isNaN(n) ? "—" : Number.isInteger(n) ? String(n) : Number(n).toPrecision(3));
const pct = (a, b) => (b ? `${((100 * a) / b).toFixed(1)}%` : "—");
const LABELS = ["HIGH", "MEDIUM", "LOW", "SKIP"];
const LABEL_COLOR = { HIGH: "#35865a", MEDIUM: "#d59124", LOW: "#c95050", SKIP: "#8a97a3", none: "#dde3e8" };
const ORIGIN_COLOR = { speakleash: "#4088b7", "fineweb-2": "#8c5fb8", "fineweb-edu": "#e0762c", unknown: "#999" };
const SL_COLOR = { HIGH: "#7fbf95", MEDIUM: "#f0c46e", LOW: "#e59393", none: "#b9a9d6" };
const SHORT = (name) => name.replace(/^(multilingual|stylometrix|cheap|loop|lm)\./, "");
const AUTO_DEFAULT = "lm.nll_mean",
  HUMAN_DEFAULT = "loop.loop_score";

let viz = null,
  stats = null;
const state = {
  tab: localStorage.getItem("dashTab") || "auto",
  autoMetric: localStorage.getItem("autoMetric") || AUTO_DEFAULT,
  humanMetric: localStorage.getItem("humanMetric") || HUMAN_DEFAULT,
};

// ---------- data ----------
async function refresh() {
  const q = new URLSearchParams();
  q.append("metric", state.autoMetric);
  q.append("metric", state.humanMetric);
  [viz, stats] = await Promise.all([
    fetch(`/api/viz?${q}`).then((r) => r.json()),
    fetch("/api/stats").then((r) => r.json()),
  ]);
  render();
  $("updated").textContent = `updated ${new Date().toLocaleTimeString()}`;
}

function myLabels() {
  // Charts follow this app instance's labeller; fall back to any labeller's latest row per item.
  const byItem = new Map();
  for (const l of viz.labels) if (l.labeller === viz.labeller) byItem.set(l.item_id, l);
  for (const l of viz.labels) if (!byItem.has(l.item_id)) byItem.set(l.item_id, l);
  return byItem;
}

const values = (name) => viz.items.map((i) => i.m[name]).filter((v) => v != null);
function quantile(sorted, q) {
  if (!sorted.length) return null;
  const i = (sorted.length - 1) * q,
    lo = Math.floor(i),
    hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}
const median = (a) =>
  quantile(
    [...a].sort((x, y) => x - y),
    0.5,
  );

function auroc(pos, neg) {
  // Mann–Whitney with average ranks
  if (!pos.length || !neg.length) return null;
  const all = pos
    .map((v) => [v, 1])
    .concat(neg.map((v) => [v, 0]))
    .sort((a, b) => a[0] - b[0]);
  let rankSum = 0;
  for (let i = 0; i < all.length; ) {
    let j = i + 1;
    while (j < all.length && all[j][0] === all[i][0]) j++;
    const rank = (i + 1 + j) / 2;
    for (let k = i; k < j; k++) if (all[k][1]) rankSum += rank;
    i = j;
  }
  return (rankSum - (pos.length * (pos.length + 1)) / 2) / (pos.length * neg.length);
}

// ---------- chart primitives ----------
const svg = (w, h, body) => `<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">${body}</svg>`;
const legend = (entries) =>
  `<div class="legend">${entries.map(([k, c]) => `<span><i style="background:${c}"></i>${esc(k)}</span>`).join("")}</div>`;
const empty = (msg) => `<div class="empty">${esc(msg)}</div>`;

function tiles(el, rows) {
  el.innerHTML = rows
    .map(
      ([label, value, sub]) =>
        `<div class="tile"><span>${esc(label)}</span><b>${esc(value)}</b><span>${esc(sub || "")}</span></div>`,
    )
    .join("");
}

// Horizontal stacked bars. rows: [{label, segments: [{v, color, tip}], link?}]
function hbars(el, rows, { max = null, labelWidth = 190, rowH = 18, W = 640 } = {}) {
  if (!rows.length) {
    el.innerHTML = empty("nothing to show yet");
    return;
  }
  const plotW = W - labelWidth - 50;
  const top = max ?? Math.max(1, ...rows.map((r) => r.segments.reduce((s, x) => s + x.v, 0)));
  let body = "";
  rows.forEach((r, i) => {
    const y = 4 + i * (rowH + 5);
    body += `<text x="${labelWidth - 6}" y="${y + rowH * 0.72}" text-anchor="end">${esc(r.label)}</text>`;
    let x = labelWidth,
      total = 0;
    for (const s of r.segments) {
      const w = (plotW * s.v) / top;
      if (w > 0)
        body += `<rect x="${x}" y="${y}" width="${w}" height="${rowH}" fill="${s.color}" data-tip="${esc(s.tip || "")}"><title>${esc(s.tip || "")}</title></rect>`;
      x += w;
      total += s.v;
    }
    body += `<text x="${x + 4}" y="${y + rowH * 0.72}" fill="#5a6b78">${esc(r.note ?? total)}</text>`;
  });
  el.innerHTML = svg(W, 8 + rows.length * (rowH + 5), body);
}

// Scatter of documents; points: [{x, y, color, tip, pos}], axes 0..1 unless given.
function scatter(el, points, { xLabel, yLabel, xMax = 1, yMax = 1, legendEntries = [] } = {}) {
  const W = 900,
    H = 380,
    L = 46,
    B = 34,
    T = 8,
    R = 10,
    pw = W - L - R,
    ph = H - T - B;
  const sx = (v) => L + pw * Math.min(1, Math.max(0, v / xMax)),
    sy = (v) => T + ph * (1 - Math.min(1, Math.max(0, v / yMax)));
  let body = "";
  for (let t = 0; t <= 5; t++) {
    const fx = (xMax * t) / 5,
      fy = (yMax * t) / 5;
    body += `<line x1="${sx(fx)}" x2="${sx(fx)}" y1="${T}" y2="${T + ph}" stroke="#eef2f5"/><text x="${sx(fx)}" y="${H - 18}" text-anchor="middle">${fmt(fx)}</text>`;
    body += `<line x1="${L}" x2="${L + pw}" y1="${sy(fy)}" y2="${sy(fy)}" stroke="#eef2f5"/><text x="${L - 5}" y="${sy(fy) + 4}" text-anchor="end">${fmt(fy)}</text>`;
  }
  body += `<text x="${L + pw / 2}" y="${H - 2}" text-anchor="middle" font-weight="600">${esc(xLabel)}</text>`;
  body += `<text transform="translate(11 ${T + ph / 2}) rotate(-90)" text-anchor="middle" font-weight="600">${esc(yLabel)}</text>`;
  // Deterministic jitter so the many documents at exactly 0 stay visible as a cloud.
  points.forEach((p, i) => {
    const jx = (((i * 7919) % 97) / 97 - 0.5) * 0.012 * xMax,
      jy = (((i * 104729) % 89) / 89 - 0.5) * 0.012 * yMax;
    body += `<circle class="dot" cx="${sx(p.x + jx)}" cy="${sy(p.y + jy)}" r="${p.r || 3.2}" fill="${p.color}" fill-opacity="${p.alpha ?? 0.75}" data-tip="${esc(p.tip)}" data-pos="${p.pos}"/>`;
  });
  el.innerHTML = legend(legendEntries) + svg(W, H, body);
}

// Histogram with stacked groups. groups: {name: [values]}, colors: {name: color}
function stackedHist(el, groups, colors, { bins = 24, title = "", W = 300, H = 120, log = false } = {}) {
  const all = Object.values(groups)
    .flat()
    .filter((v) => v != null && Number.isFinite(v));
  if (!all.length) {
    el.innerHTML = `<h4>${esc(title)}</h4>${empty("no values")}`;
    return;
  }
  const sorted = [...all].sort((a, b) => a - b);
  const lo = quantile(sorted, 0.01),
    hi = quantile(sorted, 0.99);
  const span = hi - lo || 1,
    counts = {};
  for (const [g, vals] of Object.entries(groups)) {
    counts[g] = Array(bins).fill(0);
    for (const v of vals)
      if (v != null && Number.isFinite(v))
        counts[g][Math.min(bins - 1, Math.max(0, Math.floor(((v - lo) / span) * bins)))]++;
  }
  const totals = Array.from({ length: bins }, (_, b) => Object.values(counts).reduce((s, c) => s + c[b], 0));
  const top = Math.max(1, ...totals),
    L = 4,
    B = 18,
    pw = W - 8,
    ph = H - B - 4,
    bw = pw / bins;
  const sh = (c) => (log ? (ph * Math.log1p(c)) / Math.log1p(top) : (ph * c) / top);
  let body = "";
  for (let b = 0; b < bins; b++) {
    let y = 4 + ph;
    for (const g of Object.keys(counts)) {
      const c = counts[g][b];
      if (!c) continue;
      const h0 = sh(totals[b]);
      const part = (h0 * c) / totals[b];
      y -= part;
      body += `<rect x="${L + b * bw}" y="${y}" width="${bw - 1}" height="${part}" fill="${colors[g] || "#999"}"><title>${esc(g)}: ${c} docs in [${fmt(lo + (b * span) / bins)}, ${fmt(lo + ((b + 1) * span) / bins)})</title></rect>`;
    }
  }
  const med = median(all),
    mx = L + pw * Math.min(1, Math.max(0, (med - lo) / span));
  body += `<line x1="${mx}" x2="${mx}" y1="4" y2="${4 + ph}" stroke="#172d3c" stroke-dasharray="3 3"/>`;
  body += `<text x="${L}" y="${H - 4}">${fmt(lo)}</text><text x="${W - 4}" y="${H - 4}" text-anchor="end">${fmt(hi)}</text><text x="${mx}" y="${H - 4}" text-anchor="middle" fill="#172d3c">median ${fmt(med)}</text>`;
  el.innerHTML = (title ? `<h4>${esc(title)}</h4>` : "") + svg(W, H, body);
}

// Heatmap with counts. rows/cols: label arrays; cell(r, c) -> count
function heatmap(el, rows, cols, cell, { colColor = () => "#4088b7", rowTitle = "", colTitle = "" } = {}) {
  const cw = 90,
    ch = 30,
    L = 110,
    T = 34,
    W = L + cols.length * cw + 10,
    H = T + rows.length * ch + 8;
  const max = Math.max(1, ...rows.flatMap((r) => cols.map((c) => cell(r, c))));
  let body = `<text x="${L + (cols.length * cw) / 2}" y="11" text-anchor="middle" font-weight="600">${esc(colTitle)}</text>`;
  cols.forEach((c, j) => {
    body += `<text x="${L + j * cw + cw / 2}" y="${T - 6}" text-anchor="middle">${esc(c)}</text>`;
  });
  rows.forEach((r, i) => {
    body += `<text x="${L - 6}" y="${T + i * ch + ch * 0.62}" text-anchor="end">${esc(r)}</text>`;
    cols.forEach((c, j) => {
      const n = cell(r, c),
        a = n ? 0.15 + (0.85 * n) / max : 0;
      body += `<rect x="${L + j * cw}" y="${T + i * ch}" width="${cw - 2}" height="${ch - 2}" fill="${colColor(c)}" fill-opacity="${a}" stroke="#eef2f5"/><text x="${L + j * cw + cw / 2}" y="${T + i * ch + ch * 0.62}" text-anchor="middle" fill="${a > 0.6 ? "white" : "#17212b"}">${n || ""}</text>`;
    });
  });
  if (rowTitle)
    body += `<text transform="translate(10 ${T + (rows.length * ch) / 2}) rotate(-90)" text-anchor="middle" font-weight="600">${esc(rowTitle)}</text>`;
  el.innerHTML = svg(W, H, body);
}

// ---------- Automated section ----------
function renderAuto() {
  const items = viz.items,
    n = items.length;
  $("n-items").textContent = n;
  const by = (f) => {
    const counts = {};
    for (const item of items) {
      const key = f(item);
      counts[key] = (counts[key] || 0) + 1;
    }
    return counts;
  };
  const origins = by((i) => i.origin);
  const pass = items.filter((i) => i.clean_ok).length;
  const loopHi = items.filter((i) => (i.m["loop.loop_score"] ?? 0) > 0.3).length;
  const mlHi = items.filter((i) => (i.m["multilingual.multilingual_score"] ?? 0) > 0.3).length;
  const nonPl = items.filter((i) => i.top_lang !== "pl").length;
  const nll = values("lm.nll_mean");
  const stylo = items.filter((i) => i.m["stylometrix.L_ERROR"] != null).length;
  tiles($("auto-tiles"), [
    [
      "documents",
      n,
      Object.entries(origins)
        .map(([k, v]) => `${k} ${v}`)
        .join(" · "),
    ],
    ["pass current cleaning", pct(pass, n), `${n - pass} rejected`],
    ["loop_score > 0.3", loopHi, `${pct(loopHi, n)} of sample`],
    ["multilingual_score > 0.3", mlHi, `${pct(mlHi, n)} of sample`],
    ["top language not Polish", nonPl, `${pct(nonPl, n)} of sample`],
    ["median LM loss (nats/token)", fmt(median(nll)), "126M scratch model"],
    ["StyloMetrix coverage", pct(stylo, n), `${n - stylo} missing`],
  ]);

  scatter(
    $("auto-scatter"),
    items.map((i) => ({
      x: i.m["loop.loop_score"] ?? 0,
      y: i.m["multilingual.multilingual_score"] ?? 0,
      pos: i.pos,
      color: ORIGIN_COLOR[i.origin] || "#999",
      tip: `${i.source} · ${i.id}\nloop ${fmt(i.m["loop.loop_score"])} · multilingual ${fmt(i.m["multilingual.multilingual_score"])} · top_lang ${i.top_lang}\nSpeakLeash: ${i.sl_quality || "—"} · cleaning: ${i.clean_ok ? "pass" : i.clean_reason}`,
    })),
    {
      xLabel: "loop_score",
      yLabel: "multilingual_score",
      legendEntries: Object.entries(ORIGIN_COLOR).filter(([k]) => origins[k]),
    },
  );

  const sources = [...new Set(items.map((i) => i.source))];
  hbars(
    $("auto-composition"),
    sources.map((src) => {
      const rows = items.filter((i) => i.source === src);
      const segs = ["HIGH", "MEDIUM", "LOW", "none"].map((q) => {
        const v = rows.filter((i) => (i.sl_quality || "none") === q).length;
        return {
          v,
          color: q === "none" ? ORIGIN_COLOR[rows[0].origin] || SL_COLOR.none : SL_COLOR[q],
          tip: `${src}: ${q === "none" ? "no SpeakLeash label" : `SpeakLeash ${q}`} ${v}`,
        };
      });
      return { label: src, segments: segs };
    }),
    { rowH: 14 },
  );
  $("auto-composition").insertAdjacentHTML(
    "afterbegin",
    legend([
      ["SpeakLeash HIGH", SL_COLOR.HIGH],
      ["MEDIUM", SL_COLOR.MEDIUM],
      ["LOW", SL_COLOR.LOW],
      ["FineWeb-2", ORIGIN_COLOR["fineweb-2"]],
      ["FineWeb-Edu", ORIGIN_COLOR["fineweb-edu"]],
    ]),
  );

  const langs = Object.entries(by((i) => i.top_lang)).sort((a, b) => b[1] - a[1]);
  hbars(
    $("auto-lang"),
    langs.map(([lang, v]) => ({
      label: lang,
      segments: [{ v, color: lang === "pl" ? "#4088b7" : "#e0762c", tip: `${lang}: ${v}` }],
    })),
    { labelWidth: 70 },
  );

  const reasons = Object.entries(by((i) => (i.clean_ok ? "pass" : i.clean_reason || "rejected"))).sort(
    (a, b) => b[1] - a[1],
  );
  hbars(
    $("auto-clean"),
    reasons.map(([r, v]) => ({
      label: r,
      segments: [{ v, color: r === "pass" ? "#35865a" : "#c95050", tip: `${r}: ${v}` }],
    })),
    { labelWidth: 200 },
  );

  const hists = $("auto-hists");
  hists.innerHTML = viz.metrics
    .slice(0, 12)
    .map((_, k) => `<div class="sm" id="h-${k}"></div>`)
    .join("");
  viz.metrics.slice(0, 12).forEach((m, k) => {
    const groups = {};
    for (const i of items) {
      const origin = i.origin;
      if (!groups[origin]) groups[origin] = [];
      groups[origin].push(i.m[m]);
    }
    stackedHist($(`h-${k}`), groups, ORIGIN_COLOR, { title: SHORT(m), log: false });
  });
  hists.insertAdjacentHTML(
    "afterbegin",
    `<div style="grid-column:1/-1">${legend(Object.entries(ORIGIN_COLOR).filter(([k]) => origins[k]))}</div>`,
  );

  renderCorrelation();
  const groups = {};
  for (const i of items) {
    const quality = i.sl_quality || "none";
    if (!groups[quality]) groups[quality] = [];
    groups[quality].push(i.m[state.autoMetric]);
  }
  stackedHist($("auto-explorer"), groups, SL_COLOR, { W: 420, H: 170, bins: 30 });
  $("auto-explorer").insertAdjacentHTML(
    "afterbegin",
    legend([
      ["SpeakLeash HIGH", SL_COLOR.HIGH],
      ["MEDIUM", SL_COLOR.MEDIUM],
      ["LOW", SL_COLOR.LOW],
      ["no label (FineWeb)", SL_COLOR.none],
    ]),
  );
}

function ranks(arr) {
  const idx = arr.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]),
    r = Array(arr.length);
  for (let i = 0; i < idx.length; ) {
    let j = i + 1;
    while (j < idx.length && idx[j][0] === idx[i][0]) j++;
    for (let k = i; k < j; k++) r[idx[k][1]] = (i + j - 1) / 2;
    i = j;
  }
  return r;
}
function pearson(a, b) {
  const n = a.length,
    ma = a.reduce((s, x) => s + x, 0) / n,
    mb = b.reduce((s, x) => s + x, 0) / n;
  let num = 0,
    da = 0,
    db = 0;
  for (let i = 0; i < n; i++) {
    num += (a[i] - ma) * (b[i] - mb);
    da += (a[i] - ma) ** 2;
    db += (b[i] - mb) ** 2;
  }
  return da && db ? num / Math.sqrt(da * db) : 0;
}
function renderCorrelation() {
  const ms = viz.metrics.slice(0, 12);
  const rows = viz.items.filter((i) => ms.every((m) => i.m[m] != null));
  const rk = Object.fromEntries(ms.map((m) => [m, ranks(rows.map((i) => i.m[m]))]));
  const c = 34,
    L = 150,
    W = L + ms.length * c + 4,
    H = L + ms.length * c + 4;
  let body = "";
  ms.forEach((a, i) => {
    body += `<text x="${L - 4}" y="${L + i * c + c * 0.62}" text-anchor="end">${esc(SHORT(a))}</text>`;
    body += `<text transform="translate(${L + i * c + c * 0.62} ${L - 4}) rotate(-60)">${esc(SHORT(a))}</text>`;
    ms.forEach((b, j) => {
      const r = pearson(rk[a], rk[b]);
      const color = r >= 0 ? `rgba(64,136,183,${Math.abs(r)})` : `rgba(201,80,80,${Math.abs(r)})`;
      body += `<rect x="${L + j * c}" y="${L + i * c}" width="${c - 2}" height="${c - 2}" fill="${color}"><title>${esc(SHORT(a))} × ${esc(SHORT(b))}: ρ = ${r.toFixed(2)}</title></rect>`;
      if (Math.abs(r) >= 0.5 && i !== j)
        body += `<text x="${L + j * c + c / 2 - 1}" y="${L + i * c + c * 0.62}" text-anchor="middle" fill="white" font-size="9">${r.toFixed(1)}</text>`;
    });
  });
  $("auto-corr").innerHTML =
    svg(W, H, body) +
    `<div class="legend"><span><i style="background:#4088b7"></i>positive</span><span><i style="background:#c95050"></i>negative</span><span>n = ${rows.length}</span></div>`;
}

// ---------- Human section ----------
function renderHuman() {
  const items = viz.items,
    n = items.length,
    labels = myLabels();
  const got = [...labels.values()];
  const count = (q) => got.filter((l) => l.quality === q).length;
  const secs = got.map((l) => l.seconds).filter((s) => s != null && s > 0);
  const medSec = median(secs);
  const hourAgo = Date.now() - 3600e3;
  const lastHour = got.filter((l) => Date.parse(l.created_at) > hourAgo).length;
  const remaining = n - labels.size;
  tiles($("human-tiles"), [
    ["labelled", `${labels.size} / ${n}`, pct(labels.size, n)],
    ["HIGH", count("HIGH"), pct(count("HIGH"), labels.size)],
    ["MEDIUM", count("MEDIUM"), pct(count("MEDIUM"), labels.size)],
    ["LOW", count("LOW"), pct(count("LOW"), labels.size)],
    ["SKIP", count("SKIP"), pct(count("SKIP"), labels.size)],
    [
      "median time / document",
      medSec == null ? "—" : `${fmt(medSec)} s`,
      `mean ${fmt(secs.length ? secs.reduce((a, b) => a + b, 0) / secs.length : null)} s`,
    ],
    [
      "estimated time left",
      medSec == null ? "—" : `${((remaining * medSec) / 3600).toFixed(1)} h`,
      `${remaining} documents · ${lastHour} labelled in the last hour`,
    ],
  ]);

  const sources = [...new Set(items.map((i) => i.source))];
  hbars(
    $("human-progress"),
    sources.map((src) => {
      const rows = items.filter((i) => i.source === src),
        share = 100 / rows.length;
      const segs = LABELS.map((q) => {
        const v = rows.filter((i) => labels.get(i.id)?.quality === q).length;
        return { v, color: LABEL_COLOR[q], tip: `${src}: ${q} ${v}` };
      });
      const done = segs.reduce((s, x) => s + x.v, 0);
      segs.push({ v: rows.length - done, color: LABEL_COLOR.none, tip: `${src}: not labelled ${rows.length - done}` });
      for (const s of segs) s.v *= share; // each source drawn as 100% of its own documents
      return { label: src, segments: segs, note: `${done}/${rows.length}` };
    }),
    { max: 100, rowH: 14, W: 1500, labelWidth: 210 },
  );
  $("human-progress").insertAdjacentHTML(
    "afterbegin",
    legend([...LABELS.map((q) => [q, LABEL_COLOR[q]]), ["not labelled", LABEL_COLOR.none]]),
  );

  if (!labels.size) {
    for (const id of [
      "human-labels",
      "human-flags",
      "human-confusion",
      "human-clean",
      "human-detectors",
      "human-auroc",
      "human-strip",
      "human-pace",
    ])
      $(id).innerHTML = empty("no labels yet — charts fill in as you label");
  } else {
    hbars(
      $("human-labels"),
      LABELS.map((q) => ({
        label: q,
        segments: [{ v: count(q), color: LABEL_COLOR[q], tip: `${q}: ${count(q)}` }],
        note: `${count(q)} (${pct(count(q), labels.size)})`,
      })),
      { labelWidth: 80, rowH: 22 },
    );
    const flagCounts = viz.flag_vocab
      .map((f) => [f, got.filter((l) => (l.flags || []).includes(f)).length])
      .sort((a, b) => b[1] - a[1]);
    hbars(
      $("human-flags"),
      flagCounts.map(([f, v]) => ({ label: f, segments: [{ v, color: "#6a7fa0", tip: `${f}: ${v}` }] })),
      { labelWidth: 150, rowH: 14 },
    );

    const byId = new Map(items.map((i) => [i.id, i]));
    const pairs = got.map((l) => [byId.get(l.item_id), l]).filter(([i]) => i);
    heatmap(
      $("human-confusion"),
      ["HIGH", "MEDIUM", "LOW", "no SL label"],
      LABELS,
      (r, c) => pairs.filter(([i, l]) => (i.sl_quality || "no SL label") === r && l.quality === c).length,
      { colColor: (c) => LABEL_COLOR[c], rowTitle: "SpeakLeash", colTitle: "you" },
    );
    heatmap(
      $("human-clean"),
      ["pass", "rejected"],
      LABELS,
      (r, c) => pairs.filter(([i, l]) => (i.clean_ok ? "pass" : "rejected") === r && l.quality === c).length,
      { colColor: (c) => LABEL_COLOR[c], rowTitle: "cleaning", colTitle: "you" },
    );
    renderDetectors(pairs);
    renderAuroc();
    renderStrip(pairs);
    renderPace(got);
  }

  scatter(
    $("human-scatter"),
    items
      .map((i) => {
        const l = labels.get(i.id);
        return {
          x: i.m["loop.loop_score"] ?? 0,
          y: i.m["multilingual.multilingual_score"] ?? 0,
          pos: i.pos,
          color: LABEL_COLOR[l?.quality || "none"],
          alpha: l ? 0.9 : 0.55,
          r: l ? 3.6 : 2.6,
          tip: `${i.source} · ${i.id}\nyour label: ${l ? `${l.quality}${l.flags?.length ? ` · ${l.flags.join(", ")}` : ""}` : "—"}\nloop ${fmt(i.m["loop.loop_score"])} · multilingual ${fmt(i.m["multilingual.multilingual_score"])}`,
        };
      })
      .sort((a, b) => (a.color === LABEL_COLOR.none) - (b.color === LABEL_COLOR.none))
      .reverse(),
    {
      xLabel: "loop_score",
      yLabel: "multilingual_score",
      legendEntries: [...LABELS.map((q) => [q, LABEL_COLOR[q]]), ["not labelled", LABEL_COLOR.none]],
    },
  );

  const k = stats.kappa || {};
  $("human-kappa").innerHTML = Object.keys(k).length
    ? `<table class="mini"><tr><th>pair</th><th>overlap</th><th>Cohen's κ</th></tr>${Object.entries(k)
        .map(([p, v]) => `<tr><td>${esc(p)}</td><td>${v.n}</td><td>${fmt(v.kappa)}</td></tr>`)
        .join("")}</table>`
    : empty("needs two labellers on the same documents (start the app with another --labeller name)");
}

function renderDetectors(pairs) {
  const done = pairs.filter(([, l]) => l.quality !== "SKIP");
  const checks = [
    ["looped", "loop.loop_score", 1],
    ["looped", "loop.duplicate_line_char_fraction", 1],
    ["multilingual", "multilingual.multilingual_score", 1],
    ["wrong_language", "multilingual.pl_share", -1],
    ["garbled_ocr", "lm.nll_mean", 1],
    ["garbled_ocr", "cheap.oov_ratio", 1],
    ["LOW label", "lm.nll_mean", 1],
    ["LOW label", "loop.loop_score", 1],
  ];
  const rows = checks.map(([flag, metric, sign]) => {
    const isPos = ([, l]) => (flag === "LOW label" ? l.quality === "LOW" : (l.flags || []).includes(flag));
    const pos = done
      .filter(isPos)
      .map(([i]) => sign * i.m[metric])
      .filter((v) => v != null && !Number.isNaN(v));
    const neg = done
      .filter((p) => !isPos(p))
      .map(([i]) => sign * i.m[metric])
      .filter((v) => v != null && !Number.isNaN(v));
    return { flag, metric, n: pos.length, auc: pos.length >= 3 && neg.length >= 3 ? auroc(pos, neg) : null };
  });
  const W = 640,
    L = 300,
    rowH = 20,
    pw = W - L - 60;
  let body = `<line x1="${L + pw / 2}" x2="${L + pw / 2}" y1="0" y2="${rows.length * (rowH + 4)}" stroke="#172d3c" stroke-dasharray="3 3"/>`;
  rows.forEach((r, i) => {
    const y = i * (rowH + 4);
    body += `<text x="${L - 6}" y="${y + rowH * 0.7}" text-anchor="end">${esc(r.flag)} ← ${esc(SHORT(r.metric))}${r.metric === "multilingual.pl_share" ? " (low)" : ""}</text>`;
    if (r.auc == null) {
      body += `<text x="${L + 4}" y="${y + rowH * 0.7}" fill="#5a6b78">needs ≥3 flagged (${r.n})</text>`;
      return;
    }
    const x0 = L + pw / 2,
      x1 = L + pw * r.auc;
    body += `<rect x="${Math.min(x0, x1)}" y="${y}" width="${Math.abs(x1 - x0)}" height="${rowH}" fill="${r.auc >= 0.5 ? "#35865a" : "#c95050"}"/><text x="${L + pw + 4}" y="${y + rowH * 0.7}">${r.auc.toFixed(2)} (n=${r.n})</text>`;
  });
  $("human-detectors").innerHTML = svg(W, rows.length * (rowH + 4) + 4, body);
}

function renderAuroc() {
  const ms = (stats.metrics || []).filter((m) => m.high_auroc != null || m.low_auroc != null).slice(0, 20);
  if (!ms.length) {
    $("human-auroc").innerHTML = empty("needs HIGH and non-HIGH (or LOW and non-LOW) labels");
    return;
  }
  const W = 640,
    L = 260,
    rowH = 9,
    gap = 6,
    pw = W - L - 70;
  let body = `<line x1="${L + pw / 2}" x2="${L + pw / 2}" y1="0" y2="${ms.length * (2 * rowH + gap)}" stroke="#172d3c" stroke-dasharray="3 3"/>`;
  ms.forEach((m, i) => {
    const y = i * (2 * rowH + gap);
    body += `<text x="${L - 6}" y="${y + rowH + 3}" text-anchor="end">${esc(m.name)}</text>`;
    [
      ["high_auroc", "#35865a", "HIGH vs rest"],
      ["low_auroc", "#c95050", "LOW vs rest"],
    ].forEach(([k, c, t], j) => {
      const a = m[k];
      if (a == null) return;
      const x0 = L + pw / 2,
        x1 = L + pw * a;
      body += `<rect x="${Math.min(x0, x1)}" y="${y + j * rowH}" width="${Math.abs(x1 - x0)}" height="${rowH - 1}" fill="${c}"><title>${esc(m.name)} — ${t}: ${a.toFixed(3)} (n=${m.n})</title></rect>`;
    });
    body += `<text x="${L + pw + 4}" y="${y + rowH + 3}" fill="#5a6b78">${fmt(m.high_auroc)} / ${fmt(m.low_auroc)}</text>`;
  });
  $("human-auroc").innerHTML =
    legend([
      ["HIGH vs rest", "#35865a"],
      ["LOW vs rest", "#c95050"],
    ]) +
    svg(W, ms.length * (2 * rowH + gap) + 4, body) +
    `<div class="legend"><span>left of the dashed line = lower values mean that label; ${stats.labelled} labelled documents</span></div>`;
}

function renderStrip(pairs) {
  const m = state.humanMetric;
  const rows = LABELS.slice(0, 3).map((q) => [
    q,
    pairs
      .filter(([, l]) => l.quality === q)
      .map(([i]) => i.m[m])
      .filter((v) => v != null),
  ]);
  const all = rows.flatMap(([, v]) => v);
  if (!all.length) {
    $("human-strip").innerHTML = empty("no labelled values for this metric");
    return;
  }
  const sorted = [...all].sort((a, b) => a - b),
    lo = quantile(sorted, 0),
    hi = quantile(sorted, 1),
    span = hi - lo || 1;
  const W = 640,
    L = 80,
    pw = W - L - 20,
    rowH = 46;
  const sx = (v) => L + (pw * (v - lo)) / span;
  let body = "";
  rows.forEach(([q, vals], i) => {
    const y = 6 + i * rowH;
    body += `<text x="${L - 8}" y="${y + rowH / 2}" text-anchor="end">${q} (${vals.length})</text>`;
    vals.forEach((v, k) => {
      body += `<circle cx="${sx(v)}" cy="${y + 8 + ((k * 37) % 23)}" r="2.6" fill="${LABEL_COLOR[q]}" fill-opacity="0.6"/>`;
    });
    if (vals.length) {
      const md = median(vals);
      body += `<line x1="${sx(md)}" x2="${sx(md)}" y1="${y + 2}" y2="${y + 36}" stroke="#172d3c" stroke-width="2"><title>median ${fmt(md)}</title></line>`;
    }
  });
  body += `<text x="${L}" y="${6 + 3 * rowH + 8}">${fmt(lo)}</text><text x="${L + pw}" y="${6 + 3 * rowH + 8}" text-anchor="end">${fmt(hi)}</text>`;
  $("human-strip").innerHTML = svg(W, 3 * rowH + 20, body);
}

function renderPace(got) {
  const rows = got.filter((l) => l.seconds != null).sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  if (rows.length < 2) {
    $("human-pace").innerHTML = empty("needs at least two labels");
    return;
  }
  const s = rows.map((r) => r.seconds),
    cap = Math.max(
      5,
      quantile(
        [...s].sort((a, b) => a - b),
        0.95,
      ) * 1.3,
    );
  const W = 640,
    H = 170,
    L = 36,
    B = 18,
    pw = W - L - 10,
    ph = H - B - 6;
  const sx = (i) => L + (pw * i) / Math.max(1, rows.length - 1),
    sy = (v) => 6 + ph * (1 - Math.min(v, cap) / cap);
  let body = `<text x="${L - 4}" y="10" text-anchor="end">${fmt(cap)}s</text><text x="${L - 4}" y="${6 + ph}" text-anchor="end">0</text>`;
  rows.forEach((r, i) => {
    body += `<circle cx="${sx(i)}" cy="${sy(r.seconds)}" r="2.2" fill="${LABEL_COLOR[r.quality]}" fill-opacity="0.7"><title>#${i + 1}: ${fmt(r.seconds)} s (${r.quality})</title></circle>`;
  });
  const pts = rows.map((_, i) => `${sx(i)},${sy(median(s.slice(Math.max(0, i - 19), i + 1)))}`).join(" ");
  body += `<polyline points="${pts}" fill="none" stroke="#172d3c" stroke-width="1.6"/>`;
  body += `<text x="${L}" y="${H - 2}">first</text><text x="${L + pw}" y="${H - 2}" text-anchor="end">latest (#${rows.length})</text>`;
  $("human-pace").innerHTML = svg(W, H, body);
}

// ---------- wiring ----------
function fillSelect(el, names, current) {
  if (el.options.length !== names.length)
    el.innerHTML = names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  el.value = names.includes(current) ? current : names[0];
}

function render() {
  for (const b of document.querySelectorAll(".dash-tabs button")) b.classList.toggle("on", b.dataset.tab === state.tab);
  $("auto").hidden = !(state.tab === "auto" || state.tab === "both");
  $("human").hidden = !(state.tab === "human" || state.tab === "both");
  fillSelect($("auto-metric"), stats.metric_names, state.autoMetric);
  fillSelect($("human-metric"), stats.metric_names, state.humanMetric);
  if (!$("auto").hidden) renderAuto();
  if (!$("human").hidden) renderHuman();
}

for (const b of document.querySelectorAll(".dash-tabs button"))
  b.onclick = () => {
    state.tab = b.dataset.tab;
    localStorage.setItem("dashTab", state.tab);
    render();
  };
$("auto-metric").onchange = (e) => {
  state.autoMetric = e.target.value;
  localStorage.setItem("autoMetric", state.autoMetric);
  refresh();
};
$("human-metric").onchange = (e) => {
  state.humanMetric = e.target.value;
  localStorage.setItem("humanMetric", state.humanMetric);
  refresh();
};

// Tooltips and click-through for every element with data-tip / data-pos.
const tip = $("tip");
document.addEventListener("mousemove", (e) => {
  const t = e.target.closest?.("[data-tip]");
  if (!t?.dataset.tip) {
    tip.hidden = true;
    return;
  }
  tip.textContent = t.dataset.tip;
  tip.hidden = false;
  tip.style.left = `${Math.min(e.clientX + 14, innerWidth - 380)}px`;
  tip.style.top = `${e.clientY + 14}px`;
});
document.addEventListener("click", (e) => {
  const d = e.target.closest?.("[data-pos]");
  if (d && d.dataset.pos !== "undefined") window.open(`/?pos=${d.dataset.pos}`, "_blank");
});

refresh();
setInterval(() => {
  if (!document.hidden) refresh();
}, 15000);
