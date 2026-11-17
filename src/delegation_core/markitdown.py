"""
markitdown.py — Conversor de Documentos Multi-Formato para Markdown (Inspirado no Microsoft MarkItDown).
Execução 100% Python local utilizando pypdf, python-docx, python-pptx, openpyxl e BeautifulSoup.
Converte PDF, DOCX, XLSX, PPTX, CSV e HTML para Markdown limpo pronto para o Obsidian Vault.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional


class UnsupportedFormatError(ValueError):
    """Lançado quando a extensão do arquivo não é suportada."""
    pass


class MarkItDown:
    """Motor unificado de conversão de documentos para Markdown."""

    def __init__(self):
        pass

    def convert(self, file_path: str | Path, allowed_root: Optional[str | Path] = None) -> str:
        """Converte o arquivo especificado para Markdown estruturado."""
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        if not path.is_file():
            raise ValueError(f"O caminho fornecido não é um arquivo regular: {path}")

        if allowed_root is not None:
            root = Path(allowed_root).expanduser().resolve()
            if root not in path.parents and path != root:
                raise PermissionError(f"Acesso negado: o arquivo '{path}' está fora do diretório permitido '{root}'.")

        ext = path.suffix.lower()
        if ext in (".md", ".markdown", ".txt"):
            return self._convert_text(path)
        elif ext == ".pdf":
            return self._convert_pdf(path)
        elif ext in (".docx", ".doc"):
            return self._convert_docx(path)
        elif ext in (".pptx", ".ppt"):
            return self._convert_pptx(path)
        elif ext in (".xlsx", ".xlsm", ".xltx"):
            return self._convert_xlsx(path)
        elif ext in (".csv", ".tsv"):
            return self._convert_csv(path, delimiter="\t" if ext == ".tsv" else ",")
        elif ext in (".html", ".htm"):
            return self._convert_html(path)
        elif ext in (".json", ".yaml", ".yml", ".toml"):
            return self._convert_code_block(path, lang=ext[1:])
        else:
            raise UnsupportedFormatError(f"Formato não suportado: {ext}")

    def _convert_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def _convert_pdf(self, path: Path) -> str:
        try:
            import pypdf
        except ImportError:
            raise RuntimeError("pypdf não está instalado. Instale com: pip install pypdf")

        reader = pypdf.PdfReader(str(path))
        lines = [f"# {path.stem}\n"]
        total_pages = len(reader.pages)
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text_clean = text.strip()
            if text_clean:
                lines.append(f"## Página {i} / {total_pages}\n")
                lines.append(text_clean)
                lines.append("")
        return "\n".join(lines)

    def _convert_docx(self, path: Path) -> str:
        try:
            import docx
        except ImportError:
            raise RuntimeError("python-docx não está instalado. Instale com: pip install python-docx")

        doc = docx.Document(str(path))
        lines = [f"# {path.stem}\n"]

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            style_name = p.style.name.lower() if p.style else ""
            if "heading 1" in style_name:
                lines.append(f"# {text}\n")
            elif "heading 2" in style_name:
                lines.append(f"## {text}\n")
            elif "heading 3" in style_name:
                lines.append(f"### {text}\n")
            elif "list" in style_name:
                lines.append(f"- {text}")
            else:
                lines.append(f"{text}\n")

        for table in doc.tables:
            table_md = self._render_docx_table(table)
            if table_md:
                lines.append(table_md)
                lines.append("")

        return "\n".join(lines)

    def _render_docx_table(self, table) -> str:
        rows_data = []
        for row in table.rows:
            rows_data.append([cell.text.replace("\n", " ").strip() for cell in row.cells])
        if not rows_data:
            return ""

        headers = rows_data[0]
        md_lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |"
        ]
        for row in rows_data[1:]:
            # Preencher se houver colunas faltantes
            while len(row) < len(headers):
                row.append("")
            md_lines.append("| " + " | ".join(row[:len(headers)]) + " |")
        return "\n".join(md_lines)

    def _convert_pptx(self, path: Path) -> str:
        try:
            from pptx import Presentation
        except ImportError:
            raise RuntimeError("python-pptx não está instalado. Instale com: pip install python-pptx")

        prs = Presentation(str(path))
        lines = [f"# {path.stem}\n"]

        for i, slide in enumerate(prs.slides, start=1):
            lines.append(f"## Slide {i}\n")
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    lines.append(shape.text.strip())
                    lines.append("")
        return "\n".join(lines)

    def _convert_xlsx(self, path: Path) -> str:
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("openpyxl não está instalado. Instale com: pip install openpyxl")

        wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        lines = [f"# {path.stem}\n"]

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            lines.append(f"## Planilha: {sheet_name}\n")
            rows = []
            for row in sheet.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    rows.append([str(v) if v is not None else "" for v in row])
            if rows:
                headers = rows[0]
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for r in rows[1:]:
                    while len(r) < len(headers):
                        r.append("")
                    lines.append("| " + " | ".join(r[:len(headers)]) + " |")
                lines.append("")

        wb.close()
        return "\n".join(lines)

    def _convert_csv(self, path: Path, delimiter: str = ",") -> str:
        lines = [f"# {path.stem}\n"]
        with open(path, mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f, delimiter=delimiter)
            rows = [r for r in reader if any(cell.strip() for cell in r)]
            if not rows:
                return f"# {path.stem}\n\n*Arquivo vazio.*"
            headers = [c.replace("\n", " ").strip() for c in rows[0]]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
            for r in rows[1:]:
                clean_r = [c.replace("\n", " ").strip() for c in r]
                while len(clean_r) < len(headers):
                    clean_r.append("")
                lines.append("| " + " | ".join(clean_r[:len(headers)]) + " |")
        return "\n".join(lines)

    def _convert_html(self, path: Path) -> str:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise RuntimeError("beautifulsoup4 não está instalado.")

        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        lines = [f"# {path.stem}\n"]
        title_tag = soup.find("title")
        if title_tag and title_tag.text.strip():
            lines.append(f"**Título**: {title_tag.text.strip()}\n")

        for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "table"]):
            tag_name = el.name.lower()
            text = el.get_text(separator=" ", strip=True)
            if not text:
                continue
            if tag_name == "h1":
                lines.append(f"# {text}\n")
            elif tag_name == "h2":
                lines.append(f"## {text}\n")
            elif tag_name == "h3":
                lines.append(f"### {text}\n")
            elif tag_name == "li":
                lines.append(f"- {text}")
            elif tag_name == "pre":
                lines.append(f"```\n{text}\n```\n")
            elif tag_name == "p":
                lines.append(f"{text}\n")

        return "\n".join(lines)

    def _convert_code_block(self, path: Path, lang: str) -> str:
        content = path.read_text(encoding="utf-8", errors="replace")
        return f"# {path.stem}\n\n```{lang}\n{content}\n```"


_default_converter = MarkItDown()

def convert_document(file_path: str | Path, allowed_root: Optional[str | Path] = None) -> str:
    """Função utilitária direta para conversão de documento em Markdown."""
    return _default_converter.convert(file_path, allowed_root=allowed_root)
