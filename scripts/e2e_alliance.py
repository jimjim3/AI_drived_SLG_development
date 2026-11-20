"""Headless-browser check of the diplomacy tab, alliance proposal and save/resume. Usage: python3 scripts/e2e_alliance.py [outdir]"""
import json, pathlib, sys, tempfile, threading, time, urllib.request
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from slg.engine import combat
from slg.web.server import App, make_handler
from playwright.sync_api import sync_playwright

combat.set_rules("softer_pool2_econ5_ally3")
out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/e2e_alliance"); out.mkdir(parents=True, exist_ok=True)
saves = tempfile.mkdtemp()
app = App(save_dir=saves); srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)); base = f"http://127.0.0.1:{srv.server_address[1]}"
threading.Thread(target=srv.serve_forever, daemon=True).start()
errs, res = [], {}
sid = {"v": "main"}
status = lambda: json.load(urllib.request.urlopen(urllib.request.Request(base + "/api/status", headers={"X-Session": sid["v"]})))

def wait(cond, t=20):
    t0 = time.time()
    while time.time() - t0 < t:
        if cond(): return True
        time.sleep(0.2)
    return False

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(base + "/")
    sid["v"] = pg.evaluate("sessionStorage.getItem('slg_sid')") or "main"
    res["no_resume_button_initially"] = not pg.is_visible("#btnTitleResume")
    pg.click("#btnTitleNewGame"); pg.click("#btnSetupStart")
    wait(lambda: status().get("phase") == "awaiting_input")
    pg.wait_for_selector(".opening-card"); pg.keyboard.press("Enter")
    res["diplomacy_button_visible"] = pg.is_visible("#cmdDiplomacy")
    pg.click("#cmdDiplomacy"); time.sleep(0.3)
    res["two_dip_cards"] = pg.locator(".dip-card").count() == 2
    res["friendship_shown"] = "友好度" in pg.inner_text(".diplomacy-panel")
    pg.screenshot(path=str(out / "diplomacy.png"))
    # a proposal is offered in the dispatch tab, with faction names rather than ids
    pg.click('[data-tab="dispatch"]'); time.sleep(0.3)
    found = False
    tabs = pg.locator(".officer-tab-btn")
    for i in range(tabs.count()):
        tabs.nth(i).click(); time.sleep(0.2)
        if pg.locator('.action-card[data-action="propose_alliance"]').count():
            found = True
            res["faction_names_in_choices"] = "（" in pg.locator('select[name="param_propose_alliance_to"] option').first.inner_text()
            res["pledge_label"] = "抵押金" in pg.inner_text('.action-card[data-action="propose_alliance"]')
            pg.screenshot(path=str(out / "propose.png"))
            break
    res["propose_offered"] = found
    pg.locator(".officer-tab-btn").first.click(); time.sleep(0.3)
    res["ability_hint_shown"] = pg.locator(".ability-hint").count() >= 2 and "所需能力" in pg.inner_text(".actions-form-box")
    res["ability_rule_text"] = "50 + 政治" in pg.inner_text(".actions-form-box")
    pg.screenshot(path=str(out / "abilities.png"))
    res["stamina_in_brief"] = "體 100" in pg.inner_text(".officer-brief-card")
    pg.click('[data-tab="officers"]'); time.sleep(0.3)
    res["stamina_column"] = "體力" in pg.inner_text("#panelsContainer")
    pg.screenshot(path=str(out / "stamina_officers.png"))
    pg.click('[data-tab="dispatch"]'); time.sleep(0.3)
    # save exists at turn start; leave the game and the title screen offers to continue
    res["save_written"] = (pathlib.Path(saves) / f"{sid['v']}.sav").is_file()
    s_old = app.get(sid["v"])
    app.sessions.pop(sid["v"]); s_old.abandon()  # simulate a server restart: no live session, save remains
    pg.reload(); time.sleep(0.8)
    res["resume_button_shown"] = pg.is_visible("#btnTitleResume")
    res["resume_label_has_turn"] = "第 1 回合" in pg.inner_text("#btnTitleResume")
    pg.screenshot(path=str(out / "title_resume.png"))
    pg.click("#btnTitleResume"); time.sleep(1.5)
    res["resumed_into_main"] = pg.is_visible("#screenMain") and pg.locator(".dip-card, #panelsContainer *").count() > 0
    pg.screenshot(path=str(out / "resumed.png"))
    res["resumed_diplomacy_button"] = pg.is_visible("#cmdDiplomacy")
    b.close()
res["js_errors"] = errs[:5]; print(json.dumps(res, ensure_ascii=False)); srv.shutdown()
sys.exit(0 if all(v is True for k, v in res.items() if k != "js_errors") and not errs else 1)
