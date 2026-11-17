"""As passagens em sqlite: criar, escolher, aceitar uma vez so, expirar.

Porte do protocolo de handoff do ai-memory (MIT, Fabio Akita): `insert_handoff`,
`accept_handoff`, `expire_open_handoffs`, `cancel_handoff` e `checkpoint` de
`crates/ai-memory-store/src/{ops,reader,writer}.rs`.

## O protocolo

Uma passagem nasce aberta e termina aceita ou expirada; nunca volta.

- **Manual** (`de_sessao=None`): uma pessoa deixou de proposito. Vale para o projeto todo,
  qualquer que seja o cwd, e vence a automatica.
- **Automatica** (`de_sessao` preenchido): criada quando uma sessao acaba. So serve a uma
  sessao que comeca no mesmo diretorio ou abaixo dele (fronteira de componente, ver
  `caminhos`). Ao criar uma, as automaticas abertas do mesmo cwd exato se vao, menos as de
  sessao ainda aberta, que so a propria sessao renova.
- **Aceitar** e um compare-and-set numa transacao: de duas sessoes que correm, so uma vira
  `aceita`; a outra recebe `False` e o texto nao pode chegar ao agente. Uma sessao aceita uma
  passagem so (o inicio de sessao pode ser repetido). Aceitar uma automatica expira as
  automaticas mais antigas que serviriam ao mesmo cwd, e nunca as manuais.
- Expirar e mudar de estado, nao apagar: o resumo e a origem ficam.

Este porte atende um operador so: o campo `dono` existe (nulo = de todos), mas a regra de
multiplos operadores do original nao esta aqui. Tambem nao esta o "baton por turno" (a
sessao que renova a propria passagem a cada resposta) nem a checagem de sessao ocupada, que
no original dependem de uma tabela de observacoes.

Pacote independente: so a biblioteca padrao.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from ..texto_bytes import truncar_utf8
from .caminhos import Candidata, casa_com_cwd, chave_de_escolha, escolher

CAMPO_MAX_BYTES = 16 * 1024
LISTA_MAX_ITENS = 256

ABERTA, ACEITA, EXPIRADA = "aberta", "aceita", "expirada"


class EstadoInvalido(Exception):
    """A operacao pede algo que o estado atual nao permite (sessao que nao existe, dono errado)."""


def _agora_us() -> int:
    return time.time_ns() // 1000


def _limitar(texto: str) -> str:
    return truncar_utf8(str(texto), CAMPO_MAX_BYTES)


def _limitar_lista(itens) -> list[str]:
    return [_limitar(x) for x in list(itens)[:LISTA_MAX_ITENS]]


def cwd_guardado(cwd: str) -> str:
    """O cwd como fica guardado: sem separador no fim (a raiz fica `/`)."""
    aparado = cwd.rstrip("/\\")
    return "/" if aparado == "" else aparado


class Passagens:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.RLock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False, isolation_level=None, timeout=5.0)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            PRAGMA busy_timeout = 5000;
            CREATE TABLE IF NOT EXISTS sessoes (
                id TEXT PRIMARY KEY, projeto TEXT NOT NULL, agente TEXT NOT NULL, cwd TEXT,
                iniciada_em INTEGER NOT NULL, encerrada_em INTEGER
            );
            CREATE TABLE IF NOT EXISTS passagens (
                id TEXT PRIMARY KEY, projeto TEXT NOT NULL, de_sessao TEXT, de_agente TEXT NOT NULL, para_agente TEXT,
                cwd TEXT, resumo TEXT NOT NULL, perguntas TEXT NOT NULL DEFAULT '[]', proximos TEXT NOT NULL DEFAULT '[]',
                arquivos TEXT NOT NULL DEFAULT '[]', estado TEXT NOT NULL DEFAULT 'aberta', criada_em INTEGER NOT NULL,
                aceita_por TEXT, aceita_em INTEGER, aceita_sessao TEXT, dono TEXT
            );
            CREATE INDEX IF NOT EXISTS passagens_abertas ON passagens(projeto, estado, criada_em);
            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT, operacao TEXT NOT NULL, projeto TEXT, em INTEGER NOT NULL
            );
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    @contextmanager
    def _transacao(self):
        """BEGIN IMMEDIATE: a escrita toma a trava de gravacao ja no inicio, entre processos."""
        with self._trava:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                yield self._con
            except BaseException:
                self._con.execute("ROLLBACK")
                raise
            else:
                self._con.execute("COMMIT")

    @staticmethod
    def _auditar(con, operacao: str, projeto: str | None, em: int) -> None:
        con.execute("INSERT INTO auditoria(operacao, projeto, em) VALUES (?, ?, ?)", (operacao, projeto, em))

    # ── sessoes ────────────────────────────────────────────────────────────

    def abrir_sessao(self, id: str, projeto: str, agente: str, cwd: str | None = None, agora_us: int | None = None,
                     reabrir: bool = False) -> None:
        em = _agora_us() if agora_us is None else agora_us
        with self._transacao() as con:
            con.execute(
                "INSERT OR IGNORE INTO sessoes(id, projeto, agente, cwd, iniciada_em) VALUES (?, ?, ?, ?, ?)",
                (id, projeto, agente, cwd_guardado(cwd) if cwd else None, em))
            if reabrir:
                con.execute("UPDATE sessoes SET encerrada_em = NULL WHERE id = ?", (id,))

    def encerrar_sessao(self, id: str, agora_us: int | None = None) -> None:
        em = _agora_us() if agora_us is None else agora_us
        with self._transacao() as con:
            con.execute("UPDATE sessoes SET encerrada_em = ? WHERE id = ? AND encerrada_em IS NULL", (em, id))

    # ── criar ──────────────────────────────────────────────────────────────

    def criar(self, *, projeto: str, de_agente: str, resumo: str, cwd: str | None = None, de_sessao: str | None = None,
              para_agente: str | None = None, perguntas=(), proximos=(), arquivos=(), dono: str | None = None,
              agora_us: int | None = None) -> str:
        """`insert_handoff`. Devolve o id. Campos grandes sao cortados em 16 KiB e as listas em 256 itens."""
        em = _agora_us() if agora_us is None else agora_us
        pid = uuid.uuid4().hex
        cwd_g = cwd_guardado(cwd) if cwd is not None else None
        with self._transacao() as con:
            if de_sessao is not None:
                self._expirar_automaticas_do_mesmo_cwd(con, projeto, cwd_g, dono, manter=None, de_sessao=de_sessao, em=em)
            con.execute(
                "INSERT INTO passagens(id, projeto, de_sessao, de_agente, para_agente, cwd, resumo, perguntas, proximos, arquivos,"
                " estado, criada_em, dono) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberta', ?, ?)",
                (pid, projeto, de_sessao, de_agente, para_agente, cwd_g, _limitar(resumo),
                 json.dumps(_limitar_lista(perguntas), ensure_ascii=False), json.dumps(_limitar_lista(proximos), ensure_ascii=False),
                 json.dumps(_limitar_lista(arquivos), ensure_ascii=False), em, dono))
            self._auditar(con, "criar", projeto, em)
        return pid

    def _expirar_automaticas_do_mesmo_cwd(self, con, projeto, cwd, dono, manter, de_sessao, em) -> None:
        """Uma automatica mais nova do mesmo cwd exato e a unica que pode ganhar ali, mesmo antes de uma sessao comecar."""
        cur = con.execute(
            "UPDATE passagens SET estado = 'expirada' WHERE projeto = :p AND estado = 'aberta' AND de_sessao IS NOT NULL"
            " AND (cwd = :c OR (cwd IS NULL AND :c IS NULL)) AND dono IS :d AND id IS NOT :m"
            " AND (de_sessao IS :s OR NOT EXISTS (SELECT 1 FROM sessoes x WHERE x.id = passagens.de_sessao AND x.encerrada_em IS NULL))",
            {"p": projeto, "c": cwd, "d": dono, "m": manter, "s": de_sessao})
        if cur.rowcount:
            self._auditar(con, "expirar_superadas", projeto, em)

    # ── ler ────────────────────────────────────────────────────────────────

    @staticmethod
    def _dict(linha) -> dict:
        d = dict(linha)
        for k in ("perguntas", "proximos", "arquivos"):
            d[k] = json.loads(d[k])
        d["manual"] = d["de_sessao"] is None
        return d

    def obter(self, id: str) -> dict | None:
        with self._trava:
            linha = self._con.execute("SELECT * FROM passagens WHERE id = ?", (id,)).fetchone()
        return None if linha is None else self._dict(linha)

    def listar(self, projeto: str, estado: str | None = None, limite: int = 50) -> list[dict]:
        sql = "SELECT * FROM passagens WHERE projeto = ?"
        args: list = [projeto]
        if estado:
            sql += " AND estado = ?"
            args.append(estado)
        sql += " ORDER BY criada_em DESC, id DESC LIMIT ?"
        args.append(int(limite))
        with self._trava:
            return [self._dict(x) for x in self._con.execute(sql, args).fetchall()]

    def escolher(self, projeto: str, cwd_da_sessao: str | None = None, filtro_dono=None) -> dict | None:
        """A passagem a entregar a uma sessao que comeca em `cwd_da_sessao`, entre as abertas do projeto."""
        with self._trava:
            linhas = self._con.execute("SELECT * FROM passagens WHERE projeto = ? AND estado = 'aberta'", (projeto,)).fetchall()
        por_id = {x["id"]: x for x in linhas}
        cand = [Candidata(bytes.fromhex(x["id"]), x["de_sessao"] is None, x["criada_em"], x["cwd"], x["dono"]) for x in linhas]
        e = escolher(cand, cwd_da_sessao, filtro_dono)
        return None if e is None else self._dict(por_id[e.id.hex()])

    # ── aceitar ────────────────────────────────────────────────────────────

    def aceitar(self, id: str, *, projeto: str, agente: str, sessao: str | None = None, cwd_do_receptor: str | None = None,
                filtro_dono=None, usuario: str | None = None, reabre_sessao_apos_o_fim: bool = False,
                agora_us: int | None = None) -> bool:
        """`accept_handoff`: devolve True so para quem de fato aceitou. Com False, o texto nao chega ao agente."""
        em = _agora_us() if agora_us is None else agora_us
        if filtro_dono is not None and filtro_dono != ("sem_dono",) and filtro_dono[0] == "usuario":
            if usuario is not None and filtro_dono[1] != usuario:
                raise EstadoInvalido("o operador que aceita nao confere com o filtro de dono")
            if usuario is None:
                raise EstadoInvalido("aceitar com filtro de dono pede o operador que aceita")
        if filtro_dono == ("sem_dono",) and usuario is not None:
            raise EstadoInvalido("aceitar sem dono nao pode registrar um operador")
        with self._transacao() as con:
            if sessao is not None:
                receptor = con.execute(
                    "SELECT projeto = :p AND agente = :a AS confere, encerrada_em IS NULL AS aberta FROM sessoes WHERE id = :s",
                    {"p": projeto, "a": agente, "s": sessao}).fetchone()
                if receptor is None:
                    raise EstadoInvalido("a sessao que recebe a passagem nao existe")
                if not receptor["confere"]:
                    raise EstadoInvalido("a sessao que recebe a passagem nao e do projeto e do agente que aceitam")
                ja = con.execute("SELECT EXISTS(SELECT 1 FROM passagens WHERE estado = 'aceita' AND aceita_sessao = ?)", (sessao,)).fetchone()[0]
                if ja:
                    return False  # o inicio de sessao pode ser repetido: uma sessao nao consome duas passagens
                if not receptor["aberta"]:
                    if reabre_sessao_apos_o_fim:
                        con.execute("UPDATE sessoes SET encerrada_em = NULL WHERE id = ?", (sessao,))
                    else:
                        raise EstadoInvalido("uma sessao encerrada nao pode aceitar uma passagem")
            meta = con.execute(
                "SELECT de_sessao IS NOT NULL AS automatica, cwd, criada_em, dono FROM passagens"
                " WHERE id = ? AND projeto = ? AND estado = 'aberta'", (id, projeto)).fetchone()
            if meta is None:
                return False
            clausula = ""
            args: dict = {"a": agente, "em": em, "s": sessao, "u": usuario, "id": id, "p": projeto}
            if filtro_dono is None:
                pass
            elif filtro_dono == ("sem_dono",):
                clausula = " AND dono IS NULL"
            else:
                clausula = " AND (dono IS NULL OR dono = :dono)"
                args["dono"] = filtro_dono[1]
            cur = con.execute(
                "UPDATE passagens SET estado = 'aceita', aceita_por = :a, aceita_em = :em, aceita_sessao = :s WHERE id = :id AND projeto = :p"
                " AND estado = 'aberta'" + clausula, args)
            if cur.rowcount == 0:
                return False
            self._auditar(con, "aceitar", projeto, em)
            if meta["automatica"]:
                if self._expirar_superadas(con, id, projeto, meta["cwd"], meta["criada_em"], cwd_do_receptor, meta["dono"]):
                    self._auditar(con, "expirar_superadas", projeto, em)
            return True

    def _expirar_superadas(self, con, aceita_id, projeto, cwd_aceita, criada_em, cwd_do_receptor, dono) -> int:
        """Expira as automaticas mais antigas que serviriam ao mesmo cwd. Nunca manual, nunca de outro dono, nunca de sessao aberta."""
        receptor = cwd_do_receptor if cwd_do_receptor is not None else cwd_aceita
        chave_aceita = chave_de_escolha(False, criada_em, cwd_aceita, bytes.fromhex(aceita_id))
        linhas = con.execute(
            "SELECT id, cwd, criada_em FROM passagens WHERE projeto = :p AND estado = 'aberta' AND de_sessao IS NOT NULL AND dono IS :d"
            " AND NOT EXISTS (SELECT 1 FROM sessoes x WHERE x.id = passagens.de_sessao AND x.encerrada_em IS NULL)",
            {"p": projeto, "d": dono}).fetchall()
        ids = [x["id"] for x in linhas
               if casa_com_cwd(x["cwd"], receptor) and chave_de_escolha(False, x["criada_em"], x["cwd"], bytes.fromhex(x["id"])) < chave_aceita]
        for i in range(0, len(ids), 500):
            lote = ids[i:i + 500]
            con.execute(f"UPDATE passagens SET estado = 'expirada' WHERE estado = 'aberta' AND id IN ({','.join('?' * len(lote))})", lote)
        return len(ids)

    # ── encerrar sem aceitar ───────────────────────────────────────────────

    def expirar_abertas(self, projeto: str, mais_antigas_que_us: int | None = None, filtro_dono=None, agora_us: int | None = None) -> int:
        """`expire_open_handoffs`: expira toda passagem aberta do projeto, manual ou nao, de qualquer cwd.

        E o que limpa um acumulo: as que a expiracao automatica poupa (manuais, de outro diretorio) sao exatamente o que sobra.
        """
        em = _agora_us() if agora_us is None else agora_us
        sql = "UPDATE passagens SET estado = 'expirada' WHERE projeto = :p AND estado = 'aberta'"
        args: dict = {"p": projeto}
        if filtro_dono == ("sem_dono",):
            sql += " AND dono IS NULL"
        elif filtro_dono is not None:
            sql += " AND (dono IS NULL OR dono = :dono)"
            args["dono"] = filtro_dono[1]
        if mais_antigas_que_us is not None:
            sql += " AND criada_em <= :corte"
            args["corte"] = mais_antigas_que_us
        with self._transacao() as con:
            n = con.execute(sql, args).rowcount
            if n:
                self._auditar(con, "expirar_abertas", projeto, em)
        return n

    def cancelar(self, id: str, *, projeto: str, filtro_dono=None, agora_us: int | None = None) -> bool:
        """`cancel_handoff`: tira uma aberta de circulacao. False se ja nao estava aberta ou nao e deste projeto e dono."""
        em = _agora_us() if agora_us is None else agora_us
        sql = "UPDATE passagens SET estado = 'expirada' WHERE id = :id AND projeto = :p AND estado = 'aberta'"
        args: dict = {"id": id, "p": projeto}
        if filtro_dono == ("sem_dono",):
            sql += " AND dono IS NULL"
        elif filtro_dono is not None:
            sql += " AND (dono IS NULL OR dono = :dono)"
            args["dono"] = filtro_dono[1]
        with self._transacao() as con:
            n = con.execute(sql, args).rowcount
            if n:
                self._auditar(con, "cancelar", projeto, em)
        return n > 0
