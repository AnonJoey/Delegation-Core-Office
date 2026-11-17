"""A calibracao do modelo local, fora do arquivo de configuracao.

O teste que carrega o argumento inteiro e
`test_calibrar_nao_reverte_ajuste_feito_no_dashboard`: ele reproduz o risco que
motivou o modulo, e falharia contra o codigo anterior.
"""

from __future__ import annotations

import json

import pytest

from delegation_core import calibracao


@pytest.fixture(autouse=True)
def arquivo_temporario(tmp_path, monkeypatch):
    """Nunca tocar a calibracao real da maquina.

    A suite deste repo ja tem uma guarda parecida no `conftest`, escrita depois
    de 02/09/2026, quando um teste chamou `calibrate()` e escreveu um config de
    verdade com `vault_path` temporario, tirando a maquina de servico.
    """
    monkeypatch.setattr(calibracao, "ARQUIVO", tmp_path / "calibracao.json")


def test_sem_arquivo_e_sem_legado_nao_ha_calibracao():
    assert calibracao.ler() == calibracao.SEM_CALIBRACAO


def test_grava_e_le_de_volta():
    calibracao.gravar(42.5)
    assert calibracao.ler() == 42.5


def test_o_valor_do_config_antigo_e_adotado_uma_vez():
    """Migracao: instalacao ja calibrada nao pode recalibrar do zero.

    O valor antigo mora dentro do `config.json`. Ignora-lo faria toda maquina
    em uso pagar uma recalibracao na primeira chamada depois da atualizacao.
    """
    assert calibracao.ler(config_legado=37.0) == 37.0


def test_o_arquivo_novo_vence_o_legado():
    """Depois da primeira gravacao, o config antigo deixa de ser consultado."""
    calibracao.gravar(10.0)
    assert calibracao.ler(config_legado=99.0) == 10.0


def test_calibracao_ilegivel_nao_derruba_o_motor():
    """O pior caso e recalibrar, que custa uma chamada e conserta o arquivo.

    Levantar aqui derrubaria a geracao por causa de um arquivo de medicao.
    """
    calibracao.ARQUIVO.write_text("{ isto nao e json", encoding="utf-8")
    assert calibracao.ler() == calibracao.SEM_CALIBRACAO
    assert calibracao.ler(config_legado=5.0) == 5.0


def test_limpar_invalida():
    calibracao.gravar(20.0)
    calibracao.limpar()
    assert calibracao.ler() == calibracao.SEM_CALIBRACAO


def test_limpar_sem_arquivo_nao_levanta():
    calibracao.limpar()


def test_o_arquivo_fica_com_permissao_restrita():
    """Mesmo tratamento do config: fica no mesmo diretorio, mesma regra."""
    import stat
    calibracao.gravar(1.0)
    modo = stat.S_IMODE(calibracao.ARQUIVO.stat().st_mode)
    assert modo == 0o600, f"permissao {oct(modo)}"


def test_calibrar_nao_reverte_ajuste_feito_no_dashboard(tmp_path):
    """O risco que motivou este modulo, reproduzido.

    `Config.save()` faz `json.dumps(asdict(self))`: grava o arquivo INTEIRO a
    partir do objeto em memoria daquele processo. O engine carrega o config ao
    subir; se alguem muda um ajuste pelo dashboard depois disso, a calibracao
    seguinte revertia a mudanca, sem erro e sem aviso.

    Aqui: um "config" e carregado, um "dashboard" altera outro campo, e a
    calibracao acontece. O ajuste tem que sobreviver.
    """
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"synthesis_lang": "en", "tok_sec": 0.0}),
                      encoding="utf-8")

    # o engine carregou o config ao subir
    carregado_pelo_engine = json.loads(config.read_text(encoding="utf-8"))

    # o usuario muda um ajuste pelo dashboard, depois disso
    atual = json.loads(config.read_text(encoding="utf-8"))
    atual["synthesis_lang"] = "pt"
    config.write_text(json.dumps(atual), encoding="utf-8")

    # o engine calibra, usando o objeto que ele carregou la atras
    calibracao.gravar(33.0)
    assert carregado_pelo_engine["tok_sec"] == 0.0, (
        "a calibracao nao pode mais tocar o objeto de config do engine")

    depois = json.loads(config.read_text(encoding="utf-8"))
    assert depois["synthesis_lang"] == "pt", (
        "a calibracao reverteu um ajuste feito no dashboard")
    assert calibracao.ler() == 33.0, "e a medicao foi guardada fora do config"
