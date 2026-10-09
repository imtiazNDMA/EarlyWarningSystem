"""Write an alert's wording with the model, and publish it only if it verifies."""

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from ews.alerts.lifecycle import Certainty, Urgency
from ews.alerts.service import Authored
from ews.alerts.text import HAZARD_NAMES, METRIC_NAMES, AlertText
from ews.cycles.events import RunRecorder
from ews.drafting.verifier import AlertDraft, Facts, verify
from ews.llm.gateway import LLMError, LLMGateway, LLMOutputError, Message

logger = logging.getLogger(__name__)

PROMPT_VERSION = "drafter-v1"

SYSTEM_PROMPT = """\
You write public hazard alerts for districts in Pakistan, in plain English.
You are given an assessment and the forecast evidence behind it, as JSON. Write a \
headline, a body and safety instructions.

Rules:
- Use only the facts given. Every number and date you write must appear in the \
evidence; write dates as day and month, such as 9 October.
- Name only the assessed hazard and only the assessed severity.
- Headline: the severity, the hazard and the district, under 100 characters.
- Body: two or three sentences on what is expected and when.
- Instructions: one or two sentences of practical safety advice, with no numbers."""

STRUCTURE_PROBLEM = "The draft did not have a headline, a body and instructions."


def _brief(
    district_name: str,
    province: str,
    facts: Facts,
    urgency: Urgency,
    certainty: Certainty,
) -> str:
    """The assessment and its evidence, and nothing else, for the drafter."""
    first = facts.evidence[0] if facts.evidence else {}
    metric = str(first.get("metric", ""))
    return json.dumps(
        {
            "district": district_name,
            "province": province,
            "hazard": HAZARD_NAMES.get(facts.hazard, facts.hazard.replace("_", " ")),
            "severity": facts.severity,
            "urgency": urgency,
            "certainty": certainty,
            "onset": facts.onset,
            "expires": facts.expires,
            "measured": METRIC_NAMES.get(metric, metric),
            "unit": first.get("unit"),
            "evidence": [
                {key: row[key] for key in ("date", "value", "threshold") if key in row}
                for row in facts.evidence
            ],
        },
        default=str,
        ensure_ascii=False,
    )


async def draft_alert(
    gateway: LLMGateway,
    recorder: RunRecorder,
    subject: Mapping[str, Any],
    district_name: str,
    province: str,
    facts: Facts,
    urgency: Urgency,
    certainty: Certainty,
    *,
    max_revisions: int,
) -> Authored | None:
    """Draft an alert's wording and verify it, revising on failed checks.

    Args:
        gateway: Model access
        recorder: The run's event log, which receives every verdict
        subject: District and hazard, to tag the events with
        district_name: The district's display name
        province: The district's province
        facts: The assessment and evidence the wording must keep to
        urgency: Urgency from the assessment
        certainty: Certainty from the assessment
        max_revisions: Revisions allowed after the first draft

    Returns:
        Verified wording; or the last draft marked held, with the reasons, when
        no draft passed; or None when the model produced no usable draft, so the
        caller can fall back to rule-based wording.
    """
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _brief(district_name, province, facts, urgency, certainty),
        },
    ]
    draft: AlertDraft | None = None
    problems: Sequence[str] = []

    for attempt in range(1, max_revisions + 2):
        try:
            completion = await gateway.complete(
                messages, AlertDraft, prompt_version=PROMPT_VERSION
            )
        except LLMOutputError:
            problems = [STRUCTURE_PROBLEM]
        except LLMError:
            # The message can name the provider's host; the log line keeps it
            logger.exception("Drafting failed for %s", dict(subject))
            await recorder.emit("draft_failed", **subject, reason="model_error")
            return None
        else:
            draft = completion.output
            problems = verify(draft, facts)
            messages.append({"role": "assistant", "content": draft.model_dump_json()})

        await recorder.emit(
            "draft_checked",
            **subject,
            attempt=attempt,
            passed=not problems,
            problems=list(problems),
        )
        if draft is not None and not problems:
            return Authored(_text(draft), "model")
        messages.append(
            {
                "role": "user",
                "content": "The draft failed these checks:\n"
                + "\n".join(f"- {problem}" for problem in problems)
                + "\nRewrite it so that every check passes.",
            }
        )

    if draft is None:
        await recorder.emit("draft_failed", **subject, reason="no_usable_draft")
        return None
    await recorder.emit("alert_held", **subject, reasons=list(problems))
    return Authored(_text(draft), "model", held_reasons=list(problems))


def _text(draft: AlertDraft) -> AlertText:
    return AlertText(draft.headline, draft.body, draft.instructions)
