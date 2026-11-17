"""`core/runner.rs` do RTK: o esqueleto de `run_filtered` (rodar, filtrar a saida capturada, imprimir).

So o caminho `Filtered` capturado, o unico que os modulos portados usam ate aqui.
Opcoes, como no `RunOptions` do RTK:

- `stdout_only`: o filtro le so o stdout; o stderr segue para o stderr (cortado em
  10 linhas, com dica de recuperacao, quando o comando deu certo e o stdout mostrou algo);
- `early_exit_on_failure`: comando que falhou mostra a saida original e devolve o codigo;
- `no_trailing_newline`: `print!` no lugar de `println!`;
- `clean_outputs`: o que a ferramenta imprime numa execucao limpa no formato que o RTK injetou;
- `tee_label`: guarda a saida original de uma execucao que falhou e acrescenta a dica;
- `inherit_stdin`: o comando le a entrada padrao do `shell` (`cat arq | rtk wc`).
"""

from __future__ import annotations

from typing import Callable

from .ambiente import Ambiente
from .base import force_tee_hint, guard_stdout, linhas, print_with_hint, trim

MAX_FORWARDED_STDERR_LINES = 10
MIN_TEE_SIZE = 500


def last_lines_offset(texto: str, n: int) -> tuple[int, int] | None:
    """Onde comecam as ultimas `n` linhas (indice no texto) e quantas linhas isso pula."""
    puladas = len(linhas(texto)) - n
    if puladas <= 0:
        return None
    pos = -1
    for _ in range(puladas):
        pos = texto.find("\n", pos + 1)
        if pos < 0:
            return None
    return pos + 1, puladas


def forwarded_stderr(stderr: str, codigo: int, stdout_mostrado: str,
                     dica_de_recuperacao: Callable[[str], str | None]) -> str:
    if codigo != 0 or not trim(stdout_mostrado):
        return stderr
    if len(stderr.encode("utf-8")) < MIN_TEE_SIZE:
        return stderr
    achado = last_lines_offset(stderr, MAX_FORWARDED_STDERR_LINES)
    if achado is None:
        return stderr
    deslocamento, retidas = achado
    dica = dica_de_recuperacao(stderr)
    if dica is None:
        return stderr
    palavra = "line" if retidas == 1 else "lines"
    cortado = f"... (+{retidas} earlier stderr {palavra} not shown)\n{stderr[deslocamento:]}{dica}\n"
    if len(cortado.encode("utf-8")) >= len(stderr.encode("utf-8")):
        return stderr
    return cortado


def run_filtered(amb: Ambiente, argv: list[str], ferramenta: str, filtro: Callable[[str], str], *,
                 stdout_only: bool = False, early_exit_on_failure: bool = False,
                 no_trailing_newline: bool = False, clean_outputs: tuple[str, ...] = (),
                 tee_label: str | None = None, inherit_stdin: bool = False,
                 env: dict | None = None) -> int:
    r = amb.capturar_linhas(argv, env, inherit_stdin)
    bruto = r.stdout + r.stderr
    if early_exit_on_failure and r.codigo != 0:
        if trim(r.stdout):
            amb.out(r.stdout)
        if trim(r.stderr):
            amb.err(r.stderr)
        return r.codigo

    texto = r.stdout if stdout_only else bruto
    filtrado = filtro(texto)
    if tee_label is not None:
        mostrado = print_with_hint(filtrado, bruto, texto, tee_label, r.codigo)
        amb.out(mostrado + "\n")
    else:
        mostrado = guard_stdout(texto, filtrado, clean_outputs)
        amb.out(mostrado if no_trailing_newline else mostrado + "\n")

    if stdout_only and trim(r.stderr):
        rotulo = f"{tee_label or ferramenta}-stderr"
        amb.err(forwarded_stderr(r.stderr, r.codigo, mostrado, lambda s: force_tee_hint(s, rotulo)))
    return r.codigo
