// ZecPy Live: renders the demo's event stream. Live from /events, or with ?replay from the
// recorded run in replay.json (?replay=instant shows it all at once).
(() => {
  const SCENES = [
    { id: "checkout", name: "Checkout", desc: "A shop invoices 0.0015 ZEC and sees it paid" },
    { id: "control", name: "Control: zcash-devtool", desc: "The reference wallet creates and syncs" },
    { id: "memos", name: "Memo fetch", desc: "Each unknown memo fetched among 7 decoys" },
    { id: "agent", name: "Agent pays a link", desc: "A budget the payment link cannot exceed" },
    { id: "cold", name: "Cold signing", desc: "The server holds a viewing key, nothing more" },
  ];
  const ACTOR = { zecpy: "ZecPy", devtool: "zcash-devtool" };
  const LABEL = {
    public: "Nothing", coarse: "A wide window", broadcast: "A new transaction",
    identifying: "Who you are", decoyed: "1 of 8, hidden",
  };
  const MAX_ROWS = 400;

  const $ = (id) => document.getElementById(id);
  const fmt = new Intl.NumberFormat("en-US");
  const state = {
    scenes: Object.fromEntries(SCENES.map((s) => [s.id, { state: "idle" }])),
    current: null, start: null, t0: null, steps: [], audit: [], filter: "all",
    batch: [], real: new Set(), revealed: false, running: false, live: false,
  };

  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const short = (hex) => (hex && hex.length > 20 ? `${hex.slice(0, 10)}…${hex.slice(-6)}` : hex || "");
  // Ledger times run from the first event of the session, so scenes keep their order.
  const clock = (t) => {
    if (!state.t0) return "";
    const s = Math.max(0, t - state.t0);
    return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;
  };

  // Scenes
  function renderScenes() {
    const list = $("scenes");
    list.replaceChildren(...SCENES.map((s) => {
      const info = state.scenes[s.id];
      const li = el("li", `scene${state.current === s.id ? " current" : ""}`);
      li.append(el("span", "scene-name", s.name), el("span", "scene-desc", s.desc));
      const st = el("span", "scene-state");
      if (info.state === "running") st.textContent = "Running";
      else if (info.state === "failed") st.textContent = "Failed: " + (info.error || "see the server log");
      else if (info.state === "done") {
        st.append(`Done · ${fmt.format(info.requests)} requests, `);
        if (s.id === "memos") st.append(`${fmt.format(info.identifying)} in the memo fetch, each 1 of 8`);
        else st.append(el("span", info.identifying ? "bad" : "", `${fmt.format(info.identifying)} identifying`));
      } else st.textContent = "Not run";
      li.append(st);
      const run = el("button", "ghost", info.state === "done" ? "Run again" : "Run");
      run.type = "button";
      run.disabled = state.running || !state.live;
      run.addEventListener("click", () => start(s.id));
      li.append(run);
      return li;
    }));
  }

  async function start(id) {
    state.running = true;
    renderScenes();
    try {
      const res = await fetch(`/scenes/${id}`, { method: "POST" });
      if (!res.ok && res.status !== 500) state.running = false;
    } catch { state.running = false; }
    renderScenes();
  }

  // Narration
  function renderSteps() {
    const ol = $("steps");
    const scene = SCENES.find((s) => s.id === state.current);
    $("narration-title").textContent = scene ? scene.name : "Narration";
    if (!state.steps.length) {
      ol.replaceChildren(el("li", "empty", "No scene has run yet."));
      return;
    }
    ol.replaceChildren(...state.steps.map((s) => {
      const li = el("li", `step ${s.status}`);
      const word = { run: "Working", ok: "Done", refused: "Refused", failed: "Failed" }[s.status] || "";
      li.append(el("span", "state", word), el("span", "text", s.text));
      for (const key of ["address", "uri", "txid"]) {
        if (s[key]) li.append(el("span", "extra", `${key} ${key === "uri" ? s[key] : short(s[key])}`));
      }
      if (s.summary) li.append(el("pre", "extra", s.summary));
      return li;
    }));
  }

  // KPIs and the finding
  function count(actor, label) {
    return state.audit.filter((a) => a.actor === actor && (!label || a.label === label)).length;
  }
  // A ZecPy GetTransaction is its opt-in memo fetch: one of 8, the real one hidden.
  const decoyed = (a) => a.actor === "zecpy" && a.method === "GetTransaction";
  const kind = (a) => (decoyed(a) ? "decoyed" : a.label);
  function renderKpis() {
    const zid = state.audit.filter((a) => a.actor === "zecpy" && kind(a) === "identifying").length;
    const did = count("devtool", "identifying");
    const memo = state.audit.filter(decoyed).length;
    $("k-z-id").textContent = fmt.format(zid);
    $("k-z-id").classList.toggle("bad", zid > 0);
    $("k-z-sub").textContent = `of ${fmt.format(count("zecpy") - memo)} requests, memo fetch aside`;
    $("k-d-id").textContent = fmt.format(did);
    $("k-d-id").classList.toggle("bad", did > 0);
    $("k-d-sub").textContent = `of ${fmt.format(count("devtool"))} requests`;
    $("k-memo").textContent = memo ? `${fmt.format(state.real.size || memo / 8)} in ${fmt.format(memo)}` : "-";
    $("k-memo-sub").textContent = memo ? "real transactions among requests" : "not run";
    $("k-bc").textContent = fmt.format(state.audit.filter((a) => a.label === "broadcast").length);
    renderFinding(zid, did, memo);
  }
  function renderFinding(zecpy, devtool, memo) {
    const ran = (id) => state.scenes[id].state === "done";
    const p = $("finding");
    if (!SCENES.some((s) => ran(s.id))) return;
    p.replaceChildren();
    if (SCENES.some((s) => s.id !== "control" && ran(s.id))) {
      p.append(`ZecPy: ${fmt.format(zecpy)} requests that identify the wallet.`);
      if (memo) p.append(` Its opt-in memo fetch hid ${fmt.format(state.real.size || memo / 8)} transactions among ${fmt.format(memo)}.`);
    }
    if (ran("control")) {
      p.append(" zcash-devtool, one create and sync: ");
      p.append(el("span", "bad", `${fmt.format(devtool)} identifying.`));
    }
  }

  // Memo batch
  function renderBatch() {
    const ul = $("batch");
    const btn = $("reveal");
    btn.disabled = !state.real.size || !state.batch.length;
    btn.setAttribute("aria-pressed", String(state.revealed));
    btn.textContent = state.revealed ? "Hide ours" : "Reveal ours, on this screen only";
    if (!state.batch.length) {
      $("memo-note").textContent = "No memo fetched yet. The memo scene fetches each payment whose memo is unknown, among 7 decoys.";
      ul.replaceChildren();
      return;
    }
    const fetches = Math.round(state.batch.length / 8);
    const each = fetches === 1 ? "one fetch of 8" : `${fetches} fetches of 8`;
    $("memo-note").textContent = state.revealed
      ? `Marked from the wallet's own records. The server received the same ${state.batch.length} requests and no mark.`
      : `${state.batch.length} transactions requested in ${each}, each shuffled, each on its own Tor circuit in production. Which are ours?`;
    ul.replaceChildren(...state.batch.map((txid) => {
      const ours = state.revealed && state.real.has(txid);
      const li = el("li", ours ? "ours" : "");
      li.append(el("span", "tx", txid), el("span", "who", state.revealed ? (ours ? "Ours" : "Decoy") : "?"));
      return li;
    }));
  }

  // Ledger
  let ledgerScroll;
  function row(a, fresh) {
    const tr = el("tr", kind(a) === "identifying" ? "identifying" : "");
    if (fresh) tr.classList.add("arrive");
    tr.append(
      el("td", "num", clock(a.t)),
      el("td", `who-cell who-chip ${a.actor}`, ACTOR[a.actor]),
      el("td", "method", a.method),
      el("td", "detail", a.detail || "-"),
    );
    const td = el("td", "label-cell");
    td.append(el("span", `pill ${kind(a)}`, LABEL[kind(a)] || a.label));
    tr.append(td);
    return tr;
  }
  function visible() {
    return state.audit.filter((a) => state.filter === "all" || a.actor === state.filter);
  }
  function renderLedger() {
    const body = $("ledger");
    const rows = visible().slice(-MAX_ROWS).reverse();
    if (!rows.length) {
      const tr = el("tr", "empty-row");
      const td = el("td", "", state.filter === "all" ? "Nothing received yet." : `Nothing from ${ACTOR[state.filter]} yet.`);
      td.colSpan = 5;
      tr.append(td);
      body.replaceChildren(tr);
      return;
    }
    body.replaceChildren(...rows.map((a) => row(a, false)));
  }
  function addLedger(a) {
    if (state.filter !== "all" && a.actor !== state.filter) return;
    const body = $("ledger");
    body.querySelector(".empty-row")?.remove();
    body.prepend(row(a, true));
    while (body.children.length > MAX_ROWS) body.lastChild.remove();
  }

  // Events
  function handle(e, replaying) {
    if (state.t0 === null && e.type !== "reset") state.t0 = e.t;
    switch (e.type) {
      case "reset":
        state.current = null; state.start = null; state.t0 = null; state.steps = []; state.audit = [];
        state.batch = []; state.real = new Set(); state.revealed = false;
        for (const s of SCENES) state.scenes[s.id] = { state: "idle" };
        $("finding").textContent = "Run a scene. Every request the server receives appears on the right as it arrives.";
        renderAll();
        break;
      case "chain":
        $("height").textContent = fmt.format(e.height);
        break;
      case "scene":
        if (e.state === "start") {
          state.current = e.scene; state.steps = []; state.start = e.t; state.running = true;
          if (e.scene === "memos") { state.batch = []; state.real = new Set(); state.revealed = false; renderBatch(); }
          state.scenes[e.scene] = { state: "running" };
          $("narration-time").textContent = "";
        } else {
          state.running = false;
          state.scenes[e.scene] = { state: e.state, requests: e.requests, identifying: e.identifying, error: e.error };
          if (e.state === "done") for (const s of state.steps) if (s.status === "run") s.status = "ok";
          if (e.state === "failed") state.steps.push({ status: "failed", text: e.error || "The scene failed" });
          $("narration-time").textContent = state.start ? `${(e.t - state.start).toFixed(1)} s` : "";
        }
        renderScenes(); renderSteps(); renderKpis();
        break;
      case "step":
        state.steps.push(e);
        renderSteps();
        break;
      case "audit":
        state.audit.push(e);
        if (e.method === "GetTransaction" && state.current === "memos") { state.batch.push(e.detail); renderBatch(); }
        if (!replaying) addLedger(e);
        renderKpis();
        break;
      case "secret":
        state.real = new Set(e.real_txids || []);
        renderBatch(); renderKpis();
        break;
    }
  }
  function renderAll() { renderScenes(); renderSteps(); renderKpis(); renderBatch(); renderLedger(); }

  // Controls
  $("reveal").addEventListener("click", () => { state.revealed = !state.revealed; renderBatch(); });
  $("reset").addEventListener("click", () => {
    if (state.live) fetch("/reset", { method: "POST" });
    else handle({ type: "reset" });
  });
  for (const tab of document.querySelectorAll(".tabs button")) {
    tab.addEventListener("click", () => {
      state.filter = tab.dataset.actor;
      for (const t of document.querySelectorAll(".tabs button")) t.setAttribute("aria-selected", String(t === tab));
      renderLedger();
    });
  }

  // Sources
  const params = new URLSearchParams(location.search);
  if (params.has("replay")) {
    $("conn").textContent = "Replay of a recorded run";
    fetch("/static/replay.json").then((r) => r.json()).then(async (events) => {
      if (params.get("replay") === "instant") {
        for (const e of events) handle(e, true);
        state.revealed = params.has("reveal");
        renderAll();
        return;
      }
      renderAll();
      let prev = events[0]?.t;
      for (const e of events) {
        await new Promise((ok) => setTimeout(ok, Math.min(600, Math.max(0, (e.t - prev) * 1000))));
        prev = e.t;
        handle(e, false);
      }
    }).catch((err) => { console.error(err); $("conn").textContent = `Replay failed: ${err.message}`; });
  } else {
    const source = new EventSource("/events");
    source.onopen = () => { state.live = true; $("conn").textContent = "Live"; $("conn").classList.add("live"); renderScenes(); };
    source.onerror = () => { state.live = false; $("conn").textContent = "Disconnected, retrying"; $("conn").classList.remove("live"); renderScenes(); };
    source.onmessage = (m) => handle(JSON.parse(m.data), false);
  }
  renderAll();
})();
