"""O escopo `notes+external`: tudo menos os artigos gerados pelos grafos.

Ate 05/10/2026 o padrao adaptativo caia em 'notes' quando os artigos gerados
eram maioria. O filtro de 'notes' e `kind == "note"`, entao ele tirava os
artigos gerados, que era o objetivo, e todo arquivo ingerido junto, que nao era.
Medido naquele dia, 12 perguntas com resposta conhecida: 5 acertos em 'notes',
8 em 'all' (que perdia para artigos gerados) e 9 sem os gerados e nada mais.

O filtro novo e `kind != "generated"`. Ele depende de o ChromaDB devolver, num
`$ne`, as linhas que NAO tem o campo: os trechos ingeridos e as notas antigas
nao carregam `kind`. Isso foi conferido no ChromaDB 1.5.9 e fica preso aqui,
contra o ChromaDB de verdade, para que uma versao que mude essa semantica
quebre o teste e nao a busca de quem usa.
"""

import pytest

from delegation_core.config import Config
from delegation_core.vault import VaultManager


class _Embedder:
    """Vetores deterministicos de saco de palavras: sem modelo, sem GPU."""

    def __call__(self, input):
        out = []
        for text in input:
            v = [0.0] * 16
            for w in str(text).lower().split():
                v[hash(w) % 16] += 1.0
            n = sum(x * x for x in v) ** 0.5 or 1.0
            out.append([x / n for x in v])
        return out

    def embed_documents(self, input):
        return self(input)

    def embed_query(self, input):
        if isinstance(input, str):
            return self([input])[0]
        return self(list(input))

    def name(self):
        return "probe"


@pytest.fixture
def vm(tmp_path):
    import chromadb
    cfg = Config(vault_path=str(tmp_path), vault_folders=["Notes", "Reference"],
                 search_threshold=0.0)
    (tmp_path / "Notes").mkdir()
    v = VaultManager(cfg)
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    v.collection = client.get_or_create_collection(
        "probe_escopo", embedding_function=_Embedder(),
        metadata={"hnsw:space": "cosine"})
    v._initialized = True
    v._disk_state = None
    v._read_disk_state = lambda: None
    v._ensure_ready = lambda: None
    return v


TEXTO = "contato da anthropic no dreamforce"


def _nota(vm, rel):
    vm.index_note(TEXTO, vm.note_metadata(rel, rel, rel.split("/")[0], TEXTO))


def _externo(vm, caminho):
    vm.index_note(TEXTO, {"title": "doc", "path": caminho, "folder": "_external",
                          "is_external": "true"}, doc_id=caminho)


def _legado(vm, rel):
    """Linha escrita antes de `kind` existir: sem marcador nenhum."""
    vm.collection.upsert(ids=[rel], documents=[TEXTO],
                         metadatas=[{"title": "legado", "path": rel, "folder": "Notes"}])


@pytest.fixture
def povoado(vm):
    _nota(vm, "Notes/escrita.md")
    _nota(vm, "Reference/graphs/projeto/artigo.md")
    _externo(vm, "/home/u/Carreira/03 - ALVO.md")
    _legado(vm, "Notes/antiga.md")
    return vm


def _caminhos(vm, escopo):
    return sorted(h["path"] for h in vm.search(TEXTO, limit=10, scope=escopo))


def test_a_nota_gerada_e_mesmo_marcada_como_gerada(povoado):
    """Sem isto os outros testes provariam pouco: o artigo precisa sair do
    filtro por ser gerado, e nao por acaso."""
    linhas = povoado.collection.get(include=["metadatas"])
    por_caminho = {m["path"]: m.get("kind") for m in linhas["metadatas"]}
    assert por_caminho["Reference/graphs/projeto/artigo.md"] == "generated"
    assert "kind" not in {k for m in linhas["metadatas"]
                          if m["path"] == "/home/u/Carreira/03 - ALVO.md" for k in m}


def test_notes_e_externos_tira_so_os_gerados(povoado):
    assert _caminhos(povoado, "notes+external") == [
        "/home/u/Carreira/03 - ALVO.md", "Notes/antiga.md", "Notes/escrita.md"]


def test_o_externo_sem_kind_entra(povoado):
    """O caso que motivou o escopo: arquivo ingerido, que nao carrega `kind`."""
    assert "/home/u/Carreira/03 - ALVO.md" in _caminhos(povoado, "notes+external")


def test_notes_continua_escondendo_o_externo(povoado):
    """O escopo antigo nao muda de significado; so deixa de ser o padrao."""
    assert "/home/u/Carreira/03 - ALVO.md" not in _caminhos(povoado, "notes")


def test_all_continua_trazendo_o_gerado(povoado):
    assert "Reference/graphs/projeto/artigo.md" in _caminhos(povoado, "all")
