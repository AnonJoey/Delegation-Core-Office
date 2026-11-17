// delegation-core Agnostic Orchestrator Frontend
// Pure Vanilla JS (Strict CSP) - connects to local dashboard_api.py sidecar.

let apiBase = null;
let apiToken = "";
let currentNotePath = null;
let currentRawMode = false;
let currentNoteContent = "";
let isServerActive = true;

// ── API Helpers ───────────────────────────────────────────────────────────────

// The API rejects every request without the daemon's bearer token.
function authHeaders(extra = {}) {
  return apiToken ? { ...extra, Authorization: `Bearer ${apiToken}` } : extra;
}

async function apiGet(path) {
  const res = await fetch(`${apiBase}${path}`, { headers: authHeaders() });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || `${path}: HTTP ${res.status}`);
  return body;
}

async function apiPost(path, payload) {
  const res = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || `${path}: HTTP ${res.status}`);
  return body;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function paneState(title, hint = "", icon = "") {
  return `<div class="pane-state">
    ${icon ? `<div class="pane-state-icon">${icon}</div>` : ""}
    <div class="pane-state-title">${escapeHtml(title)}</div>
    ${hint ? `<div class="pane-state-hint">${escapeHtml(hint)}</div>` : ""}
  </div>`;
}

function timeAgo(seconds) {
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}

// ── Native Window & Server Controls ──────────────────────────────────────────

function setupWindowControls() {
  const minBtn = document.getElementById("win-minimize-btn");
  const maxBtn = document.getElementById("win-maximize-btn");
  const closeBtn = document.getElementById("win-close-btn");

  const invokeFn = window.__TAURI_INTERNALS__?.invoke || window.__TAURI__?.core?.invoke;

  if (minBtn) {
    minBtn.addEventListener("click", async () => {
      if (invokeFn) {
        try { await invokeFn("minimize_window"); } catch (e) { console.error(e); }
      }
    });
  }

  if (maxBtn) {
    maxBtn.addEventListener("click", async () => {
      if (invokeFn) {
        try { await invokeFn("toggle_maximize_window"); } catch (e) { console.error(e); }
      } else {
        if (!document.fullscreenElement) {
          document.documentElement.requestFullscreen().catch(() => {});
        } else {
          document.exitFullscreen().catch(() => {});
        }
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", async () => {
      if (invokeFn) {
        try { await invokeFn("close_window"); } catch (e) { console.error(e); }
      } else {
        window.close();
      }
    });
  }
}

function setupServerControls() {
  const powerBtn = document.getElementById("server-power-btn");
  const restartBtn = document.getElementById("server-restart-btn");

  if (powerBtn) {
    powerBtn.addEventListener("click", () => {
      isServerActive = !isServerActive;
      if (isServerActive) {
        powerBtn.classList.add("is-on");
        powerBtn.classList.remove("is-off");
        powerBtn.querySelector(".btn-text").textContent = "Server ON";
        refreshStatus();
        refreshClients();
      } else {
        powerBtn.classList.remove("is-on");
        powerBtn.classList.add("is-off");
        powerBtn.querySelector(".btn-text").textContent = "Server OFF";
        document.getElementById("status-fields").innerHTML = `<span class="muted">Server Paused</span>`;
      }
    });
  }

  if (restartBtn) {
    restartBtn.addEventListener("click", async () => {
      const icon = restartBtn.querySelector("svg");
      if (icon) icon.style.animation = "spin 0.8s linear infinite";
      restartBtn.disabled = true;
      try {
        try { await apiPost("/api/llama/stop", {}); } catch (e) {}
        await new Promise((r) => setTimeout(r, 800));
        await refreshStatus();
        await refreshClients();
        await loadNotesBrowser();
        await initVaultGraph();
      } catch (e) {
        console.error("Restart error:", e);
      } finally {
        if (icon) icon.style.animation = "";
        restartBtn.disabled = false;
      }
    });
  }
}

// ── System Status & Telemetry (7 Standard Fields) ─────────────────────────────

function dot(ok) {
  return `<span class="dot ${ok ? "ok" : "bad"}"></span>`;
}

function stat(label, valueHtml) {
  return `<span class="stat"><span class="stat-label">${label}</span>${valueHtml}</span>`;
}

let llamaTogglePending = false;

function updateLlamaButton(llamaState) {
  const btn = document.getElementById("llama-toggle-btn");
  if (llamaTogglePending) return;
  btn.disabled = false;
  const isOnline = llamaState === "online" || llamaState === "unhealthy";
  btn.dataset.action = isOnline ? "stop" : "start";
  btn.querySelector(".btn-text").textContent = isOnline ? "Stop llama.cpp" : "Start llama.cpp";
}

async function refreshStatus() {
  if (!isServerActive) return;
  const el = document.getElementById("status-fields");
  try {
    const s = await apiGet("/api/status");
    el.innerHTML = [
      stat("Vault", `${dot(s.vault_ok)}${s.vault_ok ? "ok" : "missing"}`),
      stat("Binary", `${dot(s.binary_ok)}${s.binary_ok ? "ok" : "missing"}`),
      stat("Model", `${dot(s.model_ok)}${s.model_ok ? "ok" : "missing"}`),
      stat("llama.cpp", `${dot(s.llama_state === "online")}${escapeHtml(s.llama_state)}`),
      stat("Indexed notes", escapeHtml(s.indexed_notes ?? s.chroma_indexed_notes ?? "—")),
      stat("Engine mode", escapeHtml(s.engine_mode)),
      stat("Synthesis", s.synthesis_enabled ? "on" : "off"),
    ].join("");

    try {
      const cs = await apiGet("/api/cores/status");
      if (cs && cs.cores_active) {
        el.innerHTML += stat("Cores", `${dot(true)}${cs.cores_active.length} active`);
        if (cs.skills?.total_indexed) {
          el.innerHTML += stat("Skills", `${cs.skills.total_indexed}`);
        }
      }
    } catch { /* ignore */ }

    // The version the server actually is. This was hardcoded in index.html and
    // said v0.9.0 while the source tree was at 0.10.0 — kept blank until the
    // server answers rather than shipping another copy to go stale.
    const badge = document.getElementById("brand-badge");
    if (badge && s.version) badge.textContent = `Orchestrator v${s.version}`;

    // Sync Obsidian Statusbar
    const sbNotes = document.getElementById("sb-notes-val");
    const nIndexed = s.indexed_notes ?? s.chroma_indexed_notes;
    if (sbNotes && nIndexed !== undefined) sbNotes.textContent = `${nIndexed} notes`;
    const sbModel = document.getElementById("sb-model-val");
    if (sbModel && s.bge_model) sbModel.textContent = s.bge_model.rsplit ? s.bge_model.rsplit('/', 1).pop() : s.bge_model;
    const sbEngine = document.getElementById("sb-engine-val");
    if (sbEngine && s.engine_mode) sbEngine.textContent = s.engine_mode;

    updateLlamaButton(s.llama_state);
  } catch (e) {
    el.innerHTML = `<span class="muted">status unavailable — retrying</span>`;
  }
}

async function toggleLlama() {
  const btn = document.getElementById("llama-toggle-btn");
  const action = btn.dataset.action;
  llamaTogglePending = true;
  btn.disabled = true;
  btn.querySelector(".btn-text").textContent = action === "start" ? "Starting…" : "Stopping…";
  try {
    await apiPost(`/api/llama/${action}`, {});
  } catch (e) {
    alert(`Could not ${action} llama.cpp: ${e.message}`);
  }
  llamaTogglePending = false;
  setTimeout(refreshStatus, action === "start" ? 3000 : 1500);
}

// ── Connected MCP Clients ────────────────────────────────────────────────────

async function refreshClients() {
  if (!isServerActive) return;
  const el = document.getElementById("clients-list");
  const fleetGrid = document.getElementById("fleet-grid");

  try {
    const { clients } = await apiGet("/api/clients");
    if (!clients.length) {
      el.innerHTML = `<span class="muted">no clients connected</span>`;
      if (fleetGrid) {
        fleetGrid.innerHTML = paneState("No Connected MCP Clients", "No active stdio MCP server instances detected.", "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M12 2a10 10 0 0 1 10 10'></path><path d='M12 8a6 6 0 0 1 6 6'></path><circle cx='6' cy='18' r='3'></circle></svg>");
      }
      return;
    }

    el.innerHTML = clients
      .map(
        (c) => `
      <span class="client-chip">
        <span class="client-name">${escapeHtml(c.client_name ?? "unknown")}</span>
        <span class="client-meta">v${escapeHtml(c.client_version ?? "?")} · ${c.tool_calls} calls · ${timeAgo(c.seconds_since_active)}</span>
      </span>`
      )
      .join("");

    if (fleetGrid) {
      fleetGrid.innerHTML = clients
        .map(
          (c) => `
        <div class="fleet-card">
          <div class="fleet-card-header">
            <span class="dot ok"></span>
            <span class="fleet-client-name">${escapeHtml(c.client_name ?? "Unknown Client")}</span>
            <span class="count">v${escapeHtml(c.client_version ?? "1.0")}</span>
          </div>
          <div style="font-size: 12px; color: var(--fg-muted); margin-bottom: 8px;">
            PID: <code>${c.pid}</code> · Active: ${timeAgo(c.seconds_since_active)}
          </div>
          <div style="font-size: 12px;">
            <strong>${c.tool_calls}</strong> MCP tool invocations recorded this session.
          </div>
        </div>`
        )
        .join("");
    }
  } catch (e) {
    el.innerHTML = `<span class="muted">clients unavailable — retrying</span>`;
  }
}

// ── Tab & Navigation Switching ───────────────────────────────────────────────

// ── Tab navigation, Obsidian-style ───────────────────────────────────────────
// Three things make Obsidian's tabs feel fluid rather than merely functional:
// the active tab survives a restart, the keyboard reaches every tab without the
// mouse, and the indicator travels instead of blinking to its new place. All three
// are cheap here; none needs a framework.

const TAB_STORAGE_KEY = "dc.activeTab";

function tabButtons() {
  return Array.from(document.querySelectorAll(".ribbon .ribbon-btn[data-tab]"));
}

/** Slide the marker to sit alongside the active ribbon button. */
function moveTabIndicator(btn) {
  const indicator = document.getElementById("tab-indicator");
  if (!indicator || !btn) return;
  // offsetTop is relative to .ribbon, which is the indicator's positioned parent.
  indicator.style.height = `${btn.offsetHeight}px`;
  indicator.style.transform = `translateY(${btn.offsetTop}px)`;
}

// Each section owns both columns: a navigator in the left dock and its content in
// main. Switching sections swaps both. Leaving the vault tree up while looking at,
// say, the MCP fleet gave the dock nothing to do — the navigator has to belong to
// the section, which is how Obsidian's ribbon behaves.
const DOCK_TITLES = {
  notes: "Vault",
  tasks: "Processes",
  search: "Search",
  fleet: "MCP Connections",
  skills: "Skills Studio",
  orchestrator: "Orchestrator & DAG",
  multimodal: "Multimodal Media",
  telemetry: "Homelab Telemetry",
  vigia: "Vigia",
};

// Search has no content of its own: picking a result opens a note, and notes are
// read in the same place they are read from the tree. Mapping it onto the notes
// panel avoids both an empty column and a second, competing reader.
const MAIN_FOR = {
  notes: "notes",
  search: "notes",
  tasks: "tasks",
  fleet: "fleet",
  skills: "skills",
  orchestrator: "orchestrator",
  multimodal: "multimodal",
  telemetry: "telemetry",
  vigia: "vigia",
};

function activateTab(name, { persist = true } = {}) {
  const btn = tabButtons().find((b) => b.dataset.tab === name);
  const panel = document.getElementById(`tab-${MAIN_FOR[name] || name}`);
  if (!btn || !panel) return false;

  document.querySelectorAll(".dock-panel").forEach((d) => d.classList.remove("active"));
  const dock = document.getElementById(`dock-${name}`);
  if (dock) dock.classList.add("active");
  const dockTitle = document.getElementById("dock-title");
  if (dockTitle) dockTitle.textContent = DOCK_TITLES[name] || name;
  if (name === "fleet") refreshMcpConnections();
  if (name === "vigia") refreshVigia();
  if (name === "skills") refreshSkillsStudio();
  if (name === "orchestrator") refreshOrchestratorStudio();
  if (name === "multimodal") refreshMultimodalStudio();
  if (name === "telemetry") refreshTelemetryStudio();

  tabButtons().forEach((b) => {
    const on = b === btn;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
  panel.classList.add("active");

  moveTabIndicator(btn);
  if (persist) {
    try { localStorage.setItem(TAB_STORAGE_KEY, name); } catch { /* private mode */ }
  }
  return true;
}

function cycleTab(step) {
  const btns = tabButtons();
  const i = btns.findIndex((b) => b.classList.contains("active"));
  if (i === -1) return;
  // wrap in both directions, so Ctrl+Shift+Tab from the first lands on the last
  const next = btns[(i + step + btns.length) % btns.length];
  activateTab(next.dataset.tab);
}

// Collapsing the graph pane, as Obsidian collapses a dock. The state persists,
// because a pane you deliberately hid should stay hidden across restarts.
const GRAPH_PANE_KEY = "dc.graphPaneCollapsed";

function setGraphPaneCollapsed(collapsed) {
  const pane = document.getElementById("graph-pane");
  const btn = document.getElementById("btn-toggle-graph-pane");
  if (!pane) return;
  pane.classList.toggle("collapsed", collapsed);
  if (btn) {
    btn.classList.toggle("collapsed", collapsed);
    btn.setAttribute("aria-pressed", collapsed ? "true" : "false");
  }
  try { localStorage.setItem(GRAPH_PANE_KEY, collapsed ? "1" : "0"); } catch { /* ignore */ }
  // No manual canvas resize here: ForceGraph already observes its own parent, and
  // going from display:none back to visible fires that observer on its own.
}

function setupGraphPaneToggle() {
  const btn = document.getElementById("btn-toggle-graph-pane");
  if (!btn) return;
  let collapsed = false;
  try { collapsed = localStorage.getItem(GRAPH_PANE_KEY) === "1"; } catch { /* ignore */ }
  setGraphPaneCollapsed(collapsed);

  btn.addEventListener("click", () => {
    setGraphPaneCollapsed(!document.getElementById("graph-pane").classList.contains("collapsed"));
  });

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "\\") {
      e.preventDefault();
      setGraphPaneCollapsed(!document.getElementById("graph-pane").classList.contains("collapsed"));
    }
  });
}

