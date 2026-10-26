"""Cliente MCP que desconecta nao e ERROR no log (diagnostico de 26/10/2026)."""
import io
import logging

import anyio

from delegation_core import filtro_de_log


def _logger():
    saida = io.StringIO()
    h = logging.StreamHandler(saida)
    h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    lg = logging.getLogger("teste_filtro_de_log")
    lg.handlers = [h]
    lg.propagate = False
    lg.setLevel(logging.INFO)
    filtro_de_log.instalar(lg)
    return lg, saida


def test_desconexao_de_cliente_sai_como_info_e_mantem_o_traceback():
    lg, saida = _logger()
    try:
        raise anyio.ClosedResourceError
    except anyio.ClosedResourceError:
        lg.exception("Error in standalone SSE writer")
    texto = saida.getvalue()
    assert texto.startswith("[INFO] Error in standalone SSE writer")
    assert "ClosedResourceError" in texto


def test_outra_excecao_continua_sendo_error():
    lg, saida = _logger()
    try:
        raise ValueError("de verdade")
    except ValueError:
        lg.exception("Error handling POST request")
    assert saida.getvalue().startswith("[ERROR]")


def test_instalar_duas_vezes_nao_duplica_o_filtro():
    lg, _ = _logger()
    filtro_de_log.instalar(lg)
    assert sum(isinstance(f, filtro_de_log.DesconexaoDeCliente) for f in lg.handlers[0].filters) == 1
