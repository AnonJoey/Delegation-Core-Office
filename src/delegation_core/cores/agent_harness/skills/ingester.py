import os
import glob
from ..db import get_connection, init_db

REPOS = [
    ("ECC", "harness-skills"),
    ("superpowers", "tdd-discipline"),
    ("marketingskills", "marketing-cro"),
    ("ponytail", "code-conciseness"),
    ("hallmark", "anti-slop-design"),
    ("humanizer", "prose-naturalization"),
    ("i-have-adhd", "action-first-rules")
]

def ingest_all(src_modules_dir: str, db_path: str = None) -> int:
    conn = get_connection(db_path)
    init_db(conn)
    
    total_indexed = 0
    with conn:
        conn.execute("DELETE FROM skills")
        conn.execute("DELETE FROM skills_fts")
        
        for repo_name, category in REPOS:
            repo_path = os.path.join(src_modules_dir, repo_name)
            if not os.path.exists(repo_path):
                continue
                
            files = glob.glob(f"{repo_path}/**/*.md", recursive=True)
            for f in files:
                basename = os.path.basename(f)
                if basename in ["README.md", "CONTRIBUTING.md", "LICENSE.md", "CHANGELOG.md"]:
                    continue
                    
                rel_path = os.path.relpath(f, repo_path).replace(os.sep, "/")
                title = os.path.splitext(basename)[0].replace("-", " ").replace("_", " ").title()
                
                try:
                    with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                except Exception:
                    continue
                    
                char_count = len(content)
                if char_count < 10:
                    continue
                    
                conn.execute(
                    "INSERT INTO skills (source_repo, title, rel_path, category, content, char_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (repo_name, title, rel_path, category, content, char_count)
                )
                total_indexed += 1
                
    return total_indexed

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        raise SystemExit("uso: python -m delegation_core.cores.agent_harness.skills.ingester <pasta-dos-modulos-de-skills>")
    src_dir = sys.argv[1]
    count = ingest_all(src_dir)
    print(f"[OK] Ingestao concluida: {count} skills indexadas no SQLite FTS5!")
