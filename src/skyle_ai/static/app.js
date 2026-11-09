const API = "/api/v1";
const state = { csvFile: null, forecastFile: null, visionFile: null, system: null, toastTimer: null };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function request(path, options = {}, retried = false) {
  const headers = new Headers(options.headers || {});
  const token = sessionStorage.getItem("skyle-api-key");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(options.body instanceof FormData) && options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let response;
  try { response = await fetch(`${API}${path}`, { ...options, headers }); }
  catch (error) { throw new Error(`Could not reach Skyle AI (${error.message}). Is the local service running?`); }
  if (response.status === 401 && !retried) {
    const newlySavedToken = sessionStorage.getItem("skyle-api-key");
    if (newlySavedToken && newlySavedToken !== token) return request(path, options, true);
    const entered = window.prompt("This workspace requires its shared API key. Enter it to continue:");
    if (!entered) throw new Error("A workspace key is required to use the protected API.");
    sessionStorage.setItem("skyle-api-key", entered);
    return request(path, options, true);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
  return body;
}
function formDataFile(file, name = "file") { const form = new FormData(); form.append(name, file); return form; }
function notify(message, isError = false) {
  const toast = $("#toast"); toast.textContent = message; toast.style.borderColor = isError ? "#86505a" : "#4e466b"; toast.classList.add("show");
  clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => toast.classList.remove("show"), 2900);
}
function setMessage(selector, text, error = false) { const node = $(selector); node.textContent = text; node.classList.toggle("error", error); }
function showView(name) {
  $$(".view").forEach(view => view.classList.toggle("hidden", view.id !== `view-${name}`));
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.view === name));
  const label = name === "text" ? "Text lab" : name === "data" ? "Data studio" : name === "vision" ? "Vision" : name === "forecast" ? "Forecasting" : name.charAt(0).toUpperCase() + name.slice(1);
  $("#current-crumb").textContent = label;
  window.location.hash = name;
  if (name === "activity") refreshActivity();
}
$$("[data-view]").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
$$("[data-open]").forEach(button => button.addEventListener("click", () => showView(button.dataset.open)));

