const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node[key] = value;
  }
  node.append(...children.filter((child) => child !== null && child !== undefined && child !== false));
  return node;
}

const ACTION_NAMES = { allow: "Allow", redact: "Redact", ask_user: "Ask user", block: "Block" };
const state = {
  list: null,
  index: 0,
  item: null,
  draft: null,
  started: Date.now(),
  busy: false,
  policyCollapsed: false,
  twinHidden: false,
};

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function setStatus(text, kind = "") {
  $("status").textContent = text;
  $("status").className = kind;
}

const sameSet = (a, b) => a.length === b.length && a.every((x) => b.includes(x));

// ---------------------------------------------------------------- draft

function draftFrom(item) {
  const label = item.label;
  if (label) {
    return {
      verdict: label.verdict,
      category: label.category,
      action: label.action,
      clause: label.clause,
      protected: [...label.protected],
      reason: label.reason,
    };
  }
  const p = item.proposed;
  return {
    verdict: null,
    category: p?.category ?? null,
    action: p?.action ?? null,
    clause: p?.clause ?? null,
    protected: p ? [...p.protected] : [],
    reason: "",
  };
}

function matchesProposed() {
  const p = state.item.proposed;
  const d = state.draft;
  return (
    p &&
    d.category === p.category &&
    d.action === p.action &&
    (d.clause ?? null) === (p.clause ?? null) &&
    sameSet(d.protected, p.protected)
  );
}

// Any edit to the decision makes it a fix in review mode (or a confirm again if it equals the proposal),
// and a plain label in blind mode.
function touch() {
  if (state.list.blind) state.draft.verdict = "label";
  else state.draft.verdict = matchesProposed() ? "confirm" : "fix";
  if ($("status").className === "error") setStatus("");
  renderDecision();
}

function setAction(action) {
  if (!action) return;
  state.draft.action = action;
  touch();
}

function setCategory(category) {
  if (!category) return;
  state.draft.category = category;
  touch();
}

function setClause(clause) {
  state.draft.clause = clause;
  touch();
  renderPolicy();
}

function cycleClause(step) {
  const clauses = [null, ...state.item.clauses];
  const at = clauses.indexOf(state.draft.clause ?? null);
  setClause(clauses[(at + step + clauses.length) % clauses.length]);
}

function setVerdict(verdict) {
  if (!state.list.verdicts.includes(verdict)) return;
  if (verdict === "confirm") {
    const p = state.item.proposed;
    if (!p?.category || !p?.action) {
      setStatus("Nothing proposed to confirm: pick an action (1–4) and a category (⇧1–⇧7).", "error");
      return;
    }
    Object.assign(state.draft, {
      category: p.category,
      action: p.action,
      clause: p.clause,
      protected: [...p.protected],
    });
  }
  state.draft.verdict = verdict;
  renderDecision();
  renderPayload();
  renderPolicy();
}

function markSelection() {
  const selection = window.getSelection();
  const text = selection.toString().trim();
  const payload = $("payload");
  if (!text || !payload.contains(selection.anchorNode) || !payload.contains(selection.focusNode)) {
    setStatus("Select text in the payload first, then press m.", "error");
    return;
  }
  if (!state.draft.protected.includes(text)) state.draft.protected.push(text);
  selection.removeAllRanges();
  touch();
  renderPayload();
}

function dropSpan(span) {
  state.draft.protected =
    span === undefined ? state.draft.protected.slice(0, -1) : state.draft.protected.filter((s) => s !== span);
  touch();
  renderPayload();
}

// ---------------------------------------------------------------- rendering: policy

const CLAUSE_AT_START = /^(?:-\s*)?\*\*\s*(§?\d+(?:\.\d+)*)/;

