"""Onde um modulo portado roda os comandos e escreve a saida.

Os modulos do RTK que consultam a ferramenta mais de uma vez (`git status`
roda o status simples e o porcelain; `git add` roda `git diff --cached` depois)
nao cabem em `filtrar(bruto, codigo)`: precisam rodar processos. Esses modulos
exportam `rodar(args, amb) -> int`, o `run` do RTK, e falam so com um
`Ambiente`:

- `capturar(argv)`: roda com a entrada vazia e devolve stdout e stderr
  decodificados (com substituicao nos bytes invalidos, como o RTK) e o codigo;
- `capturar_bytes(argv)`: o mesmo sem decodificar (um blob que nao e UTF-8);
- `repassar(argv)`: roda com a saida do terminal e a entrada herdada;
- `out`/`out_bytes`/`err`: o `print!`/`eprint!` do Rust.

Os testes e a paridade usam o mesmo `Ambiente` com a saida em memoria.
"""

from __future__ import annotations

import io
import os
import queue
import shutil
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass


@dataclass
class Capturado:
    stdout: str
    stderr: str
    codigo: int

    def ok(self) -> bool:
        return self.codigo == 0

    def combinado(self) -> str:
        return self.stdout + self.stderr


@dataclass
class CapturadoBytes:
    stdout: bytes
    stderr: bytes
    codigo: int

    def ok(self) -> bool:
        return self.codigo == 0


def _codigo(returncode: int) -> int:
    """Codigo de saida; sinal vira 128 + sinal, como o RTK."""
    return 128 - returncode if returncode < 0 else returncode


def _texto(b: bytes) -> str:
    return b.decode("utf-8", "replace")


RAW_CAP = 10_485_760


def linha_lossy(b: bytes) -> str:
    """Uma linha do `read_lines_lossy` do RTK: sem o `\\n` final e sem um `\\r` antes dele."""
    if b.endswith(b"\n"):
        b = b[:-1]
    if b.endswith(b"\r"):
        b = b[:-1]
    return _texto(b)


def por_linhas(b: bytes) -> str:
    """`read_lines_lossy` + o laco de `run_streaming` do RTK: o texto que o filtro de um
    `run_filtered` recebe. Cada linha perde um `\\r` final e ganha `\\n` (a ultima, mesmo sem
    quebra), e o que passa de 10 MiB e descartado linha a linha."""
    partes = b.split(b"\n")
    if partes and partes[-1] == b"":
        partes.pop()
    saida: list[str] = []
    total = 0
    for parte in partes:
        if parte.endswith(b"\r"):
            parte = parte[:-1]
        linha = _texto(parte)
        tamanho = len(linha.encode("utf-8"))
        if total + tamanho < RAW_CAP:
            saida.append(linha + "\n")
            total += tamanho + 1
    return "".join(saida)


