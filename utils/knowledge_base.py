import os
import re
import sqlite3
import time
from collections import Counter
from math import log
from typing import Any, Dict, Iterable, List, Optional, Tuple
import threading


class KnowledgeBase:
    _refresh_lock = threading.Lock()

    def __init__(self, base_dir: str, db_path: str | None = None):
        if not isinstance(base_dir, str) or not base_dir.strip():
            raise ValueError("base_dir must be a non-empty string")

        self.base_dir = base_dir
        if db_path is None:
            db_path = os.path.join(self.base_dir, "data", "knowledge_base.sqlite")

        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

        self._chunk_cache: List[Dict[str, Any]] = []
        self._idf_cache: Dict[str, float] = {}
        self._cache_loaded_at = 0.0

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_sources (
                    source_key TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    mtime REAL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS kb_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(source_key) REFERENCES kb_sources(source_key) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kb_chunks_source_key ON kb_chunks(source_key)")

    def _tokenize(self, text: str) -> List[str]:
        return [t.lower() for t in re.findall(r"[A-Za-z0-9_]{2,}", text)]

    def _chunk_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be >= 0 and < chunk_size")

        chunks: List[str] = []
        i = 0
        n = len(text)
        while i < n:
            end = min(n, i + chunk_size)
            chunk = text[i:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= n:
                break
            i = end - overlap
        return chunks

    def _iter_file_sources(self) -> Iterable[Tuple[str, str, str, float]]:
        candidates = [
            ("file", "README.md", os.path.join(self.base_dir, "README.md")),
            ("file", "docs/AI_ENHANCEMENTS.md", os.path.join(self.base_dir, "docs", "AI_ENHANCEMENTS.md")),
        ]

        for _typ, rel, path in candidates:
            if os.path.exists(path):
                yield (f"file:{rel}", _typ, rel, os.path.getmtime(path))

        strat_dir = os.path.join(self.base_dir, "user_data", "strategies")
        if os.path.isdir(strat_dir):
            for name in sorted(os.listdir(strat_dir)):
                if not name.lower().endswith(".py"):
                    continue
                p = os.path.join(strat_dir, name)
                if os.path.isfile(p):
                    rel = f"user_data/strategies/{name}"
                    yield (f"file:{rel}", "file", rel, os.path.getmtime(p))

    def _iter_recent_run_sources(self, limit: int = 80) -> Iterable[Tuple[str, str, str, float]]:
        perf_db = os.path.join(self.base_dir, "data", "ai_performance.sqlite")
        if not os.path.exists(perf_db):
            return

        conn = sqlite3.connect(perf_db)
        try:
            rows = conn.execute(
                """
                SELECT id, ts, run_type
                FROM strategy_runs
                WHERE (analysis_text IS NOT NULL AND TRIM(analysis_text) != '')
                   OR (risk_text IS NOT NULL AND TRIM(risk_text) != '')
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        finally:
            conn.close()

        for r in rows:
            run_id = int(r[0])
            ts = int(r[1])
            run_type = str(r[2])
            key = f"run:{run_id}"
            label = f"strategy_run:{run_id}:{run_type}"
            yield (key, "run", label, float(ts))

    def refresh(self) -> None:
        with self._refresh_lock:
            now = int(time.time())
            sources: List[Tuple[str, str, str, float]] = []
            sources.extend(list(self._iter_file_sources()))
            sources.extend(list(self._iter_recent_run_sources()))

            with self._connect() as conn:
                conn.execute("PRAGMA foreign_keys=ON")

                existing = {
                    row[0]: {"source_type": row[1], "source_label": row[2], "mtime": row[3]}
                    for row in conn.execute("SELECT source_key, source_type, source_label, mtime FROM kb_sources").fetchall()
                }

                live_keys = set()
                for source_key, source_type, source_label, mtime in sources:
                    live_keys.add(source_key)
                    prev = existing.get(source_key)
                    changed = prev is None or (prev.get("mtime") != mtime)

                    if changed:
                        conn.execute(
                            "INSERT OR REPLACE INTO kb_sources (source_key, source_type, source_label, mtime, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (source_key, source_type, source_label, mtime, now),
                        )
                        conn.execute("DELETE FROM kb_chunks WHERE source_key = ?", (source_key,))

                        content = self._load_source_content(source_key)
                        chunks = self._chunk_text(content, chunk_size=1600, overlap=200)
                        for idx, ch in enumerate(chunks):
                            conn.execute(
                                "INSERT INTO kb_chunks (source_key, chunk_index, content, updated_at) VALUES (?, ?, ?, ?)",
                                (source_key, idx, ch, now),
                            )

                stale = [k for k in existing.keys() if k not in live_keys]
                for k in stale:
                    conn.execute("DELETE FROM kb_sources WHERE source_key = ?", (k,))

            self._chunk_cache = []
            self._idf_cache = {}
            self._cache_loaded_at = 0.0

    def refresh_if_stale(self, max_age_seconds: int = 900) -> bool:
        if not isinstance(max_age_seconds, int) or max_age_seconds < 0:
            raise ValueError("max_age_seconds must be a non-negative integer")

        now = int(time.time())
        last_updated = None
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT MAX(updated_at) FROM kb_sources").fetchone()
                if row and row[0] is not None:
                    last_updated = int(row[0])
        except Exception:
            last_updated = None

        if last_updated is None:
            self.refresh()
            return True

        if (now - last_updated) > max_age_seconds:
            self.refresh()
            return True

        return False

    def _load_source_content(self, source_key: str) -> str:
        if source_key.startswith("file:"):
            rel = source_key.split(":", 1)[1]
            path = os.path.join(self.base_dir, *rel.split("/"))
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

        if source_key.startswith("run:"):
            perf_db = os.path.join(self.base_dir, "data", "ai_performance.sqlite")
            if not os.path.exists(perf_db):
                raise RuntimeError("Performance DB not found for run source")

            run_id = int(source_key.split(":", 1)[1])
            conn = sqlite3.connect(perf_db)
            try:
                row = conn.execute(
                    """
                    SELECT run_type, strategy_hash, analysis_text, risk_text
                    FROM strategy_runs
                    WHERE id = ?
                    """,
                    (run_id,),
                ).fetchone()
            finally:
                conn.close()

            if not row:
                raise RuntimeError(f"Run not found: {run_id}")

            run_type = str(row[0])
            strategy_hash = str(row[1])
            analysis_text = row[2] or ""
            risk_text = row[3] or ""
            parts = [f"run_id={run_id}", f"run_type={run_type}", f"strategy_hash={strategy_hash}"]
            if analysis_text.strip():
                parts.append("analysis:\n" + str(analysis_text))
            if risk_text.strip():
                parts.append("risk:\n" + str(risk_text))
            return "\n\n".join(parts)

        raise RuntimeError(f"Unknown source key: {source_key}")

    def _load_cache_if_needed(self) -> None:
        if self._chunk_cache and (time.time() - self._cache_loaded_at) < 30:
            return

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT s.source_label, c.content
                FROM kb_chunks c
                JOIN kb_sources s ON s.source_key = c.source_key
                ORDER BY s.source_key, c.chunk_index
                """
            ).fetchall()

        chunks: List[Dict[str, Any]] = []
        for label, content in rows:
            txt = str(content)
            tokens = self._tokenize(txt)
            chunks.append({"source": str(label), "content": txt, "tf": Counter(tokens)})

        n = max(1, len(chunks))
        df: Counter = Counter()
        for ch in chunks:
            for t in ch["tf"].keys():
                df[t] += 1

        idf: Dict[str, float] = {}
        for t, d in df.items():
            idf[t] = log((n + 1.0) / (d + 1.0)) + 1.0

        self._chunk_cache = chunks
        self._idf_cache = idf
        self._cache_loaded_at = time.time()

    def retrieve(self, query: str, top_k: int = 4, max_chars: int = 2500) -> List[Dict[str, str]]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if max_chars < 200:
            raise ValueError("max_chars must be >= 200")

        self._load_cache_if_needed()

        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []

        scores: List[Tuple[float, Dict[str, Any]]] = []
        for ch in self._chunk_cache:
            tf: Counter = ch["tf"]
            s = 0.0
            for t in q_tokens:
                if t in tf:
                    s += float(self._idf_cache.get(t, 1.0)) * float(tf[t])
            if s > 0:
                scores.append((s, ch))

        scores.sort(key=lambda x: x[0], reverse=True)

        out: List[Dict[str, str]] = []
        used = 0
        for _s, ch in scores[: max(20, top_k * 5)]:
            if len(out) >= top_k:
                break
            content = ch["content"].strip()
            if not content:
                continue

            remaining = max_chars - used
            if remaining <= 0:
                break

            snippet = content
            if len(snippet) > min(900, remaining):
                snippet = snippet[: min(900, remaining)].rstrip()

            out.append({"source": ch["source"], "content": snippet})
            used += len(snippet)

        return out
