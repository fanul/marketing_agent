/* Vimero Agent — frontend (vanilla JS, tanpa build step) */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
let BOOT = null;
let activeKey = "terminal";
let pollTimer = null;

/* ---------------------------------------------------------------- utils */

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  $("#toast-root").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function openModal(html) {
  const back = document.createElement("div");
  back.className = "modal-back";
  back.innerHTML = `<div class="modal">${html}</div>`;
  back.addEventListener("mousedown", (e) => { if (e.target === back) back.remove(); });
  $("#modal-root").appendChild(back);
  return back;
}

function statusPill(status) {
  const map = { selesai: "green", berjalan: "amber", antre: "", gagal: "red" };
  return `<span class="pill ${map[status] ?? ""}">${esc(status)}</span>`;
}

function fmtTime(iso) {
  if (!iso) return "-";
  try { return new Date(iso).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "short" }); }
  catch { return iso; }
}

function currentModel() {
  return localStorage.getItem("vimero_model") || BOOT.default_model;
}

/* ------------------------------------------------------------- markdown */

function mdInline(s) {
  return s
    .replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      `<a href="$2" target="_blank" rel="noopener">$1</a>`);
}

function md(text) {
  const src = esc(text || "");
  const lines = src.split(/\r?\n/);
  const out = [];
  let i = 0, para = [], list = null;

  const flushPara = () => {
    if (para.length) { out.push(`<p>${mdInline(para.join("<br>"))}</p>`); para = []; }
  };
  const flushList = () => {
    if (list) { out.push(`<${list.tag}>${list.items.map(x => `<li>${mdInline(x)}</li>`).join("")}</${list.tag}>`); list = null; }
  };

  while (i < lines.length) {
    const line = lines[i];

    if (/^```/.test(line)) {                       // code fence
      flushPara(); flushList();
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push(`<pre><code>${buf.join("\n")}</code></pre>`);
      continue;
    }
    if (/^\|.*\|\s*$/.test(line)) {                // table
      flushPara(); flushList();
      const rows = [];
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++]);
      const cells = r => r.replace(/^\||\|\s*$/g, "").split("|").map(c => c.trim());
      let html = "<table>";
      rows.forEach((r, idx) => {
        if (/^\|[\s:|-]+\|?\s*$/.test(r)) return;  // separator row
        const tag = idx === 0 ? "th" : "td";
        html += `<tr>${cells(r).map(c => `<${tag}>${mdInline(c)}</${tag}>`).join("")}</tr>`;
      });
      out.push(html + "</table>");
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) { flushPara(); flushList(); out.push(`<h${h[1].length}>${mdInline(h[2])}</h${h[1].length}>`); i++; continue; }
    if (/^\s*([-*])\s+/.test(line)) {
      flushPara();
      if (!list || list.tag !== "ul") { flushList(); list = { tag: "ul", items: [] }; }
      list.items.push(line.replace(/^\s*[-*]\s+/, "")); i++; continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      flushPara();
      if (!list || list.tag !== "ol") { flushList(); list = { tag: "ol", items: [] }; }
      list.items.push(line.replace(/^\s*\d+[.)]\s+/, "")); i++; continue;
    }
    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) { flushPara(); flushList(); out.push("<hr>"); i++; continue; }
    if (/^&gt;\s?/.test(line)) {
      flushPara(); flushList();
      out.push(`<blockquote>${mdInline(line.replace(/^&gt;\s?/, ""))}</blockquote>`); i++; continue;
    }
    if (line.trim() === "") { flushPara(); flushList(); i++; continue; }
    flushList(); para.push(line); i++;
  }
  flushPara(); flushList();
  return `<div class="md">${out.join("")}</div>`;
}

/* -------------------------------------------------------------- sidebar */

function navItem(key, icon, label, sub = "") {
  return `<div class="nav-item ${key === activeKey ? "active" : ""}" data-key="${key}">
    <span class="icon">${icon}</span>
    <span class="lbl">${esc(label)}${sub ? `<span class="sub">${esc(sub)}</span>` : ""}</span>
  </div>`;
}

function renderSidebar() {
  const s = BOOT.studios;
  const bySlug = slug => s.find(x => x.slug === slug);
  const mon = bySlug("monitoring"), dir = bySlug("direksi");
  const others = s.filter(x => !["monitoring", "direksi"].includes(x.slug));

  let html = "";
  html += `<div class="nav-section"><div class="nav-title"><span class="num">1</span>Monitoring Semua Data</div>`;
  html += navItem("monitoring", "📈", "Monitoring", mon?.agents[0]?.name || "");
  html += navItem("penghasilan", "💰", "Penghasilan", mon?.agents[1]?.name || "");
  html += `</div>`;

  html += `<div class="nav-section"><div class="nav-title"><span class="num">2</span>Denah &amp; Direksi</div>`;
  html += navItem("workflows", "🗺️", "Alur (Kantor)", "Denah Kantor");
  (dir?.agents || []).forEach(a => {
    const short = (a.role.split("—")[0] || a.role).trim();
    html += navItem(`studio-${dir.id}`, a.is_lead ? "👔" : "🧑‍💼", short, a.name);
  });
  html += `</div>`;

  html += `<div class="nav-section"><div class="nav-title"><span class="num">3</span>Karyawan</div>`;
  html += navItem("laporan", "📋", "Ruang Laporan", "");
  others.forEach(st => {
    html += navItem(`studio-${st.id}`, st.icon || "🏢", st.name, st.lead_name || "");
  });
  html += navItem("terminal", "💻", "Terminal Asisten", "Tomi");
  html += `</div>`;

  html += `<div class="nav-section"><div class="nav-title">Lainnya</div>`;
  html += navItem("pengaturan", "⚙️", "Pengaturan", "");
  html += `</div>`;

  $("#sidebar").innerHTML = html;
  document.querySelectorAll(".nav-item").forEach(el => {
    el.addEventListener("click", () => go(el.dataset.key));
  });
}

function go(key) {
  activeKey = key;
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  renderSidebar();
  if (key === "terminal") return viewTerminal();
  if (key === "monitoring" || key === "penghasilan") return viewMonitoring();
  if (key === "workflows") return viewWorkflows();
  if (key === "laporan") return viewLaporan();
  if (key === "pengaturan") return viewSettings();
  if (key.startsWith("studio-")) return viewStudio(Number(key.slice(7)));
  viewTerminal();
}

/* ------------------------------------------------------------- terminal */

const BANNER = [
  "██╗   ██╗██╗███╗   ███╗███████╗██████╗  ██████╗ ",
  "██║   ██║██║████╗ ████║██╔════╝██╔══██╗██╔═══██╗",
  "██║   ██║██║██╔████╔██║█████╗  ██████╔╝██║   ██║",
  "╚██╗ ██╔╝██║██║╚██╔╝██║██╔══╝  ██╔══██╗██║   ██║",
  " ╚████╔╝ ██║██║ ╚═╝ ██║███████╗██║  ██║╚██████╔╝",
  "  ╚═══╝  ╚═╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ",
  " █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
  "██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
  "███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ",
  "██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ",
  "██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ",
  "╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ",
].join("\n");

function toolLine(t) {
  const args = esc(JSON.stringify(t.args));
  let res = JSON.stringify(t.result);
  if (res.length > 260) res = res.slice(0, 260) + "…";
  return `<div class="tool-line">🔧 <b>${esc(t.name)}</b>(${args}) → ${esc(res)}</div>`;
}

function assistantBlock(content, meta = {}) {
  const tools = (meta.tool_trace || []).map(toolLine).join("");
  const tag = meta.model ? `<div class="tag">🤖 [${esc(meta.model)}]</div>` : "";
  return `<div class="msg msg-assistant">${tools}${tag}${md(content)}</div>`;
}

async function viewTerminal() {
  view.innerHTML = `
  <div id="terminal">
    <div class="term-head">
      <span>🟢</span>
      <span class="who">Terminal Asisten <small>asisten@vimero</small></span>
      <select id="model-select">
        ${BOOT.models.map(m => `<option value="${esc(m)}" ${m === currentModel() ? "selected" : ""}>${esc(m)}</option>`).join("")}
      </select>
      <span class="online">● ONLINE</span>
    </div>
    <div class="term-body" id="term-body">
      <pre class="banner">${BANNER}</pre>
      <div class="sysline">[ SYSTEM INITIALIZED ] — Vimero Agent Terminal v1.0</div>
      <div class="hintline">Ketik perintah, atau coba: <b>"siapa saja karyawan kita?"</b> ·
        <b>"jalankan riset produk untuk skincare lokal"</b> ·
        <b>"buatkan storyboard video tentang AI"</b> ·
        <b>"rekrut copywriter baru di studio script"</b></div>
      <div id="chat-log"></div>
    </div>
    <div class="term-input">
      <textarea id="chat-input" placeholder="ketik perintah... (Enter kirim · Shift+Enter baris baru)"></textarea>
      <button class="btn btn-primary" id="btn-send">Kirim</button>
    </div>
  </div>`;

  $("#model-select").addEventListener("change", e =>
    localStorage.setItem("vimero_model", e.target.value));

  const log = $("#chat-log"), body = $("#term-body");
  try {
    const msgs = await api("/api/messages");
    log.innerHTML = msgs.map(m =>
      m.role === "user"
        ? `<div class="msg msg-user">${esc(m.content)}</div>`
        : assistantBlock(m.content, m.meta)
    ).join("");
  } catch {}
  if (!BOOT.api_key_set) {
    log.innerHTML += `<div class="msg msg-assistant"><div class="md">
      <p>⚠️ <strong>API key belum diatur.</strong> Buka <a href="#" id="goto-setting">Pengaturan</a>
      lalu isi API key gateway (adaCODE / OpenRouter) supaya para karyawan AI bisa mulai bekerja.</p></div></div>`;
    $("#goto-setting")?.addEventListener("click", e => { e.preventDefault(); go("pengaturan"); });
  }
  body.scrollTop = body.scrollHeight;

  const input = $("#chat-input");
  const send = async () => {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    log.innerHTML += `<div class="msg msg-user">${esc(text)}</div>`;
    const typing = document.createElement("div");
    typing.className = "msg typing";
    typing.textContent = "Tomi sedang bekerja";
    log.appendChild(typing);
    body.scrollTop = body.scrollHeight;
    const t0 = Date.now();
    try {
      const res = await api("/api/chat", { method: "POST", body: { text, model: currentModel() } });
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      typing.outerHTML =
        `<div class="msg-meta">⚡ ${esc(currentModel())} · ⏱ ${secs}s · <span class="ok">selesai ✓</span></div>` +
        assistantBlock(res.content, { tool_trace: res.tool_trace, model: currentModel() });
    } catch (err) {
      typing.outerHTML = `<div class="msg msg-assistant"><div class="md"><p>❌ ${esc(err.message)}</p></div></div>`;
    }
    body.scrollTop = body.scrollHeight;
  };
  $("#btn-send").addEventListener("click", send);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  input.focus();
}

/* ----------------------------------------------------------- monitoring */

async function viewMonitoring() {
  const [runs, tasks] = await Promise.all([api("/api/runs"), api("/api/tasks")]);
  const agents = BOOT.studios.flatMap(s => s.agents);
  const done = runs.filter(r => r.status === "selesai").length;
  const active = runs.filter(r => r.status === "berjalan").length +
                 tasks.filter(t => t.status === "berjalan").length;
  view.innerHTML = `
    <h2 class="page-title">📈 Monitoring Semua Data</h2>
    <div class="page-desc">Kondisi perusahaan secara real-time — studio, karyawan, dan pekerjaan yang berjalan.</div>
    <div class="grid cols-4" style="margin-bottom:18px">
      <div class="card stat"><div class="big">${BOOT.studios.length}</div><div class="lbl">Studio</div></div>
      <div class="card stat"><div class="big">${agents.length}</div><div class="lbl">Karyawan AI</div></div>
      <div class="card stat"><div class="big">${done}</div><div class="lbl">Run Selesai</div></div>
      <div class="card stat"><div class="big">${active}</div><div class="lbl">Sedang Berjalan</div></div>
    </div>
    <div class="card" style="margin-bottom:16px">
      <h3>Workflow Run Terakhir</h3>
      ${runs.length ? `<table class="tbl"><tr><th>#</th><th>Workflow</th><th>Status</th><th>Mulai</th></tr>
        ${runs.slice(0, 8).map(r => `<tr class="clickable" data-run="${r.id}">
          <td>${r.id}</td><td>${esc(r.title)}</td><td>${statusPill(r.status)}</td>
          <td>${fmtTime(r.started_at)}</td></tr>`).join("")}</table>`
        : `<div class="empty">Belum ada run. Jalankan workflow dari menu Alur (Kantor) atau lewat Terminal.</div>`}
    </div>
    <div class="card">
      <h3>Tugas Individu Terakhir</h3>
      ${tasks.length ? `<table class="tbl"><tr><th>#</th><th>Tugas</th><th>Karyawan</th><th>Status</th></tr>
        ${tasks.slice(0, 8).map(t => `<tr><td>${t.id}</td><td>${esc(t.title)}</td>
          <td>${esc(t.agent_name || "-")}</td><td>${statusPill(t.status)}</td></tr>`).join("")}</table>`
        : `<div class="empty">Belum ada tugas individu.</div>`}
    </div>`;
  view.querySelectorAll("[data-run]").forEach(el =>
    el.addEventListener("click", () => { go("laporan"); }));
}

/* ------------------------------------------------------------ workflows */

async function viewWorkflows() {
  view.innerHTML = `
    <div class="page-head">
      <div class="grow">
        <h2 class="page-title">🗺️ Alur Kantor — Workflow</h2>
        <div class="page-desc">Pipeline kerja antar-karyawan: output satu step menjadi konteks step berikutnya.
        Tambahkan workflow baru sesuai kebutuhan perusahaan.</div>
      </div>
      <button class="btn btn-primary" id="btn-new-wf">+ Buat Workflow</button>
    </div>
    <div class="grid cols-3" id="wf-grid"></div>`;

  const grid = $("#wf-grid");
  grid.innerHTML = BOOT.workflows.map(wf => `
    <div class="card">
      <h3>${esc(wf.name)}</h3>
      <div class="muted">${esc(wf.description)}</div>
      <ol style="margin:10px 0 0 20px; font-size:12.5px; color:var(--text-dim)">
        ${wf.steps.map(st => `<li>${esc(st.title)} — <span style="color:var(--cyan)">${esc(st.agent_name || "?")}</span></li>`).join("")}
      </ol>
      <div class="row">
        <button class="btn btn-primary btn-sm" data-run="${wf.id}">▶ Jalankan</button>
        <button class="btn btn-sm" data-edit="${wf.id}">Edit</button>
        <button class="btn btn-sm btn-danger" data-del="${wf.id}">Hapus</button>
      </div>
    </div>`).join("") || `<div class="empty">Belum ada workflow.</div>`;

  $("#btn-new-wf").addEventListener("click", () => workflowModal(null));
  grid.querySelectorAll("[data-run]").forEach(el =>
    el.addEventListener("click", () => runBriefModal(Number(el.dataset.run))));
  grid.querySelectorAll("[data-edit]").forEach(el =>
    el.addEventListener("click", () =>
      workflowModal(BOOT.workflows.find(w => w.id === Number(el.dataset.edit)))));
  grid.querySelectorAll("[data-del]").forEach(el =>
    el.addEventListener("click", async () => {
      if (!confirm("Hapus workflow ini?")) return;
      await api(`/api/workflows/${el.dataset.del}`, { method: "DELETE" });
      await reloadBoot(); viewWorkflows();
    }));
}

function agentOptions(selectedId) {
  return BOOT.studios.flatMap(s => s.agents.map(a =>
    `<option value="${a.id}" ${a.id === selectedId ? "selected" : ""}>${esc(a.name)} — ${esc(a.role)}</option>`
  )).join("");
}

function workflowModal(wf) {
  const steps = wf ? wf.steps : [{ title: "", agent_id: null, instruction: "", expected_output: "" }];
  const stepHtml = (st, idx) => `
    <div class="step-box" data-step>
      <span class="step-num">STEP ${idx + 1}</span>
      <button class="btn btn-sm btn-danger rm" data-rm>✕</button>
      <div class="field"><label>Judul step</label><input data-f="title" value="${esc(st.title)}"></div>
      <div class="field"><label>Karyawan</label>
        <select data-f="agent_id"><option value="">(pilih)</option>${agentOptions(st.agent_id)}</select></div>
      <div class="field"><label>Instruksi</label><textarea data-f="instruction">${esc(st.instruction)}</textarea></div>
      <div class="field"><label>Output diharapkan</label><input data-f="expected_output" value="${esc(st.expected_output)}"></div>
    </div>`;
  const back = openModal(`
    <h3>${wf ? "Edit" : "Buat"} Workflow</h3>
    <div class="field"><label>Nama</label><input id="wf-name" value="${esc(wf?.name || "")}"></div>
    <div class="field"><label>Deskripsi</label><input id="wf-desc" value="${esc(wf?.description || "")}"></div>
    <div id="wf-steps">${steps.map(stepHtml).join("")}</div>
    <button class="btn btn-sm" id="wf-add-step">+ Tambah Step</button>
    <div class="actions">
      <button class="btn" data-close>Batal</button>
      <button class="btn btn-primary" id="wf-save">Simpan</button>
    </div>`);

  const bindRm = () => back.querySelectorAll("[data-rm]").forEach(b =>
    b.onclick = () => b.closest("[data-step]").remove());
  bindRm();
  $("#wf-add-step", back).addEventListener("click", () => {
    $("#wf-steps", back).insertAdjacentHTML("beforeend",
      stepHtml({ title: "", agent_id: null, instruction: "", expected_output: "" },
        back.querySelectorAll("[data-step]").length));
    bindRm();
  });
  back.querySelector("[data-close]").addEventListener("click", () => back.remove());
  $("#wf-save", back).addEventListener("click", async () => {
    const body = {
      name: $("#wf-name", back).value.trim(),
      description: $("#wf-desc", back).value.trim(),
      steps: [...back.querySelectorAll("[data-step]")].map(el => ({
        title: $('[data-f="title"]', el).value.trim(),
        agent_id: Number($('[data-f="agent_id"]', el).value) || null,
        instruction: $('[data-f="instruction"]', el).value.trim(),
        expected_output: $('[data-f="expected_output"]', el).value.trim(),
      })).filter(s => s.title && s.instruction),
    };
    if (!body.name || !body.steps.length) return toast("Nama dan minimal 1 step wajib diisi", true);
    try {
      if (wf) await api(`/api/workflows/${wf.id}`, { method: "PUT", body });
      else await api("/api/workflows", { method: "POST", body });
      back.remove(); await reloadBoot(); viewWorkflows();
      toast("Workflow tersimpan ✓");
    } catch (err) { toast(err.message, true); }
  });
}

function runBriefModal(wfId) {
  const wf = BOOT.workflows.find(w => w.id === wfId);
  const back = openModal(`
    <h3>▶ Jalankan: ${esc(wf.name)}</h3>
    <div class="field"><label>Brief / topik untuk tim</label>
      <textarea id="run-brief" placeholder="mis. Produk skincare lokal untuk Gen Z, budget iklan kecil..."></textarea></div>
    <div class="actions">
      <button class="btn" data-close>Batal</button>
      <button class="btn btn-primary" id="run-go">Mulai Kerjakan</button>
    </div>`);
  back.querySelector("[data-close]").addEventListener("click", () => back.remove());
  $("#run-go", back).addEventListener("click", async () => {
    const brief = $("#run-brief", back).value.trim();
    if (!brief) return toast("Brief wajib diisi", true);
    try {
      await api(`/api/workflows/${wfId}/run`, {
        method: "POST", body: { brief, model: currentModel() } });
      back.remove();
      toast(`Tim mulai mengerjakan "${wf.name}" — pantau di Ruang Laporan`);
      go("laporan");
    } catch (err) { toast(err.message, true); }
  });
}

/* --------------------------------------------------------------- studio */

async function viewStudio(studioId) {
  const st = BOOT.studios.find(s => s.id === studioId);
  if (!st) return go("terminal");
  view.innerHTML = `
    <div class="page-head">
      <div class="grow">
        <h2 class="page-title">${st.icon || "🏢"} ${esc(st.name)}</h2>
        <div class="page-desc">${esc(st.description)}${st.lead_name ? ` · Kepala: <b style="color:var(--cyan)">${esc(st.lead_name)}</b>` : ""}</div>
      </div>
      <button class="btn" id="btn-edit-studio">Edit Studio</button>
      <button class="btn btn-primary" id="btn-new-agent">+ Rekrut Karyawan</button>
    </div>
    <div class="grid cols-3">
      ${st.agents.map(a => `
        <div class="card">
          <h3>${a.is_lead ? "⭐ " : ""}${esc(a.name)}</h3>
          <div class="muted">${esc(a.role)}</div>
          <div class="muted" style="margin-top:6px">${esc(a.goal)}</div>
          ${a.model ? `<div style="margin-top:6px"><span class="pill cyan">${esc(a.model)}</span></div>` : ""}
          <div class="row">
            <button class="btn btn-primary btn-sm" data-assign="${a.id}">Tugaskan</button>
            <button class="btn btn-sm" data-edit="${a.id}">Edit</button>
            <button class="btn btn-sm btn-danger" data-del="${a.id}">Hapus</button>
          </div>
        </div>`).join("") || `<div class="empty">Belum ada karyawan di studio ini.</div>`}
    </div>`;

  $("#btn-new-agent").addEventListener("click", () => agentModal(null, studioId));
  $("#btn-edit-studio").addEventListener("click", () => studioModal(st));
  view.querySelectorAll("[data-assign]").forEach(el =>
    el.addEventListener("click", () => taskModal(Number(el.dataset.assign))));
  view.querySelectorAll("[data-edit]").forEach(el =>
    el.addEventListener("click", () =>
      agentModal(st.agents.find(a => a.id === Number(el.dataset.edit)), studioId)));
  view.querySelectorAll("[data-del]").forEach(el =>
    el.addEventListener("click", async () => {
      if (!confirm("Hapus karyawan ini?")) return;
      await api(`/api/agents/${el.dataset.del}`, { method: "DELETE" });
      await reloadBoot(); viewStudio(studioId);
    }));
}

function studioModal(st) {
  const back = openModal(`
    <h3>${st ? "Edit" : "Buat"} Studio</h3>
    <div class="field-row">
      <div class="field"><label>Nama</label><input id="st-name" value="${esc(st?.name || "")}"></div>
      <div class="field" style="max-width:90px"><label>Icon</label><input id="st-icon" value="${esc(st?.icon || "🏢")}"></div>
    </div>
    <div class="field"><label>Deskripsi</label><textarea id="st-desc">${esc(st?.description || "")}</textarea></div>
    <div class="actions">
      ${st ? `<button class="btn btn-danger" id="st-del">Hapus Studio</button>` : ""}
      <button class="btn" data-close>Batal</button>
      <button class="btn btn-primary" id="st-save">Simpan</button>
    </div>`);
  back.querySelector("[data-close]").addEventListener("click", () => back.remove());
  $("#st-save", back).addEventListener("click", async () => {
    const body = {
      name: $("#st-name", back).value.trim(),
      icon: $("#st-icon", back).value.trim() || "🏢",
      description: $("#st-desc", back).value.trim(),
    };
    if (!body.name) return toast("Nama wajib diisi", true);
    try {
      if (st) await api(`/api/studios/${st.id}`, { method: "PUT", body });
      else await api("/api/studios", { method: "POST", body });
      back.remove(); await reloadBoot(); renderSidebar();
      if (st) viewStudio(st.id);
      toast("Studio tersimpan ✓");
    } catch (err) { toast(err.message, true); }
  });
  $("#st-del", back)?.addEventListener("click", async () => {
    if (!confirm("Hapus studio beserta strukturnya?")) return;
    await api(`/api/studios/${st.id}`, { method: "DELETE" });
    back.remove(); await reloadBoot(); go("terminal");
  });
}

function agentModal(agent, studioId) {
  const back = openModal(`
    <h3>${agent ? "Edit" : "Rekrut"} Karyawan AI</h3>
    <div class="field-row">
      <div class="field"><label>Nama</label><input id="ag-name" value="${esc(agent?.name || "")}"></div>
      <div class="field"><label>Peran / Jabatan</label><input id="ag-role" value="${esc(agent?.role || "")}"></div>
    </div>
    <div class="field"><label>Studio</label>
      <select id="ag-studio">${BOOT.studios.map(s =>
        `<option value="${s.id}" ${(agent?.studio_id ?? studioId) === s.id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}
      </select></div>
    <div class="field"><label>Goal</label><textarea id="ag-goal">${esc(agent?.goal || "")}</textarea></div>
    <div class="field"><label>Backstory (persona)</label><textarea id="ag-back">${esc(agent?.backstory || "")}</textarea></div>
    <div class="field-row">
      <div class="field"><label>Model khusus (opsional)</label>
        <select id="ag-model"><option value="">(ikut default)</option>
          ${BOOT.models.map(m => `<option value="${esc(m)}" ${agent?.model === m ? "selected" : ""}>${esc(m)}</option>`).join("")}
        </select></div>
      <div class="field"><label>Kepala studio?</label>
        <select id="ag-lead"><option value="0">Bukan</option>
          <option value="1" ${agent?.is_lead ? "selected" : ""}>Ya, kepala studio</option></select></div>
    </div>
    <div class="actions">
      <button class="btn" data-close>Batal</button>
      <button class="btn btn-primary" id="ag-save">Simpan</button>
    </div>`);
  back.querySelector("[data-close]").addEventListener("click", () => back.remove());
  $("#ag-save", back).addEventListener("click", async () => {
    const body = {
      name: $("#ag-name", back).value.trim(),
      role: $("#ag-role", back).value.trim(),
      studio_id: Number($("#ag-studio", back).value),
      goal: $("#ag-goal", back).value.trim(),
      backstory: $("#ag-back", back).value.trim(),
      model: $("#ag-model", back).value,
      is_lead: $("#ag-lead", back).value === "1",
    };
    if (!body.name || !body.role) return toast("Nama dan peran wajib diisi", true);
    try {
      if (agent) await api(`/api/agents/${agent.id}`, { method: "PUT", body });
      else await api("/api/agents", { method: "POST", body });
      back.remove(); await reloadBoot(); viewStudio(body.studio_id);
      toast(`${body.name} tersimpan ✓`);
    } catch (err) { toast(err.message, true); }
  });
}

function taskModal(agentId) {
  const agents = BOOT.studios.flatMap(s => s.agents);
  const back = openModal(`
    <h3>📌 Tugaskan Karyawan</h3>
    <div class="field"><label>Karyawan</label>
      <select id="tk-agent">${agents.map(a =>
        `<option value="${a.id}" ${a.id === agentId ? "selected" : ""}>${esc(a.name)} — ${esc(a.role)}</option>`).join("")}
      </select></div>
    <div class="field"><label>Judul tugas</label><input id="tk-title" placeholder="mis. Buat 10 ide hook video"></div>
    <div class="field"><label>Deskripsi / brief</label><textarea id="tk-desc"></textarea></div>
    <div class="actions">
      <button class="btn" data-close>Batal</button>
      <button class="btn btn-primary" id="tk-go">Kirim Tugas</button>
    </div>`);
  back.querySelector("[data-close]").addEventListener("click", () => back.remove());
  $("#tk-go", back).addEventListener("click", async () => {
    const body = {
      agent_id: Number($("#tk-agent", back).value),
      title: $("#tk-title", back).value.trim(),
      description: $("#tk-desc", back).value.trim(),
      model: currentModel(),
    };
    if (!body.title) return toast("Judul tugas wajib diisi", true);
    try {
      await api("/api/tasks", { method: "POST", body });
      back.remove();
      toast("Tugas dikirim — pantau di Ruang Laporan");
      go("laporan");
    } catch (err) { toast(err.message, true); }
  });
}

/* -------------------------------------------------------------- laporan */

let laporanTab = "runs";
let openRunId = null;

async function viewLaporan() {
  const [runs, tasks] = await Promise.all([api("/api/runs"), api("/api/tasks")]);
  view.innerHTML = `
    <h2 class="page-title">📋 Ruang Laporan</h2>
    <div class="page-desc">Hasil kerja tim: workflow run dan tugas individu. Halaman ini auto-refresh selama ada pekerjaan berjalan.</div>
    <div class="tabs">
      <div class="tab ${laporanTab === "runs" ? "active" : ""}" data-tab="runs">Workflow Runs (${runs.length})</div>
      <div class="tab ${laporanTab === "tasks" ? "active" : ""}" data-tab="tasks">Tugas Individu (${tasks.length})</div>
    </div>
    <div id="lap-body"></div>
    <div id="lap-detail"></div>`;

  view.querySelectorAll(".tab").forEach(el =>
    el.addEventListener("click", () => { laporanTab = el.dataset.tab; openRunId = null; viewLaporan(); }));

  const body = $("#lap-body");
  if (laporanTab === "runs") {
    body.innerHTML = runs.length ? `<div class="card"><table class="tbl">
      <tr><th>#</th><th>Workflow</th><th>Brief</th><th>Status</th><th>Mulai</th></tr>
      ${runs.map(r => `<tr class="clickable" data-run="${r.id}">
        <td>${r.id}</td><td>${esc(r.title)}</td>
        <td class="muted">${esc((r.input || "").slice(0, 60))}${(r.input || "").length > 60 ? "…" : ""}</td>
        <td>${statusPill(r.status)}</td><td>${fmtTime(r.started_at)}</td></tr>`).join("")}
      </table></div>` : `<div class="empty">Belum ada workflow run.</div>`;
    body.querySelectorAll("[data-run]").forEach(el =>
      el.addEventListener("click", () => { openRunId = Number(el.dataset.run); renderRunDetail(); }));
    if (openRunId) renderRunDetail();
  } else {
    body.innerHTML = tasks.length ? tasks.map(t => `
      <div class="run-step">
        <div class="rs-head" data-task="${t.id}">
          <b>#${t.id}</b> ${esc(t.title)}
          <span class="pill cyan">${esc(t.agent_name || "-")}</span>
          <span style="margin-left:auto">${statusPill(t.status)}</span>
        </div>
        <div class="rs-body" style="display:none">${t.result ? md(t.result) : `<span class="muted">Belum ada hasil…</span>`}</div>
      </div>`).join("") : `<div class="empty">Belum ada tugas individu.</div>`;
    body.querySelectorAll(".rs-head").forEach(el =>
      el.addEventListener("click", () => {
        const b = el.nextElementSibling;
        b.style.display = b.style.display === "none" ? "block" : "none";
      }));
  }

  const anyActive = runs.some(r => r.status === "berjalan") || tasks.some(t => t.status === "berjalan");
  if (anyActive && !pollTimer) {
    pollTimer = setInterval(() => { if (activeKey === "laporan") viewLaporan(); }, 3000);
  } else if (!anyActive && pollTimer) {
    clearInterval(pollTimer); pollTimer = null;
  }
}

async function renderRunDetail() {
  if (!openRunId) return;
  const run = await api(`/api/runs/${openRunId}`);
  $("#lap-detail").innerHTML = `
    <div class="detail-panel">
      <div class="page-head" style="margin-bottom:8px">
        <div class="grow">
          <h3 style="color:#fff">Run #${run.id} — ${esc(run.title)} ${statusPill(run.status)}</h3>
          <div class="muted" style="margin-top:4px">Brief: ${esc(run.input)}</div>
        </div>
      </div>
      ${run.steps.map(st => `
        <div class="run-step">
          <div class="rs-head" data-rs>
            <span class="pill cyan">STEP ${st.position}</span>
            <b>${esc(st.title)}</b>
            <span class="muted">${esc(st.agent_name)}</span>
            <span style="margin-left:auto">${statusPill(st.status)}</span>
          </div>
          <div class="rs-body" style="display:${st.status === "selesai" && run.status !== "selesai" ? "none" : st.output ? "block" : "none"}">
            ${st.output ? md(st.output) : ""}
          </div>
        </div>`).join("")}
    </div>`;
  $("#lap-detail").querySelectorAll(".rs-head").forEach(el =>
    el.addEventListener("click", () => {
      const b = el.nextElementSibling;
      b.style.display = b.style.display === "none" ? "block" : "none";
    }));
}

/* ------------------------------------------------------------- settings */

async function viewSettings() {
  const s = await api("/api/settings");
  view.innerHTML = `
    <h2 class="page-title">⚙️ Pengaturan</h2>
    <div class="page-desc">Koneksi ke LLM gateway (OpenAI-compatible: adaCODE, OpenRouter, dll) dan identitas perusahaan.</div>
    <div class="card" style="max-width:620px">
      <div class="field"><label>Nama Perusahaan</label><input id="set-company" value="${esc(s.company_name)}"></div>
      <div class="field"><label>API Base URL</label><input id="set-base" value="${esc(s.api_base)}"></div>
      <div class="field"><label>API Key ${s.api_key_masked ? `<span class="pill green">terisi: ${esc(s.api_key_masked)}</span>` : `<span class="pill red">belum diisi</span>`}</label>
        <input id="set-key" type="password" placeholder="kosongkan jika tidak ingin mengubah"></div>
      <div class="field"><label>Model Default</label><input id="set-model" value="${esc(s.default_model)}"></div>
      <div class="field"><label>Daftar Model (pisahkan koma)</label><textarea id="set-models">${esc(s.models)}</textarea></div>
      <div class="actions" style="display:flex; justify-content:flex-end; gap:10px; margin-top:8px">
        <button class="btn btn-primary" id="set-save">Simpan Pengaturan</button>
      </div>
    </div>`;
  $("#set-save").addEventListener("click", async () => {
    const body = {
      company_name: $("#set-company").value.trim(),
      api_base: $("#set-base").value.trim(),
      default_model: $("#set-model").value.trim(),
      models: $("#set-models").value.trim(),
    };
    const key = $("#set-key").value.trim();
    if (key) body.api_key = key;
    try {
      await api("/api/settings", { method: "PUT", body });
      await reloadBoot(); renderSidebar();
      toast("Pengaturan tersimpan ✓");
    } catch (err) { toast(err.message, true); }
  });
}

/* ----------------------------------------------------------------- init */

async function reloadBoot() {
  BOOT = await api("/api/bootstrap");
}

(async function init() {
  try {
    await reloadBoot();
  } catch (err) {
    view.innerHTML = `<div class="empty">Gagal terhubung ke server: ${esc(err.message)}</div>`;
    $(".dot").classList.add("off");
    return;
  }
  $("#btn-tugaskan").addEventListener("click", () => taskModal(null));
  renderSidebar();
  go("terminal");
})();
