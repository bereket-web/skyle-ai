from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    """Small-workspace SQLite store; raw questions and uploaded bytes are not retained."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL DEFAULT 'upload',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    page INTEGER,
                    body TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_document_id ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    happened_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    summary_json TEXT NOT NULL
                );
                """
            )
            try:
                db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
                    "chunk_id UNINDEXED, body, filename UNINDEXED, tokenize='unicode61')"
                )
            except sqlite3.OperationalError as exc:
                raise RuntimeError("This SQLite build must include the FTS5 extension.") from exc

    def add_document(
        self,
        *,
        filename: str,
        media_type: str,
        size_bytes: int,
        sha256: str,
        chunks: list[dict[str, Any]],
        source: str = "upload",
    ) -> tuple[dict[str, Any], bool]:
        with self._connect() as db:
            existing = db.execute("SELECT * FROM documents WHERE sha256=?", (sha256,)).fetchone()
            if existing:
                return self._document_dict(existing, db), False
            doc_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO documents(id, filename, media_type, size_bytes, sha256, source, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (doc_id, filename, media_type, size_bytes, sha256, source, utc_now()),
            )
            for item in chunks:
                cur = db.execute(
                    "INSERT INTO chunks(document_id, ordinal, page, body) VALUES(?,?,?,?)",
                    (doc_id, item["ordinal"], item.get("page"), item["body"]),
                )
                db.execute(
                    "INSERT INTO chunks_fts(chunk_id, body, filename) VALUES(?,?,?)",
                    (str(cur.lastrowid), item["body"], filename),
                )
            row = db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
            return self._document_dict(row, db), True

    @staticmethod
    def _document_dict(row: sqlite3.Row, db: sqlite3.Connection) -> dict[str, Any]:
        count = db.execute("SELECT COUNT(*) FROM chunks WHERE document_id=?", (row["id"],)).fetchone()[0]
        return {
            "id": row["id"],
            "filename": row["filename"],
            "media_type": row["media_type"],
            "size_bytes": row["size_bytes"],
            "sha256": row["sha256"],
            "source": row["source"],
            "created_at": row["created_at"],
            "chunk_count": count,
        }

    def list_documents(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM documents ORDER BY created_at DESC, id DESC").fetchall()
            return [self._document_dict(row, db) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as db:
            docs, chunks = (
                db.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            )
            return {"document_count": docs, "chunk_count": chunks}

    def search(self, query_tokens: list[str], limit: int = 5) -> list[dict[str, Any]]:
        if not query_tokens:
            return []
        unique = list(dict.fromkeys(token.replace('"', "") for token in query_tokens if token))[:12]
        match = " OR ".join(f'"{token}"' for token in unique)
        with self._connect() as db:
            try:
                rows = db.execute(
                    """SELECT c.id, c.document_id, c.ordinal, c.page, c.body, d.filename,
                              bm25(chunks_fts, 0.0, 1.0, 0.0) AS rank
                       FROM chunks_fts JOIN chunks c ON CAST(chunks_fts.chunk_id AS INTEGER)=c.id
                       JOIN documents d ON d.id=c.document_id
                       WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?""",
                    (match, max(1, min(limit * 4, 40))),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        hits: list[dict[str, Any]] = []
        qset = set(unique)
        for position, row in enumerate(rows, start=1):
            body_words = set(tokenize(row["body"]))
            coverage = len(qset & body_words) / max(1, len(qset))
            score = (0.7 / (60 + position)) + (0.3 * coverage)
            hits.append(
                {
                    "chunk_id": row["id"],
                    "document_id": row["document_id"],
                    "filename": row["filename"],
                    "ordinal": row["ordinal"],
                    "page": row["page"],
                    "text": row["body"],
                    "score": round(score, 4),
                }
            )
        return sorted(hits, key=lambda hit: hit["score"], reverse=True)[:limit]

    def delete_document(self, document_id: str) -> bool:
        with self._connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM chunks WHERE document_id=?", (document_id,))]
            if not db.execute("SELECT 1 FROM documents WHERE id=?", (document_id,)).fetchone():
                return False
            if ids:
                placeholders = ",".join("?" for _ in ids)
                db.execute(f"DELETE FROM chunks_fts WHERE CAST(chunk_id AS INTEGER) IN ({placeholders})", ids)
            db.execute("DELETE FROM documents WHERE id=?", (document_id,))
            return True

    def clear_documents(self) -> int:
        with self._connect() as db:
            count = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            db.execute("DELETE FROM chunks_fts")
            db.execute("DELETE FROM documents")
            return count

    def record_activity(self, action: str, status: str, duration_ms: int, summary: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO activity(happened_at, action, status, duration_ms, summary_json) VALUES(?,?,?,?,?)",
                (
                    utc_now(),
                    action,
                    status,
                    max(0, duration_ms),
                    json.dumps(summary, ensure_ascii=False, sort_keys=True),
                ),
            )

    def list_activity(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (max(1, min(limit, 100)),)).fetchall()
        return [
            {
                "id": row["id"],
                "happened_at": row["happened_at"],
                "action": row["action"],
                "status": row["status"],
                "duration_ms": row["duration_ms"],
                "summary": json.loads(row["summary_json"]),
            }
            for row in rows
        ]


def tokenize(text: str) -> list[str]:
    import re

    return re.findall(r"[\w\u1200-\u137F]+", text.lower(), flags=re.UNICODE)
