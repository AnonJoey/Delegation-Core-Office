import os
import sqlite3
from pathlib import Path

#: O catalogo de skills e construido nesta maquina, a partir das pastas de skills que o
#: usuario tem, com `python -m delegation_core.cores.agent_harness.skills.ingester <pasta>`.
#: Nao vem no pacote: o catalogo do fork reunia texto de repositorios de terceiros sem
#: licenca conferida, e o Office e publico (mesma regra do achado 10 da auditoria de
#: 16/11). Tambem nao mora dentro do pacote instalado, onde a reinstalacao o apagaria.
DEFAULT_DB_PATH = Path(os.environ.get("DELEGATION_CORE_SKILLS_DB")
                       or Path.home() / ".delegation_core" / "skills.db")


def get_connection(db_path: str = None) -> sqlite3.Connection:
    """Abre o catalogo e garante as tabelas: catalogo ainda nao construido e um catalogo
    vazio, nao um erro `no such table`."""
    path = Path(db_path or DEFAULT_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn

def init_db(conn: sqlite3.Connection):
    with conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_repo TEXT NOT NULL,
            title TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            category TEXT,
            content TEXT NOT NULL,
            char_count INTEGER,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
            title,
            category,
            content,
            content='skills',
            content_rowid='id'
        );
        """)
        # Triggers para manter o FTS5 sincronizado
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS skills_ai AFTER INSERT ON skills BEGIN
            INSERT INTO skills_fts(rowid, title, category, content)
            VALUES (new.id, new.title, new.category, new.content);
        END;
        """)
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS skills_ad AFTER DELETE ON skills BEGIN
            INSERT INTO skills_fts(skills_fts, rowid, title, category, content)
            VALUES ('delete', old.id, old.title, old.category, old.content);
        END;
        """)
        conn.execute("""
        CREATE TRIGGER IF NOT EXISTS skills_au AFTER UPDATE ON skills BEGIN
            INSERT INTO skills_fts(skills_fts, rowid, title, category, content)
            VALUES ('delete', old.id, old.title, old.category, old.content);
            INSERT INTO skills_fts(rowid, title, category, content)
            VALUES (new.id, new.title, new.category, new.content);
        END;
        """)
