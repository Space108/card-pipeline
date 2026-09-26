"""Temporal-вариант через FastAPI: старт workflow, статус, сигналы."""
import uuid

from fastapi import APIRouter, HTTPException
from temporalio.client import Client, WorkflowExecutionStatus

from app.core.config import settings
from app.schemas import JobIn

router = APIRouter(tags=["workflows"])


async def _client() -> Client:
    return await Client.connect(settings.temporal_host)


@router.post("/workflows", status_code=202)
async def start_workflow(body: JobIn):
    client = await _client()
    wf_id = f"card-{uuid.uuid4().hex[:12]}"
    await client.start_workflow(
        "CardWorkflow",
        args=[body.supplier_text, 3],
        id=wf_id,
        task_queue=settings.temporal_task_queue,
    )
    return {"id": wf_id, "status": "started"}


@router.get("/workflows/{wf_id}")
async def workflow_status(wf_id: str):
    client = await _client()
    handle = client.get_workflow_handle(wf_id)
    try:
        description = await handle.describe()
        status = await handle.query("current_status")
    except Exception as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    return {
        "id": wf_id,
        "run_status": description.status.name,
        "status": status,
    }


@router.post("/workflows/{wf_id}/approve")
async def approve(wf_id: str):
    client = await _client()
    await client.get_workflow_handle(wf_id).signal("approve")
    return {"id": wf_id, "signal": "approve"}


@router.post("/workflows/{wf_id}/request-changes")
async def request_changes(wf_id: str):
    client = await _client()
    await client.get_workflow_handle(wf_id).signal("request_changes")
    return {"id": wf_id, "signal": "request_changes"}


@router.get("/workflows/{wf_id}/result")
async def workflow_result(wf_id: str):
    client = await _client()
    handle = client.get_workflow_handle(wf_id)
    try:
        description = await handle.describe()
    except Exception as exc:
        raise HTTPException(status_code=404, detail="workflow not found") from exc
    if description.status != WorkflowExecutionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="workflow is still running")
    try:
        result = await handle.result()
    except Exception as exc:
        raise HTTPException(status_code=409, detail="workflow is still running") from exc
    return {"result": result}