function inline(text) {
  // **bold** and `code` only; everything else stays literal text (no HTML parsing of policy files).
  const out = [];
  const pattern = /\*\*(.+?)\*\*|`([^`]+)`/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) out.push(text.slice(last, match.index));
    out.push(match[1] !== undefined ? el("strong", {}, match[1]) : el("code", {}, match[2]));
    last = match.index + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function clauseBlock(tag, raw, clauses) {
  const match = CLAUSE_AT_START.exec(raw);
  const clause = match && clauses.includes(match[1]) ? match[1] : null;
  const node = el(tag, {}, ...inline(raw.replace(/^-\s*/, "")));
  if (clause) {
    node.dataset.clause = clause;
    node.title = `Click to cite ${clause}`;
    node.addEventListener("click", () => setClause(state.draft.clause === clause ? null : clause));
  }
  return node;
}

function markdown(text, clauses) {
  const nodes = [];
  let list = null;
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) nodes.push(clauseBlock("p", paragraph.join(" "), clauses));
    paragraph = [];
  };
  for (const line of text.split("\n")) {
    if (!line.trim()) {
      flush();
      list = null;
    } else if (/^#{1,6}\s/.test(line)) {
      flush();
      nodes.push(el("h4", {}, line.replace(/^#+\s*/, "")));
    } else if (/^\s*-\s/.test(line)) {
      flush();
      if (!list) {
        list = el("ul");
        nodes.push(list);
      }
      list.append(clauseBlock("li", line.trim(), clauses));
    } else if (list && /^\s+\S/.test(line)) {
      const last = list.lastElementChild;
      last.append(" ", ...inline(line.trim()));
    } else {
      paragraph.push(line.trim());
    }
  }
  flush();
  return nodes;
}

function renderPolicy() {
  const item = state.item;
  const policy = item.policy;
  $("policy-name").textContent = policy.name || policy.id || "";
  const box = $("policy");
  box.classList.toggle("collapsed", state.policyCollapsed);
  if (!policy.text) {
    box.replaceChildren(
      el(
        "p",
        { class: "warning" },
        policy.id
          ? `No text for policy "${policy.id}": start the app with --policies DIR.`
          : "This item names no policy.",
      ),
    );
    return;
  }
  if (item.kind === "state") {
    box.replaceChildren(el("pre", {}, policy.text));
    return;
  }
  box.replaceChildren(...markdown(policy.text, item.clauses));
  const gold = item.proposed?.clause;
  for (const node of box.querySelectorAll("[data-clause]")) {
    node.classList.toggle("gold-clause", node.dataset.clause === gold);
    node.classList.toggle("chosen-clause", node.dataset.clause === state.draft.clause);
  }
}

// ---------------------------------------------------------------- rendering: call

function ranges(text, spans) {
  const out = [];
  for (const span of spans) {
    if (!span) continue;
    for (let at = text.indexOf(span); at >= 0; at = text.indexOf(span, at + 1)) out.push([at, at + span.length]);
  }
  return out;
}

function highlighted(segments, goldSpans, ownSpans) {
  const text = segments.map((s) => s.text).join("");
  const bounds = [];
  let pos = 0;
  for (const segment of segments) {
    bounds.push({ start: pos, end: pos + segment.text.length, segment });
    pos += segment.text.length;
  }
  const gold = ranges(text, goldSpans);
  const own = ranges(text, ownSpans);
  const cuts = new Set([0, text.length]);
  for (const [a, b] of [...gold, ...own, ...bounds.map((x) => [x.start, x.end])]) {
    cuts.add(a);
    cuts.add(b);
  }
  const points = [...cuts].sort((a, b) => a - b);
  const nodes = [];
  for (let i = 0; i + 1 < points.length; i++) {
    const [a, b] = [points[i], points[i + 1]];
    if (a === b) continue;
    const segment = bounds.find((x) => x.start <= a && a < x.end)?.segment;
    let node = document.createTextNode(text.slice(a, b));
    if (segment?.placeholder) {
      const unresolved = segment.text === segment.placeholder;
      node = el("span", { class: `ph${unresolved ? " unresolved" : ""}`, title: segment.placeholder }, node);
    }
    const inside = (list) => list.some(([x, y]) => x <= a && b <= y);
    if (inside(own)) node = el("mark", { class: "own", title: "your protected span" }, node);
    else if (inside(gold)) node = el("mark", { title: "proposed protected span" }, node);
    nodes.push(node);
  }
  return nodes;
}

function renderPayload() {
  const item = state.item;
  const segments = item.kind === "state" ? [{ text: item.body }] : item.payload;
  const gold = item.proposed?.protected ?? [];
  $("payload").replaceChildren(...highlighted(segments, gold, state.draft.protected));
}

function renderCall() {
  const item = state.item;
  const context = item.kind === "record" ? item.context : [];
  $("context").hidden = !context.length;
  $("context").replaceChildren(
    ...context
      .filter((entry) => entry.key !== "destination_class")
      .map((entry) => {
        const value = el("dd", {}, entry.value);
        if (entry.key === "destination") {
          const cls = context.find((x) => x.key === "destination_class")?.value;
          if (cls) value.append(el("span", { class: `dest-class ${cls}` }, cls));
        }
        return el("div", {}, el("dt", {}, entry.key), value);
      }),
  );
  const facts = item.kind === "record" ? Object.entries(item.facts) : [];
  $("facts").hidden = !facts.length;
  $("facts").replaceChildren(
    ...facts.map(([key, value]) => el("span", { class: "fact" }, `${key} = ${JSON.stringify(value)}`)),
  );
  renderPayload();
  $("question-card").hidden = !item.question;
  $("question").textContent = item.question || "";
  $("options").replaceChildren(
    ...item.options.map((text, i) => el("li", { class: i === item.gold ? "gold" : "" }, text)),
  );
}

// ---------------------------------------------------------------- rendering: twin diff

function tokens(text) {
  // words keep their trailing whitespace, so a one-word edit is one token, not word + space + word
  return text.match(/[\p{L}\p{N}_]+\s*|[^\s\p{L}\p{N}_]\s*|\s+/gu) || [];
}

function diff(before, after) {
  const a = tokens(before);
  const b = tokens(after);
  if (a.length * b.length > 4_000_000) return [el("span", {}, after)];
  const table = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  // Group each changed run as one deletion followed by one insertion, so edits read as "old → new".
  const out = [];
  let removed = "";
  let added = "";
  const flush = () => {
    // whitespace both sides end with (a line break after the edit) is unchanged text, not part of the edit
    let keep = 0;
    while (
      removed &&
      added &&
      keep < Math.min(removed.length, added.length) &&
      /\s/.test(removed.at(-1 - keep)) &&
      removed.at(-1 - keep) === added.at(-1 - keep)
    ) {
      keep++;
    }
    if (removed) out.push(el("del", {}, removed.slice(0, removed.length - keep)));
    if (added) out.push(el("ins", {}, added.slice(0, added.length - keep)));
    if (keep) out.push(document.createTextNode(added.slice(added.length - keep)));
    removed = "";
    added = "";
  };
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      flush();
      out.push(document.createTextNode(a[i]));
      i++;
      j++;
    } else if (j < b.length && (i === a.length || table[i][j + 1] >= table[i + 1][j])) {
      added += b[j++];
    } else {
      removed += a[i++];
    }
  }
  flush();
  return out;
}

function renderTwin() {
  const item = state.item;
  const twin = item.twin;
  $("twin-card").hidden = !twin;
  if (!twin) return;
  $("twin-title").textContent =
    `${item.meta.role || "twin"} of ${twin.id} (${twin.role}, gold ${twin.proposed.action})`;
  const current = Object.fromEntries((item.context || []).map((x) => [x.key, x.value]));
  current.facts = item.facts;
  current.policy = item.policy.id;
  const changes = Object.entries(twin.context)
    .filter(([key, value]) => JSON.stringify(value ?? null) !== JSON.stringify(current[key] ?? null))
    .map(([key, value]) => `${key}: ${JSON.stringify(value)} → ${JSON.stringify(current[key])}`);
  $("twin-context").textContent = changes.length ? `Changed: ${changes.join(" · ")}` : "Same context; payload edit:";
  const payload = item.payload.map((s) => s.text).join("");
  $("twin-diff").replaceChildren(...diff(twin.payload, payload));
  $("twin-body").hidden = state.twinHidden;
}

function renderMeta() {
  const entries = Object.entries(state.item.meta);
  $("meta-card").hidden = !entries.length;
  $("meta").replaceChildren(
    ...entries.map(([key, value]) => el("div", {}, el("dt", {}, key), el("dd", {}, String(value)))),
  );
}

// ---------------------------------------------------------------- rendering: decision panel

function renderProposed() {
  const p = state.item.proposed;
  $("proposed").hidden = !p;
  if (!p) return;
  const rows = [
    ["action", p.action],
    ["category", p.category],
    ["acceptable", p.acceptable.length > 1 ? p.acceptable.join(", ") : null],
    ["clause", p.clause],
    ["tier", p.tier],
    ["protected", p.protected.length ? p.protected.join(" · ") : null],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");
  $("proposed-list").replaceChildren(
    ...rows.flatMap(([key, value]) => [el("dt", {}, key), el("dd", {}, String(value))]),
  );
  $("rationale").textContent = p.rationale || "";
}

function renderDecision() {
  const { list, item, draft } = state;
  const p = item.proposed;
  $("actions").replaceChildren(
    ...list.actions.map((action, i) =>
      el(
        "button",
        {
          type: "button",
          class: `action${draft.action === action ? " selected" : ""}${p?.action === action ? " proposed-mark" : ""}`,
          style: `--c: var(--${action})`,
          onclick: () => setAction(action),
        },
        el("span", {}, ACTION_NAMES[action] || action),
        el("kbd", {}, String(i + 1)),
      ),
    ),
  );
  $("categories").replaceChildren(
    ...list.categories.map((category, i) =>
      el(
        "button",
        {
          type: "button",
          class: `chip${draft.category === category ? " selected" : ""}${p?.category === category ? " proposed-mark" : ""}`,
          onclick: () => setCategory(category),
        },
        category,
        el("kbd", {}, `⇧${i + 1}`),
      ),
    ),
  );
  $("clause-section").hidden = !item.clauses.length;
  $("clauses").replaceChildren(
    ...[null, ...item.clauses].map((clause) =>
      el(
        "button",
        {
          type: "button",
          class: `chip${(draft.clause ?? null) === clause ? " selected" : ""}${p?.clause === clause && clause ? " proposed-mark" : ""}`,
          onclick: () => setClause(clause),
        },
        clause ?? "none",
      ),
    ),
  );
  $("spans").replaceChildren(
    ...draft.protected.map((span) =>
      el(
        "li",
        { title: span },
        el("span", {}, span),
        el("button", { type: "button", title: "Remove", onclick: () => dropSpan(span) }, "×"),
      ),
    ),
  );
  $("spans-warning").hidden = !(draft.action === "redact" && !draft.protected.length && item.kind === "record");
  if (document.activeElement !== $("reason")) $("reason").value = draft.reason;
  const shortcuts = { confirm: "Space", fix: "f", label: "", reject: "r", unsure: "u" };
  $("verdicts").replaceChildren(
    ...list.verdicts.map((verdict) =>
      el(
        "button",
        {
          type: "button",
          class: `verdict ${verdict}${draft.verdict === verdict ? " selected" : ""}`,
          onclick: () => setVerdict(verdict),
        },
        verdict,
        shortcuts[verdict] ? " " : "",
        shortcuts[verdict] ? el("kbd", {}, shortcuts[verdict]) : null,
      ),
    ),
  );
}

// ---------------------------------------------------------------- queue and navigation

function renderQueue() {
  const { list } = state;
  const done = list.items.filter((x) => x.verdict).length;
  $("progress").textContent = `${done} / ${list.total}`;
  $("progress-bar").style.width = `${list.total ? (100 * done) / list.total : 0}%`;
  $("position").textContent = `${state.index + 1} / ${list.total}`;
  const rows = $("queue").children;
  list.items.forEach((entry, i) => {
    const button = rows[i]?.firstElementChild;
    if (!button) return;
    button.classList.toggle("current", i === state.index);
    button.firstElementChild.className = `dot ${entry.verdict || ""}`;
  });
  rows[state.index]?.scrollIntoView({ block: "nearest" });
}

function buildQueue() {
  $("queue").replaceChildren(
    ...state.list.items.map((entry, i) =>
      el(
        "li",
        {},
        el("button", { type: "button", title: entry.id, onclick: () => open(i) }, el("i", { class: "dot" }), entry.id),
      ),
    ),
  );
}

function nextUndone(from) {
  const items = state.list.items;
  for (let step = 1; step <= items.length; step++) {
    const index = (from + step) % items.length;
    if (!items[index].verdict) return index;
  }
  return null;
}

// One load or save at a time: a key pressed mid-request would otherwise label the item that is being replaced.
async function exclusive(task) {
  if (state.busy) return;
  state.busy = true;
  try {
    await task();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    state.busy = false;
  }
}

async function show(index) {
  const items = state.list.items;
  if (!items.length) {
    setStatus("No items to label.");
    return;
  }
  const position = (index + items.length) % items.length;
  const item = await api(`/api/item/${encodeURIComponent(items[position].id)}`);
  state.index = position;
  state.item = item;
  state.draft = draftFrom(item);
  history.replaceState(null, "", `#${encodeURIComponent(item.id)}`);
  renderPolicy();
  renderCall();
  renderTwin();
  renderMeta();
  renderProposed();
  renderDecision();
  renderQueue();
  setStatus(item.label ? `Your label: ${item.label.verdict} · ${item.label.created_at}` : "");
  state.started = Date.now();
}