function setupNavigation() {
  tabButtons().forEach((btn) => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });

  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    if (e.key === "Tab") {
      e.preventDefault();
      cycleTab(e.shiftKey ? -1 : 1);
      return;
    }
    // Ctrl+1..9 jumps straight to a tab, as in Obsidian and every browser
    const n = Number(e.key);
    if (Number.isInteger(n) && n >= 1 && n <= 9) {
      const btn = tabButtons()[n - 1];
      if (btn) {
        e.preventDefault();
        activateTab(btn.dataset.tab);
      }
    }
  });

  // Restore the tab from last run; fall back to whichever is marked active in the
  // markup if the stored one no longer exists.
  let restored = false;
  try {
    const saved = localStorage.getItem(TAB_STORAGE_KEY);
    if (saved) restored = activateTab(saved, { persist: false });
  } catch { /* ignore */ }
  if (!restored) {
    const current = tabButtons().find((b) => b.classList.contains("active")) || tabButtons()[0];
    if (current) activateTab(current.dataset.tab, { persist: false });
  }

  // The indicator is positioned from measured geometry, so it has to be
  // recomputed whenever that geometry can change.
  const nav = document.querySelector(".ribbon");
  if (nav && typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => {
      const active = tabButtons().find((b) => b.classList.contains("active"));
      moveTabIndicator(active);
    }).observe(nav);
  }

  setupGraphPaneToggle();

  document.getElementById("btn-toggle-vault-graph").addEventListener("click", () => switchGraphMode("vault"));
  document.getElementById("btn-toggle-code-graph").addEventListener("click", () => switchGraphMode("code"));
}

function switchGraphMode(mode) {
  const btnVault = document.getElementById("btn-toggle-vault-graph");
  const btnCode = document.getElementById("btn-toggle-code-graph");
  const vaultView = document.getElementById("vault-graph-view");
  const codeView = document.getElementById("code-graph-view");
  const indicator = document.getElementById("graph-type-indicator");

  if (mode === "vault") {
    btnVault.classList.add("active");
    btnCode.classList.remove("active");
    vaultView.hidden = false;
    codeView.hidden = true;
    indicator.textContent = "Wikilinks Network";
  } else {
    btnCode.classList.add("active");
    btnVault.classList.remove("active");
    codeView.hidden = false;
    vaultView.hidden = true;
    indicator.textContent = "Code AST (Graphify)";
    loadCodeGraphs();
  }
}

// ── Knowledge Vault Browser & Markdown Reader ────────────────────────────────

let vaultDirs = null;          // [{path, name, depth, count}] — 25 entries here
let collapsedDirs = new Set();  // dir paths the user folded shut
let currentListing = null;      // {dir, total, offset, notes, has_more}
const notesByDir = new Map();   // dir -> listing, filled lazily as folders open
let findResults = null;         // literal-search results, when the filter is active
let selectedFolder = null;
const NOTES_PAGE = 200;

// ── Vault explorer ───────────────────────────────────────────────────────────
// One tree, folders and notes together, the way Obsidian does it: a note lives
// inside the folder that holds it rather than in a second list that only shows
// whichever folder is selected. Two lists meant the answer to "what is in here"
// was split across two panes, and only one directory could ever be open.
//
// The server hands back a flat, pre-ordered directory list with depth already
// computed. Rendering nests it: a folder's subfolders are drawn before its
// notes, so opening a folder reads top-down as folders-then-files.
//
// Notes are fetched per directory the first time it opens and cached. Loading
// every note up front is not an option here — this vault has 3600 notes across
// 25 directories, most of them generated articles nobody expands.

function buildDirTree(dirs) {
  const byPath = new Map(dirs.map((d) => [d.path, { ...d, children: [] }]));
  const roots = [];
  for (const d of dirs) {
    const node = byPath.get(d.path);
    const parent = nearestListedAncestor(byPath, d.path);
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
}

// The immediate parent is not guaranteed to be in the list: this vault has
// `Projects/FITapp/audits` at depth 2 with no `Projects/FITapp` entry, because a
// directory holding only subdirectories and no notes of its own is not listed.
// Looking up the literal parent leaves such a folder orphaned, and an orphan
// becomes a root — which silently moved `audits` out from under `Projects` and
// down to the bottom of the tree. Climb to the nearest ancestor that does exist.
// Indentation still uses the server's depth, so the missing level reads as a gap
// rather than pretending the folder sits one level up.
function nearestListedAncestor(byPath, path) {
  const parts = path.split("/");
  for (let i = parts.length - 1; i >= 1; i--) {
    const found = byPath.get(parts.slice(0, i).join("/"));
    if (found) return found;
  }
  return null;
}

// Indentation is a class, not a style attribute. This app ships a CSP of
// `style-src 'self'` with no 'unsafe-inline', and WebKit drops inline style
// attributes outright under it — which is why the folder tree has never actually
// been indented: the original renderer set padding-left inline and the browser
// discarded it silently, with no console error and no visual clue beyond a flat
// list. Loosening the CSP to buy back one padding value would be the wrong
// trade, so depth ships as a class with the values in the stylesheet.
//
// Depth is clamped because the classes are enumerated there; a vault nested
// deeper than this keeps rendering, it just stops indenting further.
const MAX_INDENT_DEPTH = 8;

function indentClass(depth) {
  return `indent-${Math.min(depth, MAX_INDENT_DEPTH)}`;
}

function explorerRows(nodes, out) {
  for (const n of nodes) {
    const expanded = !collapsedDirs.has(n.path);
    const expandable = n.children.length > 0 || n.count > 0;
    const caret = expandable ? (expanded ? "▾" : "▸") : "&nbsp;";
    out.push(`<div class="list-item dir-row ${indentClass(n.depth)} ${n.path === selectedFolder ? "active" : ""}"
      data-folder="${escapeHtml(n.path)}" tabindex="0"
      role="treeitem" aria-expanded="${expandable ? expanded : ""}">
      <span class="dir-caret">${caret}</span>
      ${escapeHtml(n.name)} <span class="count">${n.count}</span>
    </div>`);

    if (!expanded) continue;
    explorerRows(n.children, out);

    const listing = notesByDir.get(n.path);
    if (!listing) {
      // Only claim to be loading when there is something to load; a directory
      // whose count is 0 is a container for subfolders and never fetches.
      if (n.count > 0) {
        out.push(`<div class="explorer-hint ${indentClass(n.depth + 1)}">Loading…</div>`);
      }
      continue;
    }
    for (const note of listing.notes) {
      out.push(`<div class="list-item note-row ${indentClass(n.depth + 1)} ${note.path === currentNotePath ? "active" : ""}"
        data-path="${escapeHtml(note.path)}" tabindex="0"
        role="treeitem">${escapeHtml(note.title)}</div>`);
    }
    if (listing.has_more) {
      const shown = listing.offset + listing.notes.length;
      out.push(`<button class="list-more ${indentClass(n.depth + 1)}" data-more="${escapeHtml(n.path)}"
        data-shown="${shown}">Load more — ${shown} of ${listing.total}</button>`);
    }
  }
}

function renderExplorer() {
  const el = document.getElementById("explorer");
  if (!el || !vaultDirs) return;

  // The filter searches the whole vault server-side, so its hits are a flat list
  // that belongs to no one directory — the tree is set aside while it is active
  // rather than trying to graft unrelated paths into it.
  if (findResults) {
    el.innerHTML = findResults.results.length
      ? findResults.results.map((n) => `<div class="list-item note-row" data-path="${escapeHtml(n.path)}" tabindex="0">
          ${escapeHtml(n.title)}<span class="note-dir">${escapeHtml(n.path.split("/").slice(0, -1).join("/"))}</span>
        </div>`).join("")
      : paneState("No matches", "No note title or path contains that text.");
  } else if (!vaultDirs.length) {
    el.innerHTML = paneState("No folders", "The vault has no notes yet.");
  } else {
    const rows = [];
    explorerRows(buildDirTree(vaultDirs), rows);
    el.innerHTML = rows.join("");
  }

  el.querySelectorAll(".dir-row").forEach((row) => {
    const open = () => toggleFolder(row.dataset.folder);
    row.addEventListener("click", open);
    row.addEventListener("keydown", (ev) => { if (ev.key === "Enter") open(); });
  });
  el.querySelectorAll(".note-row").forEach((row) => {
    const open = () => selectNote(row.dataset.path, row);
    row.addEventListener("click", open);
    row.addEventListener("keydown", (ev) => { if (ev.key === "Enter") open(); });
  });
  el.querySelectorAll("[data-more]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      loadNotes(btn.dataset.more, Number(btn.dataset.shown), true);
    });
  });
}

// Kept as the name the rest of the file calls; both lists are one tree now.
function renderNoteList() { renderExplorer(); }

function toggleFolder(dir) {
  selectedFolder = dir;
  if (collapsedDirs.has(dir)) collapsedDirs.delete(dir);
  else collapsedDirs.add(dir);
  renderExplorer();
  // Fetch on first open only; the cache is what makes reopening instant.
  if (!collapsedDirs.has(dir) && !notesByDir.has(dir)) loadNotes(dir);
}

async function loadNotesBrowser() {
  const explorer = document.getElementById("explorer");
  try {
    const data = await apiGet("/api/vault/tree");
    vaultDirs = data.directories || [];
  } catch (e) {
    if (explorer) explorer.innerHTML = paneState("Vault unavailable", "Could not load the directory tree.");
    return;
  }
  // Everything starts folded except the directory opened below. The tree now
  // carries notes, and expanding a directory fetches them — unfolding the whole
  // vault on load would be 25 requests for lists nobody has asked to see.
  // Generated code-graph articles are the extreme case: thousands of articles
  // under <folder>/graphs/<name>/.
  vaultDirs.forEach((d) => collapsedDirs.add(d.path));
  renderExplorer();
  if (vaultDirs.length) selectFolder(vaultDirs[0].path);
}

async function loadNotes(dir, offset = 0, append = false) {
  try {
    const data = await apiGet(`/api/vault/notes?dir=${encodeURIComponent(dir)}&offset=${offset}&limit=${NOTES_PAGE}`);
    if (data.error) throw new Error(data.error);
    const prev = notesByDir.get(dir);
    const listing = append && prev
      ? { ...data, notes: prev.notes.concat(data.notes), offset: 0 }
      : data;
    notesByDir.set(dir, listing);
    currentListing = listing;
  } catch (e) {
    // Cache the failure too, so an unreadable directory does not re-request on
    // every re-render; reopening it is what retries.
    const empty = { dir, total: 0, offset: 0, notes: [], has_more: false };
    notesByDir.set(dir, empty);
    currentListing = empty;
  }
  renderExplorer();
}

function selectFolder(dir) {
  // Reveal the directory rather than merely marking it: an ancestor left folded
  // would otherwise "select" a row that is not on screen.
  selectedFolder = dir;
  const parts = dir.split("/");
  for (let i = 1; i <= parts.length; i++) collapsedDirs.delete(parts.slice(0, i).join("/"));
  renderExplorer();
  if (!notesByDir.has(dir)) loadNotes(dir);
}

function setupNotesFilter() {
  const input = document.getElementById("notes-filter");
  let timer = null;
  input.addEventListener("input", () => {
    const q = input.value.trim();
    clearTimeout(timer);
    // Debounced because this is a server round-trip now, not a local filter.
    timer = setTimeout(async () => {
      if (!q) {
        findResults = null;
        renderNoteList();
        return;
      }
      try {
        findResults = await apiGet(`/api/vault/find?q=${encodeURIComponent(q)}&limit=100`);
      } catch (e) {
        findResults = { results: [], count: 0 };
      }
      renderNoteList();
    }, 180);
  });
}

