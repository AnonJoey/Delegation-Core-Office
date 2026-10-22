#!/usr/bin/env python3
"""
generate_taxonomy_report.py — Consolidador de Taxonomia Funcional do Codebase delegation-core.
Lê o banco SQLite repo_classification.db e gera o documento Markdown completo
em docs/TAXONOMIA_ARQUITETURAL_E_FUNCOES.md.
"""

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path("/home/joey/Projects/delegation-core")
DB_PATH = REPO_ROOT / "repo_classification.db"
OUTPUT_PATH = REPO_ROOT / "docs" / "TAXONOMIA_ARQUITETURAL_E_FUNCOES.md"

def main():
    if not DB_PATH.exists():
        print(f"Erro: Banco {DB_PATH} não encontrado.")
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total_modules = cur.execute("SELECT count(*) FROM modules").fetchone()[0]
    total_functions = cur.execute("SELECT count(*) FROM functions").fetchone()[0]
    total_loc = cur.execute("SELECT sum(loc) FROM modules").fetchone()[0] or 0

    # Domínios
    domains_summary = cur.execute("""
        SELECT m.domain,
               count(DISTINCT m.module_path) as mod_count,
               sum(m.loc) as total_loc,
               (SELECT count(*) FROM functions f JOIN modules m2 ON f.module_path = m2.module_path WHERE m2.domain = m.domain) as func_count
        FROM modules m
        GROUP BY m.domain
        ORDER BY mod_count DESC, total_loc DESC
    """).fetchall()

    # Categorias de papel da função (role_category)
    roles_summary = cur.execute("""
        SELECT role_category, count(*) as cnt
        FROM functions
        GROUP BY role_category
        ORDER BY cnt DESC
    """).fetchall()

    lines = []
    lines.append("# Taxonomia Arquitetural e Catálogo Funcional do Codebase delegation-core")
    lines.append("")
    lines.append("- **Data da Catalogação**: 2026-10-22")
    lines.append("- **Motor de Inferência e Classificação**: Qwen2.5-Coder-14B-Instruct-Q4_K_M (Execução Local via GPU RTX 4070, 16.384 contexto)")
    lines.append("- **Escopo**: 100% dos módulos Python (`src/delegation_core`) mapeados via AST")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Visão Geral da Arquitetura")
    lines.append("")
    lines.append(f"O `delegation-core` é composto por **{total_modules} módulos Python**, totalizando **{total_loc:,} linhas de código** e **{total_functions:,} funções e métodos catalogados**.")
    lines.append("Todo o repositório foi decomposto em domínios de arquitetura de alta coesão e baixo acoplamento:")
    lines.append("")
    lines.append("| Domínio Funcional | Módulos | Funções / Métodos | Linhas de Código (LOC) | Proporção do Código |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for d in domains_summary:
        pct = (d['total_loc'] / total_loc) * 100 if total_loc else 0
        lines.append(f"| **{d['domain']}** | {d['mod_count']} | {d['func_count']} | {d['total_loc']:,} | {pct:.1f}% |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Distribuição por Papel Técnico das Funções (`role_category`)")
    lines.append("")
    lines.append("| Papel Técnico da Função | Ocorrências | Proporção |")
    lines.append("| :--- | :---: | :---: |")
    for r in roles_summary:
        pct = (r['cnt'] / total_functions) * 100 if total_functions else 0
        lines.append(f"| `{r['role_category']}` | **{r['cnt']}** | {pct:.1f}% |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Catálogo Detalhado de Módulos e Funções por Domínio")
    lines.append("")

    for dom_row in domains_summary:
        domain = dom_row['domain']
        lines.append(f"### Domínio: `{domain}`")
        lines.append(f"> **Módulos**: {dom_row['mod_count']} | **Funções**: {dom_row['func_count']} | **LOC**: {dom_row['total_loc']:,}")
        lines.append("")

        mods = cur.execute("""
            SELECT module_path, module_summary, loc, classes_count, functions_count
            FROM modules
            WHERE domain = ?
            ORDER BY module_path
        """, (domain,)).fetchall()

        for m in mods:
            lines.append(f"#### Módulo: `{m['module_path']}` ({m['loc']} LOC)")
            if m['module_summary']:
                lines.append(f"**Responsabilidade**: {m['module_summary']}")
            lines.append("")

            funcs = cur.execute("""
                SELECT function_name, parent, role_category, description
                FROM functions
                WHERE module_path = ?
                ORDER BY parent, function_name
            """, (m['module_path'],)).fetchall()

            if funcs:
                lines.append("| Função / Método | Escopo | Papel | Descrição |")
                lines.append("| :--- | :--- | :--- | :--- |")
                for f in funcs:
                    desc_clean = (f['description'] or '').replace("|", "-").replace("\n", " ")
                    scope = f"`{f['parent']}`" if f['parent'] != "top_level" else "*top_level*"
                    lines.append(f"| `{f['function_name']}()` | {scope} | `{f['role_category']}` | {desc_clean} |")
                lines.append("")
            else:
                lines.append("*Módulo de constantes, tipos ou declarações puras sem funções executáveis.*")
                lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Taxonomia gerada com sucesso em: {OUTPUT_PATH} ({len(lines)} linhas)")

if __name__ == "__main__":
    main()
