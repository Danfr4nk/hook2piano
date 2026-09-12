"use strict";
/* hook2piano web harness.
 * Flow: TheoryTab URL (or tab ID) -> section list -> Hooktheory project JSON
 * (direct fetch; api.hooktheory.com allows CORS *) -> hook2piano Python engine
 * running in Pyodide -> SONG structure -> VexFlow renderer (render.js).
 */

const API = "https://api.hooktheory.com/v1/songs/public/";
const FIELDS = "ID,xmlData,song,jsonData";
const PY_FILES = ["__init__.py", "fetch.py", "theory.py", "parse.py",
                  "render_text.py", "render_html.py", "cli.py"];

const $ = id => document.getElementById(id);
const statusEl = $("status"), chipsEl = $("chips"),
       scoreEl = $("score"), actionsEl = $("actions");

function setStatus(t) { statusEl.textContent = t || ""; }

/* ---------- input parsing ---------- */

function parseInput(raw) {
  const s = raw.trim();
  if (!s) return null;
  // bare tab id: no slashes/dots/spaces, e.g. nZgWr__wmry
  if (/^[A-Za-z0-9_-]{5,}$/.test(s) && !s.includes("/") && !s.includes(".")) {
    return { kind: "tab", tid: s };
  }
  // strip a possible tab- prefix pasted from page source
  const tm = s.match(/tab-([A-Za-z0-9_-]{5,})/);
  if (tm && !s.includes("/")) return { kind: "tab", tid: tm[1] };
  return { kind: "url", url: s.startsWith("http") ? s : "https://" + s };
}

/* ---------- section extraction (port of fetch.song_sections) ---------- */

function extractSections(html) {
  const divRe = /<div id="tab-([^"]+)">/g;
  const out = [];
  let m;
  while ((m = divRe.exec(html))) {
    const tid = m[1];
    const before = html.slice(Math.max(0, m.index - 3000), m.index);
    const texts = [...before.matchAll(/>([^<>]{1,60})</g)]
      .map(x => x[1].trim())
      .filter(t => t && !t.includes("Open In Hookpad"));
    let name = texts.length ? texts[texts.length - 1] : "Section " + (out.length + 1);
    if (name.includes("\u2013")) name = name.split("\u2013").pop().trim();
    else if (name.includes(" - ")) name = name.split(" - ").pop().trim();
    out.push({ name, tid });
  }
  if (!out.length) {
    const ids = [...html.matchAll(/TheoryTabs\("tab-([^"]+)"\)/g)].map(x => x[1]);
    ids.forEach((tid, i) => out.push({ name: "Section " + (i + 1), tid }));
  }
  // dedupe, keep order
  const seen = new Set();
  return out.filter(s => (seen.has(s.tid) ? false : (seen.add(s.tid), true)));
}

async function fetchViewHtml(url) {
  try {
    const r = await fetch(url);
    if (r.ok) {
      const t = await r.text();
      if (t.includes("TheoryTabs")) return t;
    }
  } catch (e) { /* CORS — fall through to proxies */ }
  const enc = encodeURIComponent(url);
  const proxies = [
    "https://api.allorigins.win/raw?url=" + enc,
    "https://corsproxy.io/?url=" + enc,
  ];
  for (const p of proxies) {
    try {
      const r = await fetch(p);
      if (r.ok) {
        const t = await r.text();
        if (t.includes("TheoryTabs")) return t;
      }
    } catch (e) { /* try next */ }
  }
  throw new Error("couldn't load that TheoryTab page (try a bare tab ID)");
}

/* ---------- project JSON (direct; api.hooktheory.com sends CORS *) ---------- */

async function fetchProject(tid) {
  const r = await fetch(API + encodeURIComponent(tid) + "?fields=" + FIELDS);
  if (!r.ok) throw new Error("tab not found (" + r.status + ")");
  const d = await r.json();
  const project = JSON.parse(d.jsonData);
  project._song_title = d.song || "";
  project._tab_id = tid;
  return project;
}

/* ---------- Pyodide + hook2piano engine ---------- */

let pyodide = null, pyReady = null;

async function ensurePy() {
  if (pyodide) return pyodide;
  if (pyReady) return pyReady;
  pyReady = (async () => {
    setStatus("loading python engine\u2026 (one-time, ~10 MB)");
    const py = await loadPyodide();
    await py.FS.mkdir("/h2p");
    await py.FS.mkdir("/h2p/hook2piano");
    for (const f of PY_FILES) {
      const r = await fetch("py/hook2piano/" + f);
      if (!r.ok) throw new Error("missing engine file: " + f);
      py.FS.writeFile("/h2p/hook2piano/" + f, await r.text());
    }
    py.runPython('import sys; sys.path.insert(0, "/h2p")\nimport hook2piano\nfrom hook2piano import parse, render_html\nimport json');
    pyodide = py;
    return py;
  })();
  return pyReady;
}

async function buildSong(sectionName, project) {
  const py = await ensurePy();
  py.globals.set("js_project", project);
  py.globals.set("js_section_name", sectionName);
  const json = py.runPython(
    'json.dumps(render_html.sections_to_js([parse.parse_section(js_section_name, js_project.to_py())]))'
  );
  return JSON.parse(json);
}

/* ---------- UI ---------- */

let sections = [];

function renderChips() {
  chipsEl.innerHTML = "";
  sections.forEach((s, i) => {
    const b = document.createElement("button");
    b.className = "ghost";
    b.textContent = s.name;
    b.onclick = () => selectSection(i);
    chipsEl.appendChild(b);
  });
}

async function selectSection(i) {
  const s = sections[i];
  [...chipsEl.children].forEach((b, j) => b.classList.toggle("active", j === i));
  setStatus("rendering " + s.name + "\u2026");
  try {
    const project = await fetchProject(s.tid);
    const song = await buildSong(s.name, project);
    window.H2P.renderSong(song, scoreEl);
    actionsEl.style.display = "flex";
    setStatus("");
  } catch (e) {
    setStatus("error: " + e.message);
  }
}

async function onLoad() {
  const parsed = parseInput($("url").value);
  if (!parsed) { setStatus("paste a TheoryTab URL or tab ID first"); return; }
  $("load").disabled = true;
  chipsEl.innerHTML = "";
  scoreEl.innerHTML = "";
  actionsEl.style.display = "none";
  try {
    if (parsed.kind === "tab") {
      sections = [{ name: "Tab", tid: parsed.tid }];
    } else {
      setStatus("reading TheoryTab page\u2026");
      const html = await fetchViewHtml(parsed.url);
      sections = extractSections(html);
      if (!sections.length) throw new Error("no tabs found on that page");
    }
    renderChips();
    setStatus(sections.length > 1 ? "pick a section" : "rendering\u2026");
    await selectSection(0);
  } catch (e) {
    setStatus("error: " + e.message);
  } finally {
    $("load").disabled = false;
  }
}

$("load").onclick = onLoad;
$("url").addEventListener("keydown", e => { if (e.key === "Enter") onLoad(); });
$("print").onclick = () => window.print();
