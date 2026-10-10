"use strict";

// Security rules for this file:
// - Every piece of server or model text goes onto the page with textContent, never as markup.
// - No inline handlers, no eval, nothing loaded from other origins (CSP: 'self' only).
// - The token lives in memory only. Refreshing the page signs the user out (V1 trade-off).
// - Hiding a control is convenience, not security: the server checks every action.

const MAX_QUESTION = 500;
const MAX_UPLOAD_MB = 50;
const GROUP_LABEL = { hr: "HR", general: "General", support: "Support", operations: "Operations" };
const groupLabel = (g) => GROUP_LABEL[g] || g;

let token = null;
let me = null;
let refreshTimer = null;
let waitTimer = null;
let lastQuestion = "";

const $ = (id) => document.getElementById(id);

// ---------- Icons: self-hosted SVG paths, 24x24 stroke icons ----------
const ICONS = {
  shield: ["M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z"],
  shieldCheck: ["M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z", "M9 12l2 2 4-4"],
  logout: ["M9 20H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h3", "M16 17l5-5-5-5", "M21 12H9"],
  arrowRight: ["M5 12h14", "M13 6l6 6-6 6"],
  search: ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14z", "M20 20l-4-4"],
  folder: ["M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"],
  lock: ["M6 11h12v9H6z", "M8 11V8a4 4 0 0 1 8 0v3"],
  file: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5"],
  fileQuestion: ["M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z", "M14 3v5h5",
    "M10 12a2 2 0 1 1 3 1.7c-.6.3-1 .8-1 1.3", "M12 18h.01"],
  external: ["M14 4h6v6", "M20 4l-9 9", "M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"],
  alert: ["M10.3 4.3L2.6 18a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0z", "M12 9v4", "M12 17h.01"],
  alertCircle: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 8v5", "M12 16h.01"],
  split: ["M12 21v-8", "M12 13L4.5 5.5", "M12 13l7.5-7.5", "M4 10V5h5", "M20 10V5h-5"],
  scan: ["M4 8V6a2 2 0 0 1 2-2h2", "M16 4h2a2 2 0 0 1 2 2v2", "M20 16v2a2 2 0 0 1-2 2h-2",
    "M8 20H6a2 2 0 0 1-2-2v-2", "M8 12h8"],
  clock: ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18z", "M12 7v5l3 2"],
  refresh: ["M20 11a8 8 0 0 0-14.9-3.9L4 9", "M4 4v5h5", "M4 13a8 8 0 0 0 14.9 3.9L20 15", "M20 20v-5h-5"],
  upload: ["M12 15V4", "M7 9l5-5 5 5", "M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"],
  check: ["M5 12l5 5 9-10"],
  quote: ["M7 7h4v4c0 3-1.5 5-4 6", "M14 7h4v4c0 3-1.5 5-4 6"],
};

function icon(name) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  for (const [k, v] of Object.entries({
    viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.75",
    "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
    focusable: "false", class: "icon",
  })) svg.setAttribute(k, v);
  for (const d of ICONS[name] || []) {
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    svg.append(p);
  }
  return svg;
}

function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((n) => {
    if (!n.querySelector("svg")) n.append(icon(n.dataset.icon));
  });
}

// ---------- DOM helpers ----------
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text); // text only, never markup
  return e;
}

function iconSpan(name, cls) {
  const s = el("span", cls);
  s.append(icon(name));
  return s;
}

function button(label, cls, iconName, iconAfter = false) {
  const b = el("button", cls);
  b.type = "button";
  const text = el("span", null, label);
  if (iconName && !iconAfter) b.append(icon(iconName));
  b.append(text);
  if (iconName && iconAfter) b.append(icon(iconName));
  return b;
}

// ---------- API ----------
class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(path, { ...opts, headers });
  } catch (_) {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  if (res.status === 401) {
    logout();
    throw new ApiError("Your session has ended. Please sign in again.", 401);
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch (_) { /* keep the generic message */ }
    throw new ApiError(msg, res.status);
  }
  return res;
}

