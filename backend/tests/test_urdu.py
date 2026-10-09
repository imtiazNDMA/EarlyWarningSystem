"""Tests for alerts published in Urdu as well: written, verified or left out."""

import json
from typing import Any

import httpx
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import Model, Upstream, draft_turn, urdu_turn
from tests.test_analyst import (
    analysed_run,
    events_named,
    lahore_alerts,
    run,
    submit,
)
from tests.test_cycles import wet_in_lahore

SUBJECT = {"district_id": "lahore", "hazard": "heavy_rain"}
# Urdu that never says which hazard the alert is about
NO_HAZARD = urdu_turn(
    headline="لاہور کے لیے شدید انتباہ",
    body="9 اکتوبر کو 120 ملی میٹر تک کی پیش گوئی ہے۔",
)
# The Urdu of the rule-based body for severe rain in Lahore
RULE_BODY_UR = (
    "9 اکتوبر کو بارش 120 ملی میٹر تک پہنچنے کی پیش گوئی ہے، جو 100 ملی میٹر کی "
    "شدید حد کے برابر یا اس سے زیادہ ہے۔ کم ترین حد 2 دن، 9 اکتوبر سے 10 اکتوبر تک، "
    "پوری ہوتی ہے۔"
)


async def bilingual_run(
    client: AsyncClient, upstream: Upstream, model: Model, *urdu: Any
) -> dict[str, Any]:
    """Run a cycle whose Lahore rain alert is drafted, then put into Urdu."""
    model.drafts = [draft_turn()]
    model.urdu = list(urdu)
    return await analysed_run(client, upstream, model, submit())


class TestUrduAlerts:
    """Test cases for alerts that carry verified Urdu"""

    async def test_verified_urdu_is_published_with_the_alert(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await bilingual_run(client, upstream, model, urdu_turn())

        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "active"
        assert alert["headline_en"] == "Severe heavy rain alert for Lahore"
        assert alert["headline_ur"] == "لاہور کے لیے شدید بارش کا انتباہ"
        assert (
            alert["body_ur"]
            == "9 اکتوبر کو بارش 120 ملی میٹر تک پہنچنے کی پیش گوئی ہے۔"
        )
        assert alert["instructions_ur"] == "نشیبی علاقوں اور ندی نالوں سے دور رہیں۔"
        checked = await events_named(client, finished["id"], "urdu_checked")
        assert checked == [{**SUBJECT, "attempt": 1, "passed": True, "problems": []}]

    async def test_the_writer_sees_only_the_english_and_its_glossary_terms(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await bilingual_run(client, upstream, model, urdu_turn())

        (request,) = model.urdu_requests
        assert "tools" not in request
        assert json.loads(request["messages"][1]["content"]) == {
            "headline": "Severe heavy rain alert for Lahore",
            "body": "Rainfall is forecast to peak at 120 mm on 9 October.",
            "instructions": "Avoid low-lying areas and stream crossings.",
            "hazard_term": "بارش",
            "severity_term": "شدید",
        }

    async def test_a_rule_worded_alert_is_put_into_urdu_too(
        self, app: FastAPI, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        app.state.settings.analyst_max_signals = 0
        upstream.payload_for = wet_in_lahore
        model.loaded = True
        model.urdu = [urdu_turn(body=RULE_BODY_UR)]

        await run(client)

        (alert,) = await lahore_alerts(client)
        assert alert["generated_by"] == "rules"
        assert alert["body_ur"] == RULE_BODY_UR
        assert model.requests == []

    async def test_an_alert_that_is_kept_is_not_written_again(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        await bilingual_run(client, upstream, model, urdu_turn())

        finished = await bilingual_run(client, upstream, model, urdu_turn())

        assert len(model.urdu_requests) == 1
        steps = await events_named(client, finished["id"], "step_started")
        assert {"step": "write_urdu"} not in steps

    async def test_urdu_is_served_as_urdu_and_not_as_escapes(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await bilingual_run(client, upstream, model, NO_HAZARD, urdu_turn())

        alerts = await client.get("/api/alerts", params={"district_id": "lahore"})
        events = await client.get(f"/api/runs/{finished['id']}/events")
        assert "شدید بارش کا انتباہ" in alerts.content.decode()
        assert 'use the glossary term \\"بارش\\"' in events.content.decode()


class TestRevisions:
    """Test cases for Urdu that fails its checks"""

    async def test_a_failed_check_is_sent_back_and_the_revision_published(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await bilingual_run(client, upstream, model, NO_HAZARD, urdu_turn())

        feedback = model.urdu_requests[1]["messages"][-1]["content"]
        assert 'The Urdu does not name the hazard; use the glossary term "بارش".' in (
            feedback
        )
        checked = await events_named(client, finished["id"], "urdu_checked")
        assert [(check["attempt"], check["passed"]) for check in checked] == [
            (1, False),
            (2, True),
        ]
        (alert,) = await lahore_alerts(client)
        assert alert["headline_ur"] == "لاہور کے لیے شدید بارش کا انتباہ"

    async def test_urdu_that_never_passes_leaves_the_alert_in_english(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await bilingual_run(client, upstream, model, NO_HAZARD)

        assert len(model.urdu_requests) == 3
        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "active"
        assert alert["headline_en"] == "Severe heavy rain alert for Lahore"
        assert alert["headline_ur"] is None
        assert alert["body_ur"] is None
        assert alert["instructions_ur"] is None
        assert alert["held_reasons"] is None
        failed = await events_named(client, finished["id"], "urdu_failed")
        assert failed == [
            {
                **SUBJECT,
                "reason": "checks_failed",
                "problems": [
                    'The Urdu does not name the hazard; use the glossary term "بارش".'
                ],
            }
        ]
        (step,) = [
            step
            for step in await events_named(client, finished["id"], "step_finished")
            if step["step"] == "write_urdu"
        ]
        assert step == {"step": "write_urdu", "written": 0, "english_only": 1}

    async def test_a_model_error_leaves_the_alert_in_english(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await bilingual_run(
            client, upstream, model, httpx.Response(500, json={"error": {}})
        )

        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "active"
        assert alert["headline_ur"] is None
        failed = await events_named(client, finished["id"], "urdu_failed")
        assert failed == [{**SUBJECT, "reason": "model_error"}]

    async def test_replies_that_are_never_an_alert_leave_it_in_english(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        finished = await bilingual_run(
            client, upstream, model, urdu_turn(headline="", body="", instructions="")
        )

        (alert,) = await lahore_alerts(client)
        assert alert["headline_ur"] is None
        (failed,) = await events_named(client, finished["id"], "urdu_failed")
        assert failed["reason"] == "checks_failed"


class TestWhenUrduIsNotWritten:
    """Test cases for alerts the Urdu writer is never asked about"""

    async def test_a_held_alert_is_not_put_into_urdu(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        model.drafts = [draft_turn(body="Up to 300 mm of rain may fall on 9 October.")]
        model.urdu = [urdu_turn()]

        await analysed_run(client, upstream, model, submit())

        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "held"
        assert alert["headline_ur"] is None
        assert model.urdu_requests == []

    async def test_an_unavailable_model_is_asked_nothing(
        self, client: AsyncClient, upstream: Upstream, model: Model
    ) -> None:
        upstream.payload_for = wet_in_lahore
        model.urdu = [urdu_turn()]

        finished = await run(client)

        skipped = await events_named(client, finished["id"], "urdu_skipped")
        assert skipped == [{"reason": "model unavailable", "alerts": 1}]
        assert model.urdu_requests == []
        (alert,) = await lahore_alerts(client)
        assert alert["status"] == "active"
        assert alert["headline_ur"] is None