async function refreshSystem() {
  try {
    const [system, docs, activity] = await Promise.all([request("/system"), request("/documents"), request("/activity?limit=30")]);
    state.system = system;
    $("#connection-label").textContent = "Connected locally";
    $("#version-label").textContent = `Version ${system.version}`;
    $("#stat-docs").textContent = docs.document_count;
    $("#stat-chunks").textContent = docs.chunk_count;
    $("#stat-runs").textContent = activity.events.length;
    $("#nav-doc-count").textContent = docs.document_count;
    $("#stat-llm").textContent = system.llm.configured ? "Connected" : "Disabled";
    $("#llm-foot").textContent = system.llm.configured ? `Endpoint enabled · ${system.llm.model || "configured model"}` : "Optional and disabled by default";
    $("#llm-swatch").classList.toggle("off", !system.llm.configured);
    $$(".privacy-card .privacy-state").forEach(el => el.innerHTML = system.llm.configured ? '<span class="tiny-dot"></span> Configured endpoint' : '<span class="tiny-dot"></span> No external model');
    renderDocuments(docs.documents); renderActivity(activity.events);
  } catch (error) {
    $("#connection-label").textContent = "Service unavailable";
    notify(error.message, true);
  }
}
function renderDocuments(documents) {
  const root = $("#document-list"); root.replaceChildren();
  if (!documents.length) { root.innerHTML = '<div class="empty-state">No documents indexed yet. Load the fictional demo or add your own file.</div>'; return; }
  for (const doc of documents) {
    const row = document.createElement("div"); row.className = "document-item";
    const icon = document.createElement("span"); icon.className = "doc-icon"; icon.textContent = doc.filename.split(".").pop().toUpperCase().slice(0, 4);
    const meta = document.createElement("span"); meta.className = "document-meta";
    const title = document.createElement("strong"); title.textContent = doc.filename;
    const sub = document.createElement("small"); sub.textContent = `${doc.chunk_count} passages · ${doc.source === "synthetic_demo" ? "fictional demo" : formatBytes(doc.size_bytes)}`;
    meta.append(title, sub);
    const del = document.createElement("button"); del.className = "delete-doc"; del.type = "button"; del.textContent = "×"; del.setAttribute("aria-label", `Delete ${doc.filename}`);
    del.addEventListener("click", async () => { if (!window.confirm(`Delete ${doc.filename} and its indexed passages?`)) return; try { await request(`/documents/${doc.id}`, { method: "DELETE" }); await refreshSystem(); notify("Document removed from the local index."); } catch (e) { notify(e.message, true); } });
    row.append(icon, meta, del); root.append(row);
  }
}
function formatBytes(bytes) { if (!bytes) return "0 B"; const units = ["B", "KB", "MB"]; const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), 2); return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`; }
function renderSources(sources, parent) {
  if (!sources?.length) return;
  const label = document.createElement("div"); label.className = "result-meta"; label.textContent = `${sources.length} cited source passage${sources.length === 1 ? "" : "s"}`; parent.append(label);
  for (const source of sources) {
    const card = document.createElement("div"); card.className = "source-card";
    const title = document.createElement("strong"); title.textContent = `[${source.citation_id}] ${source.filename}${source.page ? ` · page ${source.page}` : ""}`;
    const content = document.createElement("p"); content.textContent = source.text;
    card.append(title, content); parent.append(card);
  }
}
function resultCard(titleText, text, meta = "") { const card = document.createElement("div"); card.className = "result-card"; if (meta) { const m = document.createElement("div"); m.className = "result-meta"; m.textContent = meta; card.append(m); } const title = document.createElement("h3"); title.textContent = titleText; const p = document.createElement("p"); p.textContent = text; card.append(title, p); return card; }

$("#doc-files").addEventListener("change", e => { const files = [...e.target.files]; setMessage("#upload-message", files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected · no original bytes are saved.` : ""); });
$("#upload-docs").addEventListener("click", async () => {
  const files = [...$("#doc-files").files]; if (!files.length) return setMessage("#upload-message", "Select at least one supported file first.", true);
  const form = new FormData(); files.forEach(file => form.append("files", file));
  try { const result = await request("/documents/upload", { method: "POST", body: form }); const errors = result.results.filter(r => r.status === "error"); setMessage("#upload-message", errors.length ? `${result.results.length - errors.length} indexed; ${errors.length} need attention. ${errors[0].error}` : `${result.results.length} file(s) processed successfully.`); $("#doc-files").value = ""; await refreshSystem(); }
  catch (error) { setMessage("#upload-message", error.message, true); }
});
$("#load-demo").addEventListener("click", async () => { try { const result = await request("/demo/load", { method: "POST" }); setMessage("#upload-message", `Fictional demo loaded. ${result.document_count} document(s), ${result.chunk_count} passages in your local index.`); await refreshSystem(); } catch (e) { setMessage("#upload-message", e.message, true); } });
$("#clear-docs").addEventListener("click", async () => { if (!window.confirm("Clear every document and passage in this local workspace?")) return; try { await request("/documents", { method: "DELETE" }); $("#ask-result").replaceChildren(); await refreshSystem(); setMessage("#upload-message", "Local document index cleared."); } catch (e) { setMessage("#upload-message", e.message, true); } });
$("#ask-form").addEventListener("submit", async e => { e.preventDefault(); const root = $("#ask-result"); root.replaceChildren(resultCard("Searching…", "Looking through local text passages.")); try { const result = await request("/ask", { method: "POST", body: JSON.stringify({ question: $("#question").value, top_k: 4 }) }); root.replaceChildren(); root.append(resultCard("Workspace answer", result.answer, `${result.mode} · ${result.external_llm_used ? "external LLM used" : "no external LLM call"}`)); renderSources(result.sources, root); result.warnings?.forEach(w => root.append(resultCard("LLM fallback", w))); await refreshActivity(); } catch (error) { root.replaceChildren(resultCard("Request failed", error.message)); } });
$("#chat-form").addEventListener("submit", async e => { e.preventDefault(); const root = $("#chat-result"); root.replaceChildren(resultCard("Routing…", "Checking the available local tools.")); try { const result = await request("/chat", { method: "POST", body: JSON.stringify({ question: $("#chat-question").value, mode: $("#chat-mode").value }) }); root.replaceChildren(); root.append(resultCard(`Route · ${result.route}`, result.answer, `${result.mode} · ${result.route_reason}`)); renderSources(result.sources, root); const plan = result.plan.map(step => `${step.step}. ${step.tool} — ${step.status}`).join("\n"); root.append(resultCard("Tool trace", plan, "Deterministic, inspectable plan")); await refreshActivity(); } catch (error) { root.replaceChildren(resultCard("Request failed", error.message)); } });

