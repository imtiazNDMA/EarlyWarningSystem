"""Tests for the analyst agent inside a monitoring cycle, with a scripted model."""

import copy
import json
from typing import Any

import httpx
from fastapi import FastAPI
from httpx import AsyncClient
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from ews.api.dependencies import get_air_quality_client, get_forecast_client
from ews.cycles.events import RunEventLog, SessionFactory
from ews.cycles.service import run_cycle
from tests.conftest import (
    ADMIN_TOKEN,
    RECORDED_FORECAST,
    Model,
    Upstream,
    llm_gateway_answering,
    model_turn,
    tool_call,
)
from tests.test_cycles import polluted_lahore, wet_in_lahore
from tests.test_run_events import events_of

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


def submit(**overrides: Any) -> dict[str, Any]:
    """A turn submitting an assessment that confirms the Lahore rain signal."""
    assessment = {
        "supported": True,
        "severity": "severe",
        "urgency": "immediate",
        "certainty": "possible",
        "onset": "2026-10-09",
        "expires": "2026-10-10",
        "reasoning": "Two days above 50 mm with a 120 mm peak; neighbours are dry.",
        "evidence": ["precipitation_mm 120 on 2026-10-09"],
    }
    return model_turn(tool_call("submit_assessment", **{**assessment, **overrides}))


async def run(client: AsyncClient) -> dict[str, Any]:
    response = await client.post("/api/runs", headers=ADMIN)
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


async def analysed_run(
    client: AsyncClient, upstream: Upstream, model: Model, *turns: Any
) -> dict[str, Any]:
    """Run a cycle with severe rain in Lahore and the model playing the turns."""
    upstream.payload_for = wet_in_lahore
    model.loaded = True
    model.turns = list(turns)
    return await run(client)


async def events_named(
    client: AsyncClient, run_id: int, event_type: str
) -> list[dict[str, Any]]:
    return [
        event["payload"]
        for event in await events_of(client, run_id)
        if event["type"] == event_type
    ]


async def lahore_alerts(client: AsyncClient, **query: str) -> list[dict[str, Any]]:
    response = await client.get(
        "/api/alerts", params={"district_id": "lahore", **query}
    )
    alerts: list[dict[str, Any]] = response.json()
    return alerts


