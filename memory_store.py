from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import math
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


DB_PATH = Path(__file__).resolve().with_name("20w_memory.db")
DEFAULT_ACTIVE_BIAS_PROFILE = "sovereignty"
DEFAULT_BIAS_VALUES: Dict[str, float] = {
    "supervisor_bias": 0.5,
    "validator_bias": 0.5,
    "creative_bias": 0.5,
    "radar_bias": 0.5,
}

DEFAULT_BIAS_VECTORS = (
    (
        "sovereignty",
        "User strongly prioritises human sovereignty and long-term optionality.",
        0.98,
        0.72,
        0.68,
        0.48,
        0.54,
    ),
    (
        "synthesis",
        "Prefers ground-up synthesis, many-moves-ahead foresight, and leverage-point reasoning.",
        0.94,
        0.52,
        0.54,
        0.76,
        0.58,
    ),
    (
        "tone",
        "Reacts strongly to sycophantic, overly corporate, or over-polished tone.",
        0.9,
        0.58,
        0.72,
        0.46,
        0.78,
    ),
)


def _horizon_cache_fingerprint(prompt_text: str, source_text: str) -> str:
    fingerprint_payload = "\n".join(
        [
            "20w-dual-horizon-cache-v1",
            str(prompt_text or ""),
            str(source_text or ""),
        ]
    )
    return hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()


def _source_fingerprint(source_text: str) -> str:
    return hashlib.sha256(str(source_text or "").encode("utf-8")).hexdigest()


def _connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection
    except sqlite3.Error as exc:
        raise RuntimeError(f"Memory store connection failed: {exc}") from exc