// ---------- Sign in / out ----------
$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("login-btn");
  $("login-error").textContent = "";
  btn.disabled = true;
  btn.textContent = "Signing in…";
  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("email").value.trim(), password: $("password").value }),
    });
    if (!res.ok) throw new Error("Incorrect email or password.");
    token = (await res.json()).access_token;
    $("password").value = "";
    me = await (await api("/me")).json();
    showApp();
  } catch (err) {
    token = null;
    $("login-error").textContent = err.status === 0 || err.message.startsWith("Can't")
      ? err.message : "Incorrect email or password.";
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign in";
  }
});

function showApp() {
  $("login-view").hidden = true;
  $("app-view").hidden = false;
  $("whoami").hidden = false;
  $("user-email").textContent = me.email;
  $("user-role").textContent = String(me.role).replace(/_/g, " ");
  $("avatar").textContent = (me.email || "?").charAt(0);

  const groups = $("scope-groups");
  groups.replaceChildren(...(me.readable_groups.length
    ? me.readable_groups.map((g) => el("span", "pill", groupLabel(g)))
    : [el("span", "pill", "no groups")]));

  $("docs-tab").hidden = me.admin_groups.length === 0; // convenience only
  $("doc-group").replaceChildren(...me.admin_groups.map((g) => {
    const o = el("option", null, groupLabel(g));
    o.value = g;
    return o;
  }));
  renderEmpty();
  switchTab("ask");
  $("question").focus();
}

function logout() {
  token = null;
  me = null;
  clearTimeout(refreshTimer);
  stopWaiting();
  $("app-view").hidden = true;
  $("whoami").hidden = true;
  $("login-view").hidden = false;
  $("answer").replaceChildren();
  $("question").value = "";
  updateCounter();
  $("docs-table").querySelector("tbody").replaceChildren();
  $("email").focus();
}
$("logout").addEventListener("click", logout);

// ---------- Tabs ----------
function switchTab(tab) {
  document.querySelectorAll(".seg-btn").forEach((b) => {
    const on = b.dataset.tab === tab;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  $("ask-panel").hidden = tab !== "ask";
  $("docs-panel").hidden = tab !== "docs";
  if (tab === "docs") loadDocs();
  else clearTimeout(refreshTimer);
}
document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

// ---------- Ask: input ----------
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
$("kbd-mod").textContent = isMac ? "⌘" : "Ctrl";

function updateCounter() {
  const n = $("question").value.length;
  const c = $("counter");
  c.textContent = `${n} / ${MAX_QUESTION}`;
  c.classList.toggle("is-near", n >= MAX_QUESTION * 0.9 && n < MAX_QUESTION);
  c.classList.toggle("is-full", n >= MAX_QUESTION);
}
$("question").addEventListener("input", updateCounter);
$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    $("ask-form").requestSubmit();
  }
});

$("ask-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("question").value.trim();
  if (q && !$("ask-btn").disabled) ask(q);
});