$("#text-input").addEventListener("input", e => { $("#text-count").textContent = `${e.target.value.length.toLocaleString()} characters · processed locally`; });
$("#text-sample").addEventListener("click", () => { $("#text-input").value = "The new service is helpful and reliable. The first launch was not great, but the team fixed the problem quickly. Contact Skyle Lab on 2026-11-03 at https://example.test."; $("#text-count").textContent = `${$("#text-input").value.length} characters · processed locally`; });
$("#analyze-text").addEventListener("click", async () => { const text = $("#text-input").value; if (!text.trim()) return notify("Enter text to analyze.", true); const root = $("#text-result"); root.innerHTML = '<div class="result-placeholder"><h2>Analyzing locally…</h2></div>'; try { const data = await request("/analyze/text", { method: "POST", body: JSON.stringify({ text }) }); renderTextResult(data); await refreshActivity(); } catch (e) { root.replaceChildren(resultCard("Analysis failed", e.message)); } });
function renderTextResult(data) {
  const root = $("#text-result"); root.replaceChildren(); root.className = "panel result-panel";
  const head = document.createElement("div"); head.className = "panel-head"; const h = document.createElement("h2"); h.textContent = "Local analysis"; const badge = document.createElement("span"); badge.className = "local-badge"; badge.textContent = data.sentiment.label.toUpperCase(); head.append(h, badge); root.append(head);
  const grid = document.createElement("div"); grid.className = "csv-stat-grid"; [["Language hint", data.language_hint], ["Word count", data.token_count], ["Sentences", data.sentence_count], ["Sentiment score", data.sentiment.score]].forEach(([label, value]) => { const card = document.createElement("div"); card.className = "csv-mini-stat"; const l = document.createElement("span"); l.textContent = label; const v = document.createElement("strong"); v.textContent = value; card.append(l, v); grid.append(card); }); root.append(grid);
  root.append(resultCard("Matched sentiment terms", data.sentiment.matched_terms.length ? data.sentiment.matched_terms.map(x => `${x.term} (${x.polarity})`).join(" · ") : "No lexicon terms matched; neutral/unknown is not proof of objective neutrality."));
  root.append(resultCard("Pattern-based entities", data.entities.length ? data.entities.map(x => `${x.type}: ${x.text}`).join("\n") : "No supported patterns found. Capitalized phrases are not verified named entities."));
  root.append(resultCard("Frequent terms", data.keywords.map(x => `${x.term} (${x.count})`).join(" · ") || "No keywords found."));
  const note = document.createElement("div"); note.className = "result-meta"; note.textContent = data.method; root.append(note);
}

