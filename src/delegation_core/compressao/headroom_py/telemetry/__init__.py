"""Ligacao: a telemetria do Headroom (TOIN) fica DESLIGADA no delegation-core.

Os arquivos copiados chamam `get_toin().record_compression(...)`; aqui isso
nao registra nem envia nada.
"""


class _Nada:
    def __getattr__(self, _nome):
        return lambda *a, **k: None


def get_toin():
    return _Nada()
