"""Verificacao visual do Apply/Dismiss de um achado do sonho no cartao Needs attention."""
import sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1300}); erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto("http://127.0.0.1:8799/index.html?port=8798"); pg.wait_for_timeout(2000)
    pg.keyboard.press("Control+5")
    pg.wait_for_selector("#vigia-atencao .achado-btn[data-acao='apply']", timeout=15000)
    botao = pg.locator("#vigia-atencao .achado-btn[data-acao='apply']").first
    velha = botao.get_attribute("data-old")
    linha = pg.locator("#vigia-atencao tr", has_text=velha).first
    print("antes:", linha.inner_text()[:200].replace("\n", " | "))
    botao.click(); pg.wait_for_timeout(4000)
    print("depois, ultima coluna:", linha.locator("td").last.inner_text())
    linha.screenshot(path=f"{S}/achado.png")
    print("erros JS:", erros)
    b.close()
