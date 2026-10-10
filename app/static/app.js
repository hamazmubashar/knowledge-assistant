let token = null;
let me = null;
let refreshTimer = null;

const $ = (id) => document.getElementById(id);

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text; // never innerHTML: model text stays plain text
  if (cls) e.className = cls;
  return e;
}

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    logout();
    throw new Error("Your session has ended. Please sign in again.");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
    } catch (_) { /* keep generic message */ }
    throw new Error(msg);
  }
  return res;
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").textContent = "";
  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: $("email").value, password: $("password").value }),
    });
    if (!res.ok) throw new Error("Invalid email or password.");
    token = (await res.json()).access_token;
    $("password").value = "";
    me = await (await api("/me")).json();
    showApp();
  } catch (err) {
    $("login-error").textContent = err.message;
  }
});

function showApp() {
  $("login-view").hidden = true;
  $("app-view").hidden = false;
  $("whoami").hidden = false;
  $("user-label").textContent = `${me.email} (${me.role})`;
  const canManage = me.admin_groups.length > 0;
  $("docs-tab").hidden = !canManage; // convenience only: the server checks every action
  const select = $("doc-group");
  select.replaceChildren(...me.admin_groups.map((g) => {
    const o = el("option", g);
    o.value = g;
    return o;
  }));
  switchTab("ask");
}

function logout() {
  token = null;
  me = null;
  clearTimeout(refreshTimer);
  $("app-view").hidden = true;
  $("whoami").hidden = true;
  $("login-view").hidden = false;
  $("answer").replaceChildren();
  $("question").value = "";
}
$("logout").addEventListener("click", logout);

function switchTab(tab) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  $("ask-panel").hidden = tab !== "ask";
  $("docs-panel").hidden = tab !== "docs";
  if (tab === "docs") loadDocs();
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = $("question").value.trim();
  if (!question) return;
  const box = $("answer");
  box.replaceChildren(el("p", "Searching the documents you have access to…", "meta"));
  $("ask-btn").disabled = true;
  try {
    const res = await api("/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    renderAnswer(await res.json());
  } catch (err) {
    box.replaceChildren(el("p", err.message, "error"));
  } finally {
    $("ask-btn").disabled = false;
  }
});

function renderAnswer(d) {
  const box = $("answer");
  box.replaceChildren();
  if (d.status === "refused") {
    box.append(el("p", d.answer, "refusal"));
    return;
  }
  if (d.conflict) {
    box.append(el("p", "The documents disagree on this question. Both versions are shown; check with the document owner.", "warning"));
  }
  const list = el("ol", undefined, "sentences");
  d.sentences.forEach((s) => {
    const li = el("li");
    li.append(el("p", s.text));
    const c = s.citation;
    const cite = el("div", undefined, "citation");
    const link = el("button", `${c.document_title} · version ${c.version_number} · page ${c.page_number}`, "cite-link");
    link.type = "button";
    link.addEventListener("click", () => openSource(c.version_id, c.page_number));
    cite.append(link, el("blockquote", c.quote));
    if (c.low_confidence) {
      cite.append(el("p", "From a scanned page: text recognition may contain errors. Check the original.", "warning"));
    }
    li.append(cite);
    list.append(li);
  });
  box.append(list);
  const seconds = (d.retrieval_ms + (d.generation_ms || 0) + (d.judge_ms || 0)) / 1000;
  box.append(el("p", `Answered in ${seconds.toFixed(1)} s`, "meta"));
}

async function openSource(versionId, page) {
  try {
    const res = await api(`/versions/${versionId}/file`);
    const url = URL.createObjectURL(await res.blob());
    window.open(`${url}#page=${page}`, "_blank", "noopener");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (err) {
    $("answer").append(el("p", err.message, "error"));
  }
}

async function loadDocs() {
  clearTimeout(refreshTimer);
  const tbody = $("docs-table").querySelector("tbody");
  try {
    const docs = await (await api("/documents")).json();
    tbody.replaceChildren();
    let pending = false;
    docs.forEach((d) => {
      const v = d.versions[0];
      if (!v) return;
      if (v.status === "queued" || v.status === "processing") pending = true;
      const tr = el("tr");
      const status = v.status === "failed" ? `failed at ${v.error_step}: ${v.error_message}` : v.status;
      [d.title, d.access_group, `v${v.version_number}`, status, v.page_count ?? "—"].forEach((t) => tr.append(el("td", String(t))));
      const action = el("td");
      if (d.can_manage && v.status === "failed") {
        const btn = el("button", "Retry");
        btn.type = "button";
        btn.addEventListener("click", () => retry(v.version_id));
        action.append(btn);
      }
      tr.append(action);
      tbody.append(tr);
    });
    if (pending) refreshTimer = setTimeout(loadDocs, 3000);
  } catch (err) {
    tbody.replaceChildren();
    $("upload-msg").textContent = err.message;
  }
}
$("refresh-docs").addEventListener("click", loadDocs);

async function retry(versionId) {
  try {
    await api(`/versions/${versionId}/retry`, { method: "POST" });
    loadDocs();
  } catch (err) {
    $("upload-msg").textContent = err.message;
  }
}

$("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData();
  fd.append("title", $("doc-title").value);
  fd.append("access_group", $("doc-group").value);
  fd.append("file", $("doc-file").files[0]);
  $("upload-msg").textContent = "Uploading…";
  try {
    await api("/documents", { method: "POST", body: fd });
    $("upload-msg").textContent = "Uploaded. Processing has started.";
    $("upload-form").reset();
    loadDocs();
  } catch (err) {
    $("upload-msg").textContent = err.message;
  }
});