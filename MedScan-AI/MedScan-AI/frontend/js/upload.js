(() => {
  const $ = (id) => document.getElementById(id);
  const drop = $("dropzone"), input = $("fileInput"), preview = $("preview"), msg = $("formMsg");
  let categories = [], selected = null, file = null, objectUrl = null, maxMb = 15;

  const MAGIC = [[[0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], "PNG"], [[0xff, 0xd8, 0xff], "JPEG"]];
  async function sniff(f) {
    const b = new Uint8Array(await f.slice(0, 8).arrayBuffer());
    for (const [sig, name] of MAGIC) if (sig.every((v, i) => b[i] === v)) return name;
    return null;
  }
  const showMsg = (text, cls = "err") => { msg.innerHTML = text ? `<div class="notice ${cls}">${esc(text)}</div>` : ""; };

  async function init() {
    try {
      const [cats, health] = await Promise.all([api("/api/categories"), api("/api/health")]);
      categories = cats; maxMb = health.limits?.max_upload_mb ?? maxMb;
    } catch (e) { $("catList").innerHTML = ""; showMsg(e.message); return; }
    $("catList").innerHTML = categories.map((c) => {
      const ok = c.status === "operational";
      return `<label class="cat ${ok ? "" : "disabled"}"><input type="radio" name="cat" value="${esc(c.category)}" ${ok ? "" : "disabled"}>
        <span><strong>${esc(c.display_name)} <span class="badge ${ok ? "ok" : "off"}">${ok ? "Operational" : "Not integrated"}</span></strong>
        <small>${esc(ok ? c.description : c.blocker)}</small></span></label>`;
    }).join("");
    const first = categories.find((c) => c.status === "operational");
    if (first) { document.querySelector(`input[value="${first.category}"]`).checked = true; selectCat(first.category); }
    $("catList").addEventListener("change", (e) => selectCat(e.target.value));
    $("limitNote").textContent = `Maximum ${maxMb} MB`;
  }

  function selectCat(id) {
    selected = categories.find((c) => c.category === id);
    $("fmtNote").textContent = selected ? `Accepted formats: ${selected.accepted_formats.join(", ")}.` : "";
    if (file) validateAndPreview(file);
  }

  async function validateAndPreview(f) {
    showMsg("");
    if (!selected) return showMsg("Choose an imaging task first.");
    if (f.size === 0) return reject("The selected file is empty.");
    if (f.size > maxMb * 1024 * 1024) return reject(`File is ${fmtBytes(f.size)}; the limit is ${maxMb} MB.`);
    const fmt = await sniff(f);
    if (!fmt) return reject(`Unsupported file type. Accepted formats: ${selected.accepted_formats.join(", ")}.`);
    if (!selected.accepted_formats.includes(fmt)) return reject(`${fmt} is not accepted for this task. Accepted: ${selected.accepted_formats.join(", ")}.`);
    file = f;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(f);
    const img = $("thumb");
    img.onload = () => { $("mDim").textContent = `${img.naturalWidth} x ${img.naturalHeight} px`; };
    img.onerror = () => reject("The browser cannot read this image. It may be corrupted.");
    img.src = objectUrl;
    $("mType").textContent = fmt; $("mSize").textContent = fmtBytes(f.size); $("mCat").textContent = selected.display_name;
    drop.hidden = true; preview.hidden = false;
  }
  function reject(text) { clear(false); showMsg(text); }

  function clear(resetMsg = true) {
    file = null; input.value = "";
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    $("thumb").removeAttribute("src"); preview.hidden = true; drop.hidden = false;
    $("progress").hidden = true; $("progressLabel").textContent = ""; $("analyzeBtn").disabled = false;
    if (resetMsg) showMsg("");
  }

  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) validateAndPreview(f); });
  input.addEventListener("change", () => { if (input.files[0]) validateAndPreview(input.files[0]); });
  $("removeBtn").addEventListener("click", () => clear());
  $("replaceBtn").addEventListener("click", () => input.click());

  $("analyzeBtn").addEventListener("click", () => {
    if (!file || !selected) return;
    const fd = new FormData(); fd.append("category", selected.category); fd.append("file", file);
    const bar = $("progress"), fill = bar.firstElementChild, label = $("progressLabel");
    bar.hidden = false; bar.classList.remove("indeterminate"); fill.style.width = "0"; $("analyzeBtn").disabled = true; showMsg("");
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API + "/api/upload");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) { const p = Math.round((e.loaded / e.total) * 100); fill.style.width = p + "%"; label.textContent = `Uploading ${p}%`; }
    };
    xhr.upload.onload = () => { label.textContent = "Validating image on the server..."; bar.classList.add("indeterminate"); };
    xhr.onerror = () => { bar.hidden = true; $("analyzeBtn").disabled = false; showMsg("Cannot reach the MedScan AI server. Check that the backend is running."); };
    xhr.onload = () => {
      let body = {}; try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status === 201) { location.href = `analysis.html?image=${encodeURIComponent(body.image_id)}`; return; }
      bar.hidden = true; $("analyzeBtn").disabled = false; label.textContent = "";
      const d = body.detail; showMsg(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : `Upload failed (${xhr.status}).`);
    };
    xhr.send(fd);
  });

  init();
})();
