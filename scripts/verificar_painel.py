"""Verificacao visual do painel com Playwright: abre uma nota, clica History e Diff, e fotografa.

Nasceu em 27/09 porque duas falhas do painel so apareceram em tela: a aba Vigia
buscando antes de saber a porta ("JSON.parse: unexpected character") e o diff
colando a ultima linha removida na primeira adicionada. Teste de unidade nao
via nenhuma das duas.

Uso (Playwright instalado a parte, fora do projeto):
    python -m venv /tmp/pw && /tmp/pw/bin/pip install playwright && /tmp/pw/bin/playwright install chromium
    python -m http.server 8799 --directory dashboard/src &
    /tmp/pw/bin/python scripts/verificar_painel.py <pasta das capturas>
com um daemon servindo o painel na porta 8798 (dashboard_port) e uma nota
"teste de segredo e2e" que tenha ao menos duas versoes.
"""
import sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1500, "height": 1000})
    erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto("http://127.0.0.1:8799/index.html?port=8798")
    pg.wait_for_timeout(2500)
    pg.click('button[data-tab="notes"]')
    pg.fill("#notes-filter", "teste de segredo e2e")
    pg.wait_for_timeout(2500)
    pg.locator("#explorer >> text=teste de segredo e2e").first.click()
    pg.wait_for_timeout(1500)
    pg.click("#btn-note-history")
    pg.wait_for_selector("#note-history .hist-diff", timeout=8000)
    pg.screenshot(path=f"{S}/hist1.png")
    pg.click("#note-history .hist-diff >> nth=0")
    pg.wait_for_selector(".hist-diff-out:not([hidden])", timeout=8000)
    pg.screenshot(path=f"{S}/hist2.png")
    print("versoes na tela:", pg.locator("#note-history tr").count(), "| erros JS:", erros)
    b.close()