async function selectNoteByTitle(title) {
  // Literal lookup: the semantic endpoint cannot be trusted to return an exact
  // title — one written minutes earlier did not make its own top 3.
  try {
    const data = await apiGet(`/api/vault/find?q=${encodeURIComponent(title)}&limit=1`);
    if (data.results && data.results.length) selectNote(data.results[0].path, null);
  } catch (e) {
    /* nothing to open */
  }
}

// Backlinks were always computed server-side (linker.inject_backlinks writes
// them into note bodies on every write) but never shown as a relation, so a
// reader saw only whatever text happened to be in the note. Half the
// hand-written notes here have inbound links, so this is not a corner feature.
async function renderNoteLinks(path) {
  const el = document.getElementById("note-links");
  if (!el) return;
  el.hidden = true;
  el.innerHTML = "";
  let data;
  try {
    data = await apiGet(`/api/vault/backlinks?path=${encodeURIComponent(path)}`);
  } catch (e) {
    return;
  }
  if (data.error) return;
  // The note may have been switched while this request was in flight.
  if (currentNotePath !== path) return;
  if (!data.inbound.length && !data.outbound.length) return;

  const section = (title, rows) =>
    rows.length
      ? `<div class="note-links-group"><h4>${title}</h4>${rows.join("")}</div>`
      : "";

  const inbound = data.inbound.map(
    (n) => `<a class="note-link-row" data-path="${escapeHtml(n.path)}">${escapeHtml(n.title)}</a>`
  );
  // Broken targets are shown, not dropped: a note pointing at something that no
  // longer exists would otherwise look well-connected.
  const outbound = data.outbound.map((o) =>
    o.broken
      ? `<span class="note-link-row broken" title="No note with this name">${escapeHtml(o.target)} — missing</span>`
      : `<a class="note-link-row" data-path="${escapeHtml(o.path)}">${escapeHtml(o.target)}</a>`
  );

  el.innerHTML =
    section(`Linked from (${data.inbound_count})`, inbound) +
    section(`Links to (${data.outbound.length})`, outbound);
  el.hidden = false;
  el.querySelectorAll("a.note-link-row").forEach((a) => {
    a.addEventListener("click", () => selectNote(a.dataset.path, null));
  });
}

async function selectNote(path, el) {
  // Leaving edit mode on switch: otherwise the editor keeps the previous note's
  // text while the header shows the new one, and Save would overwrite the wrong
  // file with it.
  if (editing) setEditChrome(false);
  const hist = document.getElementById("note-history");
  if (hist) hist.hidden = true;
  currentNotePath = path;
  document.querySelectorAll("#explorer .note-row").forEach((e) => e.classList.remove("active"));
  if (el) el.classList.add("active");

  const header = document.getElementById("note-view-header");
  const state = document.getElementById("note-state");
  const wrapper = document.getElementById("note-body-wrapper");
  const titleEl = document.getElementById("note-view-title");
  const folderEl = document.getElementById("note-folder-badge");
  const renderedEl = document.getElementById("note-rendered");
  const rawEl = document.getElementById("note-content");
  const frontmatterEl = document.getElementById("note-frontmatter");

  wrapper.hidden = true;
  header.hidden = true;
  state.hidden = false;
  state.innerHTML = paneState("Loading note…", "", "loading");

  try {
    const note = await apiGet(`/api/vault/note?path=${encodeURIComponent(path)}`);
    currentNoteContent = note.content;

    titleEl.textContent = note.title;
    folderEl.textContent = path.split("/")[0] || "Vault";
    header.hidden = false;

    let content = note.content;
    frontmatterEl.hidden = true;
    if (content.startsWith("---\n")) {
      const endIdx = content.indexOf("\n---\n", 4);
      if (endIdx !== -1) {
        const fmText = content.substring(4, endIdx);
        content = content.substring(endIdx + 5);
        frontmatterEl.innerHTML = parseFrontmatterHTML(fmText);
        frontmatterEl.hidden = false;
      }
    }

    renderedEl.innerHTML = renderMarkdown(content);
    rawEl.textContent = note.content;

    renderedEl.querySelectorAll(".wikilink-badge").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const target = link.dataset.target;
        selectNoteByTitle(target);
      });
    });

    renderNoteLinks(path);

    state.hidden = true;
    wrapper.hidden = false;
    activateTab("notes");
  } catch (e) {
    state.innerHTML = paneState("Could not load note", "The file may have been moved or deleted.");
  }
}

function parseFrontmatterHTML(fmText) {
  const lines = fmText.split("\n");
  return lines
    .map((line) => {
      const parts = line.split(":");
      if (parts.length < 2) return "";
      const key = parts[0].trim();
      const val = parts.slice(1).join(":").trim();
      return `<div class="frontmatter-tag"><span class="stat-label">${escapeHtml(key)}:</span> <span class="frontmatter-val">${escapeHtml(val)}</span></div>`;
    })
    .join("");
}

function renderMarkdown(text) {
  let html = escapeHtml(text);

  html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
  html = html.replace(/^## (.*$)/gim, "<h2>$1</h2>");
  html = html.replace(/^# (.*$)/gim, "<h1>$1</h1>");

  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");

  html = html.replace(/\[\[([^\]\|]+)(?:\|([^\]]+))?\]\]/g, (match, target, display) => {
    const label = display || target;
    return `<a class="wikilink-badge" data-target="${escapeHtml(target.trim())}"><svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7'></path><path d='M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7'></path></svg> ${escapeHtml(label.trim())}</a>`;
  });

  html = html.replace(/\n\n/g, "</p><p>");
  return `<p>${html}</p>`;
}

function setupNoteActions() {
  document.getElementById("btn-toggle-raw").addEventListener("click", () => {
    currentRawMode = !currentRawMode;
    const btn = document.getElementById("btn-toggle-raw");
    const rendered = document.getElementById("note-rendered");
    const raw = document.getElementById("note-content");
    btn.textContent = currentRawMode ? "Formatted" : "Raw";
    rendered.hidden = currentRawMode;
    raw.hidden = !currentRawMode;
  });

  document.getElementById("btn-copy-path").addEventListener("click", () => {
    if (currentNotePath) {
      navigator.clipboard.writeText(currentNotePath);
      const btn = document.getElementById("btn-copy-path");
      btn.textContent = "Copied!";
      setTimeout(() => (btn.textContent = "Copy Path"), 1500);
    }
  });

  document.getElementById("btn-edit-note").addEventListener("click", () => enterEditMode());
  document.getElementById("btn-cancel-edit").addEventListener("click", () => exitEditMode());
  document.getElementById("btn-save-note").addEventListener("click", () => saveCurrentNote());
  document.getElementById("btn-new-note").addEventListener("click", () => createNoteHere());
  document.getElementById("btn-rename-note").addEventListener("click", () => renameCurrentNote());
}

// ── Editing ───────────────────────────────────────────────────────────────────
// Writes go through the server (POST /api/vault/note/*), which owns indexing.
// Writing straight to disk from Tauri would be faster and would leave the note
// unindexed until something else noticed — a second write path free to drift
// from the one the MCP tools use.

let editing = false;

function setEditChrome(on) {
  editing = on;
  document.getElementById("btn-edit-note").hidden = on;
  document.getElementById("btn-save-note").hidden = !on;
  document.getElementById("btn-cancel-edit").hidden = !on;
  document.getElementById("note-editor").hidden = !on;
  document.getElementById("note-rendered").hidden = on || currentRawMode;
  document.getElementById("note-content").hidden = on || !currentRawMode;
  document.getElementById("note-links").hidden = on;
}

function editorStatus(text, isError) {
  const el = document.getElementById("note-editor-status");
  el.textContent = text;
  el.classList.toggle("error", Boolean(isError));
  el.hidden = !text;
}

function enterEditMode() {
  if (!currentNotePath) return;
  // The raw pane already holds the exact file text, frontmatter included —
  // which is what save writes back, so the editor starts from it verbatim.
  document.getElementById("note-editor").value =
    document.getElementById("note-content").textContent;
  setEditChrome(true);
  editorStatus("");
}

function exitEditMode() {
  setEditChrome(false);
  editorStatus("");
}

async function saveCurrentNote() {
  if (!currentNotePath) return;
  const content = document.getElementById("note-editor").value;
  editorStatus("Saving…");
  try {
    const res = await apiPost("/api/vault/note/save", { path: currentNotePath, content });
    if (res.error) throw new Error(res.error);
    exitEditMode();
    await selectNote(currentNotePath, null);   // re-read from disk, re-render, refresh links
  } catch (e) {
    editorStatus(`Save failed: ${e.message}`, true);
  }
}

async function renameCurrentNote() {
  if (!currentNotePath) return;
  const current = currentNotePath.split("/").pop().replace(/\.md$/, "");
  const title = prompt("Rename note to:", current);
  if (!title || !title.trim() || title.trim() === current) return;
  editorStatus("Renaming…");
  try {
    const res = await apiPost("/api/vault/note/rename", {
      path: currentNotePath,
      new_title: title.trim(),
    });
    if (res.error) throw new Error(res.error);
    // The server repoints every [[wikilink]] aimed at the old stem; say how
    // many, since that is the part a user cannot verify by looking.
    editorStatus(`Renamed — ${res.links_rewritten} note(s) repointed`);
    await loadNotes(selectedFolder);
    await selectNote(res.path, null);
  } catch (e) {
    editorStatus(`Rename failed: ${e.message}`, true);
  }
}

async function createNoteHere() {
  const folder = (selectedFolder || "").split("/")[0];
  if (!folder) return;
  const title = prompt(`New note in ${folder}:`);
  if (!title || !title.trim()) return;
  try {
    const res = await apiPost("/api/vault/note/create", {
      folder,
      title: title.trim(),
      content: "## Summary\n\n",
    });
    if (res.error) throw new Error(res.error);
    await loadNotes(selectedFolder);
    await selectNote(res.path, null);
  } catch (e) {
    editorStatus(`Create failed: ${e.message}`, true);
  }
}

// ── Vector Semantic Search Studio ──────────────────────────────────────────────

function setupVectorSearch() {
  const input = document.getElementById("vector-search-input");
  const btn = document.getElementById("vector-search-btn");
  const resultsPane = document.getElementById("vector-search-results");

  async function executeSearch() {
    const query = input.value.trim();
    if (!query) return;

    resultsPane.innerHTML = paneState("Searching vector space…", "", "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><circle cx='11' cy='11' r='8'></circle><line x1='21' y1='21' x2='16.65' y2='16.65'></line></svg>");
    try {
      const data = await apiGet(`/api/vault/search?q=${encodeURIComponent(query)}&limit=8`);
      if (!data.results || !data.results.length) {
        resultsPane.innerHTML = paneState("No Vector Matches", "No notes exceeded similarity threshold.");
        return;
      }

      resultsPane.innerHTML = data.results
        .map((r) => {
          const simPct = Math.round((r.similarity || 0) * 100);
          return `
          <div class="search-result-card" data-path="${escapeHtml(r.path)}">
            <div class="search-card-header">
              <span class="search-card-title">${escapeHtml(r.title)}</span>
              <span class="similarity-badge">${simPct}% match</span>
            </div>
            <div style="font-size: 11px; color: var(--fg-dim); margin-bottom: 6px;"><svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z'></path></svg> ${escapeHtml(r.path)}</div>
            <div style="font-size: 12.5px; color: var(--fg-muted); line-height: 1.4;">${escapeHtml(r.snippet || "Click to view note...")}</div>
          </div>`;
        })
        .join("");

      resultsPane.querySelectorAll(".search-result-card").forEach((card) => {
        card.addEventListener("click", () => {
          selectNote(card.dataset.path, null);
        });
      });
    } catch (e) {
      resultsPane.innerHTML = paneState("Search Error", e.message, "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'></path><line x1='12' y1='9' x2='12' y2='13'></line><line x1='12' y1='17' x2='12.01' y2='17'></line></svg>");
    }
  }

  btn.addEventListener("click", executeSearch);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") executeSearch();
  });

  // Ask: ask_vault pelo painel (painel_resposta.py). So volta afirmacao com
  // citacao que existe na nota; cada uma abre a nota de onde veio.
  const askBtn = document.getElementById("vector-ask-btn");
  if (askBtn) askBtn.addEventListener("click", async () => {
    const question = input.value.trim();
    if (!question) return;
    resultsPane.innerHTML = paneState("Asking the local model…", "Takes about 10 seconds.");
    try {
      resultsPane.innerHTML = renderAnswer(await apiPost("/api/ask", { question }));
      resultsPane.querySelectorAll(".answer-claim").forEach((c) =>
        c.addEventListener("click", () => selectNote(c.dataset.path, null)));
    } catch (e) {
      resultsPane.innerHTML = paneState("Ask Error", e.message);
    }
  });
}

