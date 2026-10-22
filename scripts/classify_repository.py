#!/usr/bin/env python3
"""
classify_repository.py — Classificação e Agrupamento Funcional do delegation-core via LLM Remota (Qwen-14B).
Varre o repositório via AST, envia módulos e funções para o servidor local (10.42.0.73:8181) e
persiste a taxonomia completa em SQLite e Markdown.
"""

import ast
import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any

REPO_ROOT = Path("/home/joey/Projects/delegation-core")
SRC_DIR = REPO_ROOT / "src" / "delegation_core"
DB_PATH = REPO_ROOT / "repo_classification.db"
LLAMA_URL = os.environ.get("LLAMA_API_URL", "http://10.42.0.73:8181/v1/chat/completions")

SYSTEM_PROMPT = """Você é um Arquiteto de Software Principal especialista no framework delegation-core.
Sua tarefa é analisar os módulos Python fornecidos e suas respectivas funções/métodos (extraídos via AST),
classificando-os rigorosamente por domínio funcional de arquitetura e por categoria de papel técnico.

DOMÍNIOS FUNCIONAIS PADRÃO:
1. "Core & Daemon" — Bootstrap, ciclo de vida do processo, daemon systemd/launchd, controle de sinais e shutdown.
2. "MCP Protocol & Server" — Implementação da especificação MCP, despacho de ferramentas (tools), transporte SSE/stdio.
3. "Vault & Storage" — Acesso ao Obsidian Vault, operações de CRUD de notas, manipulação de frontmatter e arquivos.
4. "Search & Embeddings" — Busca vetorial SQLite, embeddings neurais (BGE / llama.cpp / MLX), busca híbrida e semântica.
5. "Knowledge Graph & AST" — Extração sintática (Tree-sitter), clustering Leiden, grafo de conhecimento de código e exportadores.
6. "Queue & Background Tasks" — Fila de execução de tarefas assíncronas, workers em background, locks e concorrência.
7. "Dashboard & Telemetry" — Servidor web do dashboard, métricas do vault, telemetria de integridade e endpoints de visualização.
8. "Security & Auth" — Autenticação de tokens bearer, sanitização de paths, validação de segurança e sandbox.
9. "CLI & Management" — Linha de comando (CLI), utilitários de administração, comandos de setup e doctor/diagnósticos.
10. "Hooks & Integrations" — Hooks de Git/editor, plugins de IDE e integrações com o sistema hospedeiro.
11. "Utilities & Helpers" — Utilitários de parsing, manipulação de texto, formatação e logging comum.

CATEGORIAS DE PAPEL DA FUNÇÃO (role_category):
- "Orquestração / Lifecycle"
- "Handler MCP / Endpoint"
- "Leitura / Consulta"
- "Mutação / Escrita"
- "Parser / AST / Extração"
- "Validação / Segurança"
- "Cálculo / Algoritmo"
- "Utilitário / Helper"

RETORNE ESTRITAMENTE UM JSON no formato:
{
  "modules": [
    {
      "module_path": "caminho/relativo.py",
      "domain": "Nome do Domínio Funcional",
      "module_summary": "Resumo técnico de 1 a 2 frases da responsabilidade do módulo",
      "functions": [
        {
          "name": "nome_da_funcao",
          "parent": "NomeDaClasse ou top_level",
          "role_category": "Categoria de Papel",
          "description": "Explicação técnica concisa do que a função faz (1 frase)"
        }
      ]
    }
  ]
}
"""

