(() => {
  const $ = (id) => document.getElementById(id);
  const PAGE = 10; let offset = 0;

  const badge = (s) => `<span class="badge ${s === "completed" ? "ok" : s === "failed" ? "warn" : "off"}">${esc(s)}</span>`;

  async function loadStats() {
    const s = await api("/api/stats");
    $("stats").innerHTML = [["Images uploaded", s.total_images], ["Analyses completed", s.completed], ["Analyses failed", s.failed], ["Reports generated", s.reports]]
      .map(([l, n]) => `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
    const max = Math.max(1, ...Object.values(s.by_category));
    $("cats").innerHTML = Object.keys(s.by_category).length
      ? Object.entries(s.by_category).map(([k, v]) => `<div class="cat-row"><div class="top"><span>${esc(labelize(k))}</span><strong>${v}</strong></div><div class="bar"><i style="width:${(v / max) * 100}%"></i></div></div>`).join("")
        + `<p class="muted" style="font-size:.88rem;margin:0">${s.with_flagged_findings} with at least one label above threshold${s.avg_inference_ms ? `. Mean inference ${s.avg_inference_ms} ms.` : "."}</p>`
      : `<p class="muted">No completed analyses yet.</p>`;
  }

  async function loadModels() {
    const h = await api("/api/health");
    $("models").innerHTML = h.models.map((m) => `<div class="model-line"><span>${esc(labelize(m.category))}</span>${m.status === "operational" ? '<span class="badge ok">Operational</span>' : '<span class="badge off">Not integrated</span>'}</div>`).join("")
      + `<div class="model-line"><span>Database</span><span class="badge ${h.database === "up" ? "ok" : "warn"}">${esc(h.database)}</span></div>`;
  }

  const reportLink = (a) => a.status === "completed" ? `<a href="${API}/api/report/${esc(a.id)}" download>PDF</a>` : "-";

  async function loadHistory() {
    const d = await api(`/api/analyses?limit=${PAGE}&offset=${offset}`);
    $("history").innerHTML = d.items.length ? `<table class="history"><thead><tr><th>Date</th><th>Task</th><th>Status</th><th>Top-ranked label</th><th>Report</th></tr></thead><tbody>${d.items.map((a) => `<tr>
      <td>${fmtDate(a.created_at)}</td><td>${esc(labelize(a.category))}</td><td>${badge(a.status)}</td>
      <td>${a.status === "completed" ? `<a href="results.html?id=${esc(a.id)}">${esc(labelize(a.top_finding))}</a>` : '<span class="muted">-</span>'}</td><td>${reportLink(a)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty"><p>No analyses yet.</p><a class="btn btn-primary" href="upload.html">Upload your first scan</a></div>`;
    $("pager").innerHTML = d.total > PAGE ? `<button class="btn btn-ghost" id="prev" ${offset === 0 ? "disabled" : ""}>Previous</button><span>${offset + 1}-${Math.min(offset + PAGE, d.total)} of ${d.total}</span><button class="btn btn-ghost" id="next" ${offset + PAGE >= d.total ? "disabled" : ""}>Next</button>` : "";
    const p = $("prev"), n = $("next");
    if (p) p.onclick = () => { offset = Math.max(0, offset - PAGE); loadHistory().catch(showErr); };
    if (n) n.onclick = () => { offset += PAGE; loadHistory().catch(showErr); };
  }

  async function loadReports() {
    const d = await api("/api/analyses?limit=100");
    const r = d.items.filter((a) => a.has_report);
    $("reports").innerHTML = r.length ? `<table class="history"><thead><tr><th>Analysis</th><th>Task</th><th>Analysed</th><th>PDF</th></tr></thead><tbody>${r.map((a) => `<tr><td><a href="results.html?id=${esc(a.id)}">${esc(a.id.slice(0, 8))}</a></td><td>${esc(labelize(a.category))}</td><td>${fmtDate(a.completed_at)}</td><td>${reportLink(a)}</td></tr>`).join("")}</tbody></table>` : `<div class="empty">No reports generated yet. Open a result and choose Download PDF report.</div>`;
  }

  function showErr(e) { toast(e.message, 6000); }
  Promise.all([loadStats(), loadModels(), loadHistory(), loadReports()]).catch((e) => {
    $("history").innerHTML = `<div class="notice err" role="alert">${esc(e.message)}</div>`;
  });
})();