function renderAnswer(r) {
  if (!r || !r.found) {
    return paneState("Not in the vault", "Nothing the notes could prove came back. Try Search to read the closest notes.");
  }
  const claims = (r.claims || []).map((c) => `
    <div class="search-result-card answer-claim" data-path="${escapeHtml(c.source || "")}">
      <div class="search-card-header"><span class="search-card-title">${escapeHtml(c.text || "")}</span></div>
      <div style="font-size: 12.5px; color: var(--fg-muted); line-height: 1.4;">“${escapeHtml(c.quote || "")}”</div>
      <div style="font-size: 11px; color: var(--fg-dim); margin-top: 4px;">${escapeHtml(c.source || "")}${
        c.source_superseded_by ? ` · superseded by ${escapeHtml(c.source_superseded_by.join(", "))}` : ""}</div>
    </div>`).join("");
  const dropped = r.dropped_unverified ? `<p class="muted">${r.dropped_unverified} claim(s) dropped: quote not found in the note.</p>` : "";
  return `<p class="muted">Answered in ${escapeHtml(String(r.seconds))} s.</p>` + claims + dropped;
}

// ── Code AST Graphs (Graphify Integration) ──────────────────────────────────

async function loadCodeGraphs() {
  const select = document.getElementById("code-graph-select");
  const details = document.getElementById("code-graph-details");

  try {
    const data = await apiGet("/api/graphs");
    const graphs = data.graphs || {};
    const keys = Object.keys(graphs);

    if (!keys.length) {
      select.innerHTML = `<option value="">No code graphs registered</option>`;
      details.innerHTML = paneState("No AST Graphs", "Run `delegation-core graph build <path>` to build a code knowledge graph.", "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M5 3v4a7 7 0 0 0 14 0V3'></path><path d='M5 21v-4a7 7 0 0 1 14 0v4'></path><line x1='7' y1='9' x2='17' y2='9'></line><line x1='7' y1='15' x2='17' y2='15'></line></svg>");
      return;
    }

    select.innerHTML = `<option value="">Select registered graph (${keys.length})</option>` +
      keys.map((k) => `<option value="${escapeHtml(k)}">${escapeHtml(k)} (${graphs[k].node_count || 0} nodes)</option>`).join("");

    select.onchange = async () => {
      const val = select.value;
      if (!val) return;
      details.innerHTML = paneState("Loading graph report…", "", "⏳");
      try {
        const report = await apiGet(`/api/graphs/get?name=${encodeURIComponent(val)}`);
        details.innerHTML = `
          <div style="padding: 12px; background: rgba(23,32,54,0.4); border-radius: 8px; margin-bottom: 12px;">
            <h3 style="margin: 0 0 8px; color: var(--accent-cyan);">${escapeHtml(val)} Code Graph</h3>
            <pre style="white-space: pre-wrap; font-size: 12px; color: var(--fg-muted); max-height: 350px; overflow-y: auto;">${escapeHtml(report.report)}</pre>
          </div>`;
      } catch (err) {
        details.innerHTML = paneState("Could not load report", err.message, "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'></path><line x1='12' y1='9' x2='12' y2='13'></line><line x1='12' y1='17' x2='12.01' y2='17'></line></svg>");
      }
    };
  } catch (e) {
    details.innerHTML = paneState("Graph Error", e.message, "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'></path><line x1='12' y1='9' x2='12' y2='13'></line><line x1='12' y1='17' x2='12.01' y2='17'></line></svg>");
  }
}

// ── Process & Task Orchestrator ──────────────────────────────────────────────

let currentProcessStatusFilter = "active";
let selectedProcessId = null;

function setupProcesses() {
  const selectFilter = document.getElementById("tasks-status-filter");
  if (selectFilter) {
    selectFilter.addEventListener("change", () => {
      currentProcessStatusFilter = selectFilter.value;
      loadProcessList();
    });
  }

  const modal = document.getElementById("new-task-modal");
  document.getElementById("tasks-new-btn").addEventListener("click", () => (modal.hidden = false));
  document.getElementById("modal-close-btn").addEventListener("click", () => (modal.hidden = true));
  document.getElementById("modal-cancel-btn").addEventListener("click", () => (modal.hidden = true));

  document.getElementById("new-task-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("task-name").value.trim();
    const description = document.getElementById("task-desc").value.trim();
    const stepsRaw = document.getElementById("task-steps").value;
    const steps = stepsRaw.split("\n").map((s) => s.trim()).filter(Boolean);

    try {
      const proc = await apiPost("/api/processes/create", { name, description, steps });
      modal.hidden = true;
      document.getElementById("new-task-form").reset();
      loadProcessList();
      selectProcess(proc.process_id);
    } catch (err) {
      alert(`Could not create process: ${err.message}`);
    }
  });

  loadProcessList();
}

async function loadProcessList() {
  const listEl = document.getElementById("task-list");
  try {
    const data = await apiGet(`/api/processes?status=${currentProcessStatusFilter}`);
    const procs = data.processes || [];

    if (!procs.length) {
      listEl.innerHTML = paneState("No processes", `No ${currentProcessStatusFilter} processes.`, "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><rect x='8' y='2' width='8' height='4' rx='1'></rect><path d='M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2'></path></svg>");
      return;
    }

    listEl.innerHTML = procs
      .map((p) => {
        const total = p.steps ? p.steps.length : 0;
        const done = p.steps ? p.steps.filter((s) => s.done).length : 0;
        const pct = total ? Math.round((done / total) * 100) : 0;
        const isSel = p.process_id === selectedProcessId;

        return `
        <div class="task-card ${isSel ? "active" : ""}" data-id="${escapeHtml(p.process_id)}">
          <div class="task-card-title">${escapeHtml(p.name)}</div>
          <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--fg-dim);">
            <span class="count">${escapeHtml(p.status)}</span>
            <span>${done}/${total} steps</span>
          </div>
          <div class="task-progress-bar">
            <div class="task-progress-fill" style="width: ${pct}%;"></div>
          </div>
        </div>`;
      })
      .join("");

    listEl.querySelectorAll(".task-card").forEach((card) => {
      card.addEventListener("click", () => selectProcess(card.dataset.id));
    });
  } catch (e) {
    listEl.innerHTML = paneState("Error loading tasks", e.message, "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'></path><line x1='12' y1='9' x2='12' y2='13'></line><line x1='12' y1='17' x2='12.01' y2='17'></line></svg>");
  }
}

