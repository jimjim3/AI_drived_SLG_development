"""Headless-browser smoke test of the web UI against the real server. Usage: python3 scripts/e2e_web.py [outdir]"""
import json, pathlib, sys, threading, time, urllib.request
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from slg.web.server import App, make_handler
from playwright.sync_api import sync_playwright

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_web"); out.mkdir(parents=True, exist_ok=True)
app = App(); srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start(); base = f"http://127.0.0.1:{port}"
status = lambda: json.load(urllib.request.urlopen(base + "/api/status"))
errs = []; res = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in ((1280, 800), (360, 740)):
        pg = b.new_page(viewport={"width": w, "height": h}); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto(base + "/"); pg.click("#btnTitleNewGame"); pg.click("#btnSetupStart")
        t0 = time.time()
        while status().get("phase") != "awaiting_input" and time.time() - t0 < 20: time.sleep(0.2)
        time.sleep(1.5); pg.screenshot(path=str(out / f"main_{w}.png"))
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
