(() => {
  const imageId = new URLSearchParams(location.search).get("image");
  const running = document.getElementById("running"), failed = document.getElementById("failed");
  let timer;

  function fail(text) {
    clearInterval(timer);
    running.hidden = true; failed.hidden = false;
    document.getElementById("errMsg").textContent = text;
  }

  async function start() {
    if (!imageId) return fail("No image selected. Upload an image first.");
    running.hidden = false; failed.hidden = true;
    const t0 = Date.now(), out = document.getElementById("elapsed");
    clearInterval(timer);
    timer = setInterval(() => { out.textContent = Math.floor((Date.now() - t0) / 1000) + " s"; }, 500);
    try {
      const res = await api("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ image_id: imageId }) });
      clearInterval(timer);
      location.replace(`results.html?id=${encodeURIComponent(res.id)}`);
    } catch (e) { fail(e.message); }
  }
  document.getElementById("retryBtn").addEventListener("click", start);
  start();
})();
