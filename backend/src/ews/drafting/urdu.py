"""Put an alert's wording into Urdu, and keep the Urdu only if it verifies."""

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from ews.alerts.text import AlertText
from ews.cycles.events import RunRecorder
from ews.drafting.glossary import (
    HAZARD_TERMS_UR,
    SEVERITY_TERMS_UR,
    WEATHER_TERMS_UR,
)
from ews.drafting.verifier import AlertDraft, Facts, verify_urdu
from ews.llm.gateway import LLMError, LLMGateway, LLMOutputError, Message

logger = logging.getLogger(__name__)

PROMPT_VERSION = "urdu-v1"

_GLOSSARY = "\n".join(
    f"- {english}: {urdu}"
    for english, urdu in (*WEATHER_TERMS_UR.items(), *SEVERITY_TERMS_UR.items())
)

SYSTEM_PROMPT = f"""\
You translate public hazard alerts for districts in Pakistan from English into Urdu.
You are given an English alert as JSON, with the Urdu terms for its hazard and its \
severity. Write its headline, body and instructions in Urdu.

Rules:
- Write formal advisory Urdu in declarative sentences: not conversational, no slang.
- Say exactly what the English says. Add nothing and leave nothing out.
- Keep every number and date as the English gives it, in the same digits; write \
dates as day and month, such as 9 اکتوبر.
- Write in Urdu script, place names included. Latin letters are allowed only in \
units such as mm, °C and km/h.
- Use the given terms for the hazard and the severity, and no other severity word.
- Use the glossary's terms. Never spell an English weather word in Urdu letters, \
such as اوورکاسٹ or تھنڈر اسٹورم.

Glossary:
{_GLOSSARY}"""

STRUCTURE_PROBLEM = "The Urdu did not have a headline, a body and instructions."


def _brief(english: AlertText, facts: Facts) -> str:
    """The English wording and the terms its Urdu must use, and nothing else."""
    hazard_terms = HAZARD_TERMS_UR.get(facts.hazard)
    return json.dumps(
        {
            "headline": english.headline,
            "body": english.body,
            "instructions": english.instructions,
            "hazard_term": hazard_terms[0] if hazard_terms else None,
            "severity_term": SEVERITY_TERMS_UR[facts.severity],
        },
        ensure_ascii=False,
    )


async def write_urdu(
    gateway: LLMGateway,
    recorder: RunRecorder,
    subject: Mapping[str, Any],
    english: AlertText,
    facts: Facts,
    *,
    max_revisions: int,
) -> AlertText | None:
    """Write an alert's Urdu and verify it, revising on failed checks.

    Args:
        gateway: Model access
        recorder: The run's event log, which receives every verdict
        subject: District and hazard, to tag the events with
        english: The wording the alert will be published with
        facts: The assessment the English was written from
        max_revisions: Revisions allowed after the first attempt

    Returns:
        Verified Urdu; or None when the model failed or no attempt passed, so
        the alert is published in English alone.
    """
    messages: list[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _brief(english, facts)},
    ]
    urdu: AlertDraft | None = None
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
            logger.exception("Urdu writing failed for %s", dict(subject))
            await recorder.emit("urdu_failed", **subject, reason="model_error")
            return None
        else:
            urdu = completion.output
            problems = verify_urdu(urdu, english, facts)
            messages.append({"role": "assistant", "content": urdu.model_dump_json()})

        await recorder.emit(
            "urdu_checked",
            **subject,
            attempt=attempt,
            passed=not problems,
            problems=list(problems),
        )
        if urdu is not None and not problems:
            return AlertText(urdu.headline, urdu.body, urdu.instructions)
        messages.append(
            {
                "role": "user",
                "content": "The Urdu failed these checks:\n"
                + "\n".join(f"- {problem}" for problem in problems)
                + "\nRewrite it so that every check passes.",
            }
        )

    await recorder.emit(
        "urdu_failed", **subject, reason="checks_failed", problems=list(problems)
    )
    return None
