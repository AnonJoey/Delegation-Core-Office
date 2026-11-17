"""Link para documento que vive fora do vault nao pode contar como quebrado.

## O caso real, medido em 26/09/2026

As memorias do Claude Code ficam em `~/.claude/projects/<projeto>/memory/` e sao
linkadas das notas do vault por `[[feedback_measure_dont_deduce]]` e afins. O
vault nunca resolveu esses alvos, entao eles contavam como quebrados para
sempre.

`vault_health_detail()` naquele dia: **9 links quebrados, e os 9 eram isso**,
apontando para quatro arquivos de memoria que existem e estao corretos. Ou
seja, o numero de saude do vault era inteiramente falso positivo.

## O desenho, e por que o padrao e vazio

`external_link_dirs` comeca vazia: quem nao configura nao muda de
comportamento, e o projeto nao sai adivinhando caminho de ferramenta alheia.

A resolucao mora em `notes.py` e nao no `vault.py` por duas razoes: este modulo
ja e o dono das regras de wikilink, e o `vault.py` tem guarda de tamanho em
1800 linhas que existe justamente para nao deixa-lo voltar a crescer. A guarda
pegou esta mudanca, e a resposta foi mover, nao afrouxar.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from delegation_core.config import Config
from delegation_core.notes import alias_link_targets, external_link_targets
from delegation_core.vault import VaultManager


@pytest.fixture
def memorias(tmp_path) -> Path:
    """Um diretorio de memorias com a cara do real."""
    d = tmp_path / "memory"
    d.mkdir()
    (d / "feedback_measure_dont_deduce.md").write_text("# medir", encoding="utf-8")
    (d / "reference_shell_pgrep_self_match.md").write_text("# pgrep", encoding="utf-8")
    return d


def test_sem_configurar_nada_muda(memorias):
    """O padrao vazio e o contrato: instalacao que nao configura nao muda."""
    assert external_link_targets([]) == {}
    assert external_link_targets(None) == {}


def test_o_alvo_da_memoria_passa_a_resolver(memorias):
    alvos = external_link_targets([str(memorias)])
    assert "feedback_measure_dont_deduce" in alvos
    assert "reference_shell_pgrep_self_match" in alvos


def test_diretorio_inexistente_nao_levanta():
    """Caminho velho no config nao pode derrubar a saude do vault inteiro."""
    assert external_link_targets(["/nao/existe/mesmo"]) == {}


def test_o_til_e_expandido(monkeypatch, tmp_path):
    """O usuario escreve `~/.claude/...` no config, nao o caminho absoluto."""
    monkeypatch.setenv("HOME", str(tmp_path))
    d = tmp_path / "mem"
    d.mkdir()
    (d / "user_quem_e_o_jordan.md").write_text("x", encoding="utf-8")
    assert "user_quem_e_o_jordan" in external_link_targets(["~/mem"])


def test_a_nota_do_vault_vence_o_homonimo_externo(tmp_path, memorias):
    """Se os dois existirem com o mesmo nome, o vault manda.

    `setdefault` faz o primeiro a entrar vencer, e o vault e varrido antes.
    Inverter a ordem faria um arquivo externo sequestrar o alvo de uma nota
    real, que e pior que o problema que este campo resolve.
    """
    vault = tmp_path / "vault"
    (vault / "Reference").mkdir(parents=True)
    dentro = vault / "Reference" / "feedback_measure_dont_deduce.md"
    dentro.write_text("# a nota de verdade", encoding="utf-8")

    cfg = Config(vault_path=str(vault), vault_folders=["Reference"],
                 external_link_dirs=[str(memorias)])
    vm = VaultManager(cfg)
    alvos = vm.resolvable_link_targets()

    assert alvos["feedback_measure_dont_deduce"] == dentro, (
        "o arquivo externo sequestrou o alvo de uma nota do vault")


def test_a_resolucao_do_vault_consulta_os_diretorios_externos(tmp_path, memorias):
    """A LIGACAO, e nao a funcao.

    Um campo de `Config` que nao chega a quem usa nao faz nada, e este repo ja
    tem historico disso: `embed_max_seq_length` e `embed_batch_size` existiram
    inertes ate alguem passa-los adiante.

    Conferido por mutacao: tirar a chamada de `resolvable_link_targets` derruba
    este teste.
    """
    vault = tmp_path / "vault"
    (vault / "Reference").mkdir(parents=True)
    (vault / "Reference" / "uma nota.md").write_text("# oi", encoding="utf-8")

    sem = VaultManager(Config(vault_path=str(vault), vault_folders=["Reference"]))
    assert "feedback_measure_dont_deduce" not in sem.resolvable_link_targets()

    com = VaultManager(Config(vault_path=str(vault), vault_folders=["Reference"],
                              external_link_dirs=[str(memorias)]))
    assert "feedback_measure_dont_deduce" in com.resolvable_link_targets()


def test_aliases_continuam_resolvendo_depois_da_mudanca(tmp_path):
    """O laco de aliases mudou de arquivo nesta mesma fatia; guarda de regressao.

    Mover codigo para caber numa guarda de tamanho e exatamente o momento em
    que algo se perde no caminho.
    """
    vault = tmp_path / "vault"
    (vault / "Decisions").mkdir(parents=True)
    (vault / "Decisions" / "2026-01-01-nota.md").write_text(
        "---\naliases:\n  - Command Center\n---\n\ncorpo\n", encoding="utf-8")

    alvos = alias_link_targets(vault, ["Decisions"])
    assert "command center" in alvos

    vm = VaultManager(Config(vault_path=str(vault), vault_folders=["Decisions"]))
    assert "command center" in vm.resolvable_link_targets()
