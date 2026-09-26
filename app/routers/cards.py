"""Синхронный вариант: весь пайплайн внутри запроса (шаг 1 практики)."""
from fastapi import APIRouter

from app.schemas import CardDraft, JobIn
from app.services.steps import run_pipeline

router = APIRouter(tags=["cards"])


@router.post("/cards", response_model=CardDraft)
async def create_card(body: JobIn) -> CardDraft:
    draft, _attempts, _verdict = await run_pipeline(body.supplier_text)
    return draft
