const state = { baseUrl: localStorage.getItem("ronin.url") || "http://127.0.0.1:8080", token: sessionStorage.getItem("ronin.token") || "", currentJobId: null };
const $ = (id) => document.getElementById(id);
const notice = (message, error = false) => { $("notice").textContent = message; $("notice").hidden = !message; $("notice").dataset.error = error; };
async function request(path, options = {}) {
  const response = await fetch(`${state.baseUrl.replace(/\/$/, "")}${path}`, { ...options, headers: { Accept: "application/json", ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}), ...(options.headers || {}) } });
  const payload = await response.json().catch(() => null);
  if (!response.ok) { const error = new Error(payload?.error?.message || payload?.message || `Request failed (${response.status})`); error.status = response.status; error.code = payload?.error?.code; throw error; }
  return payload;
}
function renderRuns(page) {
  const root = $("runs"); root.replaceChildren();
  if (!page?.items?.length) { root.innerHTML = '<div class="empty">No runs match the current authorization scope.</div>'; return; }
  for (const job of page.items) {
    const card = document.createElement("article"); card.className = "card";
    const summary = document.createElement("div");
    const id = document.createElement("strong"); id.textContent = job.id;
    const failure = document.createElement("div"); failure.className = "muted"; failure.textContent = job.failure_code || "No failure";
    summary.append(id, failure);
    const state = document.createElement("span"); state.className = "state"; state.textContent = job.state;
    card.append(summary, state); card.onclick = () => showDetails(job.id); root.append(card);
  }
}
async function loadRuns() { try { notice("Loading runs…"); renderRuns(await request("/v1/jobs?limit=50")); notice(""); } catch (error) { notice(error.status === 403 ? "Forbidden: your grant does not permit listing these projects." : error.message, true); } }
async function showDetails(id) { try { notice("Loading run details…"); const [status, events, evidence] = await Promise.all([request(`/v1/jobs/${encodeURIComponent(id)}`), request(`/v1/jobs/${encodeURIComponent(id)}/events?limit=100`), request(`/v1/jobs/${encodeURIComponent(id)}/evidence`)]); state.currentJobId = id; $("detail-title").textContent = id; $("status").textContent = JSON.stringify(status, null, 2); $("events").textContent = JSON.stringify(events, null, 2); $("evidence").textContent = JSON.stringify(evidence, null, 2); $("cancel").disabled = ["succeeded", "failed", "cancelled"].includes(status.state); $("cancel").onclick = () => cancelRun(id); $("runs-view").hidden = true; $("details-view").hidden = false; notice(""); } catch (error) { notice(error.status === 403 ? "Forbidden: evidence or event access is not granted." : error.message, true); } }
async function cancelRun(id) { if (!window.confirm(`Cancel run ${id}?`)) return; try { notice("Cancelling run…"); await request(`/v1/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }); await showDetails(id); notice("Run cancellation requested."); } catch (error) { notice(error.status === 403 ? "Forbidden: your grant does not permit cancellation." : error.message, true); } }
$("connection-form").onsubmit = (event) => { event.preventDefault(); state.baseUrl = $("api-url").value; state.token = $("api-token").value; localStorage.setItem("ronin.url", state.baseUrl); sessionStorage.setItem("ronin.token", state.token); loadRuns(); };
$("api-url").value = state.baseUrl; $("api-token").value = state.token; $("refresh").onclick = loadRuns; $("back").onclick = () => { $("details-view").hidden = true; $("runs-view").hidden = false; }; loadRuns();
for (const button of document.querySelectorAll(".nav")) button.onclick = () => { document.querySelectorAll(".nav").forEach((item) => item.classList.toggle("active", item === button)); if (button.dataset.view === "sql") { $("runs-view").hidden = true; $("details-view").hidden = true; $("sql-view").hidden = false; return; } if (!state.currentJobId) { notice(`Select a run to view ${button.dataset.view}.`, true); return; } $("details-view").hidden = false; $("runs-view").hidden = true; $("sql-view").hidden = true; $(button.dataset.view === "evidence" ? "evidence" : "events").scrollIntoView({ behavior: "smooth", block: "start" }); };
$("sql-form").onsubmit = async (event) => { event.preventDefault(); try { notice("Running query…"); const payload = await request("/v1/sql", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project: $("sql-project").value, sql: $("sql-text").value, max_rows: 1000 }) }); $("sql-result").textContent = JSON.stringify(payload, null, 2); notice(""); } catch (error) { $("sql-result").textContent = error.status === 404 ? "SQL engine is not configured for this deployment." : error.message; notice(error.message, true); } };
