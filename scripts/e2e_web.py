"""Headless-browser smoke test of the web UI against the real server. Usage: python3 scripts/e2e_web.py [outdir]"""
import json, pathlib, sys, threading, time, urllib.request
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from slg.web.server import App, make_handler
from playwright.sync_api import sync_playwright

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_web"); out.mkdir(parents=True, exist_ok=True)
app = App(); srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); base = f"http://127.0.0.1:{port}"
SID = {"v": "main"}  # each browser tab plays its own game; poll the same one the page uses
status = lambda: json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/status", headers={"X-Session": SID["v"]})))
errs = []; res = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in ((1280, 800), (360, 740)):
        pg = b.new_page(viewport={"width": w, "height": h}); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(base + "/"); SID["v"] = pg.evaluate("sessionStorage.getItem('slg_sid')") or "main"; pg.click("#btnTitleNewGame")
        # story preview follows the chosen scenario + lord (attack scenario favors the chosen lord)
        pg.check('input[name="setupScenario"][value="advantage"]'); pg.check('input[name="setupFaction"][value="faction_1"]')
        pg.wait_for_function("document.querySelector('#setupPreview .tone-badge')?.textContent === '優勢'", timeout=5000)
        res[f"preview_{w}"] = "曹操" in pg.inner_text("#setupPreview")
        pg.screenshot(path=str(out / f"setup_{w}.png"))
        pg.check('input[name="setupScenario"][value="default"]'); pg.check('input[name="setupFaction"][value="faction_2"]')
        pg.wait_for_function("document.querySelector('#setupPreview .tone-badge')?.textContent === '劣勢'", timeout=5000)
        pg.click("#btnSetupStart")
        t0 = time.time()
        while status().get("phase") != "awaiting_input" and time.time() - t0 < 20: time.sleep(0.2)
        pg.wait_for_selector(".opening-card", timeout=5000)
        res[f"opening_{w}"] = "洛陽" in pg.inner_text(".opening-card") and pg.locator(".opening-card li").count() == 3
        pg.screenshot(path=str(out / f"opening_{w}.png"))
        res[f"opening_scroll_ok_{w}"] = pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        pg.keyboard.press("Enter"); pg.wait_for_selector(".opening-card", state="detached", timeout=3000)
        res[f"calendar_{w}"] = pg.inner_text("#turnBadge").startswith("第1年春")
        res[f"city_blurb_{w}"] = pg.locator(".city-blurb").count() == 1
        pg.click('[data-tab="officers"]'); time.sleep(0.4)
        res[f"bios_{w}"] = pg.locator(".bio-list details").count() >= 10
        pg.click('[data-tab="city"]'); time.sleep(0.2)
        time.sleep(1.0); pg.screenshot(path=str(out / f"main_{w}.png"))
        res[f"scroll_ok_{w}"] = pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if w == 1280:
            pg.click('[data-tab="dispatch"]'); time.sleep(0.5); pg.screenshot(path=str(out / "dispatch_1280.png"))
            t1 = status()["turn"]; pg.click('[data-action="submit"]'); time.sleep(0.5)
            for sel in ("#btnConfirmSubmit", "button:has-text('確認')"):
                try: pg.click(sel, timeout=800); break
                except Exception: pass
            t0 = time.time()
            while time.time() - t0 < 20 and not (status()["turn"] > t1 and status()["phase"] == "awaiting_input"): time.sleep(0.2)
            res["advanced_turn"] = status()["turn"] > t1; time.sleep(1); pg.screenshot(path=str(out / "after_submit_1280.png"))
        pg.close()
    b.close()
res["js_errors"] = errs[:5]; print(json.dumps(res, ensure_ascii=False)); srv.shutdown()
sys.exit(0 if all(v is True for k, v in res.items() if k != "js_errors") and not errs else 1)
