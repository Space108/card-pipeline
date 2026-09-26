"""Фоновый вариант: job в RabbitMQ → Celery-воркер (шаги 2-3 практики)."""
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from app.core.db import connect
from app.schemas import JobIn
from app.services import jobs as jobs_repo
from app.workers.celery_app import celery_app

router = APIRouter(tags=["jobs"])


@router.post("/jobs", status_code=202)
async def create_job(
    body: JobIn,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    conn = connect()
    try:
        already = None
        if idempotency_key:
            found = conn.execute(
                "SELECT id FROM jobs WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
            already = found[0] if found else None
        job_id = jobs_repo.create_job(
            conn, {"supplier_text": body.supplier_text}, idempotency_key
        )
    finally:
        conn.close()
    if already is None:
        celery_app.send_task(
            "app.workers.tasks.generate_card",
            kwargs={"job_id": job_id, "supplier_text": body.supplier_text},
            queue="card.generate",
        )
    return JSONResponse({"id": job_id, "status": "pending"}, status_code=202)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
    finally:
        conn.close()
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job["result"] is not None:
        job["result"] = job["result"].model_dump()
    return job