async function ask(question) {
  lastQuestion = question;
  renderWaiting();
  $("ask-btn").disabled = true;
  try {
    const res = await api("/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    stopWaiting();
    if (data.status === "answered" && Array.isArray(data.sentences) && data.sentences.length) {
      renderAnswer(data, question);
    } else {
      renderRefusal(data.answer);
    }
  } catch (err) {
    stopWaiting();
    if (err.status !== 401) renderProblem(err);
  } finally {
    $("ask-btn").disabled = false;
  }
}

// ---------- Ask: states ----------
function stateCard(kind, iconName, title, text) {
  const card = el("div", `card state ${kind}`);
  const body = el("div", "state-body");
  body.append(el("p", "state-title", title));
  if (text) body.append(el("p", "state-text", text));
  card.append(iconSpan(iconName, "state-icon"), body);
  return { card, body };
}

function renderEmpty() {
  const row = el("div", "empty-state");
  row.append(icon("shieldCheck"),
    el("span", null, "Answers use only documents your role can read. Every sentence links to the page it was quoted from."));
  $("answer").replaceChildren(row);
}

function renderWaiting() {
  stopWaiting();
  const card = el("div", "card state state-wait");
  const iconBox = el("span", "state-icon");
  iconBox.append(el("span", "spinner"));
  const body = el("div", "state-body");
  const elapsed = el("span", "elapsed", "0 s");
  const title = el("p", "state-title", "Searching documents you can access");
  const text = el("p", "state-text");
  text.append(document.createTextNode("Finding evidence, drafting and checking each sentence against its source · "), elapsed);
  const sk = el("div", "skeleton");
  sk.append(el("span"), el("span"), el("span"));
  body.append(title, text, sk);
  card.append(iconBox, body);
  card.setAttribute("aria-busy", "true");
  $("answer").replaceChildren(card);
  const start = Date.now();
  waitTimer = setInterval(() => {
    elapsed.textContent = `${Math.floor((Date.now() - start) / 1000)} s`;
  }, 1000);
}

function stopWaiting() {
  clearInterval(waitTimer);
  waitTimer = null;
}

function renderRefusal(serverText) {
  const { card, body } = stateCard("state-refusal", "fileQuestion",
    "No answer found in your documents",
    serverText || "I can't find this in the documents you have access to.");
  const tips = el("ul", "state-tips");
  tips.append(
    el("li", null, "Try different wording, or name the policy or document you have in mind."),
    el("li", null, "If you expected an answer, the document may be outside your access. Ask its owner."));
  body.append(tips);
  $("answer").replaceChildren(card);
}

function renderProblem(err) {
  const unavailable = err.status === 503 || err.status === 429 || err.status === 0;
  const { card, body } = stateCard("state-error", "alertCircle",
    unavailable ? "The answer service is temporarily unavailable" : "Something went wrong",
    unavailable
      ? "Your question was not answered, and nothing was guessed. Please try again in a minute."
      : err.message);
  const actions = el("div", "state-actions");
  const retry = button("Try again", "btn btn-sm", "refresh");
  retry.addEventListener("click", () => { if (lastQuestion) ask(lastQuestion); });
  actions.append(retry);
  body.append(actions);
  $("answer").replaceChildren(card);
}

// ---------- Ask: answer ----------
function renderAnswer(d, question) {
  // One card per distinct quoted passage; several sentences may cite the same one.
  const cites = [];
  const keyToIndex = new Map();
  const refs = d.sentences.map((s) => {
    const c = s.citation;
    const key = `${c.version_id}|${c.page_number}|${c.quote}`;
    if (!keyToIndex.has(key)) {
      keyToIndex.set(key, cites.length);
      cites.push(c);
    }
    return keyToIndex.get(key) + 1;
  });

  const card = el("article", "card answer-card");

  // Header
  const head = el("header", "answer-head");
  const label = el("span", "answer-label");
  label.append(icon("shieldCheck"), el("span", null, "Verified answer & citations"));
  const docs = new Set(cites.map((c) => c.version_id)).size;
  const pill = el("span", "pill",
    `${cites.length} ${cites.length === 1 ? "source" : "sources"} · ${docs} ${docs === 1 ? "document" : "documents"}`);
  head.append(label, pill);
  const ms = (d.retrieval_ms || 0) + (d.generation_ms || 0) + (d.judge_ms || 0);
  if (ms > 0) {
    const t = el("span", "answer-time");
    t.append(icon("clock"), el("span", null, `${(ms / 1000).toFixed(1)} s`));
    head.append(t);
  }
  card.append(head);

  // Conflict banner
  if (d.conflict) {
    const sec = el("div", "answer-section");
    sec.append(banner("split", "The documents disagree",
      "The cited sources give different answers to this question. Compare them below and confirm with the document owner before acting."));
    card.append(sec);
  }

  // Answer text with numbered references
  const main = el("div", "answer-section");
  const echo = el("p", "question-echo");
  echo.append(document.createTextNode("You asked "), el("q", null, question));
  const text = el("p", "answer-text");
  d.sentences.forEach((s, i) => {
    const span = el("span", "sentence", s.text);
    span.dataset.ref = String(refs[i]);
    const ref = el("button", "ref", refs[i]);
    ref.type = "button";
    ref.setAttribute("aria-label", `Show source ${refs[i]}`);
    ref.addEventListener("click", () => highlight(card, refs[i], true));
    text.append(span, ref, document.createTextNode(" "));
  });
  main.append(echo, text);
  card.append(main);

  // Citation cards
  const src = el("div", "answer-section");
  const sl = el("div", "section-label");
  sl.append(el("span", null, "Sources"));
  src.append(sl);
  const list = el("div", "cites");
  cites.forEach((c, i) => list.append(citationCard(c, i + 1, card)));
  src.append(list);
  card.append(src);

  // Footer
  const foot = el("footer", "answer-foot");
  foot.append(icon("check"),
    el("span", null, "Each sentence is backed by a passage found word for word on the cited page."));
  card.append(foot);

  $("answer").replaceChildren(card);
}

function citationCard(c, n, answerCard) {
  const box = el("div", "cite");
  box.dataset.ref = String(n);

  const head = el("div", "cite-head");
  const meta = el("div", "cite-meta");
  meta.append(el("span", "pill pill-mono", `v${c.version_number}`), el("span", "pill", `Page ${c.page_number}`));
  const title = el("span", "cite-title", c.document_title);
  title.title = c.document_title;
  head.append(el("span", "cite-num", n), iconSpan("file", "cite-file"), title, meta);
  box.append(head);

  box.append(el("blockquote", null, c.quote));

  if (c.low_confidence) {
    box.append(banner("scan", "Scanned page",
      "This text was read by OCR and may contain recognition errors. Check the original PDF."));
  }

  const foot = el("div", "cite-foot");
  const msg = el("p", "form-msg");
  const open = button("Open PDF", "btn btn-sm", "external", true);
  open.setAttribute("aria-label", `Open ${c.document_title}, page ${c.page_number}`);
  open.addEventListener("click", () => openSource(c.version_id, c.page_number, msg));
  foot.append(msg, open);
  box.append(foot);

  box.addEventListener("mouseenter", () => highlight(answerCard, n, false));
  box.addEventListener("mouseleave", () => highlight(answerCard, null, false));
  return box;
}

function banner(iconName, title, text) {
  const b = el("div", "banner banner-amber");
  b.setAttribute("role", "note");
  const body = el("div");
  body.append(el("p", "banner-title", title), el("p", null, text));
  b.append(icon(iconName), body);
  return b;
}

function highlight(card, n, scroll) {
  card.querySelectorAll(".is-lit").forEach((x) => x.classList.remove("is-lit"));
  if (n === null) return;
  card.querySelectorAll(`[data-ref="${n}"]`).forEach((x) => x.classList.add("is-lit"));
  if (scroll) {
    const target = card.querySelector(`.cite[data-ref="${n}"]`);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

async function openSource(versionId, page, msgEl) {
  // Open the window inside the click so pop-up blockers allow it, then load the PDF into it.
  const win = window.open("", "_blank");
  msgEl.textContent = "";
  if (!win) {
    setMsg(msgEl, "Allow pop-ups for this site to open PDFs.", "error");
    return;
  }
  try {
    const res = await api(`/versions/${encodeURIComponent(versionId)}/file`);
    const url = URL.createObjectURL(await res.blob());
    win.opener = null;
    win.location.href = `${url}#page=${page}`;
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (err) {
    win.close();
    setMsg(msgEl, err.message, "error");
  }
}

// ---------- Documents ----------
const STATUS_CLASS = {
  published: "badge-ok", processing: "badge-progress", queued: "badge-progress",
  failed: "badge-bad", superseded: "badge-muted",
};

async function loadDocs() {
  clearTimeout(refreshTimer);
  const tbody = $("docs-table").querySelector("tbody");
  const refreshBtn = $("refresh-docs");
  refreshBtn.classList.add("is-busy");
  try {
    const docs = await (await api("/documents")).json();
    tbody.replaceChildren();
    let pending = 0;
    let published = 0;
    docs.forEach((d) => {
      const v = d.versions[0];
      if (!v) return;
      if (v.status === "queued" || v.status === "processing") pending += 1;
      if (v.status === "published") published += 1;
      tbody.append(docRow(d, v));
    });
    $("docs-empty").hidden = docs.length > 0;
    $("docs-summary").textContent = docs.length
      ? `${docs.length} ${docs.length === 1 ? "document" : "documents"} · ${published} searchable${pending ? ` · ${pending} processing` : ""}`
      : "";
    if (pending && !$("docs-panel").hidden) refreshTimer = setTimeout(loadDocs, 3000);
  } catch (err) {
    if (err.status !== 401) setMsg($("upload-msg"), err.message, "error");
  } finally {
    refreshBtn.classList.remove("is-busy");
  }
}
$("refresh-docs").addEventListener("click", loadDocs);

function docRow(d, v) {
  const tr = el("tr");

  const titleTd = el("td");
  const cell = el("div", "doc-cell");
  const texts = el("div");
  texts.append(el("div", "doc-title", d.title));
  if (v.status === "failed") {
    texts.append(el("div", "doc-error", `Failed at ${v.error_step || "unknown step"}: ${v.error_message || "no details"}`));
  }
  cell.append(icon("file"), texts);
  titleTd.append(cell);

  const statusTd = el("td");
  statusTd.append(el("span", `badge ${STATUS_CLASS[v.status] || "badge-muted"}`, v.status));

  const action = el("td");
  if (d.can_manage && v.status === "failed") {
    const btn = button("Retry", "btn btn-sm", "refresh");
    btn.addEventListener("click", () => retry(v.version_id, btn));
    action.append(btn);
  }

  const pages = el("td", "num", v.page_count ?? "—");
  tr.append(titleTd, el("td", "group-cell", groupLabel(d.access_group)), el("td", null, `v${v.version_number}`), statusTd, pages, action);
  return tr;
}

async function retry(versionId, btn) {
  btn.disabled = true;
  try {
    await api(`/versions/${encodeURIComponent(versionId)}/retry`, { method: "POST" });
    loadDocs();
  } catch (err) {
    btn.disabled = false;
    if (err.status !== 401) setMsg($("upload-msg"), err.message, "error");
  }
}

function setMsg(node, text, kind) {
  node.className = `form-msg${kind ? ` is-${kind}` : ""}`;
  node.textContent = text;
}

// Upload: drop zone
const fileInput = $("doc-file");
const dropzone = $("dropzone");

function showChosenFile() {
  const f = fileInput.files[0];
  dropzone.classList.toggle("has-file", Boolean(f));
  if (f) {
    $("drop-text").textContent = f.name;
    $("drop-sub").textContent = `${(f.size / 1024 / 1024).toFixed(1)} MB · click to choose a different file`;
  } else {
    $("drop-text").replaceChildren(document.createTextNode("Drop a PDF here or "), el("span", "link", "browse"));
    $("drop-sub").textContent = "Only people in the selected group will be able to search it.";
  }
}
fileInput.addEventListener("change", showChosenFile);
["dragenter", "dragover"].forEach((t) => dropzone.addEventListener(t, (e) => {
  e.preventDefault();
  dropzone.classList.add("is-over");
}));
["dragleave", "drop"].forEach((t) => dropzone.addEventListener(t, () => dropzone.classList.remove("is-over")));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer && e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    showChosenFile();
  }
});

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("upload-msg");
  const title = $("doc-title").value.trim();
  const f = fileInput.files[0];
  // Client-side checks are for convenience; the server enforces type, size and permissions.
  if (!title) return setMsg(msg, "Add a title.", "error");
  if (!f) return setMsg(msg, "Choose a PDF file.", "error");
  if (!/\.pdf$/i.test(f.name) && f.type !== "application/pdf") return setMsg(msg, "Only PDF files can be uploaded.", "error");
  if (f.size > MAX_UPLOAD_MB * 1024 * 1024) return setMsg(msg, `The file is larger than ${MAX_UPLOAD_MB} MB.`, "error");

  const fd = new FormData();
  fd.append("title", title);
  fd.append("access_group", $("doc-group").value);
  fd.append("file", f);
  const btn = $("upload-btn");
  btn.disabled = true;
  setMsg(msg, "Uploading…");
  try {
    await api("/documents", { method: "POST", body: fd });
    setMsg(msg, "Uploaded. Processing has started; the status updates automatically.", "ok");
    $("upload-form").reset();
    showChosenFile();
    loadDocs();
  } catch (err) {
    if (err.status !== 401) setMsg(msg, err.message, "error");
  } finally {
    btn.disabled = false;
  }
});

// ---------- Boot ----------
hydrateIcons();
updateCounter();
