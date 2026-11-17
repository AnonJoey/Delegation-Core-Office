"""Verificacao visual do cartao Facts da aba Vigia: busca um fato e lista as divergencias."""
import sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1400}); erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto("http://127.0.0.1:8799/index.html?port=8798"); pg.wait_for_timeout(2000)
    pg.keyboard.press("Control+5"); pg.wait_for_timeout(1000)
    pg.fill("#fatos-q", "llama port"); pg.click("#fatos-buscar")
    pg.wait_for_function("() => !document.getElementById('vigia-fatos').innerText.includes('Loading')", timeout=20000)
    print(pg.locator("#vigia-fatos").inner_text()[:600])
    pg.click("#fatos-divergentes")
    pg.wait_for_function("() => document.getElementById('vigia-fatos').innerText.includes('Disagreement') || document.getElementById('vigia-fatos').innerText.includes('No disagreements')", timeout=20000)
    print(pg.locator("#vigia-fatos").inner_text()[:700])
    pg.locator("#vigia-fatos").screenshot(path=f"{S}/fatos.png")
    print("erros JS:", erros)
    b.close()
