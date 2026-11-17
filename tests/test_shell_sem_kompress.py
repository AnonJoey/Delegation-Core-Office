"""O `shell` da CLI nao carrega o Kompress; o roteador do daemon continua podendo."""

import argparse

from delegation_core.compressao import roteador
from delegation_core.filtros_saida import cli

_PROSA = ("Texto corrido sem cara de log, de diff nem de json, comprido o bastante para passar "
          "do limiar em que o roteador tentaria o compressor de linguagem natural. ") * 300


def _espiao(monkeypatch):
    chamadas: list[int] = []

    def falso(texto, guarda):
        chamadas.append(len(texto))
        return None  # como se o modelo nao estivesse em cache: o resultado anterior fica

    monkeypatch.setattr(roteador, "_kompress", falso)
    return chamadas


def test_shell_de_comando_anotado_nao_chama_o_kompress(tmp_path, monkeypatch, capsys):
    """cat e `git log` passam pelo compressor do delegation-core, e cada um e um processo novo."""
    chamadas = _espiao(monkeypatch)
    arquivo = tmp_path / "prosa.txt"
    arquivo.write_text(_PROSA, encoding="utf-8")
    rc = cli.cmd_run(argparse.Namespace(comando=f"cat {arquivo}"))
    assert rc == 0
    assert capsys.readouterr().out.strip()
    assert chamadas == [], "o shell carregou o Kompress: 1,5 GB e de 3 a 7 s por comando"


def test_roteador_ainda_chama_o_kompress_por_padrao(monkeypatch):
    """O Kompress segue no daemon (compress_output e proxy): so o shell o dispensa."""
    chamadas = _espiao(monkeypatch)
    roteador.comprimir(_PROSA, "", "text")
    assert len(chamadas) == 1


def test_roteador_com_kompress_desligado_nao_o_chama(monkeypatch):
    chamadas = _espiao(monkeypatch)
    roteador.comprimir(_PROSA, "", "text", kompress=False)
    assert chamadas == []
