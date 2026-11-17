"""Verificacao visual da aba Vigia: Ctrl+5, clica Run now na tarefa alertas e confere que a linha mudou.

Mesmo preparo de scripts/verificar_painel.py (Playwright a parte, painel servido
em 8799, daemon com o painel em 8798). Foi este clique que mostrou que um Run
now nao deixava rastro na linha, porque a coluna Last so dizia "ok".
"""
import sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1100}); erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto("http://127.0.0.1:8799/index.html?port=8798"); pg.wait_for_timeout(2000)
    pg.keyboard.press("Control+5")
    pg.wait_for_selector("#vigia-agenda .vigia-run", timeout=10000)
    antes = pg.locator("#vigia-agenda tr", has_text="alertas").inner_text()
    pg.locator("#vigia-agenda .vigia-run[data-name='alertas']").click()
    pg.wait_for_timeout(6000)
    depois = pg.locator("#vigia-agenda tr", has_text="alertas").inner_text()
    pg.screenshot(path=f"{S}/vigia3.png")
    print("antes:", antes.replace("\n", " | ")); print("depois:", depois.replace("\n", " | ")); print("erros JS:", erros)
    b.close()
