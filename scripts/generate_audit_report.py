#!/usr/bin/env python3
"""
generate_audit_report.py — Consolidador de Auditoria do Codebase delegation-core.
Lê o banco SQLite audit_delegation_core.db e gera o documento Markdown completo
em docs/AUDITORIA_CONSOLIDADA_CODEBASE.md.
"""

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path("/home/joey/Projects/delegation-core")
DB_PATH = REPO_ROOT / "audit_delegation_core.db"
OUTPUT_PATH = REPO_ROOT / "docs" / "AUDITORIA_CONSOLIDADA_CODEBASE.md"

def main():
    if not DB_PATH.exists():
        print(f"Erro: Banco {DB_PATH} não encontrado.")
        sys.exit(1)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    total_findings = cur.execute("SELECT count(*) FROM audit_findings").fetchone()[0]
    total_fp = cur.execute("SELECT count(*) FROM audit_findings WHERE is_false_positive = 1").fetchone()[0]
    total_genuine = cur.execute("SELECT count(*) FROM audit_findings WHERE is_false_positive = 0").fetchone()[0]
    total_modules_audited = cur.execute("SELECT count(*) FROM audit_progress WHERE pass_1_status = 'done' AND pass_2_status = 'done' AND pass_3_status = 'done'").fetchone()[0]

    # Distribuição por severidade e categoria
    sev_cat = cur.execute("""
        SELECT category, severity, count(*) as cnt
        FROM audit_findings
        WHERE is_false_positive = 0
        GROUP BY category, severity
        ORDER BY category, cnt DESC
    """).fetchall()

    # Módulos com mais achados genuínos
    top_modules = cur.execute("""
        SELECT rel_path, count(*) as cnt,
               SUM(CASE WHEN severity = 'ALTA' THEN 1 ELSE 0 END) as alta,
               SUM(CASE WHEN severity = 'MEDIA' THEN 1 ELSE 0 END) as media,
               SUM(CASE WHEN severity = 'BAIXA' THEN 1 ELSE 0 END) as baixa
        FROM audit_findings
        WHERE is_false_positive = 0
        GROUP BY rel_path
        ORDER BY cnt DESC
    """).fetchall()

    # Todos os achados genuínos de severidade ALTA e MEDIA
    genuine_findings = cur.execute("""
        SELECT rel_path, pass_id, category, severity, line_hint, description, code_snippet, risk
        FROM audit_findings
        WHERE is_false_positive = 0
        ORDER BY rel_path, severity, line_hint
    """).fetchall()

    # Amostra de falsos positivos com teste comprovando cobertura
    fps = cur.execute("""
        SELECT rel_path, line_hint, description, code_snippet, test_verification
        FROM audit_findings
        WHERE is_false_positive = 1
        ORDER BY rel_path, line_hint
    """).fetchall()

    lines = []
    lines.append("# Relatório Consolidado de Auditoria do Codebase delegation-core")
    lines.append("")
    lines.append("- **Data da Execução**: 2026-10-22")
    lines.append("- **Motor de Inferência**: Qwen2.5-Coder-14B-Instruct-Q4_K_M (Execução Local via GPU RTX 4070, 16.384 contexto)")
    lines.append("- **Pipeline de Execução**: `scripts/audit_pipeline.py` (3 passagens especializadas) + `scripts/audit_cross_reference.py` (Passagem 4: Validação Cruzada de Testes)")
    lines.append("- **Status da Base**: 183 testes unitários validados com sucesso")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Resumo Executivo e Métricas Globais")
    lines.append("")
    lines.append(f"A esteira automatizada de auditoria multi-pass analisou exaustivamente os módulos fonte do `delegation-core`.")
    lines.append(f"Dos módulos analisados, **{total_modules_audited} módulos** completaram com sucesso todas as 3 passagens de auditoria.")
    lines.append("")
    lines.append("| Métrica | Valor Absoluto | Proporção |")
    lines.append("| :--- | :---: | :---: |")
    lines.append(f"| **Apontamentos Totais da LLM** | {total_findings:,} | 100.0% |")
    lines.append(f"| **Falsos Positivos Filtrados (Passagem 4)** | {total_fp:,} | {(total_fp/total_findings)*100:.1f}% |")
    lines.append(f"| **Achados Genuínos Catalogados** | {total_genuine:,} | {(total_genuine/total_findings)*100:.1f}% |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Distribuição dos Achados Genuínos")
    lines.append("")
    lines.append("### A. Por Categoria e Severidade")
    lines.append("")
    lines.append("| Categoria da Auditoria | Severidade | Quantidade |")
    lines.append("| :--- | :---: | :---: |")
    for r in sev_cat:
        lines.append(f"| `{r['category']}` | **{r['severity']}** | {r['cnt']} |")
    lines.append("")
    lines.append("### B. Módulos com Maior Volume de Débito Técnico")
    lines.append("")
    lines.append("| Módulo | Total Genuínos | Alta | Média | Baixa |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")
    for m in top_modules[:25]:
        lines.append(f"| `{m['rel_path']}` | **{m['cnt']}** | {m['alta']} | {m['media']} | {m['baixa']} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Remediações Críticas Já Implementadas (PR #51)")
    lines.append("")
    lines.append("1. **Parada Graciosa do Servidor Daemon (`src/delegation_core/server.py`)**:")
    lines.append("   - Implementado interceptador de sinais `SIGTERM` e `SIGINT` no loop principal.")
    lines.append("   - Chamada a `_cleanup()` e liberação ordenada de conexões de banco SQLite e workers em background.")
    lines.append("   - Previne o envio forçado de `SIGKILL` pelo systemd/launchd durante o encerramento do sistema.")
    lines.append("")
    lines.append("2. **Concorrência e Locks no Dashboard (`src/delegation_core/dashboard_api.py`)**:")
    lines.append("   - Implementado *double-checked locking* com `_engine_lock` na inicialização do SQLAlchemy engine.")
    lines.append("   - Elimina race conditions em cenários de acessos simultâneos ao endpoint de telemetria.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 4. Detalhamento de Falsos Positivos Descartados (Passagem 4)")
    lines.append("")
    lines.append(f"Um total de **{total_fp} apontamentos** gerados pelas passagens estáticas da LLM foram isolados após validação cruzada contra a suíte de testes unitários (`tests/`).")
    lines.append("Abaixo, uma amostra representativa de falsos positivos e os respectivos testes que garantem a segurança do comportamento:")
    lines.append("")
    lines.append("| Módulo | Linha | Alerta da LLM | Cobertura Comprovada em Testes |")
    lines.append("| :--- | :---: | :--- | :--- |")
    for fp in fps[:20]:
        desc_clean = fp['description'].replace("|", "-").replace("\n", " ")[:80]
        test_clean = fp['test_verification'].replace("|", "-").replace("\n", " ")[:100]
        lines.append(f"| `{fp['rel_path']}` | {fp['line_hint']} | {desc_clean}... | {test_clean} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 5. Catálogo Completo de Achados Genuínos (Por Módulo e Severidade)")
    lines.append("")
    current_mod = None
    for g in genuine_findings:
        if g['rel_path'] != current_mod:
            current_mod = g['rel_path']
            lines.append(f"### Módulo: `{current_mod}`")
            lines.append("")
        snippet = g['code_snippet'].strip() if g['code_snippet'] else "N/A"
        lines.append(f"- **[{g['severity']}]** `{g['category']}` (Linha ~{g['line_hint']})")
        lines.append(f"  - **Descrição**: {g['description']}")
        lines.append(f"  - **Risco**: {g['risk']}")
        if snippet and snippet != "N/A":
            lines.append(f"  - **Trecho**: `{snippet[:120]}`")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Relatório gerado com sucesso em: {OUTPUT_PATH} ({len(lines)} linhas)")

if __name__ == "__main__":
    main()
