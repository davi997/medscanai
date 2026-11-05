(() => {
  const id = new URLSearchParams(location.search).get("id");
  const root = document.getElementById("content"), sub = document.getElementById("subtitle");
  const SHOW_DEFAULT = 5;

  function findingRow(f) {
    return `<div class="finding ${f.flagged ? "flag" : ""}">
      <span class="name">${esc(f.label.replace(/_/g, " "))}</span>
      <span class="bar" role="img" aria-label="Score ${f.score.toFixed(3)}, threshold ${f.threshold.toFixed(3)}"><i style="width:${Math.max(f.score * 100, 0.8)}%"></i><b style="left:${f.threshold * 100}%"></b></span>
      <span class="val">${f.score.toFixed(3)}</span></div>`;
  }

  function render(a) {
    const flagged = a.findings.filter((f) => f.flagged).length;
    const none = flagged === 0;
    sub.textContent = `${labelize(a.category)} - analysed ${fmtDate(a.completed_at)}`;
    const m = a.model || {};
    const hm = a.heatmap;
    root.innerHTML = `
    <div class="results-grid">
      <div>
        <div class="viewer">
          <div class="viewer-stage"><img id="vimg" src="${API}${esc(a.image.url)}" alt="Uploaded medical image"></div>
          <div class="viewer-bar"><span id="vcap">Original image</span>
            <span class="seg" role="group" aria-label="Image view"><button type="button" id="vOrig" aria-pressed="true">Original</button><button type="button" id="vCam" aria-pressed="false" ${hm ? "" : "disabled"}>Grad-CAM</button></span></div>
          <div class="viewer-note" id="vnote">${a.image.width} x ${a.image.height} px, ${esc(a.image.format)}.</div>
        </div>
      </div>
      <div class="panel">
        <div class="summary ${none ? "none" : ""}"><div><strong>${none ? "No label above its operating threshold" : `${flagged} of ${a.findings.length} labels above their operating threshold`}</strong>
          <p>${none ? "This does not show the image is normal: the model has no normal class and can miss findings." : "A flag is a screening-style signal from the model, not a finding of disease."}</p></div></div>
        <h2 style="font-size:1.15rem">Model scores</h2>
        <div id="findings">${a.findings.slice(0, SHOW_DEFAULT).map(findingRow).join("")}</div>
        ${a.findings.length > SHOW_DEFAULT ? `<button class="btn-link" id="moreBtn" type="button">Show all ${a.findings.length} labels</button>` : ""}
        <p class="legend"><b></b>Operating threshold published with the model. Bars show the raw score from 0 to 1; labels are ranked by score relative to their own threshold. Scores are <strong>not</strong> probabilities that a patient has a condition.</p>
        <div class="result-actions"><a class="btn btn-primary" href="${API}/api/report/${esc(a.id)}" download>Download PDF report</a><a class="btn btn-ghost" href="upload.html">Analyze another image</a></div>
      </div>
    </div>
    <div class="panel info-grid">
      <div><h3>Model information</h3><ul class="plain">
        <li><strong>Model:</strong> ${esc(m.display_name)}</li><li><strong>Source:</strong> ${esc(m.source)}</li>
        <li><strong>Reference:</strong> ${esc(m.reference)}</li><li><strong>Licence:</strong> ${esc(m.license)}</li>
        <li><strong>Result type:</strong> real model inference${a.inference_ms ? `, ${a.inference_ms} ms` : ""}</li><li><strong>Analysis ID:</strong> ${esc(a.id)}</li></ul></div>
      <div><h3>Limitations</h3><ul class="plain">${(m.limitations || []).map((l) => `<li>${esc(l)}</li>`).join("")}${(a.warnings || []).map((l) => `<li><strong>Note:</strong> ${esc(l)}</li>`).join("")}</ul></div>
    </div>
    <div class="notice warn disclaimer"><strong>Medical disclaimer.</strong> This AI-generated result is intended for research and educational assistance only. It is not a definitive medical diagnosis and must be reviewed by a qualified medical professional.</div>`;

    const more = document.getElementById("moreBtn");
    if (more) more.addEventListener("click", () => {
      const open = more.dataset.open !== "1";
      document.getElementById("findings").innerHTML = (open ? a.findings : a.findings.slice(0, SHOW_DEFAULT)).map(findingRow).join("");
      more.dataset.open = open ? "1" : "0"; more.textContent = open ? "Show top 5 only" : `Show all ${a.findings.length} labels`;
    });
    const img = document.getElementById("vimg"), o = document.getElementById("vOrig"), c = document.getElementById("vCam");
    const setView = (cam) => {
      img.src = API + (cam ? hm.url : a.image.url);
      o.setAttribute("aria-pressed", !cam); c.setAttribute("aria-pressed", cam);
      document.getElementById("vcap").textContent = cam ? `Grad-CAM: ${hm.label.replace(/_/g, " ")}` : "Original image";
      document.getElementById("vnote").textContent = cam
        ? "Warm colours mark regions that most increased the network's score for this label. This is the centre-cropped 224 x 224 view the model saw. It shows where the model looked, not a confirmed lesion."
        : `${a.image.width} x ${a.image.height} px, ${a.image.format}.`;
    };
    o.onclick = () => setView(false); if (hm) c.onclick = () => setView(true);
  }

  (async () => {
    if (!id) { root.innerHTML = `<div class="notice err">No analysis selected. <a href="dashboard.html">Open the dashboard</a> or <a href="upload.html">upload an image</a>.</div>`; return; }
    try {
      const a = await api(`/api/analysis/${encodeURIComponent(id)}`);
      if (a.status !== "completed") {
        root.innerHTML = `<div class="notice err"><strong>No results available.</strong> ${esc(a.error || "This analysis did not complete.")}</div>`; sub.textContent = "Analysis did not complete"; return;
      }
      render(a);
    } catch (e) { root.innerHTML = `<div class="notice err" role="alert">${esc(e.message)}</div>`; sub.textContent = "Error"; }
  })();
})();
