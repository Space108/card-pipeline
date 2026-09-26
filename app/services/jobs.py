"""Repository-слой: таблица jobs в Postgres.

Единственный владелец SQL. Статусная машина:
pending → extracting → generating → critiquing → (regenerating) → approved | rejected | failed
"""
import json
import uuid
from datetime import UTC, datetime

import psycopg

from app.schemas import CardDraft


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(conn: psycopg.Connection, payload: dict, idempotency_key: str | None) -> str:
    """INSERT pending. При повторном idempotency_key возвращает существующий id."""
    if idempotency_key:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE idempotency_key = %s",
            (idempotency_key,),
        ).fetchone()
        if existing:
            return existing[0]
    job_id = uuid.uuid4().hex[:12]
    conn.execute(
        """
        INSERT INTO jobs (id, idempotency_key, payload)
        VALUES (%s, %s, %s)
        """,
        (job_id, idempotency_key, json.dumps(payload, ensure_ascii=False)),
    )
    return job_id


def set_status(
    conn: psycopg.Connection, job_id: str, status: str, *, result: CardDraft | None = None,
    error: str | None = None, bump_attempts: bool = False,
) -> None:
    sets = ["status = %s", "updated_at = %s"]
    args: list = [status, _now()]
    if result is not None:
        sets.append("result = %s")
        args.append(result.model_dump_json())
    if error is not None:
        sets.append("error = %s")
        args.append(error)
    if bump_attempts:
        sets.append("attempts = attempts + 1")
    args.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = %s", args)


def get_job(conn: psycopg.Connection, job_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, status, attempts, result, error FROM jobs WHERE id = %s",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    job_id_value, status, attempts, result_raw, error = row
    result = None
    if isinstance(result_raw, dict):
        result = CardDraft.model_validate(result_raw)
    elif isinstance(result_raw, str):
        result = CardDraft.model_validate_json(result_raw)
    return {
        "id": job_id_value,
        "status": status,
        "attempts": attempts,
        "result": result,
        "error": error,
    }