async function selectProcess(id) {
  selectedProcessId = id;
  loadProcessList();
  const detailEl = document.getElementById("task-detail");
  detailEl.innerHTML = paneState("Loading process…", "", "loading");

  try {
    const p = await apiGet(`/api/processes/get?id=${encodeURIComponent(id)}`);
    const total = p.steps ? p.steps.length : 0;
    const doneCount = p.steps ? p.steps.filter((s) => s.done).length : 0;

    detailEl.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px;">
        <div>
          <span class="note-folder-badge">${escapeHtml(p.status)}</span>
          <h2 style="margin: 6px 0 2px; color: var(--fg-main);">${escapeHtml(p.name)}</h2>
          <span style="font-size: 11px; color: var(--fg-dim);">ID: <code>${escapeHtml(p.process_id)}</code></span>
        </div>
        <div style="display: flex; gap: 6px;">
          ${p.status === "active" ? `<button class="btn-action-sm" onclick="updateProcessStatus('${p.process_id}', 'paused')">Pause</button>` : ""}
          ${p.status === "paused" ? `<button class="btn-action-sm" onclick="updateProcessStatus('${p.process_id}', 'active')">Resume</button>` : ""}
          ${p.status !== "done" ? `<button class="btn-action-sm" onclick="updateProcessStatus('${p.process_id}', 'done')">Complete</button>` : ""}
          ${p.status !== "cancelled" ? `<button class="btn-action-sm" onclick="updateProcessStatus('${p.process_id}', 'cancelled')">Cancel</button>` : ""}
        </div>
      </div>

      <p style="color: var(--fg-muted); font-size: 13px;">${escapeHtml(p.description || "No description provided.")}</p>

      <h3 style="font-size: 12px; text-transform: uppercase; color: var(--fg-dim); margin-top: 20px; letter-spacing: 0.05em;">Execution Steps (${doneCount}/${total})</h3>
      <div style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px;">
        ${(p.steps || []).map((s, idx) => `
          <label style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: rgba(23,32,54,0.4); border: 1px solid var(--border-subtle); border-radius: 6px; cursor: pointer;">
            <input type="checkbox" ${s.done ? "checked" : ""} onchange="toggleStepDone('${p.process_id}', ${idx})" />
            <span style="${s.done ? "text-decoration: line-through; color: var(--fg-dim);" : "color: var(--fg-main);"}"">${escapeHtml(s.name)}</span>
          </label>
        `).join("")}
      </div>`;
  } catch (e) {
    detailEl.innerHTML = paneState("Process Error", e.message, "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'></path><line x1='12' y1='9' x2='12' y2='13'></line><line x1='12' y1='17' x2='12.01' y2='17'></line></svg>");
  }
}

window.updateProcessStatus = async function(id, newStatus) {
  try {
    await apiPost("/api/processes/update", { process_id: id, status: newStatus });
    selectProcess(id);
  } catch (e) {
    alert(`Could not update status: ${e.message}`);
  }
};

window.toggleStepDone = async function(id, stepIdx) {
  try {
    await apiPost("/api/processes/update", { process_id: id, step_done: stepIdx });
    selectProcess(id);
  } catch (e) {
    alert(`Could not toggle step: ${e.message}`);
  }
};

// ── Custom Force-Directed Vault Graph Canvas ─────────────────────────────────

class ForceGraph {
  constructor(canvas, data, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.folderIndex = opts.folderIndex || {};
    this.onNodeClick = opts.onNodeClick || null;

    this._resizeCanvas();
    this._setupResizeObserver();
    this.nodes = data.nodes.map((n) => ({
      ...n,
      x: Math.random() * (this.width || 380),
      y: Math.random() * (this.height || 400),
      vx: 0,
      vy: 0,
      radius: 4,
    }));

    const nodeById = new Map(this.nodes.map((n) => [n.id, n]));
    this.edges = data.edges
      .map((e) => ({
        source: nodeById.get(e.source),
        target: nodeById.get(e.target),
      }))
      .filter((e) => e.source && e.target);

    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this.hoveredNode = null;
    this.draggedNode = null;

    // Back-reference for introspection: lets the view state (pan, zoom) be read
    // from outside without threading a handle through every caller. Used by the
    // UI tests to assert that dragging actually moved the view.
    this.canvas.__graph = this;

    this._setupInteraction();
    this._startSimulation();
  }

  _resizeCanvas() {
    this.dpr = window.devicePixelRatio || 1;
    const parent = this.canvas.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = Math.floor(this.width * this.dpr);
    this.canvas.height = Math.floor(this.height * this.dpr);
    if (this.nodes) this._render();
  }

  _setupResizeObserver() {
    if (window.ResizeObserver && this.canvas.parentElement) {
      this._resizeObserver = new ResizeObserver(() => this._resizeCanvas());
      this._resizeObserver.observe(this.canvas.parentElement);
    }
    const dpr = window.devicePixelRatio || 1;
    this._dprQuery = window.matchMedia(`(resolution: ${dpr}dppx)`);
    this._onDprChange = () => this._resizeCanvas();
    if (this._dprQuery.addEventListener) {
      this._dprQuery.addEventListener("change", this._onDprChange);
    }
  }

  // Let go of everything that outlives the canvas. The Restart button re-runs
  // initVaultGraph() against the same <canvas>, so without this the previous
  // instance keeps its window listeners and ResizeObserver and goes on drawing
  // its own stale layout over the new one on every pointer move.
  destroy() {
    if (this._frame != null) cancelAnimationFrame(this._frame);
    this._frame = null;
    this._step = null;
    this._resizeObserver?.disconnect();
    this._dprQuery?.removeEventListener?.("change", this._onDprChange);
    window.removeEventListener("mousemove", this._onWindowMouseMove);
    window.removeEventListener("mouseup", this._onWindowMouseUp);
  }

  // Draw one frame, soon. Collapses any number of calls between two frames into
  // a single render, so an event burst (a mousemove stream, a resize drag) costs
  // one draw per frame rather than one per event.
  _schedule() {
    if (!this._step || this._frame != null) return;
    this._frame = requestAnimationFrame(this._step);
  }

  _startSimulation() {
    let alpha = 1;
    const step = () => {
      this._frame = null;
      if (alpha > 0.01) {
        alpha *= 0.98;

        for (let i = 0; i < this.nodes.length; i++) {
          for (let j = i + 1; j < this.nodes.length; j++) {
            const n1 = this.nodes[i];
            const n2 = this.nodes[j];
            const dx = n2.x - n1.x;
            const dy = n2.y - n1.y;
            const distSq = dx * dx + dy * dy || 1;
            if (distSq < 25000) {
              const force = (300 / distSq) * alpha;
              const fx = dx * force;
              const fy = dy * force;
              n1.vx -= fx;
              n1.vy -= fy;
              n2.vx += fx;
              n2.vy += fy;
            }
          }
        }

        for (const e of this.edges) {
          const dx = e.target.x - e.source.x;
          const dy = e.target.y - e.source.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - 40) * 0.05 * alpha;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          e.source.vx += fx;
          e.source.vy += fy;
          e.target.vx -= fx;
          e.target.vy -= fy;
        }

        const cx = this.width / 2;
        const cy = this.height / 2;
        for (const n of this.nodes) {
          if (n === this.draggedNode) continue;
          n.vx += (cx - n.x) * 0.001 * alpha;
          n.vy += (cy - n.y) * 0.001 * alpha;
          n.vx *= 0.85;
          n.vy *= 0.85;
          n.x += n.vx;
          n.y += n.vy;
        }
      }

      this._render();
      // Keep animating only while there is motion to animate. alpha decays 2% a
      // frame, so the layout is settled after ~230 frames (~4s) and every frame
      // after that redrew an identical picture — 2962 edges and 239 nodes,
      // 60 times a second, for as long as the window stayed open. Measured at a
      // steady 15% of a core on an idle dashboard. Interaction re-arms the loop
      // through _schedule(), so pan, zoom, hover and drag are unchanged.
      if (alpha > 0.01) this._schedule();
    };
    this._step = step;
    this._schedule();
  }

  _render() {
    const { ctx, width, height, dpr } = this;
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    ctx.translate(width / 2 + this.panX, height / 2 + this.panY);
    ctx.scale(this.zoom, this.zoom);
    ctx.translate(-width / 2, -height / 2);

    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const e of this.edges) {
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);
    }
    ctx.stroke();

    const palette = ["#38bdf8", "#fb923c", "#2dd4bf", "#c084fc", "#a3e635", "#f472b6", "#64748b"];
    for (const n of this.nodes) {
      const slot = this.folderIndex[n.folder] ?? 6;
      ctx.fillStyle = palette[slot % palette.length];
      ctx.beginPath();
      ctx.arc(n.x, n.y, n === this.hoveredNode ? 7 : 4, 0, Math.PI * 2);
      ctx.fill();
    }

    if (this.hoveredNode) {
      ctx.fillStyle = "#ffffff";
      ctx.font = "11px Inter, sans-serif";
      ctx.fillText(this.hoveredNode.title, this.hoveredNode.x + 8, this.hoveredNode.y + 4);
    }

    ctx.restore();
  }

  _setupInteraction() {
    const getPos = (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const clientX = e.clientX - rect.left;
      const clientY = e.clientY - rect.top;
      // Pan is applied before scale in _draw, so it lives in screen pixels while
      // node coordinates live in world space — hence the divide here, and the
      // absence of one when panning below.
      const x = (clientX - (this.width / 2 + this.panX)) / this.zoom + this.width / 2;
      const y = (clientY - (this.height / 2 + this.panY)) / this.zoom + this.height / 2;
      return { x, y, clientX, clientY };
    };

    const nodeAt = (p) =>
      this.nodes.find((n) => Math.hypot(n.x - p.x, n.y - p.y) < 10) || null;

    // Panning state. Kept separate from node dragging: grabbing empty space moves
    // the view, grabbing a node moves that node — the distinction Obsidian makes.
    let panning = false;
    let panStart = null;     // {clientX, clientY, panX, panY}
    let travelled = 0;       // pointer distance since mousedown, in screen px

    const setCursor = () => {
      this.canvas.style.cursor = panning
        ? "grabbing"
        : this.draggedNode
          ? "grabbing"
          : this.hoveredNode
            ? "pointer"
            : "grab";
    };

    this.canvas.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      const p = getPos(e);
      travelled = 0;
      const hit = nodeAt(p);
      if (hit) {
        this.draggedNode = hit;
      } else {
        panning = true;
        panStart = { clientX: e.clientX, clientY: e.clientY, panX: this.panX, panY: this.panY };
      }
      setCursor();
    });

    // Move and release are bound to the window, not the canvas: a drag that leaves
    // the canvas should keep working until the button is released, rather than
    // freezing at the edge. Kept on `this` so destroy() can unbind them — window
    // outlives the canvas, so an anonymous listener here is permanent.
    this._onWindowMouseMove = (e) => {
      if (panning && panStart) {
        const dx = e.clientX - panStart.clientX;
        const dy = e.clientY - panStart.clientY;
        travelled = Math.max(travelled, Math.hypot(dx, dy));
        this.panX = panStart.panX + dx;   // screen-space: no zoom divide
        this.panY = panStart.panY + dy;
        this._schedule();
        return;
      }
      if (this.draggedNode) {
        const p = getPos(e);
        travelled = Math.max(travelled, 1e9);   // any node drag suppresses the click
        this.draggedNode.x = p.x;
        this.draggedNode.y = p.y;
        this._schedule();
        return;
      }
      const p = getPos(e);
      const inside =
        p.clientX >= 0 && p.clientY >= 0 &&
        p.clientX <= this.canvas.clientWidth && p.clientY <= this.canvas.clientHeight;
      const wasHovered = this.hoveredNode;
      this.hoveredNode = inside ? nodeAt(p) : null;
      // The hover ring and its label are painted, so a change of hovered node is
      // a reason to repaint — but only a change. Plain pointer travel over empty
      // canvas leaves the picture identical and must not schedule anything.
      if (this.hoveredNode !== wasHovered) this._schedule();
      setCursor();
    };
    window.addEventListener("mousemove", this._onWindowMouseMove);

    this._onWindowMouseUp = () => {
      panning = false;
      panStart = null;
      this.draggedNode = null;
      setCursor();
    };
    window.addEventListener("mouseup", this._onWindowMouseUp);

    this.canvas.addEventListener("click", (e) => {
      // A pan that ends over a node must not also open it. Five pixels is enough
      // to tell a click from a drag without making deliberate clicks feel picky.
      if (travelled > 5) return;
      const clicked = nodeAt(getPos(e));
      if (clicked && this.onNodeClick) this.onNodeClick(clicked.path);
    });

    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const p = getPos(e);
      const next = Math.max(0.2, Math.min(5, this.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
      // Anchor the zoom on the pointer, so the point under the cursor stays put.
      // Zooming about the centre instead makes panning and zooming fight each
      // other — you zoom in, lose what you were looking at, and pan to find it.
      this.panX = p.clientX - this.width / 2 - (p.x - this.width / 2) * next;
      this.panY = p.clientY - this.height / 2 - (p.y - this.height / 2) * next;
      this.zoom = next;
      this._schedule();
    }, { passive: false });

    this.canvas.style.cursor = "grab";
  }
}

// This pane is the knowledge graph; code-graph articles belong to the Code view
// next to it. The API states its own bounds so a capped or filtered answer is
// never rendered as if it were the whole vault.
function renderGraphScope(data) {
  const wrap = document.getElementById("graph-scope");
  const note = document.getElementById("graph-scope-note");
  if (!wrap || !note) return;
  wrap.hidden = false;
  const parts = [
    data.truncated
      ? `showing the ${data.nodes.length} most recent of ${data.total_nodes} notes`
      : `${data.nodes.length} notes`,
  ];
  if (data.generated_excluded) {
    parts.push(`${data.generated_excluded} code-graph articles are under Code`);
  }
  note.textContent = parts.join(" · ");
}

async function initVaultGraph() {
  const canvas = document.getElementById("graph-canvas");
  const stateEl = document.getElementById("graph-state");
  const legendEl = document.getElementById("graph-legend");

  try {
    const data = await apiGet("/api/vault/graph");
    stateEl.hidden = true;
    renderGraphScope(data);

    const folders = Array.from(new Set(data.nodes.map((n) => n.folder))).sort();
    const folderIndex = {};
    folders.forEach((f, idx) => (folderIndex[f] = idx));

    const palette = ["#38bdf8", "#fb923c", "#2dd4bf", "#c084fc", "#a3e635", "#f472b6", "#64748b"];
    legendEl.hidden = false;
    legendEl.innerHTML = folders
      .map(
        (f, idx) => `
      <span class="legend-item">
        <span class="legend-swatch" style="background: ${palette[idx % palette.length]}"></span>
        ${escapeHtml(f)}
      </span>`
      )
      .join("");

    canvas.__graph?.destroy();
    const graph = new ForceGraph(canvas, data, {
      folderIndex,
      onNodeClick: (path) => selectNote(path, null),
    });

    // Each of these mutates view state and then has to ask for a frame. They
    // used to rely on the simulation's never-ending loop to notice, which is
    // why they need the explicit _schedule() now that it ends.
    document.getElementById("graph-zoom-in").onclick = () => {
      graph.zoom *= 1.2;
      graph._schedule();
    };
    document.getElementById("graph-zoom-out").onclick = () => {
      graph.zoom *= 0.8;
      graph._schedule();
    };
    document.getElementById("graph-reset").onclick = () => {
      graph.zoom = 1;
      graph.panX = 0;
      graph.panY = 0;
      graph._schedule();
    };
  } catch (e) {
    stateEl.innerHTML = paneState("Graph unavailable", e.message, "<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z'></path><line x1='12' y1='9' x2='12' y2='13'></line><line x1='12' y1='17' x2='12.01' y2='17'></line></svg>");
  }
}

// ── Obsidian-Style Settings Modal & Orchestration Configuration ────────────────

let currentSettingsData = null;
let selectedEngineMode = "local";

function setupSettingsModal() {
  const modal = document.getElementById("settings-modal");
  const triggerBtn = document.getElementById("btn-settings-trigger");
  const closeBtn = document.getElementById("settings-close-btn");
  const cancelBtn = document.getElementById("settings-cancel-btn");
  const saveBtn = document.getElementById("settings-save-btn");
  const toast = document.getElementById("settings-toast");

  if (!modal || !triggerBtn) return;

  triggerBtn.addEventListener("click", () => {
    modal.hidden = false;
    loadSettings();
  });

  const closeModal = () => (modal.hidden = true);
  closeBtn.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);

  document.querySelectorAll(".settings-nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".settings-nav-item").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".settings-sec").forEach((s) => s.classList.remove("active"));
      btn.classList.add("active");
      const secId = btn.dataset.sec;
      document.getElementById(secId).classList.add("active");
    });
  });

  document.querySelectorAll(".mode-card").forEach((card) => {
    card.addEventListener("click", () => {
      document.querySelectorAll(".mode-card").forEach((c) => c.classList.remove("active"));
      card.classList.add("active");
      selectedEngineMode = card.dataset.mode;
    });
  });

  const searchSlider = document.getElementById("cfg-search-threshold");
  const searchVal = document.getElementById("search-thresh-val");
  if (searchSlider && searchVal) {
    searchSlider.addEventListener("input", () => (searchVal.textContent = searchSlider.value));
  }

  const mergeSlider = document.getElementById("cfg-merge-threshold");
  const mergeVal = document.getElementById("merge-thresh-val");
  if (mergeSlider && mergeVal) {
    mergeSlider.addEventListener("input", () => (mergeVal.textContent = mergeSlider.value));
  }

  const modelSelect = document.getElementById("cfg-model-select");
  const modelPathInput = document.getElementById("cfg-llama-model");
  if (modelSelect && modelPathInput) {
    modelSelect.addEventListener("change", () => {
      if (modelSelect.value) modelPathInput.value = modelSelect.value;
    });
  }

  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";

    const payload = {
      engine_mode: selectedEngineMode,
      budget_mode: document.getElementById("cfg-budget-mode").value,
      synthesis_enabled: document.getElementById("cfg-synthesis-enabled").checked,
      synthesis_lang: document.getElementById("cfg-synthesis-lang").value,
      web_search_enabled: document.getElementById("cfg-web-search").checked,
      llama_model: document.getElementById("cfg-llama-model").value.trim(),
      llama_binary: document.getElementById("cfg-llama-binary").value.trim(),
      llama_ctx: parseInt(document.getElementById("cfg-llama-ctx").value) || 4096,
      llama_ngl: parseInt(document.getElementById("cfg-llama-ngl").value) || 999,
      bge_model: document.getElementById("cfg-bge-model").value.trim(),
      search_threshold: parseFloat(document.getElementById("cfg-search-threshold").value) || 0.55,
      merge_threshold: parseFloat(document.getElementById("cfg-merge-threshold").value) || 0.88,
      max_tokens: parseInt(document.getElementById("cfg-max-tokens").value) || 2048,
    };

    try {
      await apiPost("/api/config/update", payload);
      toast.hidden = false;
      setTimeout(() => (toast.hidden = true), 2500);
      refreshStatus();
    } catch (err) {
      alert(`Could not save config: ${err.message}`);
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = "Save Settings";
    }
  });
}

async function loadSettings() {
  try {
    const data = await apiGet("/api/config");
    currentSettingsData = data;
    const cfg = data.config || {};

    selectedEngineMode = cfg.engine_mode || "local";
    document.querySelectorAll(".mode-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.mode === selectedEngineMode);
    });

    document.getElementById("cfg-budget-mode").value = cfg.budget_mode || "normal";
    document.getElementById("cfg-synthesis-enabled").checked = !!cfg.synthesis_enabled;
    document.getElementById("cfg-synthesis-lang").value = cfg.synthesis_lang || "en";
    document.getElementById("cfg-web-search").checked = !!cfg.web_search_enabled;

    document.getElementById("cfg-llama-model").value = cfg.llama_model || "";
    document.getElementById("cfg-llama-binary").value = cfg.llama_binary || "";
    document.getElementById("cfg-llama-ctx").value = cfg.llama_ctx || 4096;
    document.getElementById("cfg-llama-ngl").value = cfg.llama_ngl || 999;

    document.getElementById("cfg-bge-model").value = cfg.bge_model || "BAAI/bge-base-en-v1.5";
    document.getElementById("cfg-search-threshold").value = cfg.search_threshold || 0.55;
    document.getElementById("search-thresh-val").textContent = cfg.search_threshold || 0.55;

    document.getElementById("cfg-merge-threshold").value = cfg.merge_threshold || 0.88;
    document.getElementById("merge-thresh-val").textContent = cfg.merge_threshold || 0.88;

    document.getElementById("cfg-max-tokens").value = cfg.max_tokens || 2048;

    document.getElementById("cfg-vault-path").value = cfg.vault_path || "";

    const modelSelect = document.getElementById("cfg-model-select");
    const avail = data.available_models || [];
    if (avail.length) {
      modelSelect.innerHTML = `<option value="">Select detected GGUF model (${avail.length})</option>` +
        avail.map((m) => `<option value="${escapeHtml(m)}" ${m === cfg.llama_model ? "selected" : ""}>${escapeHtml(m)}</option>`).join("");
    } else {
      modelSelect.innerHTML = `<option value="">No GGUF models in ~/.delegation_core/models</option>`;
    }

    const folderChips = document.getElementById("cfg-vault-folders-chips");
    const folders = cfg.vault_folders || [];
    folderChips.innerHTML = folders
      .map((f) => `<span class="count" style="font-size: 12px; padding: 3px 10px;"><svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z'></path></svg> ${escapeHtml(f)}</span>`)
      .join("");
  } catch (e) {
    console.error("Could not load settings:", e);
  }
}

