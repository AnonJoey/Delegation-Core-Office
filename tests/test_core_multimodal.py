"""The multimodal core converts documents to Markdown, and says so when it cannot.

Until 17/11/2026 it also offered OCR, transcription, speech synthesis and diagrams that returned
fixed text marked as SUCCESS, and a conversion failure came back as SUCCESS with a placeholder
table. Both are gone; these tests pin the honest behaviour.
"""

from delegation_core.cores.multimodal.pipeline import MultimodalPipeline


def test_documento_de_verdade_vira_markdown(tmp_path):
    arq = tmp_path / "tabela.csv"
    arq.write_text("nome,porta\nweb,8080\n", encoding="utf-8")
    r = MultimodalPipeline().ingest_asset(str(arq))
    assert r["status"] == "SUCCESS" and r["pipeline"] == "MarkItDown"
    assert "web" in r["markdown"] and "8080" in r["markdown"]


def test_arquivo_ilegivel_e_erro_com_motivo_e_nao_sucesso(tmp_path):
    arq = tmp_path / "quebrado.pdf"
    arq.write_bytes(b"%PDF-1.4 isto nao e um pdf")
    r = MultimodalPipeline().ingest_asset(str(arq))
    assert r["status"] == "ERROR" and "quebrado.pdf" in r["error"]
    assert "markdown" not in r


def test_arquivo_que_nao_existe(tmp_path):
    r = MultimodalPipeline().ingest_asset(str(tmp_path / "nada.docx"))
    assert r["status"] == "ERROR" and "not found" in r["error"].lower()


def test_nao_ha_mais_ocr_transcricao_nem_diagrama():
    p = MultimodalPipeline()
    for nome in ("generate_diagram", "synthesize_speech", "ocr", "stt", "tts", "diagrams"):
        assert not hasattr(p, nome), nome
