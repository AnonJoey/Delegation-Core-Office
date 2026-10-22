#!/usr/bin/env python3
"""audit_pipeline.py — Pipeline de Auditoria Sequencial Multi-Passagem para o Delegation-Core.

Inspirado no harness de alta resiliência do `vault_fast_refiner.py` e nos conceitos
de checkpoint/tolerância a falhas do `batch_runner.py` (Hermes).

Mapeia a ordem de criticidade dos módulos via grafo de código (Graphify),
persiste o progresso de forma atômica em SQLite (WAL) e submete cada arquivo
a passagens de análise técnica especializada via endpoint de inferência (Qwen 14B / llama-server).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("audit_pipeline")

DEFAULT_API_URL = "http://10.42.0.73:8181/v1/chat/completions"
LOCAL_FALLBACK_API_URL = "http://127.0.0.1:8181/v1/chat/completions"
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "audit_delegation_core.db"
DEFAULT_SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "delegation_core"
DEFAULT_TESTS_DIR = Path(__file__).resolve().parents[1] / "tests"

PASS_1_PROMPT = """Você é um Engenheiro Sênior de Sistemas, Concorrência e Banco de Dados.
Sua missão é auditar o módulo Python fornecido EXCLUSIVAMENTE sob a ótica de:
1. Concorrência e Threads: Race conditions, compartilhamento indevido de estado mutável sem lock, threads que não respondem ao SIGTERM do systemd.
2. Persistência SQLite: Uso correto de modo WAL, busy_timeout, contenção de transações de escrita e escape de conexões abertas.
3. Locks e Descritores: Locks aninhados que possam causar deadlock, vazamento de file descriptors ou descritores de socket.

Ignore estilo, formatação e convenções estéticas. Aponte apenas riscos técnicos concretos.
Responda ESTRITAMENTE em formato JSON com o seguinte schema:
{
  "pass_id": 1,
  "category": "concorrencia_e_persistencia",
  "findings": [
    {
      "severity": "ALTA" | "MEDIA" | "BAIXA",
      "line_hint": <numero_aproximado_da_linha>,
      "description": "<descricao factual e concisa do problema>",
      "code_snippet": "<trecho do codigo relevante>",
      "risk": "<o que falha em producao>"
    }
  ]
}
Se não houver problemas, retorne {"pass_id": 1, "category": "concorrencia_e_persistencia", "findings": []}.
"""

PASS_2_PROMPT = """Você é um Arquiteto de Software especialista no protocolo MCP (Model Context Protocol) e APIs FastMCP.
Sua missão é auditar o módulo Python fornecido EXCLUSIVAMENTE sob a ótica de:
1. Contratos de Ferramentas: Validação rigorosa de parâmetros, tipos primitivos vs. objetos, defaults e campos obrigatórios.
2. Sanitização e Escape: Riscos de injeção em caminhos de arquivos (path traversal), subprocessos não sanitizados ou payloads Markdown/HTML que quebrem renderização.
3. Tratamento de Payload e Schemas Lazy: Compatibilidade com ferramentas carregadas dinamicamente e limites de tamanho de resposta.

Ignore estilo, formatação e convenções estéticas. Aponte apenas riscos técnicos concretos de contrato e segurança.
Responda ESTRITAMENTE em formato JSON com o seguinte schema:
{
  "pass_id": 2,
  "category": "protocolo_mcp_e_contratos",
  "findings": [
    {
      "severity": "ALTA" | "MEDIA" | "BAIXA",
      "line_hint": <numero_aproximado_da_linha>,
      "description": "<descricao factual e concisa do problema>",
      "code_snippet": "<trecho do codigo relevante>",
      "risk": "<o que falha em producao>"
    }
  ]
}
Se não houver problemas, retorne {"pass_id": 2, "category": "protocolo_mcp_e_contratos", "findings": []}.
"""

PASS_3_PROMPT = """Você é um Engenheiro de Confiabilidade de Software (SRE) e Resiliência.
Sua missão é auditar o módulo Python fornecido EXCLUSIVAMENTE sob a ótica de:
1. Timeouts de Operação: Chamadas de rede, subprocessos, IPC ou sockets bloqueantes sem timeout explícito.
2. Tratamento de Exceções: Cláusulas `except Exception: pass` silenciosas que mascaram estados corrompidos, ou exceções não capturadas que derrubam o daemon principal.
3. Degradação Graciosa: Recuperação diante de arquivos ausentes, índices corrompidos ou desconexão transitória de modelos locais.

