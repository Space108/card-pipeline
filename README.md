# card-pipeline — шаблон к Занятию 2

Каркас для практики занятия: структура приложения готова, ключевые тела —
`TODO` с подсказками. Готовая реализация — в [`../пример/`](../пример/),
пошаговый разбор — в [`../практика.md`](../практика.md).

## Что где лежит

| Файл / папка | Шаг практики | Что делать |
|---|---|---|
| `docker-compose.yml`, `schema.sql`, `Makefile`, `.env.example` | 0 | готово, не трогать |
| `app/core/` (config, logging, db) | 0 | готово |
| `app/schemas.py` | 0 | готово — контракты агентов |
| `app/agents/prompts.py` | 0 | готово — три агента из З1 |
| `app/llm/client.py` | 1 | TODO: `setup_llm`, `_retryable`, ретрай-цикл `run_agent` |
| `app/services/steps.py` | 1 | TODO: `extract` / `generate` / `critique` / `run_pipeline` |
| `app/routers/cards.py` | 1 | TODO: `POST /cards` |
| `app/services/jobs.py` | 2 | TODO: `create_job` / `set_status` / `get_job` |
| `app/workers/celery_app.py` | 2 | TODO: одна строка — импорт tasks |
| `app/workers/tasks.py` | 2-3 | TODO: обе таски |
| `app/routers/jobs.py` | 2 | TODO: `POST /jobs`, `GET /jobs/{id}` |
| `app/temporal/activities.py` | 4 | готово — обёртки над steps |
| `app/temporal/workflows.py` | 4 | TODO: `run`, сигналы |
| `app/routers/workflows.py` | 4 | TODO: старт/query/сигналы |
| `tests/test_pipeline.py` | 1 | чекер шага 1: `pytest` зелёный = клиент и пайплайн готовы |

## Запуск окружения

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # впиши LLM_MODEL из curl localhost:1234/v1/models
make infra                    # postgres + rabbitmq
make api                      # терминал 1
make worker                   # терминал 2 (после шага 2)
make temporal                 # терминал 3 (после шага 4)
make temporal-worker          # терминал 4 (после шага 4)
```

## Порядок работы

1. Шаг 1 → `pytest` зелёный → `curl POST /cards` возвращает карточку.
2. Шаг 2 → `POST /jobs` → `GET /jobs/{id}` проходит статусы до `approved`.
3. Шаг 3 → «плохой» текст запускает петлю регенерации (логи воркера).
4. Шаг 4 → workflow доходит до `awaiting human decision`, сигнал `approve`
   завершает его; история — в UI http://localhost:8233.

Если 5432 занят другим postgres — `PG_PORT=5433 make infra` и поправь
`DATABASE_URL` в `.env`.
