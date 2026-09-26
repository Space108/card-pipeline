# Отчёт

## 1. Повтор вызова модели и повтор всей задачи

Повтор одного обращения к модели делает `run_agent` в `app/llm/client.py`. Он повторяет только ошибки соединения, таймаут, 429 и коды от 500. На 400, 401 и 404 исключение пробрасывается сразу: повтор такого запроса не изменит ответ, а токены спишутся ещё раз. Пауза между попытками растёт (`min(2**attempt * 0.5, 8.0)`) и к ней добавляется случайная доля, чтобы несколько процессов не проснулись одновременно.

Повтор всего шага делает уже движок, который этот шаг запустил.

- В Celery это повторная доставка сообщения. У задач включены `task_acks_late` и `task_reject_on_worker_lost`: если исполнитель умер посреди `generate_card`, брокер возвращает сообщение в очередь, и новый исполнитель запускает задачу с начала.
- В Temporal повтор настроен на шаге. Извлечение ограничено двумя попытками (`EXTRACT_RETRY`), генерация и проверка — тремя (`GENERATE_RETRY`). Уже выполненный шаг в историю записан и заново не исполняется.

Граница стоит здесь, потому что клиент видит один HTTP-разговор с моделью и не знает, какая это стадия пайплайна. Если повторять всю задачу из клиента, обрыв сети на проверке заново запустит извлечение и генерацию. Счёт за токены умножится на число попыток, а петля переделок смешается с лечением сетевого сбоя.

## 2. Трасса переделок

Живой прогон: задача `389394bae779`, текст «Товар. Хороший. Продаем.», модель `qwen2.5:7b` через Ollama (`http://localhost:11434/v1`). Критик отработал три итерации и ни разу не поставил `approve`. `GET /jobs/389394bae779` закончился так: `status=rejected`, `attempts=3`, `error=critic not satisfied after max attempts`. Черновик в `result` сохранён.

В логе видны поля, к которым он придрался: `title` (в тексте замечания есть порог 60), пустые `characteristics`, `description` и `benefits`. На последней итерации к ним добавились `missing_fields`. Сами русские формулировки консоль Windows в этот лог не записала.

Бюджет читается из колонки `attempts`, её увеличивает генератор выражением `attempts = attempts + 1` в базе. После третьей проверки `attempts < 3` уже ложно, статус становится `rejected`, в лог пишется `job_rejected`.

Что замечания дошли до генератора, видно по строке `step_generate_start feedback=True`. Её пишет `generate` в `app/services/steps.py`, когда второй аргумент непустой. Первая генерация в том же логе — `feedback=False`. В синхронном пайплайне та же петля отмечается строкой `pipeline_regenerate`.

Фрагмент лога Celery-исполнителя (задача `389394bae779`):

```text
2026-09-27 00:00:58 [info] step_extract_start
2026-09-27 00:01:03 [info] step_generate_start            feedback=False
2026-09-27 00:01:13 [info] step_critique_start
2026-09-27 00:01:23 [info] job_regenerate
2026-09-27 00:01:23 [info] step_extract_start
2026-09-27 00:01:28 [info] step_generate_start            feedback=True
2026-09-27 00:01:58 [info] step_critique_start
2026-09-27 00:02:10 [info] job_regenerate
2026-09-27 00:02:10 [info] step_extract_start
2026-09-27 00:02:15 [info] step_generate_start            feedback=True
2026-09-27 00:02:29 [info] step_critique_start
2026-09-27 00:02:40 [info] job_rejected
```

## 3. Убитый исполнитель Celery

Задача `606690e20601`, текст про блендер «МиксерПро 800». Дождался статуса `generating` (`attempts=1`) и остановил процесс исполнителя.

Сообщение и строка задачи — разные хранилища, и живой прогон это показал.

- В интерфейсе брокера очередь `card.generate` в момент работы держала сообщение неподтверждённым: `ready 0`, `unacked 1`. Сразу после остановки процесса потребителей не осталось, сообщение вернулось в готовые: `ready 1`, `unacked 0`. Подтверждения не было, потому что у задач включён `task_acks_late`.
- `GET /jobs/606690e20601` при этом по-прежнему отвечал `status=generating`, `attempts=1`. Статус пишется в базу до вызова модели и переживает смерть процесса.

После нового запуска исполнителя то же сообщение пришло снова (`generate_card received`). Работа началась с начала задачи, а не с оборванной генерации: статус вернулся в `extracting`, в логе снова `step_extract_start`, затем новый `step_generate_start feedback=False`, и только потом `attempts` стал `2`.

К модели это стоило повторных обращений. До остановки извлечение уже успело завершиться (один ответ `200` в `00:35:09`), а генерация была оборвана. После перезапуска извлечение и генерация выполнились заново (ответы `200` в `00:35:51` и `00:36:10`). Итого до проверки — три завершённых вызова вместо двух, плюс один оборванный.