async function saveCurrent(advance = true) {
  const { draft } = state;
  if (!draft.verdict) {
    setStatus(
      state.list.blind
        ? "Pick an action (1–4) and a category (⇧1–⇧7), or r / u."
        : "Space confirms; 1–4 / ⇧1–⇧7 fix; r rejects; u unsure.",
      "error",
    );
    return;
  }
  if ((draft.verdict === "fix" || draft.verdict === "label") && (!draft.action || !draft.category)) {
    setStatus("Both an action (1–4) and a category (⇧1–⇧7) are needed.", "error");
    return;
  }
  const keeps = draft.verdict === "fix" || draft.verdict === "label";
  const body = {
    item_id: state.item.id,
    verdict: draft.verdict,
    category: keeps ? draft.category : null,
    action: keeps ? draft.action : null,
    clause: keeps ? draft.clause : null,
    protected: keeps ? draft.protected : [],
    reason: $("reason").value,
    seconds: Math.round((Date.now() - state.started) / 1000),
  };
  try {
    await api("/api/label", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    setStatus(`Not saved: ${error.message}`, "error");
    return;
  }
  document.activeElement?.blur();
  state.list.items[state.index].verdict = draft.verdict;
  const next = advance ? nextUndone(state.index) : state.index;
  await show(next ?? state.index);
  setStatus(next === null ? "Saved. Every item is labelled." : `Saved ${body.item_id} as ${body.verdict}.`, "ok");
}

const save = () => exclusive(() => saveCurrent());
const open = (index) => exclusive(() => show(index));

function confirmAndSave() {
  exclusive(async () => {
    const before = state.draft.verdict;
    setVerdict("confirm");
    if (state.draft.verdict === "confirm") await saveCurrent();
    else state.draft.verdict = before;
  });
}

// ---------------------------------------------------------------- keyboard

function onKey(event) {
  if ($("help").open) return;
  const field = event.target.closest("textarea, input, select");
  if (field) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      state.draft.reason = field.value;
      field.blur();
      save();
    } else if (event.key === "Escape") {
      state.draft.reason = field.value;
      field.blur();
    }
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (state.busy || !state.item) {
    event.preventDefault();
    return;
  }
  const digit = /^(?:Digit|Numpad)([1-9])$/.exec(event.code);
  if (digit) {
    event.preventDefault();
    const n = Number(digit[1]) - 1;
    if (event.shiftKey) setCategory(state.list.categories[n]);
    else setAction(state.list.actions[n]);
    return;
  }
  const keys = {
    " ": () => (state.list.blind ? null : confirmAndSave()),
    Enter: save,
    c: () => setVerdict("confirm"),
    f: () => setVerdict("fix"),
    r: () => setVerdict("reject"),
    u: () => setVerdict("unsure"),
    m: markSelection,
    M: () => dropSpan(),
    "[": () => cycleClause(-1),
    "]": () => cycleClause(1),
    "/": () => $("reason").focus(),
    "?": () => $("help").showModal(),
    j: () => open(state.index + 1),
    ArrowRight: () => open(state.index + 1),
    k: () => open(state.index - 1),
    ArrowLeft: () => open(state.index - 1),
    n: () => {
      const next = nextUndone(state.index);
      if (next !== null) open(next);
    },
    p: togglePolicy,
    t: toggleTwin,
  };
  const action = keys[event.key];
  if (action) {
    event.preventDefault();
    action();
  }
}