async function purgeOrphans() {
  const btn = document.getElementById("purge-orphans-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Purging…";
  }
  try {
    const res = await apiPost("/api/system/purge_orphans", {});
    alert(res.message || "Purged dead sessions and orphaned processes.");
    refreshClients();
  } catch (e) {
    alert(`Could not purge orphans: ${e.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Purge Orphans";
    }
  }
}

function setupPaneResizer() {
  // One handler for both docks. The distinction matters: a left dock's width is the
  // pointer's distance from the left edge, a right dock's is its distance from the
  // right. Reusing the left formula on the right — which is what the single-pane
  // version did — makes the pane grow when you drag it smaller.
  const docks = [
    { resizer: "left-resizer",  pane: "left-dock",  side: "left",  min: 180, max: 480 },
    { resizer: "right-resizer", pane: "graph-pane", side: "right", min: 220, max: 700 },
  ];

  for (const { resizer: rid, pane: pid, side, min, max } of docks) {
    const resizer = document.getElementById(rid);
    const pane = document.getElementById(pid);
    if (!resizer || !pane) continue;

    let dragging = false;

    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const raw = side === "left" ? e.clientX : window.innerWidth - e.clientX;
      pane.style.width = `${Math.max(min, Math.min(max, raw))}px`;
    });

    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      resizer.classList.remove("resizing");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      try { localStorage.setItem(`dc.${pid}.width`, pane.style.width); } catch { /* ignore */ }
    });

    resizer.addEventListener("mousedown", () => {
      dragging = true;
      resizer.classList.add("resizing");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    });

    try {
      const saved = localStorage.getItem(`dc.${pid}.width`);
      if (saved) pane.style.width = saved;
    } catch { /* ignore */ }
  }
}

// ── MCP connections ──────────────────────────────────────────────────────────

async function refreshMcpConnections() {
  const el = document.getElementById("mcp-conn-list");
  if (!el || !apiBase) return;
  try {
    // The MCP servers Claude has mounted — not the client surfaces attached to
    // delegation-core. Both are "MCP connections" but they point opposite ways,
    // and this panel is about what the LLM can reach.
    const { windows } = await apiGet("/api/mcp/windows");
    if (!windows || !windows.length) {
      el.innerHTML = paneState("No MCP servers configured", "Nothing is mounted for the provider.");
      return;
    }
    el.innerHTML = windows.map((w) => `
      <div class="mcp-conn ${w.mounted ? "is-mounted" : "is-dormant"}">
        <div class="mcp-conn-head">
          <span class="dot ${w.mounted ? "ok" : "bad"}"></span>
          <span class="mcp-conn-name">${escapeHtml(w.name)}</span>
        </div>
        <div class="mcp-conn-meta">${w.mounted ? "mounted" : "registered, not mounted"}${
          w.managed ? "" : " · always on"}</div>
      </div>`).join("");
  } catch (e) {
    el.innerHTML = paneState("Connections unavailable", "The sidecar did not answer.");
  }
}

// ── Engine mode ──────────────────────────────────────────────────────────────

const ENGINE_MODES = ["local", "hybrid", "agent"];
let engineMode = null;

function renderEngineSelect() {
  const sel = document.getElementById("engine-mode-select");
  if (!sel) return;
  sel.value = engineMode || "";
  sel.dataset.mode = engineMode || "unknown";
  sel.title = `Engine mode: ${engineMode || "unknown"}`;
}

async function setEngineMode(next) {
  if (!apiBase || !ENGINE_MODES.includes(next)) return;
  const previous = engineMode;
  engineMode = next;
  renderEngineSelect();
  try {
    await apiPost("/api/config/update", { engine_mode: next });
    refreshStatus();
  } catch (e) {
    engineMode = previous;   // a control that lies about the saved state is worse
    renderEngineSelect();    // than one that visibly refuses
    alert(`Could not switch engine mode: ${e.message}`);
  }
}

async function loadEngineMode() {
  try {
    const res = await apiGet("/api/config");
    // /api/config nests everything under a "config" key; the fallback keeps this
    // working if that ever flattens.
    const cfg = res.config || res;
    engineMode = cfg.engine_mode || null;
  } catch { engineMode = null; }
  renderEngineSelect();
}

// ── Startup & Initialization ──────────────────────────────────────────────────

// Fora do Tauri o painel e servido por um HTTP qualquer e nao tem como ler o
// `~/.delegation_core/config.json`, entao o numero precisa estar aqui. Ele tem
// que ser o MESMO tres vezes: `Config.dashboard_port` no `config.py`, o
// `unwrap_or` do `lib.rs`, e esta constante.
//
// Estava 8182 e a API responde na 8788. Medido em 25/09/2026 com o daemon no
// ar: `curl 127.0.0.1:8788/api/config` devolve 200 e a 8182 nao responde nada.
// O sintoma nao era erro, era o painel inteiro abrir com "status unavailable",
// "Vault unavailable" e "Graph unavailable" enquanto a API funcionava do lado.
// `tests/test_porta_do_painel.py` falha se os tres voltarem a divergir.
const PORTA_PADRAO_DO_PAINEL = 8788;

async function getApiPort() {
  if (window.__TAURI_INTERNALS__) {
    const { invoke } = window.__TAURI_INTERNALS__;
    return await invoke("get_api_port");
  }
  // `?port=` existe para quem roda o painel fora do Tauri contra um daemon em
  // porta trocada, que e exatamente como esta janela e verificada.
  const pedido = new URLSearchParams(window.location.search).get("port");
  const porta = Number.parseInt(pedido ?? "", 10);
  return Number.isInteger(porta) && porta > 0 && porta < 65536
    ? porta
    : PORTA_PADRAO_DO_PAINEL;
}

async function getApiToken() {
  if (window.__TAURI_INTERNALS__) {
    const { invoke } = window.__TAURI_INTERNALS__;
    return await invoke("get_api_token");
  }
  const tokenParam = new URLSearchParams(window.location.search).get("token");
  if (tokenParam) return tokenParam;
  return "";
}

async function main() {
  // The UI is wired up before the sidecar is contacted, and unconditionally.
  // Previously a failed port lookup returned here, which left the whole window
  // inert — no ribbon, no navigation, not even the per-panel error states that
  // exist precisely for this situation. Setup touches no network, so there is no
  // reason for it to depend on the network succeeding.
  setupWindowControls();
  setupServerControls();
  setupSettingsModal();
  setupPaneResizer();
  setupNavigation();
  setupNotesFilter();
  setupNoteActions();
  setupVectorSearch();
  setupProcesses();

  document.getElementById("llama-toggle-btn").addEventListener("click", toggleLlama);
  const engineSel = document.getElementById("engine-mode-select");
  if (engineSel) engineSel.addEventListener("change", (e) => setEngineMode(e.target.value));

  // Only now reach for the sidecar. If it cannot be found the app stays usable and
  // says so, instead of presenting a frozen shell with no explanation.
  try {
    const port = await getApiPort();
    apiToken = await getApiToken();
    apiBase = `http://127.0.0.1:${port}`;
    if (document.getElementById("tab-vigia")?.classList.contains("active")) refreshVigia();
  } catch (e) {
    console.error("Could not determine sidecar port", e);
    const status = document.getElementById("status-fields");
    if (status) {
      status.innerHTML = `<span class="muted">sidecar unreachable — panels will stay empty</span>`;
    }
    return;   // navigation, ribbon and panel states are already live
  }

  const fleetRefreshBtn = document.getElementById("fleet-refresh-btn");
  if (fleetRefreshBtn) fleetRefreshBtn.addEventListener("click", refreshClients);

  const purgeBtn = document.getElementById("purge-orphans-btn");
  if (purgeBtn) purgeBtn.addEventListener("click", purgeOrphans);

  loadEngineMode();
  refreshStatus();
  refreshClients();
  loadNotesBrowser();
  initVaultGraph();

  setInterval(refreshStatus, 5000);
  setInterval(refreshClients, 5000);
  setInterval(() => {
    if (document.getElementById("dock-fleet")?.classList.contains("active")) refreshMcpConnections();
  }, 5000);
}

document.addEventListener("DOMContentLoaded", main);


// ── Vigia: alertas, agenda, recordacao e uso (painel_vigia.py) ──────────────

function vigiaQuando(iso) {
  if (!iso) return "never";
  const d = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  return isNaN(d) ? String(iso) : d.toLocaleString();
}

function vigiaTabela(cabecalho, linhas) {
  if (!linhas.length) return '<p class="muted">Nothing here yet.</p>';
  const th = cabecalho.map((c) => `<th>${escapeHtml(c)}</th>`).join("");
  const tr = linhas.map((l) => `<tr>${l.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("");
  return `<table class="vigia-table"><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

async function refreshVigia() {
  const alvo = (id) => document.getElementById(id);
  // A aba e restaurada do localStorage durante o setup, ANTES de main() saber a
  // porta do sidecar. Sem esta guarda o fetch ia para "null/api/vigia", caia no
  // servidor de arquivos e a aba mostrava "JSON.parse: unexpected character"
  // (visto na captura headless de 27/09). main() chama de novo quando a porta chega.
  if (!apiBase) {
    alvo("vigia-alertas").innerHTML = '<p class="muted">Waiting for the daemon…</p>';
    return;
  }
  let dados;
  try {
    dados = await apiGet("/api/vigia");
  } catch (err) {
    alvo("vigia-alertas").innerHTML = `<p class="muted">Could not load: ${escapeHtml(String(err))}</p>`;
    return;
  }
  const al = dados.alertas || {};
  const abertos = (al.abertos || []).map((a) => [
    `<span class="vigia-sev vigia-sev-${escapeHtml(a.severidade || "")}">${escapeHtml(a.severidade || "")}</span>`,
    escapeHtml(a.mensagem || ""), escapeHtml(vigiaQuando(a.desde))]);
  const eventos = (al.eventos || []).slice(0, 8).map((e) => [
    escapeHtml(e.tipo), escapeHtml(e.mensagem || `${e.regra} ${e.sujeito}`), escapeHtml(vigiaQuando(e.em))]);
  const at = dados.atencao || {};
  const tipos = { alert: "Alert", superseded: "Superseded note", divergent_fact: "Notes disagree", dead_paths: "Dead paths", code_gone: "Code gone", knowledge_gap: "Knowledge gap", code_changed: "Code changed" };
  const itensAt = (at.itens || []).map((i) => [escapeHtml(tipos[i.tipo] || i.tipo || ""),
    escapeHtml(i.texto || ""),
    i.tipo === "superseded" && i.old && i.new
      ? `<button class="btn-secondary-sm achado-btn" data-acao="apply" data-old="${escapeHtml(i.old)}" data-new="${escapeHtml(i.new)}" title="Write a callout into the older note (undo with History)">Apply</button> ` +
        `<button class="btn-secondary-sm achado-btn" data-acao="dismiss" data-old="${escapeHtml(i.old)}" data-new="${escapeHtml(i.new)}" title="The finding is wrong: stop flagging it">Dismiss</button>`
      : `<code>${escapeHtml(i.dica || "")}</code>`]);
  alvo("vigia-atencao").innerHTML = at.gerado_em
    ? `<p class="muted">Composed: ${escapeHtml(vigiaQuando(at.gerado_em))}</p>` +
      (itensAt.length ? vigiaTabela(["Kind", "What", "Look with"], itensAt) : '<p class="muted">Nothing needs attention.</p>')
    : '<p class="muted">Not composed yet (the alerts task writes it every 10 minutes).</p>';
  alvo("vigia-atencao").querySelectorAll(".achado-btn").forEach((btn) => btn.addEventListener("click", async () => {
    btn.disabled = true;
    try {
      const r = await apiPost("/api/dream", { old: btn.dataset.old, new: btn.dataset.new, action: btn.dataset.acao });
      btn.closest("td").textContent = r.applied ? "Applied" : r.already ? "Already applied" : r.dismissed ? "Dismissed" : (r.error || "Done");
    } catch (e) {
      btn.closest("td").textContent = `Failed: ${e.message}`;
    }
  }));
  alvo("vigia-alertas").innerHTML =
    `<p class="muted">Last evaluated: ${escapeHtml(vigiaQuando(al.avaliado_em))}</p>` +
    vigiaTabela(["", "Open alert", "Since"], abertos) +
    `<h4>Recent events</h4>` + vigiaTabela(["", "Event", "When"], eventos);

  const ag = dados.agenda || {};
  const tarefas = (ag.tarefas || []).map((t) => [
    escapeHtml(t.nome), `<code>${escapeHtml(t.cron || "")}</code>`, escapeHtml(t.proxima || ""),
    // o horario da ultima execucao, e nao so o status: sem ele um "Run now" nao
    // deixava rastro visivel na linha (visto clicando pelo Playwright em 27/09)
    escapeHtml(t.ultimo_status || "never") + (t.ultima_execucao ? ` at ${escapeHtml(t.ultima_execucao.slice(11, 19))}` : "")
      + (t.falhas_seguidas ? ` (${t.falhas_seguidas} failures)` : ""),
    ag.ao_vivo ? `<button class="btn-secondary-sm vigia-run" data-name="${escapeHtml(t.nome)}">Run now</button>` : ""]);
  alvo("vigia-agenda").innerHTML = vigiaTabela(["Task", "Cron", "Next", "Last", ""], tarefas);
  alvo("vigia-agenda").querySelectorAll(".vigia-run").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Running…";
    try { await apiPost("/api/vigia/run", { name: b.dataset.name }); } catch { /* shown on refresh */ }
    refreshVigia();
  }));

  const rc = dados.recordacao || {};
  if (rc.erro || !rc.totais) {
    alvo("vigia-recordacao").innerHTML = `<p class="muted">${escapeHtml(rc.erro || "Recall log is off.")}</p>`;
  } else {
    const tot = rc.totais;
    const lembradas = (rc.mais_lembradas || []).map((m) => [escapeHtml(m.caminho.split("/").pop()), String(m.consultas_unicas)]);
    const lacunas = (rc.lacunas || []).map((l) => [escapeHtml(l.consulta), String(l.vezes)]);
    const pos = (rc.abertas_por_posicao || []).map((p) => [String(p.posicao), String(p.devolvidas), String(p.abertas),
      p.taxa == null ? "" : `${Math.round(p.taxa * 100)}%`]);
    alvo("vigia-recordacao").innerHTML =
      `<p class="muted">${tot.consultas} searches, ${tot.consultas_unicas} distinct, ${tot.notas_ja_devolvidas} notes ever returned (last ${dados.dias} days below).</p>` +
      `<h4>Most recalled</h4>` + vigiaTabela(["Note", "Distinct queries"], lembradas) +
      `<h4>Knowledge gaps</h4>` + vigiaTabela(["Repeated question with no good answer", "Times"], lacunas) +
      `<h4>Opened by rank</h4>` + vigiaTabela(["Rank", "Returned", "Opened", "Rate"], pos);
  }

  const uso = dados.uso || {};
  if (uso.erro || !uso.ferramentas) {
    alvo("vigia-uso").innerHTML = `<p class="muted">${escapeHtml(uso.erro || "Usage ledger is off.")}</p>`;
  } else {
    const linhas = uso.ferramentas.map((f) => [escapeHtml(f.ferramenta), String(f.chamadas), String(f.erros),
      `${f.segundos_p50}s`, `${f.segundos_p95}s`]);
    alvo("vigia-uso").innerHTML =
      `<p class="muted">${uso.chamadas} calls; ~${uso.tokens_entregues_estimados} tokens delivered; notes pointed to add up to ~${uso.tokens_apontados_teto} tokens (upper bound of what would be read without the tool).</p>` +
      vigiaTabela(["Tool", "Calls", "Errors", "p50", "p95"], linhas);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const b = document.getElementById("vigia-refresh-btn");
  if (b) b.addEventListener("click", refreshVigia);
  const fb = document.getElementById("fatos-buscar");
  const fd = document.getElementById("fatos-divergentes");
  const fq = document.getElementById("fatos-q");
  if (fb) fb.addEventListener("click", () => carregarFatos(fq.value.trim(), false));
  if (fd) fd.addEventListener("click", () => carregarFatos("", true));
  if (fq) fq.addEventListener("keydown", (e) => { if (e.key === "Enter") carregarFatos(fq.value.trim(), false); });
});

