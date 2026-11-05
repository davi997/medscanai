"""Frontend integration: static contract checks + a real-browser end-to-end run (Playwright)."""
import re
import socket
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from backend.main import app

FRONT = Path(__file__).parent.parent / "frontend"
SAMPLE = Path(__file__).parent / "data" / "sample_cxr.png"


def test_pages_reference_existing_assets():
    pages = list(FRONT.glob("*.html"))
    assert {p.name for p in pages} >= {"index.html", "upload.html", "analysis.html", "results.html", "dashboard.html"}
    for p in pages:
        for ref in re.findall(r'(?:href|src)="((?:css|js)/[^"]+)"', p.read_text()):
            assert (FRONT / ref).exists(), f"{p.name} -> {ref}"


def test_every_api_call_in_js_exists_in_openapi(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    pats = [re.sub(r"\{[^}]+\}", "{x}", p) for p in paths]
    for js in (FRONT / "js").glob("*.js"):
        for m in re.findall(r"/api/[A-Za-z0-9_/\-\${}.\[\]()?=&,]*", js.read_text()):
            call = re.sub(r"\$\{[^}]*\}", "{x}", m).split("?")[0].rstrip("/")
            call = call.rstrip("`'\"")
            assert any(call == p or call.startswith(p.replace("{x}", "")) for p in pats), f"{js.name}: {m}"


def test_disclaimer_present_on_user_facing_pages():
    needle = "must be reviewed by a qualified medical professional"
    for name in ("index.html", "js/results.js"):
        assert needle in (FRONT / name).read_text()


def test_no_frameworks_used():
    text = " ".join(p.read_text() for p in FRONT.rglob("*") if p.suffix in (".html", ".js"))
    assert not re.search(r"react|vue\.|angular|jquery", text, re.I)


@pytest.fixture(scope="module")
def live_url():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True; t.join(5)


@pytest.mark.browser
def test_browser_end_to_end(live_url, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Chromium not available: {e}")
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        # not-integrated tasks cannot be selected
        page.goto(f"{live_url}/upload.html"); page.wait_for_selector(".cat")
        assert page.locator('input[value="brain_ct"]').is_disabled()
        # invalid file is rejected client-side, nothing is sent
        bad = tmp_path / "bad.png"; bad.write_bytes(b"not an image")
        page.set_input_files("#fileInput", str(bad))
        assert "Unsupported file type" in page.inner_text("#formMsg")
        # valid file -> preview -> analyze -> results
        page.set_input_files("#fileInput", str(SAMPLE))
        page.wait_for_selector("#preview:not([hidden])")
        page.click("#analyzeBtn")
        page.wait_for_url("**/results.html*", timeout=90000)
        page.wait_for_selector(".finding", timeout=30000)
        body = page.inner_text("body")
        assert "not probabilities" in body and "qualified medical professional" in body
        assert page.locator("#vCam").is_enabled()
        page.click("#vCam"); assert "Grad-CAM" in page.inner_text("#vcap")
        # report download
        with page.expect_download() as dl:
            page.click("text=Download PDF report")
        assert dl.value.suggested_filename.endswith(".pdf")
        # dashboard shows the analysis
        page.goto(f"{live_url}/dashboard.html"); page.wait_for_selector(".history")
        assert "completed" in page.inner_text("#history")
        # mobile layout: no horizontal overflow on any page
        page.set_viewport_size({"width": 375, "height": 800})
        for name in ("index.html", "upload.html", "dashboard.html"):
            page.goto(f"{live_url}/{name}"); page.wait_for_timeout(400)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), name
        assert not errors, errors
        browser.close()
