"""A velocidade medida do modelo local, fora do arquivo de configuracao.

## O que estava errado

`tok_sec` morava no `Config`. O proprio docstring do `Config` o descreve como
`measured tokens/sec (0 = not calibrated yet)`: **medicao**, nao ajuste.
Rastreado no codigo, nenhum caminho de usuario define um valor para ele. O
wizard nao pergunta, o dashboard nao edita, e o unico toque no CLI e zerar para
invalidar a calibracao.

Quem escrevia era o `engine`, em tempo de execucao, com
`self.cfg.tok_sec = tok_sec` seguido de `self.cfg.save()`.

## A consequencia, que nao e teorica

`Config.save()` faz `json.dumps(asdict(self))`: grava o arquivo **inteiro** a
partir do objeto em memoria daquele processo. O engine carregou o config quando
subiu; se alguem mexeu numa configuracao pelo dashboard depois disso, a
calibracao seguinte **reverte a mudanca**, sem erro e sem aviso.

E a mesma familia de update perdido que apagou duas fontes do registro de
ingestao em 31/08/2026, e que `locking.py` resolveu. A diferenca e que aqui a
trava sozinha nao bastaria: o problema nao e so a corrida, e uma medicao ter
autoridade para reescrever ajuste que ela nao conhece.

O docstring de `Config.save()` ja carrega um incidente irmao: em 02/09/2026 um
teste chamou `calibrate()` e escreveu um config real com `vault_path`
temporario, tirando a maquina de servico. A guarda no `conftest` existe por
causa daquele dia. O caminho que causou aquilo e exatamente este.

## O desenho

Arquivo proprio, minusculo, com um campo. Escrita sob a mesma trava do
`locking.py`, porque dois processos calibrando ao mesmo tempo e possivel e
barato de proteger.

Pelo criterio de lego: nao sabe o que e `Config`, nao sabe o que e `engine`,
recebe e devolve `float`. Da para apagar este modulo e o sistema volta ao que
era, perdendo so a calibracao.

Depende de `locking`, e essa dependencia e de **utilidade pura**, da mesma
natureza de `pathlib`: nao carrega estado nem politica, entao nao e solda.
"""

from __future__ import annotations

import json
import logging
import os
import stat

from .config import CONFIG_DIR
from .locking import arquivo_travado

logger = logging.getLogger("calibracao")

ARQUIVO = CONFIG_DIR / "calibracao.json"

#: Valor de quem nunca calibrou. O `engine` ja trata zero como "sem calibracao"
#: e cai no orcamento fixo, entao este e o padrao que nao muda comportamento.
SEM_CALIBRACAO = 0.0


def ler(config_legado: float | None = None) -> float:
    """A velocidade medida, ou zero.

    `config_legado` existe para a migracao: instalacoes anteriores guardam o
    valor dentro do `config.json`, e ignora-lo faria toda maquina ja calibrada
    recalibrar do zero na primeira chamada. Quem passa esse argumento e o
    `engine`, com `cfg.tok_sec`.

    O arquivo novo vence quando existe. O legado so e consultado enquanto o
    novo nao foi escrito nenhuma vez.
    """
    try:
        if ARQUIVO.exists():
            dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                valor = float(dados.get("tok_sec", SEM_CALIBRACAO))
                if valor > 0:
                    return valor
    except Exception as e:
        # Calibracao ilegivel nao pode derrubar o motor: o pior caso e
        # recalibrar, que custa uma chamada e conserta o arquivo sozinho.
        logger.warning("calibracao ilegivel em %s (%s); tratando como ausente",
                       ARQUIVO, e)

    if config_legado and config_legado > 0:
        return float(config_legado)
    return SEM_CALIBRACAO


def gravar(tok_sec: float) -> float:
    """Guarda a medicao, sob trava, sem tocar no arquivo de configuracao.

    Devolve o valor gravado para quem chama poder encadear.

    Falha calada por escolha: nao conseguir persistir a calibracao significa
    recalibrar na proxima vez, que e um custo pequeno e visivel no log.
    Derrubar a geracao por causa disso seria trocar um problema barato por um
    caro.
    """
    try:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        with arquivo_travado(ARQUIVO):
            tmp = ARQUIVO.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump({"tok_sec": round(float(tok_sec), 2)}, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            os.replace(tmp, ARQUIVO)
    except Exception as e:
        logger.warning("nao foi possivel gravar a calibracao (%s); "
                       "o proximo uso recalibra", e)
    return tok_sec


def limpar() -> None:
    """Invalida a calibracao. O que `delegation-core` faz ao trocar de modelo."""
    try:
        ARQUIVO.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("nao foi possivel limpar a calibracao (%s)", e)
