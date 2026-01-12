import hashlib
import json
import os
import sqlite3
import time
from typing import Any, Dict, Optional, List


class AIPerformanceStore:
    def __init__(self, db_path: str | None = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, "data", "ai_performance.sqlite")

        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    run_type TEXT NOT NULL,
                    strategy_hash TEXT NOT NULL,
                    strategy_code TEXT NOT NULL,
                    user_goal TEXT,
                    scenario_name TEXT,
                    iteration INTEGER,
                    timerange TEXT,
                    timeframe TEXT,
                    pairs TEXT,
                    result_file TEXT,
                    model_analysis TEXT,
                    model_risk TEXT,
                    analysis_text TEXT,
                    risk_text TEXT,
                    backtest_summary_json TEXT,
                    trade_forensics_json TEXT,
                    market_context_json TEXT,
                    extra_json TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy_runs_ts ON strategy_runs(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy_runs_hash ON strategy_runs(strategy_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_strategy_runs_type ON strategy_runs(run_type)")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    run_id INTEGER NOT NULL,
                    rating INTEGER NOT NULL,
                    comments TEXT,
                    FOREIGN KEY(run_id) REFERENCES strategy_runs(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_feedback_ts ON run_feedback(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_run_feedback_run_id ON run_feedback(run_id)")

    @staticmethod
    def compute_strategy_hash(strategy_code: str) -> str:
        if not isinstance(strategy_code, str) or not strategy_code.strip():
            raise ValueError("strategy_code must be a non-empty string")
        return hashlib.sha256(strategy_code.strip().encode("utf-8")).hexdigest()

    def record_run(
        self,
        *,
        run_type: str,
        strategy_code: str,
        user_goal: str | None = None,
        scenario_name: str | None = None,
        iteration: int | None = None,
        timerange: str | None = None,
        timeframe: str | None = None,
        pairs: str | None = None,
        result_file: str | None = None,
        model_analysis: str | None = None,
        model_risk: str | None = None,
        analysis_text: str | None = None,
        risk_text: str | None = None,
        backtest_summary: Optional[Dict[str, Any]] = None,
        trade_forensics: Optional[Dict[str, Any]] = None,
        market_context: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        if not isinstance(run_type, str) or not run_type.strip():
            raise ValueError("run_type must be a non-empty string")
        if not isinstance(strategy_code, str) or not strategy_code.strip():
            raise ValueError("strategy_code must be a non-empty string")

        ts = int(time.time())
        strategy_hash = self.compute_strategy_hash(strategy_code)

        bt_summary_json = json.dumps(backtest_summary, ensure_ascii=False) if isinstance(backtest_summary, dict) else None
        tf_json = json.dumps(trade_forensics, ensure_ascii=False) if isinstance(trade_forensics, dict) else None
        mc_json = json.dumps(market_context, ensure_ascii=False) if isinstance(market_context, dict) else None
        extra_json = json.dumps(extra, ensure_ascii=False) if isinstance(extra, dict) else None

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO strategy_runs (
                    ts, run_type, strategy_hash, strategy_code, user_goal,
                    scenario_name, iteration, timerange, timeframe, pairs,
                    result_file, model_analysis, model_risk,
                    analysis_text, risk_text,
                    backtest_summary_json, trade_forensics_json, market_context_json, extra_json
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    ts,
                    run_type.strip(),
                    strategy_hash,
                    strategy_code,
                    (user_goal or None),
                    (scenario_name or None),
                    iteration,
                    (timerange or None),
                    (timeframe or None),
                    (pairs or None),
                    (result_file or None),
                    (model_analysis or None),
                    (model_risk or None),
                    (analysis_text or None),
                    (risk_text or None),
                    bt_summary_json,
                    tf_json,
                    mc_json,
                    extra_json,
                ),
            )
            return int(cur.lastrowid)

    def get_run_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(1) FROM strategy_runs").fetchone()[0]
            last_ts_row = conn.execute("SELECT MAX(ts) FROM strategy_runs").fetchone()
            last_ts = last_ts_row[0] if last_ts_row else None

            rows = conn.execute(
                "SELECT run_type, COUNT(1) FROM strategy_runs GROUP BY run_type ORDER BY COUNT(1) DESC"
            ).fetchall()
            by_type: Dict[str, int] = {}
            for r in rows:
                if r and isinstance(r[0], str):
                    by_type[r[0]] = int(r[1])

            return {
                "total_runs": int(total),
                "last_ts": int(last_ts) if last_ts is not None else None,
                "by_type": by_type,
            }

    def get_recent_runs(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM strategy_runs ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
            
            results = []
            for row in rows:
                d = dict(row)
                if d.get("backtest_summary_json"):
                    try:
                        d["backtest_summary"] = json.loads(d["backtest_summary_json"])
                    except Exception:
                        d["backtest_summary"] = {}
                if d.get("trade_forensics_json"):
                    try:
                        d["trade_forensics"] = json.loads(d["trade_forensics_json"])
                    except Exception:
                        d["trade_forensics"] = {}
                results.append(d)
            return results

    def get_run_by_id(self, run_id: int) -> Dict[str, Any]:
        if not isinstance(run_id, int) or run_id <= 0:
            raise ValueError("run_id must be a positive integer")

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM strategy_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                raise RuntimeError("run_id not found")

            d = dict(row)
            if d.get("backtest_summary_json"):
                try:
                    d["backtest_summary"] = json.loads(d["backtest_summary_json"])
                except Exception:
                    d["backtest_summary"] = {}
            if d.get("trade_forensics_json"):
                try:
                    d["trade_forensics"] = json.loads(d["trade_forensics_json"])
                except Exception:
                    d["trade_forensics"] = {}
            if d.get("market_context_json"):
                try:
                    d["market_context"] = json.loads(d["market_context_json"])
                except Exception:
                    d["market_context"] = {}
            if d.get("extra_json"):
                try:
                    d["extra"] = json.loads(d["extra_json"])
                except Exception:
                    d["extra"] = {}

            return d

    def get_latest_run_for_hash(self, strategy_hash: str) -> Optional[Dict[str, Any]]:
        if not isinstance(strategy_hash, str) or not strategy_hash.strip():
            raise ValueError("strategy_hash must be a non-empty string")

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM strategy_runs WHERE strategy_hash = ? ORDER BY ts DESC, id DESC LIMIT 1",
                (strategy_hash.strip(),),
            ).fetchone()
            if not row:
                return None

            d = dict(row)
            if d.get("backtest_summary_json"):
                try:
                    d["backtest_summary"] = json.loads(d["backtest_summary_json"])
                except Exception:
                    d["backtest_summary"] = {}
            if d.get("trade_forensics_json"):
                try:
                    d["trade_forensics"] = json.loads(d["trade_forensics_json"])
                except Exception:
                    d["trade_forensics"] = {}
            if d.get("market_context_json"):
                try:
                    d["market_context"] = json.loads(d["market_context_json"])
                except Exception:
                    d["market_context"] = {}
            if d.get("extra_json"):
                try:
                    d["extra"] = json.loads(d["extra_json"])
                except Exception:
                    d["extra"] = {}
            return d

    def get_recent_param_suggestions(self, limit: int = 200) -> Dict[str, List[str]]:
        if not isinstance(limit, int) or limit < 1 or limit > 5000:
            raise ValueError("limit must be an integer between 1 and 5000")

        timeranges: List[str] = []
        timeframes: List[str] = []
        pairs: List[str] = []

        def _add_unique(dst: List[str], v: str) -> None:
            if not isinstance(v, str):
                return
            s = v.strip()
            if not s:
                return
            if s not in dst:
                dst.append(s)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT ts, timerange, timeframe, pairs FROM strategy_runs ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()

            for row in rows:
                d = dict(row)
                _add_unique(timeranges, str(d.get("timerange") or "").strip())
                _add_unique(timeframes, str(d.get("timeframe") or "").strip())

                p = str(d.get("pairs") or "").strip()
                if p:
                    for part in p.replace(";", ",").split(","):
                        _add_unique(pairs, part)

        return {
            "timeranges": timeranges,
            "timeframes": timeframes,
            "pairs": pairs,
        }

    def record_feedback(self, *, run_id: int, rating: int, comments: str | None = None) -> int:
        if not isinstance(run_id, int) or run_id <= 0:
            raise ValueError("run_id must be a positive integer")
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            raise ValueError("rating must be an integer between 1 and 5")
        if comments is not None and (not isinstance(comments, str) or not comments.strip()):
            comments = None

        ts = int(time.time())
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM strategy_runs WHERE id = ?", (run_id,)).fetchone()
            if not exists:
                raise RuntimeError(f"strategy run not found: {run_id}")

            cur = conn.execute(
                "INSERT INTO run_feedback (ts, run_id, rating, comments) VALUES (?, ?, ?, ?)",
                (ts, run_id, rating, comments),
            )
            return int(cur.lastrowid)

    def get_feedback_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(1) FROM run_feedback").fetchone()[0]
            avg_row = conn.execute("SELECT AVG(rating) FROM run_feedback").fetchone()
            avg_rating = float(avg_row[0]) if avg_row and avg_row[0] is not None else 0.0
            with_comments = conn.execute(
                "SELECT COUNT(1) FROM run_feedback WHERE comments IS NOT NULL AND TRIM(comments) != ''"
            ).fetchone()[0]

            dist_rows = conn.execute(
                "SELECT rating, COUNT(1) FROM run_feedback GROUP BY rating ORDER BY rating"
            ).fetchall()
            dist: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for r in dist_rows:
                try:
                    k = int(r[0])
                    v = int(r[1])
                    if 1 <= k <= 5:
                        dist[k] = v
                except Exception:
                    continue

            return {
                "total_feedback": int(total),
                "average_rating": round(avg_rating, 2),
                "rating_distribution": dist,
                "feedback_with_comments": int(with_comments),
            }
