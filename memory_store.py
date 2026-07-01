from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = Path(__file__).resolve().with_name("20w_memory.db")

DEFAULT_BIAS_VECTORS = (
    (
        "sovereignty",
        "User strongly prioritises human sovereignty and long-term optionality.",
        0.98,
    ),
    (
        "synthesis",
        "Prefers ground-up synthesis, many-moves-ahead foresight, and leverage-point reasoning.",
        0.94,
    ),
    (
        "tone",
        "Reacts strongly to sycophantic, overly corporate, or over-polished tone.",
        0.9,
    ),
)


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_memory(db_path: Path = DB_PATH) -> None:
    """Create the v1.2 memory schema and seed baseline bias vectors."""
    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                core_target TEXT NOT NULL,
                variance_threshold REAL NOT NULL,
                lookahead_horizon INTEGER NOT NULL,
                E_c REAL NOT NULL,
                delta_a REAL NOT NULL,
                S_d REAL NOT NULL,
                success_flag INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS bias_vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                description TEXT NOT NULL,
                strength REAL NOT NULL,
                last_used TEXT,
                UNIQUE(pattern_type, description)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_success_timestamp ON runs(success_flag, timestamp)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_bias_strength ON bias_vectors(strength DESC)"
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO bias_vectors (pattern_type, description, strength, last_used)
            VALUES (?, ?, ?, NULL)
            """,
            DEFAULT_BIAS_VECTORS,
        )


def load_successful_runs(limit: int = 5, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, timestamp, core_target, variance_threshold, lookahead_horizon,
                   E_c, delta_a, S_d, success_flag
            FROM runs
            WHERE success_flag = 1
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def load_bias_vectors(limit: int = 5, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, pattern_type, description, strength, last_used
            FROM bias_vectors
            ORDER BY strength DESC, id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def build_bias_profile(
    successful_runs: List[Dict[str, Any]], bias_vectors: List[Dict[str, Any]]
) -> str:
    vector_text = " ".join(vector["description"] for vector in bias_vectors)
    if not vector_text:
        vector_text = (
            "User strongly prioritises human sovereignty and long-term optionality. "
            "Prefers ground-up synthesis. Reacts strongly to sycophantic or overly corporate tone."
        )

    recent_targets = [
        str(run["core_target"]).strip()
        for run in successful_runs
        if str(run.get("core_target", "")).strip()
    ]
    if recent_targets:
        target_hint = " Recent successful target pattern: " + " | ".join(recent_targets[:3])
    else:
        target_hint = " No prior successful run history yet; use baseline bias vectors."

    return f"Neil Strategic Bias Profile: {vector_text}{target_hint}"


def load_bias_profile(db_path: Path = DB_PATH) -> str:
    return build_bias_profile(
        successful_runs=load_successful_runs(db_path=db_path),
        bias_vectors=load_bias_vectors(db_path=db_path),
    )


def record_run(state: Dict[str, Any], db_path: Path = DB_PATH) -> Optional[str]:
    run_id = state.get("run_id")
    if not run_id:
        return None

    timestamp = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id, timestamp, core_target, variance_threshold, lookahead_horizon,
                E_c, delta_a, S_d, success_flag
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                timestamp,
                state.get("target_prompt", ""),
                float(state.get("variance_threshold", 0.0)),
                int(state.get("lookahead_horizon", 0)),
                float(state.get("E_c", 0.0)),
                float(state.get("delta_a", 0.0)),
                float(state.get("S_d", 0.0)),
                1 if state.get("success_flag", True) else 0,
            ),
        )
        connection.execute(
            """
            UPDATE bias_vectors
            SET last_used = ?
            WHERE id IN (
                SELECT id FROM bias_vectors
                ORDER BY strength DESC, id ASC
                LIMIT 5
            )
            """,
            (timestamp,),
        )

    return str(run_id)