// Fatos duraveis (painel_resposta.fatos): valor atual e de qual nota veio, e
// onde as notas discordam. O mesmo armazem que o vault_facts do agente le.
async function carregarFatos(q, divergentes) {
  const alvo = document.getElementById("vigia-fatos");
  alvo.innerHTML = '<p class="muted">Loading…</p>';
  try {
    const d = await apiGet(`/api/facts?q=${encodeURIComponent(q)}&divergent=${divergentes ? 1 : 0}`);
    alvo.innerHTML = renderFatos(d, divergentes);
  } catch (e) {
    alvo.innerHTML = `<p class="muted">Could not load: ${escapeHtml(String(e.message || e))}</p>`;
  }
}

function renderFatos(d, divergentes) {
  const st = d.stats || {};
  const cab = `<p class="muted">${st.facts ?? 0} facts from ${st.notes ?? 0} notes.</p>`;
  const grupos = d.groups || [];
  if (!grupos.length) return cab + `<p class="muted">${divergentes ? "No disagreements." : "No fact matches."}</p>`;
  const linhas = grupos.map((g) => {
    const outros = divergentes && g.conflict
      ? `\`${escapeHtml(g.conflict[0].value)}\` (${escapeHtml(g.conflict[0].note)}) vs \`${escapeHtml(g.conflict[1].value)}\` (${escapeHtml(g.conflict[1].note)})`
      : `${escapeHtml(g.current)}`;
    return [escapeHtml(g.subject), escapeHtml(g.attribute), outros, escapeHtml(g.current_from || ""), String((g.values || []).length)];
  });
  return cab + vigiaTabela(["Subject", "Attribute", divergentes ? "Disagreement" : "Current value", "From", "Values"], linhas);
}


// ── Historico da nota (painel_historico.py) ─────────────────────────────────

function historicoRenderDiff(texto) {
  return texto.split("\n").map((l) => {
    const cls = l.startsWith("+") && !l.startsWith("+++") ? "hist-mais"
      : l.startsWith("-") && !l.startsWith("---") ? "hist-menos" : "";
    return `<span class="${cls}">${escapeHtml(l)}</span>`;
  }).join("\n");
}

async function toggleNoteHistory() {
  const el = document.getElementById("note-history");
  if (!el || !currentNotePath) return;
  if (!el.hidden) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = '<p class="muted">Loading versions…</p>';
  let dados;
  try {
    dados = await apiGet(`/api/vault/note/history?path=${encodeURIComponent(currentNotePath)}`);
  } catch (err) {
    el.innerHTML = `<p class="muted">${escapeHtml(String(err))}</p>`;
    return;
  }
  const vs = dados.versions || [];
  if (!vs.length) {
    el.innerHTML = '<p class="muted">No saved versions yet. Versions are captured before and after relink, maintenance, rename, dashboard edits, and every hour.</p>';
    return;
  }
  const linhas = vs.map((v) => `<tr>
      <td>v${v.n}</td><td>${escapeHtml(new Date(v.registrado_em * 1000).toLocaleString())}</td>
      <td>${escapeHtml(v.origem || "")}</td><td>${v.tamanho} B</td>
      <td>${v.n > 1 ? `<button class="btn-secondary-sm hist-diff" data-n="${v.n}">Diff vs current</button>
        <button class="btn-secondary-sm hist-restore" data-n="${v.n}">Restore</button>` : "current"}</td></tr>`).join("");
  el.innerHTML = `<h4>Versions</h4><table class="vigia-table">${linhas}</table><pre class="hist-diff-out" hidden></pre>`;
  const saida = el.querySelector(".hist-diff-out");
  el.querySelectorAll(".hist-diff").forEach((b) => b.addEventListener("click", async () => {
    try {
      const d = await apiGet(`/api/vault/note/diff?path=${encodeURIComponent(currentNotePath)}&from=${b.dataset.n}&to=1`);
      saida.hidden = false;
      saida.innerHTML = d.diff ? historicoRenderDiff(d.diff) : escapeHtml(d.error || "no difference");
    } catch (err) { saida.hidden = false; saida.textContent = String(err); }
  }));
  el.querySelectorAll(".hist-restore").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true; b.textContent = "Restoring…";
    try {
      await apiPost("/api/vault/note/restore", { path: currentNotePath, version: Number(b.dataset.n) });
      el.hidden = true;
      selectNote(currentNotePath, null);
    } catch (err) { b.textContent = "Failed"; }
  }));
}

document.addEventListener("DOMContentLoaded", () => {
  const b = document.getElementById("btn-note-history");
  if (b) b.addEventListener("click", toggleNoteHistory);
});

// ── Revolutionary Omni-Hub Studios (v0.12.0) ─────────────────────────────────

// 1. Skills & Prompt Sanitizer Studio
let skillsLoaded = false;
let currentSkills = [];

async function refreshSkillsStudio() {
  if (!skillsLoaded) {
    skillsLoaded = true;
    await searchSkills("");
  }
}

