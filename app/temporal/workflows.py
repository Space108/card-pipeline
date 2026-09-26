"""CardWorkflow: extract → (generate → critique)* → сигнал оператора → финал.

Правила детерминизма workflow-кода:
- никаких datetime.now / random / HTTP / чтения конфига — только логика;
- все side-effects — в activities (app/temporal/activities.py);
- таймауты и лимиты — константы модуля, не settings (конфиг меняется
  между реплеями и ломает воспроизведение истории).

Песочница воркфлоу запрещает тяжёлые импорты, поэтому app.schemas
и activities проходят через workflow.unsafe.imports_passed_through().
"""
import json
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.schemas import CritiqueReport
    from app.temporal.activities import (
        critique_activity,
        extract_activity,
        generate_activity,
    )

ACTIVITY_TIMEOUT = timedelta(seconds=300)
EXTRACT_RETRY = RetryPolicy(maximum_attempts=2)
GENERATE_RETRY = RetryPolicy(maximum_attempts=3)


@workflow.defn
class CardWorkflow:
    def __init__(self) -> None:
        self._status = "starting"
        self._human_decision: str | None = None

    @workflow.run
    async def run(self, supplier_text: str, max_attempts: int = 3) -> str:
        self._status = "extracting"
        facts_json = await workflow.execute_activity(
            extract_activity,
            supplier_text,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=EXTRACT_RETRY,
        )
        feedback = None
        draft_json = ""
        for attempt in range(1, max_attempts + 1):
            self._status = f"generating (attempt {attempt})"
            feedback_json = json.dumps(feedback, ensure_ascii=False) if feedback else None
            draft_json = await workflow.execute_activity(
                generate_activity,
                args=[facts_json, feedback_json],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=GENERATE_RETRY,
            )
            self._status = f"critiquing (attempt {attempt})"
            report_json = await workflow.execute_activity(
                critique_activity,
                args=[facts_json, draft_json],
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=GENERATE_RETRY,
            )
            report = CritiqueReport.model_validate_json(report_json)
            if report.verdict == "approve":
                break
            feedback = report.issues
        self._status = "awaiting human decision"
        await workflow.wait_condition(lambda: self._human_decision is not None)
        self._status = "completed" if self._human_decision == "approve" else "rejected by human"
        return draft_json

    @workflow.signal
    def approve(self) -> None:
        self._human_decision = "approve"

    @workflow.signal
    def request_changes(self) -> None:
        self._human_decision = "regenerate"

    @workflow.query
    def current_status(self) -> str:
        return self._status
