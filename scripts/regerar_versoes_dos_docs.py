"""Regera `versoes_entregues_docs.json`: o hash de toda versao que ja entregamos de cada doc.

Rode depois de editar AGENT_GUIDE.md ou CLAUDE_SYSTEM_PROMPT.md e antes de commitar:

    python3 scripts/regerar_versoes_dos_docs.py

Le o historico inteiro do git de cada doc mais a copia de trabalho. O instalador usa o
arquivo para saber que uma copia local identica a uma versao antiga nunca foi editada e pode
ser trocada pela nova (`refresh_shipped_files`). Mantem os hashes que ja estavam no JSON, para
um clone raso nao perder versoes. O teste `test_versoes_dos_docs_cobrem_o_que_o_repo_entrega`
falha se isto for esquecido.
"""
import hashlib
import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOCS = ("AGENT_GUIDE.md", "CLAUDE_SYSTEM_PROMPT.md")
ALVO = RAIZ / "versoes_entregues_docs.json"


def historico(doc: str) -> set[str]:
    hashes = set()
    commits = subprocess.run(["git", "log", "--format=%H", "--", doc], cwd=RAIZ, capture_output=True,
                             text=True, check=False).stdout.split()
    for c in commits:
        r = subprocess.run(["git", "show", f"{c}:{doc}"], cwd=RAIZ, capture_output=True, check=False)
        if r.returncode == 0:
            hashes.add(hashlib.sha256(r.stdout).hexdigest())
    return hashes


def main() -> None:
    atual = {k: set(v) for k, v in json.loads(ALVO.read_text(encoding="utf-8")).items()} if ALVO.exists() else {}
    for doc in DOCS:
        atual.setdefault(doc, set()).update(historico(doc))
        atual[doc].add(hashlib.sha256((RAIZ / doc).read_bytes()).hexdigest())
    ALVO.write_text(json.dumps({k: sorted(v) for k, v in sorted(atual.items())}, indent=1) + "\n", encoding="utf-8")
    for k, v in sorted(atual.items()):
        print(len(v), k)


if __name__ == "__main__":
    main()