Ignore estilo, formatação e convenções estéticas. Aponte apenas riscos de travamento ou crash.
Responda ESTRITAMENTE em formato JSON com o seguinte schema:
{
  "pass_id": 3,
  "category": "resiliencia_e_excecoes",
  "findings": [
    {
      "severity": "ALTA" | "MEDIA" | "BAIXA",
      "line_hint": <numero_aproximado_da_linha>,
      "description": "<descricao factual e concisa do problema>",
      "code_snippet": "<trecho do codigo relevante>",
      "risk": "<o que falha em producao>"
    }
  ]
}
Se não houver problemas, retorne {"pass_id": 3, "category": "resiliencia_e_excecoes", "findings": []}.
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_progress (
            rel_path TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            lines_count INTEGER NOT NULL,
            pass_1_status TEXT DEFAULT 'pending',
            pass_2_status TEXT DEFAULT 'pending',
            pass_3_status TEXT DEFAULT 'pending',
            updated_at REAL NOT NULL
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rel_path TEXT NOT NULL,
            pass_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            line_hint INTEGER,
            description TEXT NOT NULL,
            code_snippet TEXT,
            risk TEXT,
            created_at REAL NOT NULL
        );
    """)
    conn.commit()
    return conn


def calculate_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call_llm(api_url: str, system_prompt: str, user_prompt: str, timeout: int = 180) -> dict[str, Any]:
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
    except urllib.error.URLError as e:
        logger.error("Erro ao conectar ao endpoint %s: %s", api_url, e)
        raise
    except (json.JSONDecodeError, KeyError) as e:
        logger.error("Resposta inválida do modelo: %s", e)
        raise ValueError(f"Resposta inválida de LLM: {e}") from e


def get_target_files(src_dir: Path) -> list[Path]:
    files = [f for f in src_dir.rglob("*.py") if f.is_file() and not f.name.startswith("__")]
    # Ordenar por tamanho (módulos maiores/mais complexos primeiro)
    files.sort(key=lambda p: p.stat().st_size, reverse=True)
    return files


def chunk_code(code: str, max_lines: int = 500, overlap: int = 40) -> list[tuple[int, int, str]]:
    lines = code.splitlines()
    if len(lines) <= max_lines:
        return [(1, len(lines), code)]
    
    chunks = []
    start = 0
    while start < len(lines):
        end = min(start + max_lines, len(lines))
        chunk_str = "\n".join(lines[start:end])
        chunks.append((start + 1, end, chunk_str))
        if end >= len(lines):
            break
        start += max_lines - overlap
    return chunks


def run_pipeline(
    src_dir: Path,
    db_path: Path,
    api_url: str,
    dry_run: bool = False,
    single_module: str | None = None,
) -> None:
    conn = init_db(db_path)
    files = get_target_files(src_dir)

    if single_module:
        files = [f for f in files if single_module in f.name]
        if not files:
            logger.error("Nenhum módulo encontrado correspondente a '%s'", single_module)
            return

    logger.info("Total de módulos elegíveis para auditoria: %d", len(files))

    for f in files:
        rel_path = str(f.relative_to(src_dir.parent.parent))
        sha = calculate_sha256(f)
        code = f.read_text(encoding="utf-8", errors="replace")
        lines_count = len(code.splitlines())
        chunks = chunk_code(code, max_lines=550)

        cur = conn.cursor()
        cur.execute("SELECT sha256, pass_1_status, pass_2_status, pass_3_status FROM audit_progress WHERE rel_path = ?", (rel_path,))
        row = cur.fetchone()

        if row and row[0] == sha and all(s == "done" for s in row[1:4]):
            logger.info("Módulo %s já auditado (hash inalterado). Pulando.", rel_path)
            continue

        if not row:
            conn.execute(
                "INSERT INTO audit_progress (rel_path, sha256, lines_count, updated_at) VALUES (?, ?, ?, ?)",
                (rel_path, sha, lines_count, time.time()),
            )
            conn.commit()

        logger.info("Auditando %s (%d linhas, %d bloco(s))", rel_path, lines_count, len(chunks))

        if dry_run:
            logger.info("[DRY-RUN] Módulo enfileirado: %s", rel_path)
            continue

        passes = [
            (1, "pass_1_status", PASS_1_PROMPT),
            (2, "pass_2_status", PASS_2_PROMPT),
            (3, "pass_3_status", PASS_3_PROMPT),
        ]

        module_failed = False
        for pass_id, col_name, sys_prompt in passes:
            cur.execute(f"SELECT {col_name} FROM audit_progress WHERE rel_path = ?", (rel_path,))
            status_row = cur.fetchone()
            if status_row and status_row[0] == "done":
                continue

            for idx, (l_start, l_end, c_text) in enumerate(chunks, 1):
                part_tag = f" [bloco {idx}/{len(chunks)} L{l_start}-L{l_end}]" if len(chunks) > 1 else ""
                user_prompt = f"MÓDULO: {rel_path}{part_tag}\nLINHAS: {l_start} a {l_end} (total {lines_count})\n\nCÓDIGO FONTE:\n```python\n{c_text}\n```"
                logger.info("Executando Passagem %d para %s%s...", pass_id, rel_path, part_tag)
                
                success = False
                for tentativa in range(1, 3):
                    try:
                        result = call_llm(api_url, sys_prompt, user_prompt, timeout=180)
                        findings = result.get("findings", [])
                        category = result.get("category", f"pass_{pass_id}")

                        for item in findings:
                            conn.execute("""
                                INSERT INTO audit_findings (rel_path, pass_id, category, severity, line_hint, description, code_snippet, risk, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                rel_path,
                                pass_id,
                                category,
                                item.get("severity", "MEDIA"),
                                item.get("line_hint") or l_start,
                                item.get("description", ""),
                                item.get("code_snippet", ""),
                                item.get("risk", ""),
                                time.time(),
                            ))
                        conn.commit()
                        success = True
                        break
                    except Exception as ex:
                        logger.warning("Tentativa %d falhou na Passagem %d para %s: %s", tentativa, pass_id, rel_path, ex)
                        time.sleep(2)

                if not success:
                    module_failed = True
                    conn.execute(f"UPDATE audit_progress SET {col_name} = 'error', updated_at = ? WHERE rel_path = ?", (time.time(), rel_path))
                    conn.commit()
                    break

            if module_failed:
                break
            else:
                conn.execute(f"UPDATE audit_progress SET {col_name} = 'done', updated_at = ? WHERE rel_path = ?", (time.time(), rel_path))
                conn.commit()
                logger.info("Passagem %d concluída com sucesso para %s", pass_id, rel_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de Auditoria Sequencial Multi-Passagem (Delegation-Core)")
    parser.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR, help="Diretório de código fonte")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Caminho do banco SQLite de controle")
    parser.add_argument("--api-url", type=str, default=DEFAULT_API_URL, help="Endpoint OpenAI-compatível de inferência")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mapeia arquivos e estado sem disparar inferência")
    parser.add_argument("--module", type=str, help="Filtra e executa apenas para um módulo específico")
    args = parser.parse_args()

    run_pipeline(
        src_dir=args.src_dir,
        db_path=args.db_path,
        api_url=args.api_url,
        dry_run=args.dry_run,
        single_module=args.module,
    )


if __name__ == "__main__":
    main()
