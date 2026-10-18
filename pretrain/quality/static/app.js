const FLAGS = [
  "looped",
  "multilingual",
  "wrong_language",
  "boilerplate",
  "spam_ads",
  "machine_generated",
  "garbled_ocr",
  "truncated_fragment",
  "personal_data",
  "offensive",
  "code_or_markup",
  "list_or_table",
];
const KEY = {
  l: "looped",
  m: "multilingual",
  w: "wrong_language",
  b: "boilerplate",
  s: "spam_ads",
  x: "machine_generated",
  g: "garbled_ocr",
  t: "truncated_fragment",
  p: "personal_data",
  o: "offensive",
  k: "code_or_markup",
  a: "list_or_table",
};
const STYLO_KEY = [
  "L_ERROR",
  "L_TTR_IA",
  "L_TTR_LA",
  "L_CONT_A",
  "L_CONT_T",
  "L_CONT_L",
  "L_STOP",
  "SY_S_DE",
  "SY_S_EX",
  "SY_S_IN",
  "SY_NPHR",
  "GR_LINK",
  "GR_HASH",
  "GR_MENTION",
  "GR_EMOJI",
  "GR_UPPER",
  "PUNCT_TOTAL",
];
let item = null,
  quality = "MEDIUM",
  confidence = 2,
  flags = new Set(),
  started = Date.now(),
  showHighlights = true,
  position = 0;

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
const format = (n) => (Number.isInteger(n) ? String(n) : Number(n).toPrecision(3));
function setStatus(message) {
  $("status").textContent = message || "";
}

FLAGS.forEach((f) => {
  $("flaglist").insertAdjacentHTML(
    "beforeend",
    `<label title="${esc(f)}"><input type="checkbox" value="${f}">${f}</label>`,
  );
});
$("flaglist").addEventListener("change", (e) => {
  if (e.target.checked) flags.add(e.target.value);
  else flags.delete(e.target.value);
});

async function load(pos) {
  const data = await (await fetch(`/api/items?offset=${pos}&limit=1`)).json();
  if (!data.items.length) return;
  item = data.items[0];
  position = pos;
  started = Date.now();
  quality = "MEDIUM";
  confidence = 2;
  flags = new Set();
  $("note").value = "";
  const detail = await (await fetch(`/api/item/${encodeURIComponent(item.id)}`)).json();
  const prior = detail.latest_label?.[0];
  if (prior) {
    quality = prior.quality;
    confidence = prior.confidence;
    flags = new Set(JSON.parse(prior.flags || "[]"));
    $("note").value = prior.note || "";
  }
  $("progress").textContent = `${pos + 1} / ${data.total}`;
  $("origin").textContent = `${item.origin} · ${item.source}`;
  $("badge").textContent = item.truncated ? "TRUNCATED" : "";
  document.querySelectorAll("#flaglist input").forEach((x) => {
    x.checked = flags.has(x.value);
  });
  renderText();
  renderItem();
}

function renderText() {
  const text = item.text || "",
    spans = [];
  if (showHighlights) {
    (item.highlights?.loop_spans || []).forEach((x) => {
      spans.push([x[0], x[1], '<mark class="loop" title="Repeated text">', "</mark>"]);
    });
    (item.highlights?.foreign_spans || []).forEach((x) => {
      spans.push([x[0], x[1], `<span class="foreign" title="Foreign language: ${esc(x[2])}">`, "</span>"]);
    });
  }
  spans.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  let html = "",
    at = 0;
  for (const [s, e, open, close] of spans) {
    const start = Math.max(0, s),
      end = Math.min(text.length, e);
    if (start < at || start >= text.length) continue;
    html += esc(text.slice(at, start)) + open + esc(text.slice(start, end)) + close;
    at = end;
  }
  $("text").innerHTML = html + esc(text.slice(at));
}

function metricList(group, title) {
  const vals = item.features?.[group];
  if (!vals || typeof vals !== "object")
    return `<div class="metric-group"><b>${title}</b> <span class="muted">not available</span></div>`;
  return `<div class="metric-group"><b>${title}</b>${Object.entries(vals)
    .map(([k, v]) => metric(`${group}.${k}`, k, v))
    .join("")}</div>`;
}

function metric(name, label, value) {
  const p = item.metric_percentiles?.[name],
    num = typeof value === "number";
  const display = num ? format(value) : typeof value === "object" ? JSON.stringify(value) : value;
  return `<div class="metric ${p?.extreme ? "extreme" : ""}" title="${esc(p?.description || "")}"><span>${esc(label)}</span><span>${esc(display)} ${num && p ? `<small>${format(p.percentile)}th pct</small>` : ""}</span></div>`;
}

