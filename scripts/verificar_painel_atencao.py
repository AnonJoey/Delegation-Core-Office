"""Verificacao visual do cartao "Needs attention" da aba Vigia (atencao.json do daemon).

Mesmo preparo de scripts/verificar_painel.py: painel servido em 8799, daemon
com o painel em 8798. Abre a aba (Ctrl+5), espera o cartao e fotografa.
"""
import sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1300}); erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto("http://127.0.0.1:8799/index.html?port=8798"); pg.wait_for_timeout(2000)
    pg.keyboard.press("Control+5")
    pg.wait_for_selector("#vigia-atencao p, #vigia-atencao table", timeout=15000)
    pg.wait_for_timeout(1500)
    print(pg.locator("#vigia-atencao").inner_text())
    pg.locator("#vigia-atencao").screenshot(path=f"{S}/atencao.png")
    print("erros JS:", erros)
    b.close()
