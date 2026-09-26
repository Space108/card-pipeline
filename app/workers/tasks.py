"""Мульти-агент через брокер: очередь генерации.

generate_card (очередь card.generate):
    extract → generate → UPDATE jobs → отправить critique_card.

Celery-таски sync, а Agents SDK async → мост asyncio.run() в каждой таске.
Стейт между агентами живёт ТОЛЬКО в таблице jobs — не в памяти воркера.
"""
import asyncio

from app.core.db import connect
from app.core.logging import get_logger
from app.services import jobs as jobs_repo
from app.services import steps
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="app.workers.tasks.generate_card", max_retries=2)
def generate_card(job_id: str, supplier_text: str, feedback: list[str] | None = None):
    conn = connect()
    try:
        jobs_repo.set_status(conn, job_id, "extracting")
        facts = asyncio.run(steps.extract(supplier_text))
        jobs_repo.set_status(conn, job_id, "generating", bump_attempts=True)
        draft = asyncio.run(steps.generate(facts, feedback))
        jobs_repo.set_status(conn, job_id, "critiquing")
        celery_app.send_task(
            "app.workers.tasks.critique_card",
            kwargs={
                "job_id": job_id,
                "supplier_text": supplier_text,
                "facts_json": facts.model_dump_json(),
                "draft_json": draft.model_dump_json(),
            },
            queue="card.critique",
        )
    except Exception as exc:
        jobs_repo.set_status(conn, job_id, "failed", error=repr(exc))
        log.error("generate_failed", job_id=job_id, error=repr(exc))
        raise