class TestRouting:
    """Test cases for when a cycle visits the analyst"""

    async def test_a_run_with_no_signals_skips_the_analyst(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        model.loaded = True
        model.turns = [submit()]

        finished = await run(client)

        steps = await events_named(client, finished["id"], "step_started")
        assert {"step": "analyse_signals"} not in steps
        assert {"step": "apply_alert_lifecycle"} in steps
        assert model.requests == []
        assert upstream.calls > 0

    async def test_flagged_signals_are_analysed_before_alerts_are_applied(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(client, upstream, model, submit())

        steps = await events_named(client, finished["id"], "step_started")
        assert [step["step"] for step in steps][-2:] == [
            "analyse_signals",
            "apply_alert_lifecycle",
        ]
        assert len(model.requests) == 1

    async def test_an_unavailable_model_leaves_alerts_to_the_rules(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        upstream.payload_for = wet_in_lahore

        finished = await run(client)

        skipped = await events_named(client, finished["id"], "analysis_skipped")
        assert skipped == [{"reason": "model unavailable", "signals": 1}]
        assert model.requests == []
        (alert,) = await lahore_alerts(client)
        assert alert["severity"] == "severe"

    async def test_only_the_most_severe_signals_within_the_limit_are_analysed(
        self, app: FastAPI, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        app.state.settings.analyst_max_signals = 1
        assert upstream.air_quality is not None
        upstream.air_quality.payload_for = polluted_lahore

        def moderate_rain(lat: str, lon: str) -> dict[str, Any]:
            payload = copy.deepcopy(RECORDED_FORECAST)
            if wet_in_lahore(lat, lon) != RECORDED_FORECAST:
                payload["daily"]["precipitation_sum"] = [0.0, 60.0, 0.0]
            return payload

        upstream.payload_for = moderate_rain
        model.loaded = True
        model.turns = [submit(onset="2026-10-08", expires="2026-10-10")]

        finished = await run(client)

        started = await events_named(client, finished["id"], "analysis_started")
        skipped = await events_named(client, finished["id"], "analysis_skipped")
        assert started == [
            {"district_id": "lahore", "hazard": "poor_air_quality", "level": "severe"}
        ]
        assert skipped == [{"reason": "over the per-run limit", "signals": 1}]


class TestAssessment:
    """Test cases for alerts following the analyst's assessment"""

    async def test_a_confirmed_signal_becomes_an_alert_with_the_analysts_judgement(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(client, upstream, model, submit())

        (alert,) = await lahore_alerts(client)
        assert alert["severity"] == "severe"
        # Lead time alone would have said "expected" and "likely"
        assert alert["urgency"] == "immediate"
        assert alert["certainty"] == "possible"
        (assessment,) = await events_named(client, finished["id"], "assessment")
        assert assessment["decision"] == "confirm"
        assert assessment["district_id"] == "lahore"
        assert assessment["hazard"] == "heavy_rain"
        assert assessment["reasoning"].startswith("Two days above 50 mm")
        assert assessment["provider"] == "lm_studio"
        assert assessment["model"] == "qwen-test"
        assert assessment["prompt_version"] == "analyst-v1"

    async def test_an_upgrade_raises_the_alerts_severity(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(
            client, upstream, model, submit(severity="extreme")
        )

        (alert,) = await lahore_alerts(client)
        (assessment,) = await events_named(client, finished["id"], "assessment")
        assert alert["severity"] == "extreme"
        assert assessment["decision"] == "upgrade"

    async def test_a_downgrade_lowers_it_and_narrows_the_window(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(
            client,
            upstream,
            model,
            submit(severity="moderate", onset="2026-10-09", expires="2026-10-09"),
        )

        (alert,) = await lahore_alerts(client)
        (assessment,) = await events_named(client, finished["id"], "assessment")
        assert alert["severity"] == "moderate"
        assert (alert["onset"], alert["expires"]) == ("2026-10-09", "2026-10-09")
        assert assessment["decision"] == "downgrade"

    async def test_a_dismissed_signal_raises_no_alert_but_stays_a_signal(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(client, upstream, model, submit(supported=False))

        signals = (await client.get("/api/signals")).json()["signals"]
        (assessment,) = await events_named(client, finished["id"], "assessment")
        assert await lahore_alerts(client) == []
        assert [signal["hazard"] for signal in signals] == ["heavy_rain"]
        assert assessment["decision"] == "dismiss"

    async def test_dismissing_a_signal_ends_the_alert_it_had(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        upstream.payload_for = wet_in_lahore
        await run(client)

        await analysed_run(client, upstream, model, submit(supported=False))

        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "cancelled"


class TestToolLoop:
    """Test cases for the analyst's tool calls"""

    async def test_tool_calls_and_results_are_recorded_and_fed_back(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(
            client,
            upstream,
            model,
            model_turn(
                tool_call("get_forecast", days=2), tool_call("get_district_profile")
            ),
            submit(),
        )

        called = await events_named(client, finished["id"], "tool_called")
        results = await events_named(client, finished["id"], "tool_result")
        assert [(call["tool"], call["arguments"]) for call in called] == [
            ("get_forecast", {"days": 2}),
            ("get_district_profile", {}),
        ]
        assert [result["ok"] for result in results] == [True, True]
        forecast = json.loads(results[0]["result"])
        assert [day["precipitation_mm"] for day in forecast[0]["days"]] == [0.0, 120.0]
        assert json.loads(results[1]["result"])["province"] == "Punjab"

        fed_back = [m for m in model.requests[1]["messages"] if m["role"] == "tool"]
        assert [json.loads(message["content"]) for message in fed_back] == [
            forecast,
            json.loads(results[1]["result"]),
        ]

    async def test_the_model_is_offered_the_tools_and_the_signal(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await analysed_run(client, upstream, model, submit())

        request = model.requests[0]
        assert [tool["function"]["name"] for tool in request["tools"]] == [
            "get_forecast",
            "get_neighbouring_signals",
            "get_alert_history",
            "get_district_profile",
            "submit_assessment",
        ]
        brief = json.loads(request["messages"][1]["content"])
        assert brief["district"] == "Lahore"
        assert brief["signal"]["hazard"] == "heavy_rain"
        assert brief["forecast_window"] == {
            "first_day": "2026-10-08",
            "last_day": "2026-10-10",
        }

    async def test_neighbours_and_history_come_from_this_system(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        upstream.payload_for = wet_in_lahore
        await run(client)

        finished = await analysed_run(
            client,
            upstream,
            model,
            model_turn(
                tool_call("get_neighbouring_signals", limit=3),
                tool_call("get_alert_history"),
            ),
            submit(),
        )

        neighbours, history = (
            json.loads(result["result"])
            for result in await events_named(client, finished["id"], "tool_result")
        )
        distances = [neighbour["distance_km"] for neighbour in neighbours]
        assert len(neighbours) == 3
        assert distances == sorted(distances)
        assert distances[-1] < 100
        assert all(neighbour["signals"] == [] for neighbour in neighbours)
        assert [(alert["hazard"], alert["status"]) for alert in history] == [
            ("heavy_rain", "active")
        ]

    async def test_a_failed_tool_call_is_reported_to_the_model_and_survived(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(
            client,
            upstream,
            model,
            model_turn(
                tool_call("get_river_level"), tool_call("get_forecast", days=99)
            ),
            submit(),
        )

        results = await events_named(client, finished["id"], "tool_result")
        assert [result["ok"] for result in results] == [False, False]
        assert results[0]["result"] == "Unknown tool: get_river_level"
        assert results[1]["result"].startswith("Invalid arguments")
        (assessment,) = await events_named(client, finished["id"], "assessment")
        assert assessment["decision"] == "confirm"

    async def test_an_invalid_assessment_is_sent_back_for_correction(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await analysed_run(
            client,
            upstream,
            model,
            submit(onset="2026-11-01", expires="2026-11-02"),
            submit(severity="catastrophic"),
            submit(),
        )

        complaints = [
            request["messages"][-1]["content"] for request in model.requests[1:]
        ]
        assert "within 2026-10-08 to 2026-10-10" in complaints[0]
        assert "severity" in complaints[1]
        (assessment,) = await events_named(client, finished["id"], "assessment")
        assert assessment["model_turns"] == 3

    async def test_a_model_that_answers_in_prose_is_asked_to_use_a_tool(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await analysed_run(
            client, upstream, model, model_turn(content="It looks wet."), submit()
        )

        nudge = model.requests[1]["messages"][-1]
        assert nudge["role"] == "user"
        assert "submit_assessment" in nudge["content"]
        (alert,) = await lahore_alerts(client)
        assert alert["urgency"] == "immediate"


class TestLimits:
    """Test cases for the bounds on one analysis; the rule-based alert stands"""

    async def test_the_loop_stops_at_the_step_limit(
        self, app: FastAPI, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        app.state.settings.analyst_max_steps = 3

        finished = await analysed_run(
            client, upstream, model, model_turn(tool_call("get_district_profile"))
        )

        failed = await events_named(client, finished["id"], "analysis_failed")
        assert failed == [
            {"district_id": "lahore", "hazard": "heavy_rain", "reason": "step_limit"}
        ]
        assert len(model.requests) == 3
        assert finished["status"] == "succeeded"
        (alert,) = await lahore_alerts(client)
        assert (alert["severity"], alert["urgency"]) == ("severe", "expected")

    async def test_the_loop_stops_at_the_time_budget(
        self, app: FastAPI, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        app.state.settings.analyst_time_budget_seconds = 0.05
        model.delay = 0.5

        finished = await analysed_run(client, upstream, model, submit())

        (failed,) = await events_named(client, finished["id"], "analysis_failed")
        assert failed["reason"] == "time_budget"
        (alert,) = await lahore_alerts(client)
        assert alert["urgency"] == "expected"

    async def test_a_model_error_does_not_fail_the_run(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        overloaded = httpx.Response(
            503, json={"error": {"message": "overloaded at http://gpu-box:1234"}}
        )

        finished = await analysed_run(client, upstream, model, overloaded)

        (failed,) = await events_named(client, finished["id"], "analysis_failed")
        # Only the category: the provider's message can name internal hosts
        assert failed == {
            "district_id": "lahore",
            "hazard": "heavy_rain",
            "reason": "model_error",
        }
        assert finished["status"] == "succeeded"
        assert len(await lahore_alerts(client)) == 1


class TestCheckpoints:
    """Test cases for the graph saving its progress"""

    async def test_each_run_checkpoints_its_progress_under_its_own_thread(
        self,
        app: FastAPI,
        db_session: AsyncSession,
        open_session: SessionFactory,
        upstream: Upstream,
        model: Model,
    ) -> None:
        upstream.payload_for = wet_in_lahore
        model.loaded = True
        model.turns = [submit()]
        saver = InMemorySaver()

        finished = await run_cycle(
            db_session,
            app.dependency_overrides[get_forecast_client](),
            app.dependency_overrides[get_air_quality_client](),
            app.state.settings,
            trigger="manual",
            events=RunEventLog(open_session),
            gateway=llm_gateway_answering(model.handle),
            checkpointer=saver,
        )

        thread: RunnableConfig = {"configurable": {"thread_id": str(finished.id)}}
        latest = await saver.aget_tuple(thread)
        assert latest is not None
        assert latest.checkpoint["channel_values"] == {
            "district_count": 155,
            "signal_count": 1,
            "analysed": 1,
            "alert_actions": {"issue": 1},
        }
        # One before anything ran, one for the input, and one after each node
        assert len([checkpoint async for checkpoint in saver.alist(thread)]) == 6
