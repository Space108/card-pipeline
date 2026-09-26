"""Тесты пайплайна с mock-агентами: без LM Studio и без сети."""
import asyncio

import pytest

from app.llm import client as llm_client
from app.schemas import CardDraft, CritiqueReport, SupplierFacts
from app.services import steps


def _facts() -> SupplierFacts:
    return SupplierFacts(
        product_name="Блендер погружной «МиксерПро 800»",
        characteristics={"Мощность": "800 Вт", "Питание": "220 В"},
    )


def _draft(title="МиксерПро 800 — блендер 800 Вт") -> CardDraft:
    return CardDraft(
        title=title,
        description="Погружной блендер с металлической ножкой и турбо-режимом.",
        characteristics={"Мощность": "800 Вт"},
        benefits=["Металлическая ножка", "6 скоростей"],
    )


@pytest.fixture
def fake_llm(monkeypatch):
    """Подменяем run_agent: сценарий задаётся тестом."""
    calls = {"n": 0}
    scenario: list = []

    async def fake_run(agent, prompt):
        result = scenario[calls["n"]]
        calls["n"] += 1
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(steps, "run_agent", fake_run)
    return {"scenario": scenario, "calls": calls}


def test_extract_parses_json_with_markdown_fencing(fake_llm):
    fake_llm["scenario"].append("```json\n" + _facts().model_dump_json() + "\n```")
    facts = asyncio.run(steps.extract("текст поставщика"))
    assert facts.product_name.startswith("Блендер")
    assert facts.characteristics["Мощность"] == "800 Вт"


def test_pipeline_approves_on_first_critique(fake_llm):
    fake_llm["scenario"] += [_facts(), _draft(), CritiqueReport(verdict="approve")]
    draft, attempts, verdict = asyncio.run(steps.run_pipeline("текст"))
    assert verdict == "approved"
    assert attempts == 1
    assert draft.title.startswith("МиксерПро")


def test_pipeline_regenerates_until_max_attempts(fake_llm):
    fake_llm["scenario"] += [
        _facts(),
        _draft(), CritiqueReport(verdict="regenerate", issues=["заголовок длинный"]),
        _draft(), CritiqueReport(verdict="regenerate", issues=["много воды"]),
        _draft(), CritiqueReport(verdict="regenerate", issues=["всё ещё вода"]),
    ]
    draft, attempts, verdict = asyncio.run(steps.run_pipeline("текст", max_attempts=3))
    assert verdict == "rejected"
    assert attempts == 3
    assert draft is not None


def test_run_agent_retries_on_429(monkeypatch):
    """429 → пауза → повтор. 4xx без повтора — см. test_run_agent_no_retry_on_4xx."""
    from openai import APIStatusError

    class FakeResult:
        final_output = "ok"

    err = APIStatusError.__new__(APIStatusError)
    err.status_code = 429

    calls = {"n": 0}
    sleeps: list[float] = []

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt):
            calls["n"] += 1
            if calls["n"] == 1:
                raise err
            return FakeResult()

    async def fake_sleep(sec):
        sleeps.append(sec)

    class FakeAgent:
        name = "test"

    monkeypatch.setattr(llm_client, "setup_llm", lambda: None)
    monkeypatch.setattr(llm_client, "Runner", FakeRunner)
    monkeypatch.setattr(llm_client.asyncio, "sleep", fake_sleep)

    out = asyncio.run(llm_client.run_agent(FakeAgent(), "x"))
    assert out == "ok"
    assert calls["n"] == 2
    assert len(sleeps) == 1


def test_run_agent_no_retry_on_4xx(monkeypatch):
    from openai import APIStatusError

    err = APIStatusError.__new__(APIStatusError)
    err.status_code = 400

    calls = {"n": 0}

    class FakeRunner:
        @staticmethod
        async def run(agent, prompt):
            calls["n"] += 1
            raise err

    class FakeAgent:
        name = "test"

    monkeypatch.setattr(llm_client, "setup_llm", lambda: None)
    monkeypatch.setattr(llm_client, "Runner", FakeRunner)

    with pytest.raises(APIStatusError):
        asyncio.run(llm_client.run_agent(FakeAgent(), "x"))
    assert calls["n"] == 1  # без повторов


def test_retryable_classification():
    assert llm_client._retryable(Exception("x")) is False
    assert llm_client._retryable(ValueError("x")) is False
