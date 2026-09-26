"""Celery-приложение: брокер — RabbitMQ, result backend не нужен.

Статус работы живёт в таблице jobs (Postgres), а не в result backend Celery —
нам важно бизнес-состояние, а не возвращаемое значение таски.
"""
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "card",
    broker=settings.rabbitmq_url,
    backend=None,
)

celery_app.conf.update(
    task_acks_late=True,          # ack ПОСЛЕ выполнения, не при получении
    task_reject_on_worker_lost=True,  # упал воркер → сообщение вернётся в очередь
)

import app.workers.tasks  # noqa: E402,F401
