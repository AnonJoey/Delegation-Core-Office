from typing import List, Dict, Any, Optional
from ..db import get_connection

class SkillsRegistry:
    def __init__(self, db_path: str = None):
        self.db_path = db_path

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        sql = """
        SELECT s.id, s.source_repo, s.title, s.category, s.rel_path, s.char_count,
               snippet(skills_fts, 2, '<b>', '</b>', '...', 20) as snippet
        FROM skills_fts f
        JOIN skills s ON f.rowid = s.id
        WHERE skills_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """
        try:
            cursor.execute(sql, (query, limit))
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            # Fallback para LIKE se a query FTS5 tiver sintaxe especial
            sql_fallback = """
            SELECT id, source_repo, title, category, rel_path, char_count,
                   substr(content, 1, 150) as snippet
            FROM skills
            WHERE title LIKE ? OR content LIKE ?
            LIMIT ?
            """
            pattern = f"%{query}%"
            cursor.execute(sql_fallback, (pattern, pattern, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_by_id(self, skill_id: int) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skills WHERE id = ?", (skill_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM skills WHERE title LIKE ? LIMIT 1", (f"%{title}%",))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_stats(self) -> Dict[str, Any]:
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT source_repo, count(*), sum(char_count) FROM skills GROUP BY source_repo")
        rows = cursor.fetchall()
        return {
            row[0]: {"count": row[1], "total_chars": row[2]}
            for row in rows
        }