class Ambiente:
    """Processos de verdade; a saida vai para `saida`/`erro` (binarios) ou para o terminal."""

    def __init__(self, cwd: str | None = None, saida=None, erro=None, env: dict | None = None,
                 entrada: bytes | None = None):
        self.cwd = cwd
        self._env = env
        self._terminal = saida is None and erro is None
        self._saida = saida if saida is not None else sys.stdout.buffer
        self._erro = erro if erro is not None else sys.stderr.buffer
        #: Em memoria: o que o comando "herda" como entrada padrao (None: nada, como /dev/null).
        self._entrada = entrada

    @classmethod
    def em_memoria(cls, cwd: str | None = None, env: dict | None = None,
                   entrada: bytes | None = None) -> "Ambiente":
        return cls(cwd, io.BytesIO(), io.BytesIO(), env, entrada)

    def stdin_legivel(self) -> bool:
        """A entrada padrao e algo que a ferramenta le: arquivo comum, FIFO ou socket (a regra do
        ripgrep). `/dev/null` e um dispositivo de caractere e nao conta; terminal tambem nao."""
        if not self._terminal:
            return self._entrada is not None
        try:
            modo = os.fstat(0).st_mode
        except OSError:
            return False
        return stat.S_ISREG(modo) or stat.S_ISFIFO(modo) or stat.S_ISSOCK(modo)

    def stdout_e_terminal(self) -> bool:
        return self._terminal and sys.stdout.isatty()

    def resolver(self, nome: str) -> str:
        """O `resolved_command` do RTK: o executavel pelo caminho absoluto no PATH (as mensagens de
        erro do motor levam o argv[0], e `/usr/bin/grep: x: Is a directory` e a que o RTK mostra)."""
        path = (self._env if self._env is not None else os.environ).get("PATH")
        return shutil.which(nome, path=path) or nome

    def caminho(self, p: str) -> str:
        """`p` resolvido a partir do diretorio de trabalho do ambiente."""
        return p if os.path.isabs(p) or not self.cwd else os.path.join(self.cwd, p)

    def _ambiente(self, extra: dict | None) -> dict | None:
        if self._env is None and not extra:
            return None
        env = dict(self._env if self._env is not None else os.environ)
        env.update(extra or {})
        return env

    def capturar_bytes(self, argv: list[str], env: dict | None = None,
                       herdar_stdin: bool = False) -> CapturadoBytes:
        kw: dict = {"stdin": subprocess.DEVNULL}
        if herdar_stdin:
            if self._terminal:
                kw = {"stdin": None}
            elif self._entrada is not None:
                kw = {"input": self._entrada}
        p = subprocess.run(argv, capture_output=True, cwd=self.cwd, env=self._ambiente(env), **kw)
        return CapturadoBytes(p.stdout, p.stderr, _codigo(p.returncode))

    def capturar(self, argv: list[str], env: dict | None = None, herdar_stdin: bool = False) -> Capturado:
        r = self.capturar_bytes(argv, env, herdar_stdin)
        return Capturado(_texto(r.stdout), _texto(r.stderr), r.codigo)

    def capturar_linhas(self, argv: list[str], env: dict | None = None, herdar_stdin: bool = False) -> Capturado:
        """Como `capturar`, mas com o texto normalizado como o `run_filtered` do RTK o le."""
        r = self.capturar_bytes(argv, env, herdar_stdin)
        return Capturado(por_linhas(r.stdout), por_linhas(r.stderr), r.codigo)

    def repassar(self, argv: list[str]) -> int:
        if self._terminal:
            self._saida.flush()
            self._erro.flush()
            return _codigo(subprocess.run(argv, cwd=self.cwd, env=self._ambiente(None)).returncode)
        r = self.capturar_bytes(argv, herdar_stdin=True)
        self.out_bytes(r.stdout)
        self._erro.write(r.stderr)
        return r.codigo

    def transmitir(self, argv: list[str], alimentar) -> int:
        """O `FilterMode::Streaming` do RTK: stdout e stderr do comando, linha a linha e na
        ordem em que chegam, passam por `alimentar(linha, eh_stderr) -> str | None`; o texto
        devolvido vai para o mesmo fluxo de onde a linha veio. A entrada padrao e herdada."""
        if self._terminal:
            self._saida.flush()
            self._erro.flush()
            stdin = None
        else:
            stdin = subprocess.PIPE if self._entrada is not None else subprocess.DEVNULL
        p = subprocess.Popen(argv, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=self.cwd, env=self._ambiente(None))
        fila: queue.Queue = queue.Queue()

        def ler(fluxo, eh_stderr: bool) -> None:
            for bruta in iter(fluxo.readline, b""):
                fila.put((eh_stderr, linha_lossy(bruta)))
            fila.put(None)

        def escrever_entrada() -> None:
            try:
                p.stdin.write(self._entrada)
            except OSError:
                pass
            finally:
                try:
                    p.stdin.close()
                except OSError:
                    pass

        threads = [threading.Thread(target=ler, args=(p.stdout, False), daemon=True),
                   threading.Thread(target=ler, args=(p.stderr, True), daemon=True)]
        if stdin == subprocess.PIPE:
            threads.append(threading.Thread(target=escrever_entrada, daemon=True))
        for t in threads:
            t.start()
        abertos = 2
        while abertos:
            item = fila.get()
            if item is None:
                abertos -= 1
                continue
            eh_stderr, linha = item
            texto = alimentar(linha, eh_stderr)
            if texto:
                (self.err if eh_stderr else self.out)(texto)
                (self._erro if eh_stderr else self._saida).flush()
        for t in threads:
            t.join()
        return _codigo(p.wait())

    def out(self, texto: str) -> None:
        self._saida.write(texto.encode("utf-8"))

    def out_bytes(self, dados: bytes) -> None:
        self._saida.write(dados)

    def err(self, texto: str) -> None:
        self._erro.write(texto.encode("utf-8"))

    def flush(self) -> None:
        self._saida.flush()
        self._erro.flush()

    def saida_gravada(self) -> tuple[bytes, bytes]:
        return self._saida.getvalue(), self._erro.getvalue()