$("#csv-file").addEventListener("change", e => { state.csvFile = e.target.files[0] || null; $("#csv-file-label").textContent = state.csvFile?.name || "Choose a CSV file"; $("#profile-csv").disabled = !state.csvFile; setMessage("#csv-message", state.csvFile ? `${formatBytes(state.csvFile.size)} · processed in memory, not saved.` : ""); });
$("#profile-csv").addEventListener("click", async () => { if (!state.csvFile) return; setMessage("#csv-message", "Profiling locally…"); try { const data = await request("/analyze/csv", { method: "POST", body: formDataFile(state.csvFile) }); renderCSV(data); setMessage("#csv-message", `Profile complete · ${data.rows.toLocaleString()} rows and ${data.columns} columns.`); await refreshActivity(); } catch (e) { setMessage("#csv-message", e.message, true); } });
function renderCSV(data) {
  const root = $("#csv-result"); root.classList.remove("hidden"); root.replaceChildren();
  const panel = document.createElement("div"); panel.className = "panel"; const head = document.createElement("div"); head.className = "panel-head"; const title = document.createElement("h2"); title.textContent = data.filename; const badge = document.createElement("span"); badge.className = "local-badge"; badge.textContent = "IN-MEMORY PROFILE"; head.append(title, badge); panel.append(head);
  const stats = document.createElement("div"); stats.className = "csv-stat-grid"; [["Rows", data.rows], ["Columns", data.columns], ["Duplicate rows", data.duplicate_rows], ["Approx. memory", formatBytes(data.memory_bytes_estimate)]].forEach(([label, value]) => { const card = document.createElement("div"); card.className = "csv-mini-stat"; const l = document.createElement("span"); l.textContent = label; const v = document.createElement("strong"); v.textContent = value; card.append(l, v); stats.append(card); }); panel.append(stats);
  const wrap = document.createElement("div"); wrap.className = "table-wrap"; const table = document.createElement("table"); table.className = "profile-table"; table.innerHTML = "<thead><tr><th>Column</th><th>Type</th><th>Missing</th><th>Unique</th><th>Examples / numeric summary</th></tr></thead>"; const body = document.createElement("tbody");
  data.column_profile.forEach(col => { const row = document.createElement("tr"); [col.name, col.inferred_type, `${col.missing} (${col.missing_pct}%)`, col.unique, col.summary ? `mean ${col.summary.mean} · min ${col.summary.min} · median ${col.summary.median} · max ${col.summary.max}` : col.examples.join(", ")].forEach(value => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }); body.append(row); }); table.append(body); wrap.append(table); panel.append(wrap);
  if (data.strongest_numeric_correlations.length) panel.append(resultCard("Strongest Pearson correlations", data.strongest_numeric_correlations.map(c => `${c.left} ↔ ${c.right}: r=${c.pearson_r}`).join("\n"), "Descriptive association only · not causal")); root.append(panel);
  const numericCols = data.column_profile.filter(c => /int|float|double|number/i.test(c.inferred_type)); populateSelect($("#value-column"), numericCols.map(c => c.name), "Select value column"); populateSelect($("#date-column"), data.column_profile.map(c => c.name), "Use current row order", true); $("#value-column").disabled = numericCols.length === 0; $("#date-column").disabled = false;
}
function populateSelect(select, values, firstLabel, optional = false) { select.replaceChildren(); const first = document.createElement("option"); first.value = ""; first.textContent = firstLabel; select.append(first); for (const value of values) { const option = document.createElement("option"); option.value = value; option.textContent = value; select.append(option); } if (!optional && values.length) select.value = values[0]; }

