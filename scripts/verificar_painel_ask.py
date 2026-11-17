"""Verificacao visual do Ask na aba de busca: pergunta, espera as afirmacoes, clica na primeira.

Mesmo preparo de scripts/verificar_painel.py (painel em 8799, daemon em 8798).
"""
import sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]
PERGUNTA = sys.argv[2] if len(sys.argv) > 2 else "Por que o BGE-m3 foi movido para a CPU?"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1200}); erros = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto("http://127.0.0.1:8799/index.html?port=8798"); pg.wait_for_timeout(2000)
    pg.keyboard.press("Control+3")
    pg.fill("#vector-search-input", PERGUNTA)
    pg.click("#vector-ask-btn")
    pg.wait_for_function("() => !document.getElementById('vector-search-results').innerText.includes('Asking')",
                         timeout=90000)
    pg.wait_for_timeout(500)
    print(pg.locator("#vector-search-results").inner_text()[:1500])
    pg.locator("#vector-search-results").screenshot(path=f"{S}/ask.png")
    n = pg.locator(".answer-claim").count()
    if n:
        pg.locator(".answer-claim").first.click(); pg.wait_for_timeout(1500)
        print("nota aberta:", pg.locator("#tab-notes, .note-title, h1").first.inner_text()[:120] if pg.locator("#tab-notes, .note-title, h1").count() else "?")
    print("afirmacoes:", n, "erros JS:", erros)
    b.close()
