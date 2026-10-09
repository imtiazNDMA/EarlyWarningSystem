"""Tests for model-written alert text inside a cycle: drafted, verified or held."""

import json
from typing import Any

import httpx
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import Model, Upstream, draft_turn
from tests.test_analyst import (
    analysed_run,
    events_named,
    lahore_alerts,
    run,
    submit,
)
from tests.test_cycles import wet_in_lahore

INVENTED = draft_turn(body="Up to 300 mm of rain may fall on 9 October.")


async def drafted_run(
    client: AsyncClient, upstream: Upstream, model: Model, *drafts: Any
) -> dict[str, Any]:
    """Run a cycle whose Lahore rain signal is confirmed, then drafted as scripted."""
    model.drafts = list(drafts)
    return await analysed_run(client, upstream, model, submit())


class TestDrafting:
    """Test cases for alerts worded by the model"""

    async def test_a_verified_draft_is_published_as_the_alert(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await drafted_run(client, upstream, model, draft_turn())

        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "active"
        assert alert["generated_by"] == "model"
        assert alert["headline_en"] == "Severe heavy rain alert for Lahore"
        assert (
            alert["body_en"] == "Rainfall is forecast to peak at 120 mm on 9 October."
        )
        assert alert["held_reasons"] is None
        checked = await events_named(client, finished["id"], "draft_checked")
        assert checked == [
            {
                "district_id": "lahore",
                "hazard": "heavy_rain",
                "attempt": 1,
                "passed": True,
                "problems": [],
            }
        ]

    async def test_the_drafter_sees_only_the_assessment_and_its_evidence(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await drafted_run(client, upstream, model, draft_turn())

        request = model.draft_requests[0]
        assert "tools" not in request
        assert json.loads(request["messages"][1]["content"]) == {
            "district": "Lahore",
            "province": "Punjab",
            "hazard": "heavy rain",
            "severity": "severe",
            "urgency": "immediate",
            "certainty": "possible",
            "onset": "2026-10-09",
            "expires": "2026-10-10",
            "measured": "rainfall",
            "unit": "mm",
            "evidence": [
                {"date": "2026-10-09", "value": 120.0, "threshold": 100.0},
                {"date": "2026-10-10", "value": 60.0, "threshold": 100.0},
            ],
        }

    async def test_a_failed_check_is_sent_back_and_the_revision_published(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await drafted_run(client, upstream, model, INVENTED, draft_turn())

        feedback = model.draft_requests[1]["messages"][-1]["content"]
        assert "The number 300 is not in the evidence." in feedback
        checked = await events_named(client, finished["id"], "draft_checked")
        assert [(check["attempt"], check["passed"]) for check in checked] == [
            (1, False),
            (2, True),
        ]
        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "active"
        assert "300" not in alert["body_en"]

    async def test_a_dismissed_signal_is_not_drafted(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        model.drafts = [draft_turn()]

        finished = await analysed_run(client, upstream, model, submit(supported=False))

        steps = await events_named(client, finished["id"], "step_started")
        assert {"step": "draft_alerts"} not in steps
        assert model.draft_requests == []

    async def test_an_alert_that_is_kept_is_not_drafted_again(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await drafted_run(client, upstream, model, draft_turn())

        await drafted_run(client, upstream, model, draft_turn())

        assert len(model.draft_requests) == 1
        assert len(await lahore_alerts(client)) == 1

    async def test_signals_the_analyst_did_not_assess_keep_rule_wording(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        upstream.payload_for = wet_in_lahore
        model.drafts = [draft_turn()]

        await run(client)

        (alert,) = await lahore_alerts(client)
        assert alert["generated_by"] == "rules"
        assert model.draft_requests == []


class TestHeldAlerts:
    """Test cases for drafts that never pass verification"""

    async def test_an_alert_is_held_after_two_failed_revisions(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await drafted_run(client, upstream, model, INVENTED)

        assert len(model.draft_requests) == 3
        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "held"
        assert alert["held_reasons"] == ["The number 300 is not in the evidence."]
        assert alert["generated_by"] == "model"
        (held,) = await events_named(client, finished["id"], "alert_held")
        assert held["reasons"] == ["The number 300 is not in the evidence."]
        lifecycle = [
            step
            for step in await events_named(client, finished["id"], "step_finished")
            if step["step"] == "apply_alert_lifecycle"
        ]
        assert lifecycle[0]["actions"] == {"hold": 1}

    async def test_a_held_alert_is_never_listed_as_active(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await drafted_run(client, upstream, model, INVENTED)

        assert await lahore_alerts(client, status="active") == []
        assert len(await lahore_alerts(client, status="held")) == 1

    async def test_the_revision_limit_is_configurable(
        self, app: FastAPI, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        app.state.settings.drafter_max_revisions = 0

        await drafted_run(client, upstream, model, INVENTED)

        assert len(model.draft_requests) == 1
        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "held"

    async def test_a_held_replacement_leaves_the_current_alert_active(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await drafted_run(client, upstream, model, draft_turn())
        model.drafts = [INVENTED]

        await analysed_run(client, upstream, model, submit(severity="extreme"))

        held, current = await lahore_alerts(client)
        assert (current["status"], current["severity"]) == ("active", "severe")
        assert (held["status"], held["severity"]) == ("held", "extreme")
        assert held["supersedes_id"] is None
        detail = (await client.get(f"/api/alerts/{current['id']}")).json()
        assert detail["superseded_by_id"] is None


class TestDrafterFailures:
    """Test cases for a model that cannot draft; rule-based wording is used"""

    async def test_a_model_error_falls_back_to_rule_wording(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await drafted_run(
            client, upstream, model, httpx.Response(500, json={"error": {}})
        )

        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "active"
        assert alert["generated_by"] == "rules"
        failed = await events_named(client, finished["id"], "draft_failed")
        assert failed == [
            {"district_id": "lahore", "hazard": "heavy_rain", "reason": "model_error"}
        ]

    async def test_replies_that_are_never_a_draft_fall_back_to_rule_wording(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await drafted_run(
            client, upstream, model, draft_turn(headline="", body="", instructions="")
        )

        (alert,) = await lahore_alerts(client)
        assert alert["generated_by"] == "rules"
        (failed,) = await events_named(client, finished["id"], "draft_failed")
        assert failed["reason"] == "no_usable_draft"
        checked = await events_named(client, finished["id"], "draft_checked")
        assert [check["passed"] for check in checked] == [False, False, False]
