from contextlib import contextmanager
import sqlite3
from pathlib import Path
from .config import DATABASE_PATH

@contextmanager
def connect():
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()

def init_db():
    with connect() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS documents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source TEXT NOT NULL UNIQUE,
          domain TEXT NOT NULL,
          title TEXT NOT NULL,
          content TEXT NOT NULL,
          fetched_at TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain)")

def upsert_document(source, domain, title, content, fetched_at):
    content = " ".join((content or "").split())[:30000]
    if len(content) < 80:
        return False
    with connect() as db:
        db.execute("""INSERT INTO documents(source,domain,title,content,fetched_at)
        VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET
        domain=excluded.domain,title=excluded.title,content=excluded.content,
        fetched_at=excluded.fetched_at""", (source, domain, title[:300], content, fetched_at))
    return True

def all_documents():
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM documents ORDER BY fetched_at DESC")]

def count_documents():
    with connect() as db:
        return db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

def search_documents(query, limit=6):
    terms = [t.lower() for t in __import__("re").findall(r"[a-zA-Z0-9]{2,}", query)]
    docs = all_documents()
    scored = []
    for d in docs:
        haystack = (d["title"] + " " + d["content"]).lower()
        score = sum(haystack.count(term) for term in set(terms))
        if score:
            scored.append((score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:limit]]
