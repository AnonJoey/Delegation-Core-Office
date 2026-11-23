"""As duas decisoes do `delegation-core shell`, num lugar so (item 6.1.2).

Antes ficavam dentro de `cli.cmd_run`. Agora o daemon (rotas /api/saidas/*), o cliente fino
(`cliente_fino.shell`) e o caminho local (`cli.cmd_run`, quando o daemon nao atende) chamam
as mesmas funcoes, entao a regra nao tem como divergir entre eles.

- `plano(comando)`: como rodar o comando, ANTES de rodar. Os modos:
  - `local`:  modulo que consulta a ferramenta varias vezes (git, gh). So roda no processo do
              agente, pelo caminho local; o daemon nunca roda comando do agente.
  - `modulo`: modulo do RTK portado; roda `comando_real`, stdout e stderr juntos, salvo
              `so_stdout`.
  - `toml`:   filtro TOML; stderr junto so com `filter_stderr`.
  - `rota`:   comando de um modulo Rust do RTK nao portado: vai ao compressor.
  - `direto`: nada casa; a saida passa intacta.
- `exibir(comando, modo, saida, codigo)`: o que o agente ve, depois de rodar.
"""

from __future__ import annotations

from . import execucao, modulos, modulos_rtk, motor

MODOS = ("local", "modulo", "toml", "rota", "direto")


def plano(comando: str) -> dict:
    if modulos.rodavel(comando) is not None:
        return {"modo": "local"}
    achado = modulos.modulo_para(comando)
    if achado is not None:
        return {"modo": "modulo", "comando_real": modulos.comando_do_rtk(comando),
                "so_stdout": bool(getattr(achado[1], "SO_STDOUT", False))}
    f = motor.achar(comando)
    if f is not None:
        return {"modo": "toml", "juntar_stderr": bool(f.filter_stderr)}
    if modulos_rtk.modulo_para(comando) is not None:
        return {"modo": "rota"}
    return {"modo": "direto"}


def exibir(comando: str, modo: str, saida: str, codigo: int, kompress: bool = False) -> dict:
    """`{"output": texto, ...}`. `kompress` so o daemon liga: e ele que tem o modelo carregado."""
    if modo == "modulo":
        return modulos.aplicar(comando, saida, codigo, injetado=True)
    if modo == "toml":
        f = motor.achar(comando)
        if f is not None:
            return execucao.exibir(f, saida, comando, codigo)
    elif modo == "rota":
        m = modulos_rtk.modulo_para(comando)
        if m is not None:
            from ..compressao.roteador import comprimir
            rota = m["delegation_core_route"]
            tipo = rota if rota in ("diff", "search", "log", "text") else "auto"
            return comprimir(saida, comando, tipo, kompress=kompress)
    # `direto`, ou o filtro sumiu entre o plano e a saida (filtros recarregados): mostra intacta.
    return {"output": saida}
