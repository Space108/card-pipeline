"""Стадии пайплайна: extract → generate → critique.

Каждая функция — один агент-шаг. Один и тот же код работает в трёх runtime:
- FastAPI-эндпоинт (шаг 1 практики),
- Celery-воркер (шаги 2-3),
- Temporal activity (шаг 4).
Это и есть выигрыш слоистой архитектуры.
"""
from app.agents.prompts import critic_agent, extractor_agent, generator_agent
from app.core.logging import get_logger
from app.llm.client import run_agent
from app.schemas import CardDraft, CritiqueReport, SupplierFacts

log = get_logger(__name__)


async def extract(supplier_text: str) -> SupplierFacts:
    log.info("step_extract_start")
    out = await run_agent(extractor_agent, supplier_text)
    if isinstance(out, SupplierFacts):
        return out
    return SupplierFacts.model_validate_json(_ensure_json(out))


async def generate(facts: SupplierFacts, feedback: list[str] | None = None) -> CardDraft:
    log.info("step_generate_start", feedback=bool(feedback))
    prompt = "Факты о товаре:\n" + facts.model_dump_json(indent=2)
    if feedback:
        lines = "\n".join(f"- {item}" for item in feedback)
        prompt += "\n\nЗамечания критика, учти:\n" + lines
    out = await run_agent(generator_agent, prompt)
    if isinstance(out, CardDraft):
        return out
    return CardDraft.model_validate_json(_ensure_json(out))


async def critique(facts: SupplierFacts, draft: CardDraft) -> CritiqueReport:
    log.info("step_critique_start")
    prompt = (
        "Факты о товаре:\n"
        + facts.model_dump_json(indent=2)
        + "\n\nЧерновик карточки для проверки:\n"
        + draft.model_dump_json(indent=2)
    )
    out = await run_agent(critic_agent, prompt)
    if isinstance(out, CritiqueReport):
        return out
    return CritiqueReport.model_validate_json(_ensure_json(out))


def _ensure_json(text) -> str:
    """Локальные модели иногда оборачивают JSON в ```json ... ``` — срезаем."""
    s = str(text).strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    return s.strip()


async def run_pipeline(supplier_text: str, max_attempts: int = 3):
    """Полный цикл: extract → (generate → critique → feedback)* → итог.

    Возвращает (итоговый черновик, число генераций, вердикт).
    """
    facts = await extract(supplier_text)
    feedback = None
    draft = None
    verdict = "rejected"
    attempts = 0
    for _ in range(max_attempts):
        attempts += 1
        draft = await generate(facts, feedback)
        report = await critique(facts, draft)
        if report.verdict == "approve":
            verdict = "approved"
            break
        feedback = report.issues
        log.info("pipeline_regenerate", issues=report.issues)
    return draft, attempts, verdict