$("#forecast-file").addEventListener("change", async e => { state.forecastFile = e.target.files[0] || null; $("#forecast-file-label").textContent = state.forecastFile?.name || "Choose a CSV file"; if (!state.forecastFile) return; try { const data = await request("/analyze/csv", { method: "POST", body: formDataFile(state.forecastFile) }); const numeric = data.column_profile.filter(c => /int|float|double|number/i.test(c.inferred_type)).map(c => c.name); populateSelect($("#value-column"), numeric, "Select value column"); populateSelect($("#date-column"), data.column_profile.map(c => c.name), "Use current row order", true); $("#value-column").disabled = !numeric.length; $("#date-column").disabled = false; $("#run-forecast").disabled = !numeric.length; setMessage("#forecast-message", `${data.rows} rows · choose a numeric series and optional date field.`); await refreshActivity(); } catch (error) { $("#run-forecast").disabled = true; setMessage("#forecast-message", error.message, true); } });
$("#run-forecast").addEventListener("click", async () => { if (!state.forecastFile || !$("#value-column").value) return; const form = new FormData(); form.append("file", state.forecastFile); form.append("value_column", $("#value-column").value); form.append("date_column", $("#date-column").value); form.append("horizon", $("#forecast-horizon").value); setMessage("#forecast-message", "Evaluating on a chronological holdout…"); try { const result = await request("/forecast", { method: "POST", body: form }); renderForecast(result); setMessage("#forecast-message", `Selected ${result.model_selected_on_holdout_mae} by holdout MAE.`); await refreshActivity(); } catch (e) { setMessage("#forecast-message", e.message, true); } });
function renderForecast(data) {
  const root = $("#forecast-result"); root.classList.remove("hidden"); root.replaceChildren(); const panel = document.createElement("div"); panel.className = "panel"; const head = document.createElement("div"); head.className = "panel-head"; const h = document.createElement("h2"); h.textContent = `Holdout comparison · ${data.observations} observations`; const badge = document.createElement("span"); badge.className = "local-badge"; badge.textContent = `SELECTED · ${data.model_selected_on_holdout_mae.replaceAll("_", " ").toUpperCase()}`; head.append(h, badge); panel.append(head);
  const grid = document.createElement("div"); grid.className = "forecast-result-grid"; for (const [key, label] of [["last_value_baseline", "Last-value baseline"], ["linear_trend", "Linear trend"]]) { const metric = data.holdout_metrics[key]; const card = document.createElement("div"); card.className = "forecast-metric"; const title = document.createElement("h3"); title.textContent = label; const val = document.createElement("div"); val.className = "forecast-value"; val.textContent = `MAE ${metric.mae}`; const detail = document.createElement("p"); detail.textContent = `RMSE ${metric.rmse} · holdout n=${data.holdout_metrics.holdout_observations}`; card.append(title, val, detail); grid.append(card); } panel.append(grid);
  const forecast = document.createElement("div"); forecast.className = "result-card"; const title = document.createElement("h3"); title.textContent = `Next ${data.forecast.length} steps · ${data.model_selected_on_holdout_mae.replaceAll("_", " ")}`; forecast.append(title); const chips = document.createElement("div"); chips.className = "forecast-series"; data.forecast.forEach(point => { const chip = document.createElement("span"); chip.className = "forecast-chip"; chip.textContent = `t+${point.step} · ${point.value}`; chips.append(chip); }); forecast.append(chips); panel.append(forecast); const note = document.createElement("div"); note.className = "result-meta"; note.textContent = data.notes.join(" "); panel.append(note); root.append(panel);
}