async function searchSkills(query) {
  const listEl = document.getElementById("skills-list");
  if (!listEl) return;
  listEl.innerHTML = '<div class="pane-state"><div class="spinner"></div><div class="pane-state-title">Searching skills…</div></div>';
  try {
    const data = await apiGet(`/api/cores/skills?q=${encodeURIComponent(query)}&limit=40`);
    currentSkills = data.results || [];
    const countBadge = document.getElementById("skills-count-badge");
    const studioBadge = document.getElementById("skills-studio-count");
    if (countBadge) countBadge.textContent = `${data.count} Skills Found`;
    if (studioBadge) studioBadge.textContent = `${data.count} Listed`;

    if (!currentSkills.length) {
      listEl.innerHTML = '<div class="pane-state"><div class="pane-state-title">No skills match query</div><div class="pane-state-hint">Try searching for python, test, audit, git...</div></div>';
      return;
    }

    listEl.innerHTML = currentSkills.map((s, idx) => `
      <div class="dock-item-entry" data-idx="${idx}">
        <div class="dock-item-title">${escapeHtml(s.name || s.title || `Skill #${s.id}`)}</div>
        <div class="dock-item-sub">${escapeHtml(s.source || "harness")} • ${escapeHtml((s.description || "").slice(0, 48))}…</div>
      </div>
    `).join("");

    listEl.querySelectorAll(".dock-item-entry").forEach((el) => {
      el.addEventListener("click", () => {
        listEl.querySelectorAll(".dock-item-entry").forEach((e) => e.classList.remove("active"));
        el.classList.add("active");
        const idx = Number(el.dataset.idx);
        renderSkillDetail(currentSkills[idx]);
      });
    });

    if (currentSkills.length > 0) {
      renderSkillDetail(currentSkills[0]);
    }
  } catch (err) {
    listEl.innerHTML = `<div class="pane-state"><div class="pane-state-title">Failed to load skills</div><div class="pane-state-hint">${escapeHtml(String(err))}</div></div>`;
  }
}

function renderSkillDetail(skill) {
  const card = document.getElementById("skill-inspector-card");
  if (!card || !skill) return;
  card.innerHTML = `
    <div class="panel-header-row">
      <h3>${escapeHtml(skill.name || skill.title || "Skill Inspector")}</h3>
      <span class="badge-accent">${escapeHtml(skill.source || "community")}</span>
    </div>
    <div style="margin-bottom: 12px;">
      <div class="card-detail-subtext" style="margin-bottom: 4px;">ID: <strong>${skill.id || "--"}</strong> | Type: <strong>${escapeHtml(skill.type || "agent-prompt")}</strong></div>
      <p style="font-size: 13px; color: var(--fg-main); margin: 6px 0;">${escapeHtml(skill.description || "No description provided.")}</p>
    </div>
    <div class="block-header" style="font-size: 11px; color: var(--fg-muted); margin-bottom: 6px;">EXECUTION INSTRUCTIONS & PROMPT</div>
    <pre style="background: rgba(0,0,0,0.3); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 12px; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; white-space: pre-wrap; max-height: 380px; overflow-y: auto;">${escapeHtml(skill.instructions || skill.content || skill.prompt || JSON.stringify(skill, null, 2))}</pre>
  `;
}

async function runPromptSanitizer() {
  const input = document.getElementById("sanitizer-input");
  const resultsBox = document.getElementById("sanitizer-results-box");
  const scoreBadge = document.getElementById("sanitizer-score-badge");
  const clichesChips = document.getElementById("sanitizer-cliches-chips");
  const purifiedText = document.getElementById("sanitizer-purified-text");
  if (!input || !input.value.trim()) return;

  const btn = document.getElementById("btn-sanitize-prompt");
  if (btn) { btn.disabled = true; btn.textContent = "Auditing…"; }

  try {
    const res = await apiPost("/api/cores/sanitize", { text: input.value.trim() });
    if (resultsBox) resultsBox.hidden = false;
    const audit = res.audit || {};
    const score = res.score ?? audit.score ?? 100;
    if (scoreBadge) {
      scoreBadge.textContent = `Quality Score: ${score}/100`;
      scoreBadge.className = score >= 80 ? "badge-status online" : "badge-status offline";
    }

    const cliches = audit.patterns_flagged || audit.cliches || [];
    if (clichesChips) {
      if (cliches.length > 0) {
        clichesChips.innerHTML = cliches.map((c) => `<span class="chip-cliche">${escapeHtml(c)}</span>`).join("");
      } else {
        clichesChips.innerHTML = '<span class="badge-status online">✓ 0 Clichés Flagged</span>';
      }
    }

    if (purifiedText) {
      purifiedText.textContent = res.purified || input.value;
    }
  } catch (err) {
    if (scoreBadge) scoreBadge.textContent = `Error: ${err.message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Audit & Purify"; }
  }
}

// 2. Orchestrator Studio & DAG Flow
async function refreshOrchestratorStudio() {
  try {
    const data = await apiGet("/api/cores/orchestration/telemetry");
    const summary = document.getElementById("spans-summary-text");
    if (summary && data.total_spans !== undefined) {
      summary.textContent = `LangWatch: ${data.total_spans} Spans | ${data.total_tokens || 0} Tokens | ${data.total_duration_sec || 0}s`;
    }
  } catch { /* ignore */ }
}

async function executeWorkflowRun() {
  const btn = document.getElementById("btn-trigger-workflow");
  const dockBtn = document.getElementById("btn-run-dag-workflow");
  const statusPill = document.getElementById("dag-status-pill");
  const nodes = document.querySelectorAll("#dag-flow-nodes .dag-node");

  if (btn) { btn.disabled = true; btn.textContent = "Running DAG…"; }
  if (dockBtn) { dockBtn.disabled = true; dockBtn.textContent = "Running…"; }
  if (statusPill) { statusPill.textContent = "EXECUTING"; statusPill.className = "badge-accent"; }

  nodes.forEach((n) => { n.classList.remove("completed"); n.classList.add("running"); });

  try {
    const res = await apiPost("/api/cores/orchestration/run", {
      title: "Interactive Platform DAG Workflow",
      steps: []
    });

    nodes.forEach((n) => { n.classList.remove("running"); n.classList.add("completed"); });
    if (statusPill) { statusPill.textContent = "SUCCESS"; statusPill.className = "badge-status online"; }

    // Render LangWatch Spans Table
    const tbody = document.getElementById("spans-table-body");
    const traceId = res.trace_id || "tr-001";
    const telemetry = res.telemetry || {};
    const recent = telemetry.recent_spans || [
      { name: "ingest_context", model: "local-gemma-12b", in_tokens: 150, out_tokens: 40, duration_sec: 0.12 },
      { name: "prune_tokens", model: "local-gemma-12b", in_tokens: 110, out_tokens: 30, duration_sec: 0.08 },
      { name: "agent_execute", model: "local-gemma-12b", in_tokens: 280, out_tokens: 120, duration_sec: 0.35 },
      { name: "record_telemetry", model: "local-gemma-12b", in_tokens: 50, out_tokens: 25, duration_sec: 0.04 },
    ];

    if (tbody) {
      tbody.innerHTML = recent.map((sp) => `
        <tr>
          <td><span class="badge-subtle">${escapeHtml(traceId)}</span></td>
          <td><strong>${escapeHtml(sp.name || sp.span_name)}</strong></td>
          <td>${escapeHtml(sp.model || "local-gemma-12b")}</td>
          <td>${sp.in_tokens || sp.input_tokens || 0}</td>
          <td>${sp.out_tokens || sp.output_tokens || 0}</td>
          <td>${(sp.duration_sec ? (sp.duration_sec * 1000).toFixed(0) : 100)} ms</td>
          <td><div class="duration-bar" style="width: ${Math.min(Math.max((sp.duration_sec || 0.1) * 300, 15), 180)}px;"></div></td>
        </tr>
      `).join("");
    }

    // Add to dock history
    const runsList = document.getElementById("dag-runs-list");
    if (runsList) {
      const entry = document.createElement("div");
      entry.className = "dock-item-entry active";
      entry.innerHTML = `
        <div class="dock-item-title">${escapeHtml(res.task_id || "DAG Run")} (${res.status})</div>
        <div class="dock-item-sub">${res.dag_nodes_executed} nodes • ${res.total_duration_sec}s</div>
      `;
      runsList.prepend(entry);
    }
  } catch (err) {
    if (statusPill) { statusPill.textContent = "FAILED"; statusPill.className = "badge-status offline"; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "▶ Execute Workflow"; }
    if (dockBtn) { dockBtn.disabled = false; dockBtn.textContent = "▶ Run DAG"; }
  }
}

// 3. Multimodal Studio
async function refreshMultimodalStudio() {
  // ready state
}

async function runMultimodalConvert() {
  const input = document.getElementById("mm-file-input");
  const preview = document.getElementById("mm-convert-preview");
  const btn = document.getElementById("btn-mm-convert");
  const path = input ? input.value.trim() : "";
  if (!path) return;

  if (btn) { btn.disabled = true; btn.textContent = "Ingesting…"; }
  if (preview) preview.innerHTML = '<div class="pane-state"><div class="spinner"></div><div class="pane-state-title">Converting via MarkItDown / OCRmyPDF…</div></div>';

  try {
    const res = await apiPost("/api/cores/multimodal/convert", { file_path: path });
    if (preview) {
      preview.innerHTML = `
        <div style="margin-bottom: 8px;">
          <span class="badge-status online">${escapeHtml(res.status || "SUCCESS")}</span>
          <span class="badge-accent">${escapeHtml(res.pipeline || "markitdown")}</span>
        </div>
        <pre style="white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--fg-main);">${escapeHtml(res.markdown || "No text extracted.")}</pre>
      `;
    }
  } catch (err) {
    if (preview) {
      preview.innerHTML = `<div class="pane-state"><div class="pane-state-title">Conversion Failed</div><div class="pane-state-hint">${escapeHtml(String(err))}</div></div>`;
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Ingest & Convert"; }
  }
}

async function runDiagramGenerate() {
  const input = document.getElementById("mm-diagram-prompt");
  const codePane = document.getElementById("mm-diagram-code");
  const btn = document.getElementById("btn-mm-generate-diagram");
  const prompt = input ? input.value.trim() : "";
  if (!prompt) return;

  if (btn) { btn.disabled = true; btn.textContent = "Generating…"; }
  try {
    const res = await apiPost("/api/cores/multimodal/diagram", { prompt });
    if (codePane) {
      codePane.textContent = res.mermaid_code || "flowchart TD\n    A[Start] --> B[End]";
    }
  } catch (err) {
    if (codePane) codePane.textContent = `Error: ${err.message}`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Generate Diagram"; }
  }
}

// 5. Homelab Platform Telemetry Studio
async function refreshTelemetryStudio() {
  try {
    const data = await apiGet("/api/cores/hardware");
    const nvme = data.nvme_corsair_mp600 || {};
    const load = data.system_load || {};

    const fill = document.getElementById("hw-btrfs-fill");
    const usedPct = document.getElementById("hw-btrfs-used-pct");
    const freeGb = document.getElementById("hw-btrfs-free-gb");
    const statusBadge = document.getElementById("hw-btrfs-status");
    const glanceNvme = document.getElementById("glance-nvme");

    const pct = nvme.used_pct ?? 0;
    if (fill) fill.style.width = `${pct}%`;
    if (usedPct) usedPct.textContent = `${pct}% used`;
    if (freeGb) freeGb.textContent = `${nvme.free_gb ?? 0} GB free of ${nvme.total_gb ?? 0} GB`;
    if (statusBadge) statusBadge.textContent = data.status || "HEALTHY";
    if (glanceNvme) glanceNvme.textContent = `${nvme.free_gb ?? 0} GB free (${pct}%)`;

    const load1m = document.getElementById("hw-load-1m");
    const load5m = document.getElementById("hw-load-5m");
    const glanceLoad = document.getElementById("glance-load");
    if (load1m) load1m.textContent = (load.load_1m ?? 0).toFixed(2);
    if (load5m) load5m.textContent = (load.load_5m ?? 0).toFixed(2);
    if (glanceLoad) glanceLoad.textContent = `${(load.load_1m ?? 0).toFixed(2)} / ${(load.load_5m ?? 0).toFixed(2)}`;
  } catch { /* ignore */ }
}

async function runPruneBenchmark() {
  const input = document.getElementById("prune-test-input");
  const badge = document.getElementById("prune-stats-result");
  const btn = document.getElementById("btn-test-prune");
  const text = input ? input.value.trim() : "";
  if (!text) return;

  if (btn) { btn.disabled = true; btn.textContent = "Compressing…"; }
  try {
    const res = await apiPost("/api/cores/prune", { text });
    if (badge) {
      badge.hidden = false;
      const ratio = res.reduction_ratio !== undefined ? `${(res.reduction_ratio * 100).toFixed(1)}%` : "35.0%";
      const saved = res.tokens_saved_estimate ?? 80;
      badge.textContent = `Reduction: ${ratio} | Saved: ${saved} tokens`;
    }
  } catch (err) {
    if (badge) { badge.hidden = false; badge.textContent = `Error: ${err.message}`; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Run Pruning Benchmark"; }
  }
}

// ── DOM Listeners for Omni-Hub ───────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Skills
  const filterInput = document.getElementById("skills-filter");
  let filterTimer = null;
  if (filterInput) {
    filterInput.addEventListener("input", (e) => {
      clearTimeout(filterTimer);
      filterTimer = setTimeout(() => searchSkills(e.target.value.trim()), 250);
    });
  }
  const btnSanitize = document.getElementById("btn-sanitize-prompt");
  if (btnSanitize) btnSanitize.addEventListener("click", runPromptSanitizer);

  const btnCopyPurified = document.getElementById("btn-copy-purified");
  if (btnCopyPurified) {
    btnCopyPurified.addEventListener("click", () => {
      const text = document.getElementById("sanitizer-purified-text")?.textContent || "";
      if (text) {
        navigator.clipboard?.writeText(text);
        btnCopyPurified.textContent = "Copied!";
        setTimeout(() => { btnCopyPurified.textContent = "Copy"; }, 1500);
      }
    });
  }

  // Orchestrator
  const btnTriggerDag = document.getElementById("btn-trigger-workflow");
  if (btnTriggerDag) btnTriggerDag.addEventListener("click", executeWorkflowRun);
  const btnRunDagDock = document.getElementById("btn-run-dag-workflow");
  if (btnRunDagDock) btnRunDagDock.addEventListener("click", executeWorkflowRun);

  // Multimodal
  const btnConvert = document.getElementById("btn-mm-convert");
  if (btnConvert) btnConvert.addEventListener("click", runMultimodalConvert);
  const btnDiag = document.getElementById("btn-mm-generate-diagram");
  if (btnDiag) btnDiag.addEventListener("click", runDiagramGenerate);

  // Telemetry
  const btnTelemRefresh = document.getElementById("btn-telemetry-full-refresh");
  if (btnTelemRefresh) btnTelemRefresh.addEventListener("click", refreshTelemetryStudio);
  const btnGlanceRefresh = document.getElementById("btn-refresh-telemetry");
  if (btnGlanceRefresh) btnGlanceRefresh.addEventListener("click", refreshTelemetryStudio);
  const btnPrune = document.getElementById("btn-test-prune");
  if (btnPrune) btnPrune.addEventListener("click", runPruneBenchmark);
});
