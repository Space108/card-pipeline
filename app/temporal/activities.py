"""Temporal-activities: те же стадии пайплайна из app/services.

Activities выполняются БЕЗ песочницы — здесь можно импортировать конфиг,
LLM-клиент, ходить в сеть. Данные передаём JSON-строками: Temporal
сериализует их в историю workflow, Pydantic-валидация — на границе.
"""
import json

from temporalio import activity

from app.schemas import CardDraft, SupplierFacts
from app.services import steps


@activity.defn
async def extract_activity(supplier_text: str) -> str:
    facts = await steps.extract(supplier_text)
    return facts.model_dump_json()


@activity.defn
async def generate_activity(facts_json: str, feedback_json: str | None = None) -> str:
    facts = SupplierFacts.model_validate_json(facts_json)
    feedback = json.loads(feedback_json) if feedback_json else None
    draft = await steps.generate(facts, feedback)
    return draft.model_dump_json()


@activity.defn
async def critique_activity(facts_json: str, draft_json: str) -> str:
    facts = SupplierFacts.model_validate_json(facts_json)
    draft = CardDraft.model_validate_json(draft_json)
    report = await steps.critique(facts, draft)
    return report.model_dump_json()
