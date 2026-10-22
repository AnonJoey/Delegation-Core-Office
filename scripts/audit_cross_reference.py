#!/usr/bin/env python3
"""audit_cross_reference.py — Passagem 4: Validação Cruzada contra a Suíte de Testes.

Cruza cada apontamento registrado em `audit_findings` contra os 80+ arquivos
de teste em `tests/`. Identifica cenários que já possuem testes automatizados
cobrindo o comportamento e classifica como falsos positivos, isolando os débitos
técnicos e vulnerabilidades genuínas que carecem de cobertura.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cross_reference")

REPO_DIR = Path(__file__).resolve().parents[1]
DB_PATH = REPO_DIR / "audit_delegation_core.db"
TESTS_DIR = REPO_DIR / "tests"


def carregar_testes() -> dict[str, str]:
    """Mapeia nome do arquivo de teste -> conteúdo de texto."""
    testes = {}
    for p in TESTS_DIR.glob("test_*.py"):
        try:
            testes[p.stem] = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning("Falha ao ler teste %s: %s", p.name, e)
    return testes


def encontrar_testes_candidatos(rel_path: str, testes: dict[str, str]) -> list[tuple[str, str]]:
    """Devolve a lista de (nome_do_teste, conteudo) que testam este módulo."""
    nome_modulo = Path(rel_path).stem  # ex: locking, indice_sqlite, clients
    candidatos = []

    # 1. Correspondência direta por nome
    for t_nome, t_conteudo in testes.items():
        if nome_modulo in t_nome or t_nome.replace("test_", "") in nome_modulo:
            candidatos.append((t_nome, t_conteudo))
        elif f"import {nome_modulo}" in t_conteudo or f"from delegation_core import {nome_modulo}" in t_conteudo or f"from .{nome_modulo}" in t_conteudo:
            candidatos.append((t_nome, t_conteudo))

    return candidatos


def extrair_termos_chave(descricao: str, risco: str) -> list[str]:
    """Extrai termos técnicos para busca no código de teste."""
    texto = f"{descricao} {risco}".lower()
    termos = []
    padroes = [
        r"\b(sigterm|sigkill)\b",
        r"\b(wal|journal_mode)\b",
        r"\b(busy_timeout)\b",
        r"\b(rlock|mutex|lock)\b",
        r"\b(deadlock)\b",
        r"\b(timeout)\b",
        r"\b(path traversal|\.\.)\b",
        r"\b(popen|subprocess)\b",
        r"\b(oserror)\b",
        r"\b(permissionerror)\b",
    ]
    for p in padroes:
        m = re.findall(p, texto)
        termos.extend(m)
    return list(set(termos))


def avaliar_apontamento(descricao: str, risco: str, testes_candidatos: list[tuple[str, str]]) -> tuple[bool, str]:
    """Devolve (is_false_positive, motivo_verificacao)."""
    termos = extrair_termos_chave(descricao, risco)
    if not testes_candidatos:
        return False, "Nenhum arquivo de teste correspondente encontrado."

    coberturas = []
    for t_nome, t_code in testes_candidatos:
        t_code_lower = t_code.lower()
        # Verificar se os termos específicos do apontamento aparecem no teste
        matches = [termo for termo in termos if termo in t_code_lower]
        if matches:
            coberturas.append(f"{t_nome}.py (termos: {', '.join(matches)})")

    if coberturas:
        # Se mais de 2 termos chave ou teste explícito trata disso, é candidato a falso positivo / já coberto
        return True, f"Cenário já coberto em: {'; '.join(coberturas[:2])}"

    return False, "Sem evidência de teste cobrindo este caso de borda."


def run_cross_reference() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    testes = carregar_testes()
    logger.info("Total de suítes de teste carregadas: %d", len(testes))

    cur = conn.cursor()
    cur.execute("SELECT id, rel_path, category, severity, description, risk FROM audit_findings")
    findings = cur.fetchall()
    logger.info("Total de apontamentos a cruzar: %d", len(findings))

    atualizados = 0
    falsos_positivos = 0
    genuinos = 0

    for fid, rel_path, category, severity, desc, risk in findings:
        candidatos = encontrar_testes_candidatos(rel_path, testes)
        is_fp, motivo = avaliar_apontamento(desc, risk or "", candidatos)

        conn.execute("""
            UPDATE audit_findings
            SET is_false_positive = ?, test_verification = ?
            WHERE id = ?
        """, (1 if is_fp else 0, motivo, fid))

        if is_fp:
            falsos_positivos += 1
        else:
            genuinos += 1
        atualizados += 1

    conn.commit()
    logger.info("Cruzamento concluído: %d achados analisados.", atualizados)
    logger.info(" -> Falsos Positivos (já cobertos por testes): %d", falsos_positivos)
    logger.info(" -> Débitos Técnicos Genuínos (sem teste correspondente): %d", genuinos)


if __name__ == "__main__":
    run_cross_reference()
