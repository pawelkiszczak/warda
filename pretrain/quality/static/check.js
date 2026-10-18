const t = document.getElementById("text"),
  r = document.getElementById("result");
let timer;
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

t.addEventListener("input", () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const x = await (
      await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: t.value }),
      })
    ).json();
    if (!x.available) {
      r.textContent = x.message;
      return;
    }
    r.innerHTML =
      `<h2>Loop metrics</h2><pre>${esc(JSON.stringify(x.loop, null, 2))}</pre>` +
      `<h2>Multilingual metrics</h2><pre>${esc(JSON.stringify(x.multilingual, null, 2))}</pre>` +
      `<h2>Highlights</h2><pre>${esc(JSON.stringify(x.highlights, null, 2))}</pre>`;
  }, 300);
});