$("#image-file").addEventListener("change", e => { state.visionFile = e.target.files[0] || null; $("#inspect-image").disabled = !state.visionFile; const preview = $("#image-preview"); if (state.visionFile) { preview.src = URL.createObjectURL(state.visionFile); preview.classList.remove("hidden"); } else { preview.classList.add("hidden"); preview.removeAttribute("src"); } setMessage("#vision-message", state.visionFile ? `${formatBytes(state.visionFile.size)} · image bytes are processed in memory.` : ""); });
$("#inspect-image").addEventListener("click", async () => { if (!state.visionFile) return; const form = new FormData(); form.append("file", state.visionFile); form.append("question", $("#vision-question").value); setMessage("#vision-message", "Inspecting image properties locally…"); try { const result = await request("/vision", { method: "POST", body: form }); renderVision(result); setMessage("#vision-message", result.external_llm_used ? "An external multimodal endpoint was used; see the disclosure." : "Complete · no remote semantic vision model was used."); await refreshActivity(); } catch (e) { setMessage("#vision-message", e.message, true); } });
function renderVision(data) { const root = $("#vision-result"); root.replaceChildren(); const box = document.createElement("div"); box.className = "vision-result"; const head = document.createElement("div"); head.className = "panel-head"; const title = document.createElement("h2"); title.textContent = "Image properties"; const badge = document.createElement("span"); badge.className = "local-badge"; badge.textContent = data.external_llm_used ? "EXTERNAL LLM USED" : "LOCAL DIAGNOSTICS"; head.append(title, badge); box.append(head); const dl = document.createElement("dl"); [["File", data.filename], ["Format", data.format], ["Dimensions", `${data.width} × ${data.height} px`], ["Aspect ratio", data.aspect_ratio], ["Color mode", data.mode], ["Mean luminance", `${data.mean_luminance_0_255} / 255`], ["Contrast std. dev.", data.grayscale_contrast_stddev]].forEach(([label, val]) => { const dt = document.createElement("dt"); dt.textContent = label; const dd = document.createElement("dd"); dd.textContent = val; dl.append(dt, dd); }); box.append(dl); const paletteLabel = document.createElement("div"); paletteLabel.className = "result-meta"; paletteLabel.textContent = "Approximate dominant colors"; box.append(paletteLabel); const palette = document.createElement("div"); palette.className = "palette-row"; data.dominant_colors.forEach(color => { const swatch = document.createElement("span"); swatch.className = "color-swatch"; swatch.style.backgroundColor = color.hex; swatch.title = `${color.hex} · ${color.share_pct}%`; const label = document.createElement("small"); label.textContent = color.hex; swatch.append(label); palette.append(swatch); }); box.append(palette); if (data.semantic_description) box.append(resultCard("Configured model description", data.semantic_description, "External multimodal model · may be inaccurate")); if (data.llm_warning) box.append(resultCard("External model fallback", data.llm_warning)); box.append(resultCard("What this means", data.notes)); root.append(box); }

function renderActivity(events) { const root = $("#activity-list"); root.replaceChildren(); if (!events?.length) { root.innerHTML = '<div class="empty-state">No activity recorded yet. Tool run summaries appear here.</div>'; $("#stat-runs").textContent = "0"; return; } for (const event of events) { const row = document.createElement("div"); row.className = "activity-row"; const bullet = document.createElement("span"); bullet.className = "activity-bullet"; bullet.textContent = event.action.includes("forecast") ? "⌁" : event.action.includes("vision") ? "◉" : event.action.includes("csv") ? "▥" : event.action.includes("text") ? "Aa" : "◈"; const main = document.createElement("span"); main.className = "activity-main"; const title = document.createElement("strong"); title.textContent = event.action.replaceAll("_", " "); const details = document.createElement("small"); details.textContent = Object.entries(event.summary).map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`).join(" · ") || "Completed"; main.append(title, details); const status = document.createElement("span"); status.className = `activity-status ${event.status}`; status.textContent = event.status.replaceAll("_", " "); const time = document.createElement("span"); time.className = "activity-time"; time.textContent = new Date(event.happened_at).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); const duration = document.createElement("span"); duration.className = "activity-duration"; duration.textContent = `${event.duration_ms} ms`; row.append(bullet, main, status, time, duration); root.append(row); } $("#stat-runs").textContent = events.length; }
async function refreshActivity() { try { const data = await request("/activity?limit=30"); renderActivity(data.events); } catch (e) { if (e.message.includes("API key")) notify(e.message, true); } }
$("#refresh-activity").addEventListener("click", refreshActivity);

const initialView = window.location.hash.replace("#", "");
showView(["overview", "knowledge", "text", "data", "forecast", "vision", "activity"].includes(initialView) ? initialView : "overview");
refreshSystem();