function renderItem() {
  const loop = item.features?.loop || {},
    multi = item.features?.multilingual || {},
    shares = multi.lang_shares || {},
    stylo = item.features?.stylometrix || {};
  const shareEntries = Object.entries(shares).sort((a, b) => b[1] - a[1]);
  const languageBar = shareEntries
    .map(
      ([lang, share], i) =>
        `<span class="share ${lang === "pl" ? "polish" : "foreign-share"}" style="width:${Math.max(0, share * 100)}%;background:${i % 2 ? "#e99c47" : "#4088b7"}" title="${esc(lang)} ${format(share * 100)}%">${share * 100 >= 8 ? `${esc(lang)} ${format(share * 100)}%` : ""}</span>`,
    )
    .join("");
  const foreign = shareEntries.filter(([lang]) => lang !== "pl");
  $("metrics").innerHTML =
    `<h2>Current data metrics</h2>` +
    `<div class="metric-group"><b>Loop</b>${metric("loop.loop_score", "loop_score", loop.loop_score)}` +
    `<div class="gauge"><i style="width:${Math.min(100, Math.max(0, (loop.loop_score || 0) * 100))}%"></i></div>` +
    `${Object.entries(loop)
      .filter(([k]) => k !== "loop_score")
      .map(([k, v]) => metric(`loop.${k}`, k, v))
      .join("")}</div>` +
    `<div class="metric-group"><b>Multilingual</b>${metric("multilingual.multilingual_score", "multilingual_score", multi.multilingual_score)}` +
    `${metric("multilingual.top_lang", "top_lang", multi.top_lang)}${metric("multilingual.pl_share", "pl_share", multi.pl_share)}` +
    `<div class="bar">${languageBar || '<span class="muted">language shares unavailable</span>'}</div>` +
    `<div class="muted">Language shares: ${shareEntries.map(([lang, share]) => `${esc(lang)} ${format(share * 100)}%`).join(" · ") || "unavailable"}</div>` +
    `<div><b>Foreign languages:</b> ${foreign.map(([lang, share]) => `${esc(lang)} (${format(share * 100)}%)`).join(", ") || "none detected"}</div></div>` +
    `${metricList("lm", "LM perplexity")}${metricList("cheap", "Cheap features")}` +
    `<div class="metric-group"><b>StyloMetrix key metrics</b>${
      STYLO_KEY.filter((k) => k in stylo)
        .map((k) => metric(`stylometrix.${k}`, k, stylo[k]))
        .join("") || '<span class="muted">not available</span>'
    }` +
    `<details><summary>All StyloMetrix metrics (${Object.keys(stylo).length})</summary>${metricList("stylometrix", "StyloMetrix")}</details></div>` +
    `<details><summary>All feature groups</summary>${Object.keys(item.features || {})
      .filter((g) => g !== "stylometrix" && g !== "loop" && g !== "multilingual" && g !== "lm" && g !== "cheap")
      .map((g) => metricList(g, g))
      .join("")}</details>`;
  const m = item.source_meta || {};
  const metadata = [
    ["origin", item.origin],
    ["source", item.source],
    ["url", item.url],
    ["license", item.license],
    ["SpeakLeash quality", m.quality],
    ["FineWeb language_score", m.language_score],
    ["minhash_cluster_size", m.minhash_cluster_size],
    ["strata", JSON.stringify(item.strata || {})],
    ["clean_ok", item.pipeline?.clean_ok],
    ["clean_reason", item.pipeline?.clean_reason],
  ];
  $("metadata").innerHTML =
    `<h2>Source metadata</h2>${metadata.map(([k, v]) => `<div class="metadata-row"><b>${esc(k)}:</b> ${esc(typeof v === "number" ? format(v) : (v ?? "—"))}</div>`).join("")}`;
  document.querySelectorAll("[data-quality]").forEach((b) => {
    b.classList.toggle("active", b.dataset.quality === quality);
  });
  $("confidence").textContent = confidence;
}

async function save(next = true) {
  if (!item) return;
  const res = await fetch("/api/label", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      item_id: item.id,
      quality,
      flags: [...flags],
      note: $("note").value,
      confidence,
      seconds: (Date.now() - started) / 1000,
    }),
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.error) message = body.error;
    } catch {
      /* no body; keep the status line */
    }
    setStatus(`Save failed: ${message}`);
    return;
  }
  setStatus("");
  if (next) load(Math.min(position + 1, Number($("progress").textContent.split("/")[1]) - 1));
}

async function nextUnlabelled() {
  const total = Number($("progress").textContent.split("/")[1]);
  for (let offset = 0; offset < total; offset += 100) {
    const page = await (await fetch(`/api/items?offset=${offset}&limit=100`)).json();
    const found = page.items.findIndex((x) => !x.labelled && x.id !== item.id);
    if (found >= 0) return load(offset + found);
  }
}

document.querySelectorAll("[data-quality]").forEach((b) => {
  b.onclick = () => {
    quality = b.dataset.quality;
    renderItem();
  };
});
$("confidence").onclick = () => {
  confidence = (confidence % 3) + 1;
  renderItem();
};
$("save").onclick = () => save();
$("previous").onclick = () => load(Math.max(0, position - 1));
$("next").onclick = () => load(position + 1);
$("unlabelled").onclick = nextUnlabelled;
$("mono").onclick = () => $("text").classList.toggle("mono");
$("highlight").onclick = () => {
  showHighlights = !showHighlights;
  $("highlight").textContent = `Highlights ${showHighlights ? "on" : "off"}`;
  renderText();
};

document.addEventListener("keydown", (e) => {
  if (e.target.matches("textarea,input")) return;
  if (e.key === "1") quality = "HIGH";
  else if (e.key === "2") quality = "MEDIUM";
  else if (e.key === "3") quality = "LOW";
  else if (e.key === "0") quality = "SKIP";
  else if (e.key === "c") {
    confidence = (confidence % 3) + 1;
    renderItem();
  } else if (e.key === "n") $("note").focus();
  else if (e.key === "Enter") {
    save();
    return;
  } else if (e.key === "ArrowLeft") {
    load(Math.max(0, position - 1));
    return;
  } else if (e.key === "ArrowRight") {
    load(position + 1);
    return;
  } else if (e.key === "u") {
    nextUnlabelled();
    return;
  } else if (KEY[e.key.toLowerCase()]) {
    const x = KEY[e.key.toLowerCase()];
    flags.has(x) ? flags.delete(x) : flags.add(x);
    document.querySelector(`#flaglist input[value="${x}"]`).checked = flags.has(x);
  } else return;
  renderItem();
});

load(Math.max(0, Number(new URLSearchParams(location.search).get("pos")) || 0)); // dashboard charts link here with ?pos=N
