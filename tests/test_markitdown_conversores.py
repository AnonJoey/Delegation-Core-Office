"""
test_markitdown_conversores.py — Testes unitários do conversor MarkItDown em Python.
"""

import csv
import pytest
from pathlib import Path
from delegation_core.markitdown import MarkItDown, convert_document, UnsupportedFormatError


def test_convert_text(tmp_path: Path):
    txt_file = tmp_path / "exemplo.txt"
    txt_file.write_text("Linha 1\nLinha 2", encoding="utf-8")
    res = convert_document(txt_file)
    assert "Linha 1" in res
    assert "Linha 2" in res


def test_convert_csv(tmp_path: Path):
    csv_file = tmp_path / "tabela.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Nome", "Idade", "Cargo"])
        writer.writerow(["Ana", "30", "Engenheira"])
        writer.writerow(["Bruno", "25", "Analista"])

    res = convert_document(csv_file)
    assert "| Nome | Idade | Cargo |" in res
    assert "| Ana | 30 | Engenheira |" in res
    assert "| Bruno | 25 | Analista |" in res


def test_convert_html(tmp_path: Path):
    html_file = tmp_path / "pagina.html"
    html_file.write_text("""
    <html>
        <head><title>Página de Teste</title></head>
        <body>
            <h1>Título Principal</h1>
            <p>Parágrafo explicativo sobre o sistema.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
        </body>
    </html>
    """, encoding="utf-8")

    res = convert_document(html_file)
    assert "# Título Principal" in res
    assert "Parágrafo explicativo sobre o sistema." in res
    assert "- Item 1" in res


def test_convert_code_block(tmp_path: Path):
    json_file = tmp_path / "config.json"
    json_file.write_text('{"key": "value"}', encoding="utf-8")
    res = convert_document(json_file)
    assert "```json" in res
    assert '{"key": "value"}' in res


def test_unsupported_format(tmp_path: Path):
    bin_file = tmp_path / "arquivo.desconhecido"
    bin_file.write_bytes(b"\x00\x01\x02")
    with pytest.raises(UnsupportedFormatError):
        convert_document(bin_file)
