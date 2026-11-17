"""Transcricao bruta vira resumo curado, pelo modelo local. Pacote independente: ver `resumo.py`."""

from .resumo import citacoes_sem_lastro, pedacos, resumir

__all__ = ["citacoes_sem_lastro", "pedacos", "resumir"]
