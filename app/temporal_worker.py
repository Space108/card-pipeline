"""Точка входа Temporal-воркера: регистрирует workflows + activities."""
import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.temporal.activities import critique_activity, extract_activity, generate_activity
from app.temporal.workflows import CardWorkflow

log = get_logger(__name__)


async def main():
    setup_logging()
    client = await Client.connect(settings.temporal_host)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[CardWorkflow],
        activities=[extract_activity, generate_activity, critique_activity],
    )
    log.info("temporal_worker_started", task_queue=settings.temporal_task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
