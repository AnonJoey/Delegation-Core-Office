"""O que fecha a migracao: escolha do backend, indice danificado, recuperacao e dependencia opcional."""
import sqlite3
import sys

import pytest

from delegation_core import index_lock, recuperacao
from delegation_core.config import Config
from delegation_core.indice_sqlite import ClienteSqlite


def _cfg(tmp_path, **kw):
    return Config(vault_path=str(tmp_path / "vault"), **kw)


# -- escolha automatica do backend ---------------------------------------------

def test_instalacao_nova_usa_sqlite(tmp_path):
    assert _cfg(tmp_path).usa_sqlite is True


def test_indice_do_chroma_com_dados_nunca_e_trocado_sozinho(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.chroma_path.mkdir(parents=True)
    (cfg.chroma_path / "chroma.sqlite3").write_bytes(b"x")
    assert cfg.usa_sqlite is False


def test_com_os_dois_presentes_vale_o_sqlite(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.chroma_path.mkdir(parents=True)
    (cfg.chroma_path / "chroma.sqlite3").write_bytes(b"x")
    ClienteSqlite(cfg.sqlite_path).close()
    assert cfg.usa_sqlite is True


@pytest.mark.parametrize("valor,esperado", [("chroma", False), ("sqlite", True), ("SQLITE", True), (" Chroma ", False)])
def test_valor_explicito_vence_o_que_existe_em_disco(tmp_path, valor, esperado):
    cfg = _cfg(tmp_path, index_backend=valor)
    ClienteSqlite(cfg.sqlite_path).close()
    assert cfg.usa_sqlite is esperado


def test_index_dir_acompanha_o_backend(tmp_path):
    assert _cfg(tmp_path, index_backend="sqlite").index_dir == _cfg(tmp_path).sqlite_path
    assert _cfg(tmp_path, index_backend="chroma").index_dir == _cfg(tmp_path).chroma_path


# -- indice danificado -----------------------------------------------------------

def test_indice_sqlite_ilegivel_e_posto_de_lado_e_um_novo_abre(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, index_backend="sqlite")
    cfg.sqlite_path.mkdir(parents=True)
    (cfg.sqlite_path / "indice.db").write_bytes(b"isto nao e um banco sqlite " * 400)
    monkeypatch.setattr(recuperacao, "_dir_de_estado", lambda: tmp_path / "estado")
    (tmp_path / "estado").mkdir()
    cliente = index_lock.abrir_cliente(cfg)
    assert cliente.verificar() == "ok"
    assert cliente.list_collections() == []
    postos = list(cfg.vault.glob(".indice_sqlite-danificado-*"))
    assert len(postos) == 1 and (postos[0] / "indice.db").read_bytes().startswith(b"isto nao e"), \
        "o arquivo danificado tem que ser guardado, nao apagado"
    assert recuperacao.reconstrucao_pendente(), "a reconstrucao tem que ficar pedida"


def test_banco_ocupado_por_outro_processo_nao_e_tratado_como_dano(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, index_backend="sqlite")

    def ocupado(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr("delegation_core.indice_sqlite.ClienteSqlite", ocupado)
    with pytest.raises(sqlite3.OperationalError):
        index_lock.abrir_cliente(cfg)
    assert not list(cfg.vault.glob(".indice_sqlite-danificado-*"))


def test_quarentena_do_indice_sqlite_renomeia_a_pasta_dele_e_nao_a_do_chroma(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, index_backend="sqlite")
    monkeypatch.setattr(recuperacao, "_dir_de_estado", lambda: tmp_path / "estado")
    (tmp_path / "estado").mkdir()
    ClienteSqlite(cfg.sqlite_path).close()
    cfg.chroma_path.mkdir(parents=True)
    (cfg.chroma_path / "chroma.sqlite3").write_bytes(b"antigo")
    pedido = recuperacao.pos_em_quarentena(cfg, motivo="teste")
    assert pedido["indice_novo"] == str(cfg.sqlite_path)
    assert not cfg.sqlite_path.exists() and (cfg.chroma_path / "chroma.sqlite3").exists()


# -- dependencia opcional --------------------------------------------------------

def test_sem_chromadb_instalado_o_aviso_diz_o_que_fazer(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, index_backend="chroma")
    monkeypatch.setitem(sys.modules, "chromadb", None)         # import levanta ImportError
    with pytest.raises(RuntimeError, match=r"delegation-core\[chroma\].*index-migrate"):
        index_lock.abrir_cliente(cfg)


def test_o_runtime_do_sqlite_nao_importa_chromadb(tmp_path):
    """O caminho de busca e escrita nao pode puxar o chromadb de volta."""
    import subprocess
    codigo = (
        "import sys; sys.modules['chromadb'] = None\n"
        "import numpy as np\n"
        "from delegation_core.config import Config\n"
        "from delegation_core.index_lock import abrir_cliente\n"
        "from delegation_core.embeddings import EmbedderSentenceTransformer\n"
        "cfg = Config(vault_path=sys.argv[1])\n"
        "c = abrir_cliente(cfg).get_or_create_collection('c', metadata={'hnsw:space': 'cosine'})\n"
        "c.upsert(ids=['a'], embeddings=[[1.0, 0.0]], documents=['x'])\n"
        "assert c.query(query_embeddings=[[1.0, 0.0]], n_results=1)['ids'] == [['a']]\n"
        "print('ok sem chromadb')\n")
    import os
    p = subprocess.run([sys.executable, "-c", codigo, str(tmp_path / "v")], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)))
    assert p.returncode == 0 and "ok sem chromadb" in p.stdout, p.stderr[-400:]


# -- index-migrate: quem nao pediu para trocar fica onde estava -------------------

def _rodar_migrate(tmp_path, monkeypatch, ativar, backend_inicial=""):
    from types import SimpleNamespace
    from delegation_core import cli, migracao_indice
    cfg = _cfg(tmp_path, index_backend=backend_inicial)
    salvos = []
    monkeypatch.setattr(Config, "load", classmethod(lambda c: cfg))
    monkeypatch.setattr(Config, "is_configured", lambda self: True)
    monkeypatch.setattr(Config, "save", lambda self: salvos.append(self.index_backend))
    monkeypatch.setattr(migracao_indice, "migrar", lambda *a, **k: {
        "verificacao": {"colecoes": {"c": {"linhas_destino": 3}}}, "exportacao": "/x"})
    cli.cmd_index_migrate(SimpleNamespace(origem=None, amostra=5, force=False, ativar=ativar))
    return cfg, salvos


def test_migrar_sem_ativar_fixa_o_chroma_para_o_sqlite_novo_nao_assumir_sozinho(tmp_path, monkeypatch):
    cfg, salvos = _rodar_migrate(tmp_path, monkeypatch, ativar=False)
    assert cfg.index_backend == "chroma" and salvos == ["chroma"]


def test_migrar_sem_ativar_respeita_uma_escolha_explicita(tmp_path, monkeypatch):
    cfg, salvos = _rodar_migrate(tmp_path, monkeypatch, ativar=False, backend_inicial="sqlite")
    assert cfg.index_backend == "sqlite" and salvos == []


def test_migrar_com_ativar_grava_sqlite(tmp_path, monkeypatch):
    cfg, salvos = _rodar_migrate(tmp_path, monkeypatch, ativar=True)
    assert cfg.index_backend == "sqlite" and salvos == ["sqlite"]
