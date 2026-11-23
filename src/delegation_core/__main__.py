from .entrada_rapida import main

# SystemExit com o retorno: sem isto, `python -m delegation_core` saia 0 mesmo
# quando o comando falhava (achado pelo teste do `shell`, 05/10/2026). O
# executavel instalado ja fazia isso pelo wrapper do setuptools.
# O guarda importa: o pool de processos dos compressores (compressao/pool.py) cria workers
# por `forkserver`, e o multiprocessing reimporta o modulo principal em cada um. Sem o
# guarda, `python -m delegation_core run` subiria outro daemon dentro de cada worker.
if __name__ == "__main__":
    raise SystemExit(main())
