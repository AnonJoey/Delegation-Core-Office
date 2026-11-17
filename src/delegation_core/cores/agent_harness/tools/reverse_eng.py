"""
reverse_eng.py — Ferramenta unificada de engenharia reversa e inspeção estática por AST.
Fusão com scripts/classify_repository.py (extração profunda de classes, métodos, docstrings e métricas).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Any


class ReverseEngTool:
    """Analisador estático estruturado de repositórios e módulos Python (REA)."""

    def __init__(self):
        self.engine = "rea-ast-analyzer"

    def inspect_python_file(self, file_path: str) -> Dict[str, Any]:
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            return {"error": f"File not found: {file_path}"}

        try:
            code = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"error": f"Read error: {e}"}

        lines = code.splitlines()
        loc = len(lines)

        try:
            tree = ast.parse(code, filename=str(p))
            module_doc = ast.get_docstring(tree) or ""
        except Exception as e:
            return {
                "file": str(p),
                "parse_error": str(e),
                "total_loc": loc,
                "classes": [],
                "functions": [],
            }

        classes = []
        class_names = []
        top_functions = []
        function_names = []
        async_functions = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_names.append(node.name)
                c_doc = ast.get_docstring(node) or ""
                methods = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_doc = ast.get_docstring(item) or ""
                        is_async = isinstance(item, ast.AsyncFunctionDef)
                        methods.append({
                            "name": item.name,
                            "is_async": is_async,
                            "doc": m_doc.split("\n")[0] if m_doc else "",
                        })
                classes.append({
                    "name": node.name,
                    "doc": c_doc.split("\n")[0] if c_doc else "",
                    "methods_count": len(methods),
                    "methods": methods,
                })

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_names.append(node.name)
                is_async = isinstance(node, ast.AsyncFunctionDef)
                if is_async:
                    async_functions.append(node.name)
                f_doc = ast.get_docstring(node) or ""
                top_functions.append({
                    "name": node.name,
                    "is_async": is_async,
                    "doc": f_doc.split("\n")[0] if f_doc else "",
                })

        return {
            "file": str(p),
            "docstring": module_doc.split("\n")[0] if module_doc else "",
            "classes": class_names,
            "classes_detail": classes,
            "functions": function_names,
            "functions_detail": top_functions,
            "async_functions": async_functions,
            "total_loc": loc,
            "classes_count": len(class_names),
            "functions_count": len(function_names),
        }
