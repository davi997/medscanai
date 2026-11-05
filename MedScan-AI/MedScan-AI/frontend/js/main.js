/* Shared helpers. Plain JavaScript, no frameworks. */
const API = window.MEDSCAN_API_BASE || "";

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtBytes(n) { return n < 1024 * 1024 ? (n / 1024).toFixed(0) + " KB" : (n / 1024 / 1024).toFixed(1) + " MB"; }
function fmtDate(iso) { return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "-"; }
function labelize(s) {
  return String(s || "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()).replace(/\bxray\b/i, "X-ray").replace(/\bct\b/i, "CT");
}

/** fetch wrapper that turns API errors into readable Error messages. */
async function api(path, opts) {
  let res;
  try { res = await fetch(API + path, opts); }
  catch { throw new Error("Cannot reach the MedScan AI server. Check that the backend is running."); }
  if (!res.ok) {
    let msg = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d) => d.msg).join("; ");
    } catch { /* non-JSON error body */ }
    const err = new Error(msg); err.status = res.status; throw err;
  }
  return res.json();
}

function toast(msg, ms = 4000) {
  const t = document.createElement("div");
  t.className = "toast"; t.setAttribute("role", "status"); t.textContent = msg;
  document.body.appendChild(t); setTimeout(() => t.remove(), ms);
}

document.addEventListener("DOMContentLoaded", () => {
  const btn = document.querySelector(".nav-toggle"), links = document.getElementById("navlinks");
  if (btn && links) {
    btn.addEventListener("click", () => { const open = links.classList.toggle("open"); btn.setAttribute("aria-expanded", open); });
    links.addEventListener("click", (e) => { if (e.target.closest("a")) links.classList.remove("open"); });
  }
});
