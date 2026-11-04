"""doctor: uma fonte ingerida que parou ou que falha em massa tem de aparecer.

Relato do Mac de um colega em 2026-11-04: `Documents/Work` nao era reindexada
desde 29/09, a ultima carga teve 791 erros e a pasta nao tinha atualizacao
automatica. O material de outubro nao entrou e nenhuma checagem dizia isso.
`check_ingest_registry` so olhava se o caminho ainda existia.
"""

import json
from datetime import datetime, timedelta

import pytest

from delegation_core import doctor

AGORA = datetime(2026, 11, 4, 12, 0, 0)


@pytest.fixture
def registro(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "CONFIG_DIR", tmp_path)
    pasta = tmp_path / "fonte"
    pasta.mkdir()

    def grava(**campos):
        entrada = {"recursive": True, "exclude": None, "files": {}}
        entrada.update(campos)
        (tmp_path / "ingested_sources.json").write_text(
            json.dumps({str(pasta): entrada}), encoding="utf-8")
        return pasta
    return grava


def _dias(n):
    return (AGORA - timedelta(days=n)).isoformat()


def test_fonte_recente_e_sem_erros_fica_ok(registro):
    registro(last_indexed=_dias(2), indexed_count=40, error_count=0)
    r = doctor.check_ingest_registry(agora=AGORA)
    assert r["status"] == "ok", r


def test_fonte_parada_ha_mais_de_catorze_dias_avisa(registro):
    registro(last_indexed=_dias(36), indexed_count=40, error_count=0)
    r = doctor.check_ingest_registry(agora=AGORA)
    assert r["status"] == "warn"
    assert "36" in r["detail"]
    assert "ingest" in r["fix"]


def test_carga_com_muitos_erros_avisa_mesmo_sendo_recente(registro):
    registro(last_indexed=_dias(1), indexed_count=200, skipped_unchanged_count=0, error_count=791)
    r = doctor.check_ingest_registry(agora=AGORA)
    assert r["status"] == "warn"
    assert "791" in r["detail"]


def test_poucos_erros_em_carga_grande_nao_avisa(registro):
    registro(last_indexed=_dias(1), indexed_count=900, skipped_unchanged_count=0, error_count=3)
    assert doctor.check_ingest_registry(agora=AGORA)["status"] == "ok"


def test_entrada_reconstruida_sem_data_nao_vira_alarme(registro):
    """Entradas refeitas a partir do indice nao tem last_indexed: dizer isso, nao acusar."""
    registro(reconstruido_do_indice=True)
    r = doctor.check_ingest_registry(agora=AGORA)
    assert r["status"] == "ok"
    assert "sem data" in r["detail"]


def test_o_limite_de_dias_e_configuravel(registro):
    registro(last_indexed=_dias(5), indexed_count=10, error_count=0)
    assert doctor.check_ingest_registry(agora=AGORA, dias_parada=3)["status"] == "warn"
    assert doctor.check_ingest_registry(agora=AGORA, dias_parada=7)["status"] == "ok"


def test_caminho_que_sumiu_continua_sendo_avisado(registro, tmp_path):
    pasta = registro(last_indexed=_dias(1), indexed_count=1, error_count=0)
    pasta.rmdir()
    assert doctor.check_ingest_registry(agora=AGORA)["status"] == "warn"