Temporal ту же паузу отрабатывает иначе. История процесса помнит завершённое извлечение. Новый воркер продолжает с упавшего шага, а `extract_activity` второй раз не запускается. Пока процесс стоит на `workflow.wait_condition`, воркер вообще не держит поток: ожидание человека ничего не стоит.

## 4. История Temporal

Прогон `card-a6ba035dca14` на тексте про блендер «МиксерПро 800». Опрос `GET /workflows/card-a6ba035dca14` дошёл до `awaiting human decision` при `run_status=RUNNING`. После `POST /workflows/card-a6ba035dca14/approve` статус стал `completed`, `run_status=COMPLETED`.

```text
temporal workflow show --workflow-id card-a6ba035dca14

Progress:
  ID           Time                     Type
    1  2026-09-26T21:04:19Z  WorkflowExecutionStarted
    2  2026-09-26T21:04:19Z  WorkflowTaskScheduled
    3  2026-09-26T21:04:19Z  WorkflowTaskStarted
    4  2026-09-26T21:04:19Z  WorkflowTaskCompleted
    5  2026-09-26T21:04:19Z  ActivityTaskScheduled
    6  2026-09-26T21:04:19Z  ActivityTaskStarted
    7  2026-09-26T21:04:32Z  ActivityTaskCompleted
    8  2026-09-26T21:04:32Z  WorkflowTaskScheduled
    9  2026-09-26T21:04:32Z  WorkflowTaskStarted
   10  2026-09-26T21:04:32Z  WorkflowTaskCompleted
   11  2026-09-26T21:04:32Z  ActivityTaskScheduled
   12  2026-09-26T21:04:32Z  ActivityTaskStarted
   13  2026-09-26T21:04:58Z  ActivityTaskCompleted
   14  2026-09-26T21:04:58Z  WorkflowTaskScheduled
   15  2026-09-26T21:04:58Z  WorkflowTaskStarted
   16  2026-09-26T21:04:58Z  WorkflowTaskCompleted
   17  2026-09-26T21:04:58Z  ActivityTaskScheduled
   18  2026-09-26T21:04:58Z  ActivityTaskStarted
   19  2026-09-26T21:05:11Z  ActivityTaskCompleted
   20  2026-09-26T21:05:11Z  WorkflowTaskScheduled
   21  2026-09-26T21:05:11Z  WorkflowTaskStarted
   22  2026-09-26T21:05:11Z  WorkflowTaskCompleted
   23  2026-09-26T21:05:11Z  ActivityTaskScheduled
   24  2026-09-26T21:05:11Z  ActivityTaskStarted
   25  2026-09-26T21:05:33Z  ActivityTaskCompleted
   26  2026-09-26T21:05:33Z  WorkflowTaskScheduled
   27  2026-09-26T21:05:33Z  WorkflowTaskStarted
   28  2026-09-26T21:05:33Z  WorkflowTaskCompleted
   29  2026-09-26T21:05:33Z  ActivityTaskScheduled
   30  2026-09-26T21:05:33Z  ActivityTaskStarted
   31  2026-09-26T21:05:39Z  ActivityTaskCompleted
   32  2026-09-26T21:05:39Z  WorkflowTaskScheduled
   33  2026-09-26T21:05:39Z  WorkflowTaskStarted
   34  2026-09-26T21:05:39Z  WorkflowTaskCompleted
   35  2026-09-26T21:05:51Z  WorkflowExecutionSignaled
   36  2026-09-26T21:05:51Z  WorkflowTaskScheduled
   37  2026-09-26T21:05:51Z  WorkflowTaskStarted
   38  2026-09-26T21:05:51Z  WorkflowTaskCompleted
   39  2026-09-26T21:05:51Z  WorkflowExecutionCompleted

Results:
  Status          COMPLETED
```

Тот же прогон с `--detailed` называет шаги: событие 5 — `extract_activity` (`maximumAttempts: 2`), 11 — `generate_activity`, 17 — `critique_activity` с `verdict=regenerate`, 23 — снова `generate_activity`, на вход уже список замечаний, 29 — `critique_activity` с `verdict=approve`. Событие 35: `signalName: approve`. Между событием 34 и сигналом процесс стоял на `awaiting human decision`: новых activity в истории нет.

В этой истории видно то, чего нет в логе Celery: отдельные события по шагам (что извлечение уже закрыто, какая попытка генерации ещё идёт), сигнал `approve` и момент, когда процесс дошёл до `awaiting human decision`. Лог Celery показывает только то, что успел напечатать живой процесс, и после рестарта это новая задача, а не продолжение той же истории.

## 5. Что было сложным

Сложнее всего оказалось не смешать два уровня повтора и вызов асинхронных стадий из синхронной задачи Celery. Статус пишется до долгого вызова, и каждая стадия идёт в своём `asyncio.run`, иначе опрос не видит `extracting` → `generating` → `critiquing`.

Вторая ловушка — аргументы шага Temporal. Один аргумент передаётся позиционно, несколько только через `args=[...]`. Кортеж позиционно приезжает одним значением, и шаг падает одинаково на каждой попытке: политика повторов это не лечит.