@contextmanager
def _connection_scope(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = _connect(db_path)
        yield connection
        try:
            connection.commit()
        except sqlite3.Error as exc:
            raise RuntimeError(f"Memory store commit failed: {exc}") from exc
    except RuntimeError:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        raise
    except sqlite3.Error as exc:
        if connection is not None:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
        raise RuntimeError(f"Memory store transaction failed: {exc}") from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:
                pass


def _ensure_columns(
    connection: sqlite3.Connection,
    table_name: str,
    column_sql: Dict[str, str],
) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column_name, ddl in column_sql.items():
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _ensure_bias_columns(connection: sqlite3.Connection) -> None:
    _ensure_columns(
        connection,
        "bias_vectors",
        {
            "supervisor_bias": "supervisor_bias REAL NOT NULL DEFAULT 0.50",
            "validator_bias": "validator_bias REAL NOT NULL DEFAULT 0.50",
            "creative_bias": "creative_bias REAL NOT NULL DEFAULT 0.50",
            "radar_bias": "radar_bias REAL NOT NULL DEFAULT 0.50",
        },
    )


def _calibrate_seed_bias_rows(connection: sqlite3.Connection) -> None:
    for (
        pattern_type,
        description,
        _strength,
        supervisor_bias,
        validator_bias,
        creative_bias,
        radar_bias,
    ) in DEFAULT_BIAS_VECTORS:
        connection.execute(
            """
            UPDATE bias_vectors
            SET supervisor_bias = ?,
                validator_bias = ?,
                creative_bias = ?,
                radar_bias = ?
            WHERE pattern_type = ?
              AND description = ?
              AND supervisor_bias = ?
              AND validator_bias = ?
              AND creative_bias = ?
              AND radar_bias = ?
            """,
            (
                supervisor_bias,
                validator_bias,
                creative_bias,
                radar_bias,
                pattern_type,
                description,
                DEFAULT_BIAS_VALUES["supervisor_bias"],
                DEFAULT_BIAS_VALUES["validator_bias"],
                DEFAULT_BIAS_VALUES["creative_bias"],
                DEFAULT_BIAS_VALUES["radar_bias"],
            ),
        )


def _fallback_bias_profile(profile_name: str = DEFAULT_ACTIVE_BIAS_PROFILE) -> Dict[str, Any]:
    return {
        "pattern_type": profile_name or DEFAULT_ACTIVE_BIAS_PROFILE,
        "description": "Fallback baseline bias matrix; SQLite profile unavailable.",
        "strength": 0.5,
        "last_used": None,
        **DEFAULT_BIAS_VALUES,
    }


def _row_to_bias_profile(row: sqlite3.Row) -> Dict[str, Any]:
    row_dict = dict(row)
    for key, default_value in DEFAULT_BIAS_VALUES.items():
        row_dict[key] = min(1.0, max(0.0, float(row_dict.get(key, default_value))))
    row_dict["strength"] = min(1.0, max(0.0, float(row_dict.get("strength", 0.5))))
    return row_dict


def load_active_bias_profile(
    profile_name: str = DEFAULT_ACTIVE_BIAS_PROFILE,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """Load a concrete numeric bias row, falling back to a baseline if SQLite is unavailable."""
    initialize_memory(db_path=db_path)
    normalized_profile = (profile_name or DEFAULT_ACTIVE_BIAS_PROFILE).strip()
    try:
        with _connection_scope(db_path) as connection:
            _ensure_bias_columns(connection)
            row = connection.execute(
                """
                SELECT id, pattern_type, description, strength, last_used,
                       supervisor_bias, validator_bias, creative_bias, radar_bias
                FROM bias_vectors
                WHERE pattern_type = ?
                ORDER BY strength DESC, id ASC
                LIMIT 1
                """,
                (normalized_profile,),
            ).fetchone()
    except RuntimeError:
        return _fallback_bias_profile(normalized_profile)

    if row is None:
        return _fallback_bias_profile(normalized_profile)
    return _row_to_bias_profile(row)


async def update_bias_profile(
    profile_name: str,
    score_adjustment: float,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    """Persist adaptive bias-vector adjustments for an operator-scored profile."""
    initialize_memory(db_path=db_path)
    normalized_profile = (profile_name or DEFAULT_ACTIVE_BIAS_PROFILE).strip()
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with _connection_scope(db_path) as connection:
            _ensure_bias_columns(connection)
            row = connection.execute(
                """
                SELECT id, pattern_type, description, strength, last_used,
                       supervisor_bias, validator_bias, creative_bias, radar_bias
                FROM bias_vectors
                WHERE pattern_type = ?
                ORDER BY strength DESC, id ASC
                LIMIT 1
                """,
                (normalized_profile,),
            ).fetchone()
            if row is None:
                profile = _fallback_bias_profile(normalized_profile)
                profile["updated"] = False
                profile["score_adjustment"] = float(score_adjustment)
                return profile

            profile = _row_to_bias_profile(row)
            if score_adjustment > 0:
                profile["validator_bias"] = min(1.0, profile["validator_bias"] + 0.02)
                profile["supervisor_bias"] = min(1.0, profile["supervisor_bias"] + 0.02)
            elif score_adjustment < 0:
                profile["creative_bias"] = min(1.0, profile["creative_bias"] + 0.03)
                profile["radar_bias"] = min(1.0, profile["radar_bias"] + 0.03)

            connection.execute(
                """
                UPDATE bias_vectors
                SET supervisor_bias = ?,
                    validator_bias = ?,
                    creative_bias = ?,
                    radar_bias = ?,
                    last_used = ?
                WHERE id = ?
                """,
                (
                    profile["supervisor_bias"],
                    profile["validator_bias"],
                    profile["creative_bias"],
                    profile["radar_bias"],
                    timestamp,
                    profile["id"],
                ),
            )
            profile["last_used"] = timestamp
            profile["updated"] = True
            profile["score_adjustment"] = float(score_adjustment)
            return profile
    except RuntimeError:
        profile = _fallback_bias_profile(normalized_profile)
        profile["updated"] = False
        profile["score_adjustment"] = float(score_adjustment)
        return profile


def initialize_memory(db_path: Path = DB_PATH) -> None:
    """Create the v1.2 memory schema and seed baseline bias vectors."""
    try:
        with _connection_scope(db_path) as connection:
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
                    velocity_ms REAL NOT NULL DEFAULT 0.0,
                    intercept_triggered INTEGER NOT NULL DEFAULT 0,
                    raw_prompt_length INTEGER NOT NULL DEFAULT 0,
                    success_flag INTEGER NOT NULL
                )
                """
            )
            _ensure_columns(
                connection,
                "runs",
                {
                    "velocity_ms": "velocity_ms REAL NOT NULL DEFAULT 0.0",
                    "intercept_triggered": "intercept_triggered INTEGER NOT NULL DEFAULT 0",
                    "raw_prompt_length": "raw_prompt_length INTEGER NOT NULL DEFAULT 0",
                },
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bias_vectors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    strength REAL NOT NULL,
                    last_used TEXT,
                    supervisor_bias REAL NOT NULL DEFAULT 0.50,
                    validator_bias REAL NOT NULL DEFAULT 0.50,
                    creative_bias REAL NOT NULL DEFAULT 0.50,
                    radar_bias REAL NOT NULL DEFAULT 0.50,
                    UNIQUE(pattern_type, description)
                )
                """
            )
            _ensure_bias_columns(connection)
            _calibrate_seed_bias_rows(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_success_timestamp ON runs(success_flag, timestamp)"
            )
            connection.execute(
                """
                CREATE VIEW IF NOT EXISTS cognitive_history AS
                SELECT run_id, timestamp, core_target, variance_threshold, lookahead_horizon,
                       E_c, delta_a, S_d, velocity_ms, intercept_triggered, raw_prompt_length,
                       success_flag
                FROM runs
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_bias_strength ON bias_vectors(strength DESC)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dual_horizon_cache (
                    cache_key TEXT PRIMARY KEY,
                    source_fingerprint TEXT NOT NULL,
                    cached_node_payload TEXT NOT NULL,
                    persisted_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_fingerprint ON dual_horizon_cache(source_fingerprint)"
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO bias_vectors (
                    pattern_type, description, strength, supervisor_bias, validator_bias,
                    creative_bias, radar_bias, last_used
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                DEFAULT_BIAS_VECTORS,
            )
    except RuntimeError:
        return


async def fetch_horizon_cache(
    prompt_text: str,
    source_text: str,
    db_path: Path = DB_PATH,
) -> Optional[str]:
    """Return a cached node payload for an identical prompt/source fingerprint."""

    def _fetch() -> Optional[str]:
        initialize_memory(db_path=db_path)
        cache_key = _horizon_cache_fingerprint(prompt_text, source_text)
        try:
            with _connection_scope(db_path) as connection:
                row = connection.execute(
                    """
                    SELECT cached_node_payload
                    FROM dual_horizon_cache
                    WHERE cache_key = ?
                    LIMIT 1
                    """,
                    (cache_key,),
                ).fetchone()
        except RuntimeError:
            return None
        if row is None:
            return None
        return str(row["cached_node_payload"])

    return await asyncio.to_thread(_fetch)


async def commit_horizon_cache(
    prompt_text: str,
    source_text: str,
    generated_payload: str,
    db_path: Path = DB_PATH,
) -> Optional[str]:
    """Persist a generated payload against the deterministic prompt/source fingerprint."""

    def _commit() -> Optional[str]:
        initialize_memory(db_path=db_path)
        cache_key = _horizon_cache_fingerprint(prompt_text, source_text)
        source_fingerprint = _source_fingerprint(source_text)
        try:
            with _connection_scope(db_path) as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO dual_horizon_cache (
                        cache_key, source_fingerprint, cached_node_payload, persisted_timestamp
                    )
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        cache_key,
                        source_fingerprint,
                        str(generated_payload or ""),
                    ),
                )
        except RuntimeError:
            return None
        return cache_key

    return await asyncio.to_thread(_commit)


def calculate_relevance_score(target_prompt: str, historical_intent: str) -> float:
    """Score history by lowercase alphanumeric token overlap against the current target."""
    target_words = set(re.findall(r"[a-z0-9]+", target_prompt.lower()))
    historical_words = set(re.findall(r"[a-z0-9]+", historical_intent.lower()))
    if not target_words or not historical_words:
        return 0.0

    intersection_count = len(target_words.intersection(historical_words))
    if intersection_count == 0:
        return 0.0

    normalization = max(1.0, math.log1p(len(target_words)))
    return round(intersection_count / normalization, 6)


def load_successful_runs(
    limit: int = 3,
    db_path: Path = DB_PATH,
    target_prompt: str = "",
    candidate_limit: int = 15,
) -> List[Dict[str, Any]]:
    candidate_limit = max(limit, candidate_limit)
    try:
        with _connection_scope(db_path) as connection:
            rows = connection.execute(
                """
                SELECT run_id, timestamp, core_target, variance_threshold, lookahead_horizon,
                       E_c, delta_a, S_d, velocity_ms, intercept_triggered, raw_prompt_length,
                       success_flag
                FROM cognitive_history
                WHERE success_flag = 1
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (candidate_limit,),
            ).fetchall()
    except RuntimeError:
        return []

    scored_rows: List[Dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        row_dict["relevance_score"] = calculate_relevance_score(
            target_prompt=target_prompt,
            historical_intent=str(row_dict.get("core_target", "")),
        )
        scored_rows.append(row_dict)

    scored_rows.sort(
        key=lambda row: (
            float(row.get("relevance_score", 0.0)),
            str(row.get("timestamp", "")),
        ),
        reverse=True,
    )
    return scored_rows[:limit]


def load_bias_vectors(limit: int = 5, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    initialize_memory(db_path=db_path)
    try:
        with _connection_scope(db_path) as connection:
            _ensure_bias_columns(connection)
            rows = connection.execute(
                """
                SELECT id, pattern_type, description, strength, last_used,
                       supervisor_bias, validator_bias, creative_bias, radar_bias
                FROM bias_vectors
                ORDER BY strength DESC, id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except RuntimeError:
        return [_fallback_bias_profile()]
    return [_row_to_bias_profile(row) for row in rows]


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


def log_run(state: Dict[str, Any], db_path: Path = DB_PATH) -> Optional[str]:
    run_id = state.get("run_id")
    if not run_id:
        return None

    timestamp = datetime.now(timezone.utc).isoformat()
    target_prompt = str(state.get("target_prompt", ""))
    try:
        with _connection_scope(db_path) as connection:
            _ensure_columns(
                connection,
                "runs",
                {
                    "velocity_ms": "velocity_ms REAL NOT NULL DEFAULT 0.0",
                    "intercept_triggered": "intercept_triggered INTEGER NOT NULL DEFAULT 0",
                    "raw_prompt_length": "raw_prompt_length INTEGER NOT NULL DEFAULT 0",
                },
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, timestamp, core_target, variance_threshold, lookahead_horizon,
                    E_c, delta_a, S_d, velocity_ms, intercept_triggered, raw_prompt_length,
                    success_flag
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    timestamp,
                    target_prompt,
                    float(state.get("variance_threshold", 0.0)),
                    int(state.get("lookahead_horizon", 0)),
                    float(state.get("E_c", 0.0)),
                    float(state.get("delta_a", 0.0)),
                    float(state.get("S_d", 0.0)),
                    float(state.get("velocity_ms", 0.0)),
                    1 if state.get("intercept_triggered", False) else 0,
                    len(target_prompt),
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
    except RuntimeError:
        return None

    return str(run_id)


def record_run(state: Dict[str, Any], db_path: Path = DB_PATH) -> Optional[str]:
    return log_run(state, db_path=db_path)
