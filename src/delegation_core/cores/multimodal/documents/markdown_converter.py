"""Document conversion for the multimodal core, through delegation_core.markitdown
(pypdf, python-docx, openpyxl, python-pptx, BeautifulSoup). A file it cannot read is an error,
never a success with placeholder text."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from delegation_core.markitdown import MarkItDown


class MarkdownConverter:
    """Conversor unificado de documentos para Markdown estruturado."""

    def __init__(self):
        self.engine_name = "delegation_core.markitdown (pypdf, python-docx, openpyxl, python-pptx, BeautifulSoup)"
        self.supported_extensions = [
            ".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".pptx", ".ppt",
            ".html", ".htm", ".csv", ".tsv", ".md", ".txt", ".json", ".yaml", ".toml"
        ]
        self._converter = MarkItDown()

    def convert_to_markdown(self, file_path: str) -> Dict[str, Any]:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"status": "ERROR", "error": f"File not found: {file_path}"}

        ext = path.suffix.lower()
        basename = path.name

        try:
            markdown_content = self._converter.convert(path)
        except Exception as e:  # noqa: BLE001 - o motivo vai para quem chamou
            # Ate 17/11/2026 a falha virava SUCCESS com uma tabela dizendo "Convertido com sucesso".
            return {"status": "ERROR", "error": f"Could not convert {basename}: {e}",
                    "source_file": str(path), "format": ext}

        return {
            "status": "SUCCESS",
            "engine": self.engine_name,
            "source_file": str(path),
            "format": ext,
            "markdown": markdown_content,
            "char_count": len(markdown_content),
        }
