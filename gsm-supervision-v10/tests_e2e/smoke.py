"""Test de bout en bout (navigateur sans tête) : connexion, carte, fiche, historique, tableau de bord,
administration, alarmes, affichage mobile. Captures dans $OUT. Nécessite des sites DOWN (ex. seed-demo).

  pip install playwright && python -m playwright install chromium
  BASE_URL=http://serveur:8080 E2E_USER=admin E2E_PASSWORD=... python tests_e2e/smoke.py
"""
import asyncio, json, urllib.request
from playwright.async_api import async_playwright
import os, sys
OUT=os.environ.get("OUT", "e2e-captures")
BASE=os.environ.get("BASE_URL", "http://localhost:8080")
USER=os.environ.get("E2E_USER", "admin")
PWD=os.environ["E2E_PASSWORD"]
os.makedirs(OUT, exist_ok=True)
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width":1500,"height":900})
        errors=[]
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type=="error" and "tile.openstreetmap" not in m.text and errors.append(m.text))
        await pg.route("**/tile.openstreetmap.org/**", lambda r: r.abort())
        await pg.goto(BASE+"/")
        await pg.fill("input[autocomplete=username]",USER)
        await pg.fill("input[type=password]",PWD)
        await pg.click("button[type=submit]")
        await pg.wait_for_selector(".kpi-v")
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=f"{OUT}/1_carte.png")
        # site DOWN
        tok = await pg.evaluate("sessionStorage.getItem('gsm.token')")
        req = urllib.request.Request(BASE+"/api/sites?status=DOWN&page_size=1", headers={"Authorization":"Bearer "+tok})
        sid = json.load(urllib.request.urlopen(req))["items"][0]["id"]
        await pg.goto(f"{BASE}/?wilaya=16&site={sid}&table=1")
        await pg.wait_for_selector(".status-hero")
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=f"{OUT}/2_fiche_tableau.png")
        await pg.click("text=Historique")
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=f"{OUT}/3_historique.png")
        await pg.goto(BASE+"/dashboard")
        await pg.wait_for_selector(".grid")
        await pg.wait_for_timeout(1500)
        await pg.screenshot(path=f"{OUT}/4_dashboard.png", full_page=True)
        await pg.goto(BASE+"/admin")
        await pg.wait_for_selector("table")
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=f"{OUT}/5_admin.png")
        await pg.goto(BASE+"/alarms")
        await pg.wait_for_selector("table")
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=f"{OUT}/6_alarmes.png")
        m = await b.new_page(viewport={"width":390,"height":800})
        await m.route("**/tile.openstreetmap.org/**", lambda r: r.abort())
        await m.goto(BASE+"/")
        await m.evaluate(f"sessionStorage.setItem('gsm.token', '{tok}')")
        await m.goto(f"{BASE}/?status=DOWN")
        await m.wait_for_selector(".kpi-v"); await m.wait_for_timeout(2000)
        await m.screenshot(path=f"{OUT}/7_mobile.png")
        errs = [e for e in errors if "ERR_FAILED" not in e]
        print("Erreurs JavaScript :", errs or "aucune")
        if errs:
            sys.exit(1)
        await b.close()
asyncio.run(main())
