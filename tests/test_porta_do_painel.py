"""A porta do painel esta escrita em TRES linguagens e precisa concordar.

## O defeito, medido em 25/09/2026

`Config.dashboard_port` e 8788. O `lib.rs` do Tauri cai em 8788. E o `main.js`
caia em **8182**, que nao e porta de nada neste projeto.

Medido com o daemon no ar: `curl 127.0.0.1:8788/api/config` devolve **200**, e a
8182 nao responde **nada**. Conferido tambem na tela, servindo a frente fora do
Tauri e abrindo em navegador headless:

- **antes:** "status unavailable", "clients unavailable", "Vault unavailable",
  "Graph unavailable, Failed to fetch". A casca da interface renderiza, porque
  isso e deliberado, mas nenhum painel tem dado
- **depois:** `VAULT ok`, `BINARY ok`, `MODEL ok`, `INDEXED NOTES 16158`,
  arvore do vault com 27 projetos, e o grafo desenhado com
  "482 notes, 9728 code-graph articles"

A API estava funcionando o tempo todo. O sintoma nao era erro em lugar nenhum,
era o painel abrir vazio quando aberto fora do Tauri.

## Por que um teste em vez de so corrigir o numero

Porque a mesma constante mora em tres arquivos de tres linguagens, e nada
comparava os tres. E exatamente a familia de defeito das copias de
`scripts/office/`: nao e a duplicacao que machuca, e a **divergencia
silenciosa**.

Este teste nao pede que a duplicacao acabe. O Tauri precisa do valor em Rust
antes de qualquer JS rodar, e o navegador nao tem como ler o `config.json`.
Pede que os tres continuem iguais enquanto existirem.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from delegation_core.config import Config

RAIZ = Path(__file__).resolve().parents[1]
MAIN_JS = RAIZ / "dashboard" / "src" / "main.js"
LIB_RS = RAIZ / "dashboard" / "src-tauri" / "src" / "lib.rs"


def _porta_no_js() -> int:
    texto = MAIN_JS.read_text(encoding="utf-8")
    achado = re.search(r"const PORTA_PADRAO_DO_PAINEL\s*=\s*(\d+)", texto)
    assert achado, "a constante da porta sumiu do main.js"
    return int(achado.group(1))


def _porta_no_rust() -> int:
    texto = LIB_RS.read_text(encoding="utf-8")
    achado = re.search(r"\.unwrap_or\((\d+)\)", texto)
    assert achado, "o fallback da porta sumiu do lib.rs"
    return int(achado.group(1))


@pytest.mark.skipif(not MAIN_JS.is_file(), reason="o painel nao esta neste checkout")
def test_o_js_concorda_com_o_config():
    """O caso que quebrou: 8182 no JS contra 8788 no Config."""
    assert _porta_no_js() == Config().dashboard_port, (
        f"o main.js cai em {_porta_no_js()} e o Config usa "
        f"{Config().dashboard_port}; aberto fora do Tauri o painel nao acha a API")


@pytest.mark.skipif(not LIB_RS.is_file(), reason="o painel nao esta neste checkout")
def test_o_rust_concorda_com_o_config():
    assert _porta_no_rust() == Config().dashboard_port


@pytest.mark.skipif(not (MAIN_JS.is_file() and LIB_RS.is_file()),
                    reason="o painel nao esta neste checkout")
def test_os_tres_concordam_entre_si():
    """A guarda que pega o caso de alguem mudar dois dos tres."""
    assert _porta_no_js() == _porta_no_rust() == Config().dashboard_port


def test_os_arquivos_do_painel_existem():
    """Se o painel sair do repo, os testes acima viram skip e param de guardar.

    Sem esta guarda, apagar o dashboard deixaria o arquivo verde dando a
    impressao de que a concordancia esta conferida quando nao ha mais nada
    para conferir.
    """
    assert MAIN_JS.is_file(), f"{MAIN_JS} sumiu"
    assert LIB_RS.is_file(), f"{LIB_RS} sumiu"
