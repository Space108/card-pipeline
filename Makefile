.PHONY: help infra api worker temporal temporal-worker

help:
	@echo "make infra           - поднять postgres + rabbitmq (docker compose)"
	@echo "make api             - FastAPI на :8000"
	@echo "make worker          - celery-воркер (очереди card.generate + card.critique)"
	@echo "make temporal        - temporal dev server на :7233, UI :8233"
	@echo "make temporal-worker - temporal-воркер (workflow + activities)"

infra:
	docker compose up -d

api:
	uvicorn app.main:app --reload --port 8000

worker:
	celery -A app.workers.celery_app worker -Q card.generate,card.critique --pool=solo -l info

temporal:
	temporal server start-dev

temporal-worker:
	python -m app.temporal_worker