def init_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS modules (
        module_path TEXT PRIMARY KEY,
        domain TEXT NOT NULL,
        module_summary TEXT,
        loc INTEGER,
        classes_count INTEGER,
        functions_count INTEGER,
        updated_at REAL
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS functions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        module_path TEXT NOT NULL,
        function_name TEXT NOT NULL,
        parent TEXT NOT NULL,
        role_category TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY(module_path) REFERENCES modules(module_path)
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_func_module ON functions(module_path);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_func_role ON functions(role_category);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mod_domain ON modules(domain);")
    conn.commit()
    conn.close()

def extract_ast_metadata(filepath: Path, src_dir: Path) -> Dict[str, Any]:
    rel_path = str(filepath.relative_to(src_dir))
    content = filepath.read_text(encoding="utf-8", errors="replace")
    loc = len(content.splitlines())
    
    try:
        tree = ast.parse(content)
        doc = ast.get_docstring(tree) or ""
    except Exception as e:
        return {
            "module_path": rel_path,
            "docstring": f"Syntax error: {e}",
            "loc": loc,
            "classes": [],
            "top_level_functions": []
        }

    classes = []
    top_level_functions = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            f_doc = ast.get_docstring(node) or ""
            top_level_functions.append({
                "name": node.name,
                "doc": f_doc.split("\n")[0] if f_doc else ""
            })
        elif isinstance(node, ast.ClassDef):
            c_doc = ast.get_docstring(node) or ""
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_doc = ast.get_docstring(item) or ""
                    methods.append({
                        "name": item.name,
                        "doc": m_doc.split("\n")[0] if m_doc else ""
                    })
            classes.append({
                "name": node.name,
                "doc": c_doc.split("\n")[0] if c_doc else "",
                "methods": methods
            })

    return {
        "module_path": rel_path,
        "docstring": doc.split("\n")[0] if doc else "",
        "loc": loc,
        "classes": classes,
        "top_level_functions": top_level_functions
    }

def call_remote_classifier(batch: List[Dict[str, Any]], timeout: int = 120) -> Dict[str, Any]:
    user_content = "Classifique os seguintes módulos e suas funções:\n" + json.dumps(batch, indent=2, ensure_ascii=False)
    
    payload = {
        "model": "qwen",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }

    req = urllib.request.Request(
        LLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        raw_msg = data["choices"][0]["message"]["content"]
        return json.loads(raw_msg)

def save_classifications(db_path: Path, result: Dict[str, Any], batch_meta: List[Dict[str, Any]]):
    meta_lookup = {m["module_path"]: m for m in batch_meta}
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    modules_data = result.get("modules", [])
    now = time.time()

    for mod in modules_data:
        mpath = mod.get("module_path")
        if not mpath or mpath not in meta_lookup:
            continue
        
        meta = meta_lookup[mpath]
        domain = mod.get("domain", "Utilities & Helpers")
        summary = mod.get("module_summary", meta.get("docstring", ""))
        loc = meta["loc"]
        classes_cnt = len(meta["classes"])
        total_funcs = len(meta["top_level_functions"]) + sum(len(c["methods"]) for c in meta["classes"])

        cur.execute("""
        INSERT OR REPLACE INTO modules (module_path, domain, module_summary, loc, classes_count, functions_count, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (mpath, domain, summary, loc, classes_cnt, total_funcs, now))

        cur.execute("DELETE FROM functions WHERE module_path = ?", (mpath,))

        for f in mod.get("functions", []):
            cur.execute("""
            INSERT INTO functions (module_path, function_name, parent, role_category, description)
            VALUES (?, ?, ?, ?, ?)
            """, (mpath, f.get("name", "unknown"), f.get("parent", "top_level"), f.get("role_category", "Utilitário / Helper"), f.get("description", "")))

    conn.commit()
    conn.close()

def build_batches(modules_meta: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    batches = []
    current_batch = []
    current_funcs = 0

    for m in modules_meta:
        m_funcs = len(m["top_level_functions"]) + sum(len(c["methods"]) for c in m["classes"])
        if m_funcs > 25:
            # Módulo grande vai isolado
            batches.append([m])
            continue
        
        if current_batch and (current_funcs + m_funcs > 35 or len(current_batch) >= 5):
            batches.append(current_batch)
            current_batch = [m]
            current_funcs = m_funcs
        else:
            current_batch.append(m)
            current_funcs += m_funcs

    if current_batch:
        batches.append(current_batch)
    return batches

def main():
    init_db(DB_PATH)
    
    # Verificar o que já foi processado
    conn = sqlite3.connect(DB_PATH)
    processed = set(r[0] for r in conn.execute("SELECT module_path FROM modules").fetchall())
    conn.close()

    py_files = sorted([p for p in SRC_DIR.rglob("*.py") if "__pycache__" not in p.parts])
    all_meta = [extract_ast_metadata(f, SRC_DIR) for f in py_files]
    
    pending_meta = [m for m in all_meta if m["module_path"] not in processed]
    print(f"Total de módulos encontrados: {len(all_meta)}")
    print(f"Módulos já classificados: {len(processed)}")
    print(f"Módulos pendentes: {len(pending_meta)}")

    if not pending_meta:
        print("Todos os módulos já foram classificados!")
        return

    batches = build_batches(pending_meta)
    print(f"Lotes para processar: {len(batches)}")

    completed_modules = len(processed)
    total_modules = len(all_meta)

    def process_batch(idx, batch):
        m_names = [m["module_path"] for m in batch]
        t0 = time.time()
        try:
            res = call_remote_classifier(batch)
            save_classifications(DB_PATH, res, batch)
            dt = time.time() - t0
            return (True, idx, m_names, dt, None)
        except Exception as e:
            dt = time.time() - t0
            return (False, idx, m_names, dt, str(e))

    # Executar com pool de 3 threads
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_batch, i, b): (i, b) for i, b in enumerate(batches)}
        for fut in as_completed(futures):
            ok, idx, m_names, dt, err = fut.result()
            if ok:
                completed_modules += len(m_names)
                print(f"[OK] Lote {idx+1}/{len(batches)} ({len(m_names)} módulos: {', '.join(m_names[:2])}...) em {dt:.2f}s | Progresso: {completed_modules}/{total_modules}")
            else:
                print(f"[ERRO] Lote {idx+1}/{len(batches)} falhou em {dt:.2f}s: {err}")

    print("\nClassificação concluída com sucesso!")

if __name__ == "__main__":
    main()
