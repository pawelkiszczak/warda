const $ = (id) => document.getElementById(id);
const state = { list: null, index: 0, item: null, verdict: null, started: Date.now() };

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function setStatus(text, isError = false) {
  $("status").textContent = text;
  $("status").className = isError ? "error" : "";
}

function fillSelect(select, values) {
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
}

function updateProgress() {
  state.list.done = state.list.items.filter((item) => item.done).length;
  $("progress").textContent = `${state.list.done}/${state.list.total}`;
  $("position").textContent = `${state.index + 1}/${state.list.total}`;
}

function setVerdict(verdict) {
  state.verdict = verdict;
  for (const button of document.querySelectorAll("[data-verdict]")) {
    button.classList.toggle("active", button.dataset.verdict === verdict);
  }
  $("fix").hidden = verdict !== "fix";
}

function nextUndone(from) {
  const items = state.list.items;
  for (let step = 1; step <= items.length; step++) {
    const index = (from + step) % items.length;
    if (!items[index].done) return index;
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
    setStatus(error.message, true);
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
  $("policy").textContent = item.policy || "(no policy block)";
  $("body").textContent = item.body;
  $("question-box").hidden = !item.question;
  $("question").textContent = item.question || "";
  $("options").replaceChildren(
    ...item.options.map((text, i) => {
      const li = document.createElement("li");
      li.textContent = text;
      li.classList.toggle("gold", i === item.gold);
      return li;
    }),
  );
  $("proposed-category").textContent = item.proposed.category ?? "none proposed";
  $("proposed-action").textContent = item.proposed.action ?? "none proposed";
  $("meta").textContent = Object.entries(item.meta)
    .map(([key, value]) => `${key}: ${value}`)
    .join(" · ");
  const label = item.label;
  $("category").value = label?.category ?? item.proposed.category ?? state.list.categories[0];
  $("action").value = label?.action ?? item.proposed.action ?? state.list.actions[0];
  $("reason").value = label?.reason ?? "";
  setVerdict(label?.verdict ?? null);
  setStatus(label ? `Labelled: ${label.verdict} (${label.created_at})` : "");
  state.started = Date.now();
  updateProgress();
}

async function saveCurrent() {
  if (!state.verdict) {
    setStatus("Pick a verdict first: c, f, r or u.", true);
    return;
  }
  const body = {
    item_id: state.item.id,
    verdict: state.verdict,
    category: state.verdict === "fix" ? $("category").value : null,
    action: state.verdict === "fix" ? $("action").value : null,
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
    setStatus(`Not saved: ${error.message}`, true);
    return;
  }
  document.activeElement?.blur();
  state.list.items[state.index].done = true;
  const next = nextUndone(state.index);
  if (next === null) {
    await show(state.index);
    setStatus("Saved. Every item is labelled.");
  } else {
    await show(next);
  }
}

const save = () => exclusive(saveCurrent);
const open = (index) => exclusive(() => show(index));

function onKey(event) {
  if (state.busy) return;
  const field = event.target.closest("textarea, select, input");
  if (field) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      save();
    } else if (event.key === "Escape") {
      field.blur();
    }
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const verdicts = { c: "confirm", f: "fix", r: "reject", u: "unsure" };
  if (verdicts[event.key]) {
    event.preventDefault();
    setVerdict(verdicts[event.key]);
    if (event.key === "f") $("category").focus();
  } else if (event.key === "Enter") {
    event.preventDefault();
    save();
  } else if (event.key === "ArrowLeft") {
    open(state.index - 1);
  } else if (event.key === "ArrowRight") {
    open(state.index + 1);
  } else if (event.key === "n") {
    const next = nextUndone(state.index);
    if (next !== null) open(next);
  }
}

async function init() {
  state.list = await api("/api/items");
  $("labeller").textContent = `Labeller: ${state.list.labeller}`;
  fillSelect($("category"), state.list.categories);
  fillSelect($("action"), state.list.actions);
  for (const button of document.querySelectorAll("[data-verdict]")) {
    button.addEventListener("click", () => setVerdict(button.dataset.verdict));
  }
  $("save").addEventListener("click", save);
  $("previous").addEventListener("click", () => open(state.index - 1));
  $("next").addEventListener("click", () => open(state.index + 1));
  $("next-undone").addEventListener("click", () => {
    const next = nextUndone(state.index);
    if (next !== null) open(next);
  });
  document.addEventListener("keydown", onKey);
  setInterval(() => {
    $("timer").textContent = `${Math.round((Date.now() - state.started) / 1000)} s`;
  }, 1000);
  const ids = state.list.items.map((item) => item.id);
  const last = state.list.last ? ids.indexOf(state.list.last) : -1;
  await open(last >= 0 ? last : (nextUndone(-1) ?? 0));
}

init().catch((error) => setStatus(error.message, true));
