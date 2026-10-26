"""O aviso "clamping to 512" aparecia a cada carga do modelo: 1.055 vezes em 27 dias (diagnostico de 26/10/2026)."""
import logging

from delegation_core import embeddings


def test_o_aviso_de_max_seq_length_sai_uma_vez_por_modelo_e_valor(caplog):
    embeddings._CLAMPS_JA_AVISADOS.clear()
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            assert embeddings._effective_max_seq_length("BAAI/bge-base-en-v1.5", 2048) == 512
    avisos = [r for r in caplog.records if "clamping" in r.getMessage()]
    assert len(avisos) == 1 and "embed_max_seq_length to 512" in avisos[0].getMessage()


def test_um_valor_diferente_volta_a_avisar(caplog):
    embeddings._CLAMPS_JA_AVISADOS.clear()
    with caplog.at_level(logging.WARNING):
        embeddings._effective_max_seq_length("BAAI/bge-base-en-v1.5", 2048)
        embeddings._effective_max_seq_length("BAAI/bge-base-en-v1.5", 4096)
    assert len([r for r in caplog.records if "clamping" in r.getMessage()]) == 2
