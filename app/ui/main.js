// Cluster Job Runner web UI. Plain ES2020, no dependencies.
// Server-provided text only ever reaches the page as text nodes, never as HTML.
"use strict";

// ========== State ==========

const POLL_MS = 3000;
const FILTER_DEBOUNCE_MS = 400;

// [status, meaning], in legend order.
const STATUSES = [
  ["PENDING", "Waiting to start or retry"],
  ["RUNNING", "A pod is running"],
  ["SUCCEEDED", "Completed successfully"],
  ["FAILED", "Retry limit reached"],
  ["STUCK", "Image pull error or crash loop"],
  ["UNKNOWN", "Node lost contact"],
];
const SUMMARY_ORDER = ["SUCCEEDED", "RUNNING", "PENDING", "STUCK", "FAILED", "UNKNOWN"];

// Waiting reasons the backend counts as STUCK (mirrors app/services/status.py).
const STUCK_REASONS = new Set(["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "InvalidImageName"]);

const PRESETS = {
  ok: (rand) => ({ name: `hello-ok-${rand}`, namespace: "demo", image: "busybox:1.36", command: ["sh", "-c", "echo hello from k8s"] }),
  badImage: (rand) => ({ name: `bad-image-${rand}`, namespace: "demo", image: "doesnotexist/nope:1.0" }),
  exits1: (rand) => ({ name: `exits-1-${rand}`, namespace: "demo", image: "busybox:1.36", command: ["sh", "-c", "echo failing; exit 1"] }),
};

const CONN_LABELS = {
  connecting: "Connecting…",
  live: "Live",
  paused: "Paused",
  cluster: "Cluster unreachable",
  server: "Server unreachable",
  error: "Server error",
};

const state = {
  namespace: "",      // applied filter; "" means all namespaces
  jobs: [],           // last successful list response
  loaded: false,      // the list has loaded at least once
  stale: false,       // the last list poll failed, so `jobs` is old
  listSig: null,      // JSON of the rendered list, to skip identical re-renders
  listError: null,    // error shown in the banner
  conn: "connecting",
  lastOk: 0,          // time of the last successful list poll
  auto: true,
  timer: null,        // the single polling timeout
  inFlight: false,
  queued: false,      // a forced refresh arrived while a poll was in flight
  filterTimer: null,
  highlightKey: null, // row to flash after a create
  drawer: null,       // { name, namespace, focusId, job, error, sig }
};

const el = {};

// ========== API ==========

const enc = encodeURIComponent;
const jobKey = (ref) => `${ref.namespace}/${ref.name}`;
// Detail, delete and rerun must name the Job's namespace; the server assumes "default" otherwise.
const jobPath = (ref, suffix = "") => `/api/jobs/${enc(ref.name)}${suffix}?namespace=${enc(ref.namespace)}`;

function apiError(status, code, message, details) {
  return Object.assign(new Error(message), { status, code, details: details || [] });
}

// Every request goes through here. `body` is a raw JSON string and is sent untouched.
async function api(method, path, body) {
  const init = { method, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = body;
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch {
    throw apiError(0, "NETWORK", "Could not reach the server.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (res.ok) return data;
  const e = (data && data.error) || {};
  throw apiError(res.status, e.code || `HTTP_${res.status}`, e.message || res.statusText || "Request failed.", e.details);
}

// ========== Formatting ==========

// Accepts ISO 8601 (Job times), RFC 1123 (container state times) or a Date.
function toDate(value) {
  const d = value ? new Date(value) : null;
  return d && !isNaN(d) ? d : null;
}

function ago(ms) {
  const s = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (s < 2) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

const pad2 = (n) => String(n).padStart(2, "0");

function duration(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${pad2(s % 60)}s`;
  return `${Math.floor(m / 60)}h ${pad2(m % 60)}m`;
}

// Failed Jobs never get a completion_time; their Failed condition records when they ended.
function endTime(job) {
  const done = job.conditions.find((c) => (c.type === "Complete" || c.type === "Failed") && c.status === "True");
  return toDate(job.completion_time) || toDate(done && done.last_transition_time);
}

// Not-yet-started Jobs first, then newest start first.
function newestFirst(a, b) {
  const ta = a.start_time ? Date.parse(a.start_time) : Infinity;
  const tb = b.start_time ? Date.parse(b.start_time) : Infinity;
  return tb - ta || a.name.localeCompare(b.name);
}

// pydantic prefixes validator messages with "Value error, "; drop it for display.
const cleanMessage = (msg) => String(msg).replace(/^Value error, /, "");

function randomSuffix() {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) => chars[b % chars.length]).join("");
}

const presetText = (id) => JSON.stringify(PRESETS[id](randomSuffix()), null, 2);

// ========== Rendering ==========

// Element builder. String children become text nodes; null/false children are skipped.
function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.flat().filter((c) => c != null && c !== false));
  return node;
}

const code = (text) => h("code", null, text);
const muted = (text) => h("p", { class: "muted" }, text);
// Interleave " · " between the non-empty parts.
const joinDot = (parts) => parts.filter(Boolean).flatMap((p, i) => (i ? [" · ", p] : [p]));

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function badge(status) {
  return h("span", { class: `badge st-${status}` }, h("span", { class: "dot", "aria-hidden": "true" }), status);
}

// "3m ago" with the local time in `title`; tickClock() keeps the text current. Null if no date.
function timeAgo(value, prefix = "") {
  const d = toDate(value);
  if (!d) return null;
  return h("time", { datetime: d.toISOString(), title: d.toLocaleString(), dataset: { ago: d.getTime(), prefix } },
    prefix + ago(d.getTime()));
}

function when(value) {
  const d = toDate(value);
  return d ? [timeAgo(d), h("span", { class: "muted" }, ` · ${d.toLocaleString()}`)] : "—";
}

function durationNode(job) {
  const start = toDate(job.start_time);
  const end = endTime(job);
  if (start && end) return duration(end - start);
  if (start) return h("span", { dataset: { since: start.getTime() } }, `running ${duration(Date.now() - start)}`);
  return "—";
}

// Re-rendering replaces nodes; put focus back on the equivalent control so keyboard users keep their place.
function keepFocus(container, render) {
  const active = document.activeElement;
  const id = container.contains(active) && active.dataset.focus;
  render();
  if (id) (container.querySelector(`[data-focus="${CSS.escape(id)}"]`) || container).focus();
}

function renderConn() {
  const key = state.conn === "live" && !state.auto ? "paused" : state.conn;
  el.conn.dataset.state = key;
  setText(el.connLabel, CONN_LABELS[key]);
  setText(el.updated, state.lastOk ? `Updated ${ago(state.lastOk)}` : "");
}

// Display clock: refreshes relative times every second. It never fetches.
function tickClock() {
  const now = Date.now();
  for (const n of document.querySelectorAll("[data-ago]")) setText(n, n.dataset.prefix + ago(Number(n.dataset.ago)));
  for (const n of document.querySelectorAll("[data-since]")) setText(n, `running ${duration(now - Number(n.dataset.since))}`);
  renderConn();
}

function renderLegend() {
  el.legend.replaceChildren(...STATUSES.map(([status, meaning]) => h("li", null, badge(status), meaning)));
}

function renderBanner() {
  const err = state.listError;
  const sig = err ? `${err.code} ${err.message}` : "";
  if (el.banner.dataset.sig === sig) return; // avoid re-announcing the same error every poll
  el.banner.dataset.sig = sig;
  el.banner.replaceChildren(...(err ? [h("div", { class: "banner" }, code(err.code), h("span", null, err.message))] : []));
}

function renderSummary(jobs) {
  const counts = {};
  for (const job of jobs) counts[job.status] = (counts[job.status] || 0) + 1;
  const parts = SUMMARY_ORDER.filter((s) => counts[s]).map((s) => `${counts[s]} ${s.toLowerCase()}`);
  el.summary.textContent = jobs.length ? [`${jobs.length} ${jobs.length === 1 ? "job" : "jobs"}`, ...parts].join(" · ") : "";
}

function jobRow(job) {
  const key = jobKey(job);
  return h("tr", { class: key === state.highlightKey ? "flash" : null, onclick: () => openDrawer(job, `${key}|open`) },
    h("td", { class: "c-status" }, badge(job.status)),
    h("td", { class: "c-name" },
      h("button", { type: "button", class: "name-link", dataset: { focus: `${key}|open` } }, job.name),
      h("div", { class: "ns" }, job.namespace)),
    h("td", { class: "c-pods num", "data-label": "Pods a/s/f", title: "active · succeeded · failed" },
      `${job.active} · ${job.succeeded} · ${job.failed}`),
    h("td", { class: "c-started", "data-label": "Started" }, timeAgo(job.start_time) || "—"),
    h("td", { class: "c-duration", "data-label": "Duration" }, durationNode(job)),
    h("td", { class: "c-actions" },
      h("button", {
        type: "button", class: "btn-text", "aria-label": `Rerun ${job.name}`, dataset: { focus: `${key}|rerun` },
        onclick: (e) => { e.stopPropagation(); rerunJob(job, e.currentTarget); },
      }, "Rerun"),
      h("button", {
        type: "button", class: "btn-text danger", "aria-label": `Delete ${job.name}`, dataset: { focus: `${key}|delete` },
        onclick: (e) => { e.stopPropagation(); deleteJob(job, e.currentTarget); },
      }, "Delete")));
}

function renderList() {
  renderConn();
  renderBanner();
  el.loading.hidden = state.loaded || Boolean(state.listError);
  el.jobs.classList.toggle("is-stale", state.stale);
  const sig = JSON.stringify(state.jobs);
  if (!state.loaded || sig === state.listSig) return;
  state.listSig = sig;
  const jobs = [...state.jobs].sort(newestFirst);
  renderSummary(jobs);
  el.empty.hidden = jobs.length > 0;
  el.table.hidden = jobs.length === 0;
  keepFocus(el.jobs, () => el.rows.replaceChildren(...jobs.map(jobRow)));
  if (jobs.some((j) => jobKey(j) === state.highlightKey)) state.highlightKey = null;
}

const section = (label, ...body) => h("section", { class: "d-section" }, h("h3", { class: "label" }, label), ...body);
const fact = (term, ...value) => [h("dt", null, term), h("dd", null, ...value)];

// One-line summary of a container's state, plus the tone for its dot and an optional note.
function describeState(s) {
  const { running, waiting, terminated } = s || {};
  if (waiting) {
    return { tone: STUCK_REASONS.has(waiting.reason) ? "STUCK" : "PENDING", parts: ["Waiting", waiting.reason], note: waiting.message };
  }
  if (terminated) {
    return {
      tone: terminated.exit_code === 0 ? "SUCCEEDED" : "FAILED",
      parts: ["Terminated", terminated.reason, `exit ${terminated.exit_code}`,
        terminated.signal != null && `signal ${terminated.signal}`, timeAgo(terminated.finished_at, "finished ")],
      note: terminated.message,
    };
  }
  if (running) return { tone: "RUNNING", parts: ["Running", timeAgo(running.started_at, "since ")] };
  return { tone: "UNKNOWN", parts: ["No state reported yet"] };
}

function containerBlock(c) {
  const { tone, parts, note } = describeState(c.state);
  return h("div", { class: "ctr" },
    h("p", { class: "ctr-head" }, h("span", null, c.name), h("span", { class: "muted" }, c.image)),
    h("p", { class: `ctr-state st-${tone}` }, h("span", { class: "dot", "aria-hidden": "true" }), h("span", null, ...joinDot(parts))),
    note ? h("p", { class: "ctr-note" }, note) : null);
}

function podBlock(pod) {
  const restarts = `${pod.restart_count} restart${pod.restart_count === 1 ? "" : "s"}`;
  return h("article", { class: "pod" },
    h("div", { class: "pod-head" }, h("span", { class: "pod-name" }, pod.name), h("span", { class: "pod-phase" }, pod.phase || "Unknown")),
    h("p", { class: "pod-meta" }, joinDot([pod.node ? `Node ${pod.node}` : "Not scheduled yet", restarts])),
    pod.container_states.length ? pod.container_states.map(containerBlock) : h("p", { class: "ctr-note" }, "No container status yet"));
}

function conditionsTable(conditions) {
  const head = ["Type", "Status", "Reason", "Message", "Last transition"].map((t) => h("th", { scope: "col" }, t));
  return h("div", { class: "table-wrap" }, h("table", { class: "mini" },
    h("thead", null, h("tr", null, head)),
    h("tbody", null, conditions.map((c) => h("tr", null,
      h("td", null, c.type), h("td", null, c.status), h("td", null, c.reason || "—"),
      h("td", null, c.message || "—"), h("td", null, timeAgo(c.last_transition_time) || "—"))))));
}

function detailSections(job, rawOpen) {
  const end = endTime(job);
  return [
    section("Overview", h("dl", { class: "facts" },
      fact("Status", badge(job.status)),
      fact("Pods", `${job.active} active · ${job.succeeded} succeeded · ${job.failed} failed`),
      fact("Started", when(job.start_time)),
      fact("Completed", when(end)),
      fact("Duration", durationNode(job)))),
    section("Conditions", job.conditions.length ? conditionsTable(job.conditions) : muted("No conditions yet")),
    section("Pods", job.pods.length ? job.pods.map(podBlock) : muted("No pods yet")),
    h("details", { class: "d-section raw", open: rawOpen },
      h("summary", { class: "label", dataset: { focus: "raw" } }, "Raw JSON"),
      h("pre", null, JSON.stringify(job, null, 2))),
  ];
}

function renderDrawer() {
  const d = state.drawer;
  if (!d) return;
  const { job, error } = d;
  const gone = Boolean(error) && error.status === 404;
  el.dRerun.disabled = gone;
  el.dDelete.disabled = gone;
  const notice = gone ? "This Job no longer exists" : error ? `Couldn't refresh: ${error.code} · ${error.message}` : "";
  el.dNotice.hidden = !notice;
  setText(el.dNotice, notice);
  el.dBody.classList.toggle("is-stale", Boolean(error && job));

  // Rebuild only when the data changed, so open sections, selection and the pulse survive polls.
  const sig = job ? JSON.stringify(job) : error ? "error" : "loading";
  if (sig === d.sig) return;
  d.sig = sig;
  setText(el.dName, d.name);
  setText(el.dNamespace, d.namespace);
  setText(el.dUid, job ? job.uid : "");
  el.dBadge.replaceChildren(...(job ? [badge(job.status)] : []));
  const rawOpen = Boolean(el.dBody.querySelector("details[open]"));
  const scroll = el.dBody.scrollTop;
  const body = job ? detailSections(job, rawOpen) : error ? [] : [h("p", { class: "quiet" }, "Loading…")];
  keepFocus(el.dBody, () => el.dBody.replaceChildren(...body));
  el.dBody.scrollTop = scroll;
}

// ========== Actions ==========

async function rerunJob(ref, button) {
  button.disabled = true;
  try {
    const created = await api("POST", jobPath(ref, "/rerun"));
    toast(["Rerun started: ", code(created.name)], { action: { label: "Open", run: () => openDrawer(created) } });
    refreshNow();
  } catch (err) {
    errorToast(err);
  } finally {
    button.disabled = false;
    renderDrawer();
  }
}

async function deleteJob(ref, button) {
  if (!(await confirmDelete(ref))) return;
  button.disabled = true;
  try {
    await api("DELETE", jobPath(ref));
    toast(["Deleted ", code(ref.name)]);
    if (state.drawer && jobKey(state.drawer) === jobKey(ref)) closeDrawer();
    refreshNow();
  } catch (err) {
    errorToast(err);
  } finally {
    button.disabled = false;
    renderDrawer();
  }
}

async function submitCreate(event) {
  event.preventDefault();
  el.createSubmit.disabled = true;
  showCreateError(null);
  try {
    // Sent exactly as typed: the server's validation errors are the feedback.
    const created = await api("POST", "/api/jobs", el.spec.value);
    el.create.close();
    el.spec.value = presetText("ok");
    state.highlightKey = jobKey(created);
    toast(["Created ", code(created.name), ` · ${created.status}`]);
    refreshNow();
  } catch (err) {
    showCreateError(err);
  } finally {
    el.createSubmit.disabled = false;
  }
}

function applyFilter() {
  clearTimeout(state.filterTimer);
  const ns = el.ns.value.trim();
  if (ns === state.namespace) return;
  state.namespace = ns;
  refreshNow();
}

function setAuto(on) {
  state.auto = on;
  el.auto.setAttribute("aria-pressed", String(on));
  renderConn();
  if (on) refreshNow();
  else schedule();
}

// ========== Dialogs ==========

function openDrawer(ref, focusId) {
  const listed = state.jobs.find((j) => jobKey(j) === jobKey(ref));
  // Opening another Job from a toast keeps the original row as the focus return target.
  const returnTo = focusId || (state.drawer && state.drawer.focusId);
  state.drawer = { name: ref.name, namespace: ref.namespace, focusId: returnTo, job: listed || null, error: null, sig: null };
  el.dBody.replaceChildren();
  el.dBody.scrollTop = 0;
  renderDrawer();
  el.header.inert = true;
  el.main.inert = true;
  el.drawer.classList.add("open");
  el.backdrop.classList.add("open");
  el.dClose.focus();
  loadDetail();
}

function closeDrawer() {
  if (!state.drawer) return;
  const { focusId } = state.drawer;
  state.drawer = null;
  el.header.inert = false;
  el.main.inert = false;
  el.drawer.classList.remove("open");
  el.backdrop.classList.remove("open");
  const row = focusId && el.rows.querySelector(`[data-focus="${CSS.escape(focusId)}"]`);
  (row || el.jobs).focus();
}

const drawerRef = () => ({ name: state.drawer.name, namespace: state.drawer.namespace });

function confirmDelete(ref) {
  el.confirmText.replaceChildren("Delete ", code(ref.name), " in ", code(ref.namespace), "? Its pods will be removed too.");
  el.confirm.returnValue = "";
  el.confirm.showModal();
  return new Promise((resolve) => {
    el.confirm.addEventListener("close", () => resolve(el.confirm.returnValue === "delete"), { once: true });
  });
}

function openCreate() {
  showCreateError(null);
  el.create.showModal();
}

function showCreateError(err) {
  el.createError.hidden = !err;
  if (!err) {
    el.createError.replaceChildren();
    return;
  }
  el.createError.replaceChildren(
    h("p", null, code(err.code), " ", err.message),
    err.details.length ? h("ul", null, err.details.map((d) => h("li", null, code(d.field), " — ", cleanMessage(d.message)))) : "");
}

function toast(parts, { error = false, action = null } = {}) {
  const node = h("div", { class: error ? "toast toast-error" : "toast" }, h("p", null, ...parts));
  if (action) {
    node.append(h("button", { type: "button", class: "btn-text", onclick: () => { node.remove(); action.run(); } }, action.label));
  }
  el.toasts.append(node);
  setTimeout(() => node.remove(), error ? 6000 : 4000);
}

const errorToast = (err) => toast([code(err.code), " ", err.message], { error: true });

// ========== Polling ==========

async function loadList() {
  const ns = state.namespace;
  try {
    // An empty ?namespace= is a 400, so leave the parameter out to list every namespace.
    const jobs = await api("GET", ns ? `/api/jobs?namespace=${enc(ns)}` : "/api/jobs");
    if (ns !== state.namespace) return; // filter changed mid-flight; the queued poll fetches the new one
    Object.assign(state, { jobs, loaded: true, stale: false, listError: null, conn: "live", lastOk: Date.now() });
    el.nsError.hidden = true;
  } catch (err) {
    if (ns !== state.namespace) return;
    state.stale = true;
    if (err.status === 400 && ns) {
      // A bad filter is an input problem: explain it under the box, not in the banner.
      el.nsError.textContent = cleanMessage(err.details.length ? err.details[0].message : err.message);
      el.nsError.hidden = false;
      state.listError = null;
    } else {
      state.listError = err;
      state.conn = err.code === "NETWORK" ? "server" : err.code === "K8S_UNREACHABLE" ? "cluster" : "error";
    }
  }
  renderList();
}

async function loadDetail() {
  const d = state.drawer;
  if (!d) return;
  try {
    const job = await api("GET", jobPath(d));
    if (state.drawer !== d) return; // closed or switched mid-flight
    d.job = job;
    d.error = null;
  } catch (err) {
    if (state.drawer !== d) return;
    d.error = err;
  }
  renderDrawer();
}

async function poll(force) {
  if (state.inFlight) {
    if (force) state.queued = true; // run again as soon as the current poll finishes
    return;
  }
  state.inFlight = true;
  try {
    await Promise.all([loadList(), loadDetail()]);
  } finally {
    state.inFlight = false;
  }
  if (state.queued) {
    state.queued = false;
    await poll(false);
  }
}

// Re-arm the one polling timeout. Clearing first guarantees there is never a second loop.
function schedule() {
  clearTimeout(state.timer);
  state.timer = state.auto && !document.hidden ? setTimeout(tick, POLL_MS) : null;
}

async function tick() {
  try {
    await poll(false);
  } finally {
    schedule();
  }
}

// Poll right away (Refresh, filter change, after an action), then resume the normal cadence.
async function refreshNow() {
  clearTimeout(state.timer);
  try {
    await poll(true);
  } finally {
    schedule();
  }
}

function onVisibilityChange() {
  if (document.hidden || !state.auto) schedule();
  else refreshNow();
}

// ========== Init ==========

function init() {
  const $ = (id) => document.getElementById(id);
  Object.assign(el, {
    header: $("masthead"), main: $("main"), conn: $("conn"), connLabel: $("conn-label"), updated: $("conn-updated"),
    ns: $("ns-input"), nsError: $("ns-error"), refresh: $("refresh-btn"), auto: $("auto-btn"), newJob: $("new-btn"),
    legend: $("legend"), banner: $("banner"), summary: $("summary"),
    jobs: $("jobs"), loading: $("loading"), empty: $("empty"), table: $("job-table"), rows: $("job-rows"),
    backdrop: $("backdrop"), drawer: $("drawer"), dName: $("d-name"), dNamespace: $("d-namespace"),
    dBadge: $("d-badge"), dUid: $("d-uid"), dRerun: $("d-rerun"), dDelete: $("d-delete"), dClose: $("d-close"),
    dNotice: $("d-notice"), dBody: $("d-body"),
    confirm: $("confirm-dialog"), confirmText: $("confirm-text"),
    create: $("create-dialog"), createForm: $("create-form"), spec: $("spec-input"), createError: $("create-error"),
    createSubmit: $("create-submit"), createCancel: $("create-cancel"),
    toasts: $("toasts"),
  });

  el.ns.addEventListener("input", () => {
    clearTimeout(state.filterTimer);
    state.filterTimer = setTimeout(applyFilter, FILTER_DEBOUNCE_MS);
  });
  el.ns.addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilter();
  });
  el.refresh.addEventListener("click", () => refreshNow());
  el.auto.addEventListener("click", () => setAuto(!state.auto));
  el.newJob.addEventListener("click", openCreate);

  el.backdrop.addEventListener("click", closeDrawer);
  el.dClose.addEventListener("click", closeDrawer);
  el.dRerun.addEventListener("click", (e) => rerunJob(drawerRef(), e.currentTarget));
  el.dDelete.addEventListener("click", (e) => deleteJob(drawerRef(), e.currentTarget));
  document.addEventListener("keydown", (e) => {
    // A native <dialog> on top handles its own Esc.
    if (e.key === "Escape" && state.drawer && !document.querySelector("dialog[open]")) closeDrawer();
  });

  el.confirm.addEventListener("click", (e) => {
    if (e.target === el.confirm) el.confirm.close(); // backdrop click cancels
  });
  for (const button of el.create.querySelectorAll("[data-preset]")) {
    button.addEventListener("click", () => { el.spec.value = presetText(button.dataset.preset); });
  }
  el.createForm.addEventListener("submit", submitCreate);
  el.createCancel.addEventListener("click", () => el.create.close());
  document.addEventListener("visibilitychange", onVisibilityChange);

  renderLegend();
  el.spec.value = presetText("ok");
  setInterval(tickClock, 1000);
  refreshNow();
}

init();