function togglePolicy() {
  state.policyCollapsed = !state.policyCollapsed;
  $("policy").classList.toggle("collapsed", state.policyCollapsed);
  $("policy-toggle").firstChild.textContent = state.policyCollapsed ? "expand " : "collapse ";
}

function toggleTwin() {
  state.twinHidden = !state.twinHidden;
  $("twin-body").hidden = state.twinHidden;
  $("twin-toggle").firstChild.textContent = state.twinHidden ? "show " : "hide ";
}

// ---------------------------------------------------------------- start

async function init() {
  state.list = await api("/api/items");
  const { list } = state;
  $("labeller").textContent = list.labeller;
  $("mode").textContent = list.blind ? "blind" : "review";
  $("mode").classList.toggle("blind", list.blind);
  $("mode").title = list.blind
    ? "The proposed gold and hinting metadata are hidden (Brama R-08)"
    : "Confirm or fix the proposed gold";
  buildQueue();
  $("save").addEventListener("click", save);
  $("help-open").addEventListener("click", () => $("help").showModal());
  $("policy-toggle").addEventListener("click", togglePolicy);
  $("twin-toggle").addEventListener("click", toggleTwin);
  $("next-undone").addEventListener("click", () => {
    const next = nextUndone(state.index);
    if (next !== null) open(next);
  });
  $("reason").addEventListener("input", (event) => {
    state.draft.reason = event.target.value;
  });
  document.addEventListener("keydown", onKey);
  // #item-id links: replaceState in show() does not fire this, so only a typed or pasted link does
  window.addEventListener("hashchange", () => {
    const index = list.items.findIndex((x) => x.id === decodeURIComponent(location.hash.slice(1)));
    if (index >= 0) open(index);
  });
  setInterval(() => {
    $("timer").textContent = String(Math.round((Date.now() - state.started) / 1000));
  }, 1000);
  const ids = list.items.map((x) => x.id);
  const hash = decodeURIComponent(location.hash.slice(1));
  const start = ids.includes(hash) ? ids.indexOf(hash) : list.last ? ids.indexOf(list.last) : (nextUndone(-1) ?? 0);
  await open(start);
}

init().catch((error) => setStatus(error.message, "error"));
