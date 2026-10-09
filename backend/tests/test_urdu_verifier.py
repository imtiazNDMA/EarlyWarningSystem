"""Tests for the Urdu verifier: glossary use and agreement with the English."""

import datetime as dt
from typing import Any

from ews.alerts.text import AlertText
from ews.drafting.verifier import AlertDraft, Facts, verify_urdu

FACTS = Facts(
    hazard="heavy_rain",
    severity="severe",
    onset=dt.date(2026, 10, 9),
    expires=dt.date(2026, 10, 10),
    evidence=[
        {"snapshot_id": 7, "date": "2026-10-09", "value": 120.3, "threshold": 100.0},
        {"snapshot_id": 7, "date": "2026-10-10", "value": 60.0, "threshold": 100.0},
    ],
)
ENGLISH = AlertText(
    headline="Severe heavy rain alert for Lahore",
    body="Rainfall is forecast to peak at 120 mm on 9 October, above the "
    "threshold of 100 mm, and to continue on 10 October.",
    instructions="Avoid low-lying areas and stream crossings.",
)


def urdu(**overrides: Any) -> AlertDraft:
    text = {
        "headline": "لاہور کے لیے شدید بارش کا انتباہ",
        "body": "9 اکتوبر کو بارش 120 ملی میٹر تک پہنچنے کی پیش گوئی ہے، جو "
        "100 ملی میٹر کی حد سے زیادہ ہے، اور 10 اکتوبر کو بھی جاری رہے گی۔",
        "instructions": "نشیبی علاقوں اور ندی نالوں سے دور رہیں۔",
    }
    return AlertDraft(**{**text, **overrides})


class TestEquivalence:
    """Test cases for the Urdu making the same claims as the English"""

    def test_urdu_that_says_what_the_english_says_passes(self) -> None:
        assert verify_urdu(urdu(), ENGLISH, FACTS) == []

    def test_a_number_the_english_does_not_give_is_rejected(self) -> None:
        body = "9 اکتوبر کو بارش 300 ملی میٹر، حد 100 ملی میٹر، 10 اکتوبر تک۔"

        problems = verify_urdu(urdu(body=body), ENGLISH, FACTS)

        assert problems == [
            "The Urdu gives the number 300, which the English does not.",
            "The Urdu leaves out the number 120 given in the English.",
        ]

    def test_a_date_the_english_does_not_give_is_rejected(self) -> None:
        body = "12 اکتوبر کو بارش 120 ملی میٹر، حد 100 ملی میٹر، 10 اکتوبر تک۔"

        problems = verify_urdu(urdu(body=body), ENGLISH, FACTS)

        assert problems == [
            'The Urdu gives the date "12 October", which the English does not.',
            'The Urdu leaves out the date "9 October" given in the English.',
        ]

    def test_urdu_digits_are_read_as_the_same_numbers(self) -> None:
        body = "۹ اکتوبر کو بارش ۱۲۰ ملی میٹر، حد ۱۰۰ ملی میٹر، ۱۰ اکتوبر تک۔"

        assert verify_urdu(urdu(body=body), ENGLISH, FACTS) == []


class TestGlossary:
    """Test cases for the Urdu keeping to the glossary"""

    def test_the_hazard_must_be_named_by_its_glossary_term(self) -> None:
        text = urdu(
            headline="لاہور کے لیے شدید انتباہ",
            body="9 اکتوبر کو 120 ملی میٹر، حد 100 ملی میٹر، 10 اکتوبر تک۔",
        )

        problems = verify_urdu(text, ENGLISH, FACTS)

        assert problems == [
            'The Urdu does not name the hazard; use the glossary term "بارش".'
        ]

    def test_a_transliterated_weather_word_is_rejected(self) -> None:
        text = urdu(headline="لاہور کے لیے شدید بارش اور تھنڈر اسٹورم کا انتباہ")

        problems = verify_urdu(text, ENGLISH, FACTS)

        assert problems == [
            'The Urdu transliterates an English weather word, "تھنڈر اسٹورم"; '
            'use "گرج چمک".'
        ]

    def test_latin_words_are_rejected_but_units_are_not(self) -> None:
        body = "9 اکتوبر کو Lahore میں بارش 120 mm، حد 100 mm، 10 اکتوبر تک۔"

        problems = verify_urdu(urdu(body=body), ENGLISH, FACTS)

        assert problems == [
            'The Urdu has the word "Lahore" in Latin letters; write it in Urdu script.'
        ]

    def test_another_hazard_is_rejected(self) -> None:
        text = urdu(instructions="برفباری کے دوران نشیبی علاقوں سے دور رہیں۔")

        problems = verify_urdu(text, ENGLISH, FACTS)

        assert problems == [
            'The Urdu says "برفباری", which names a hazard that was not assessed.'
        ]

    def test_another_severity_is_rejected(self) -> None:
        text = urdu(headline="لاہور کے لیے انتہائی شدید بارش کا انتباہ")

        problems = verify_urdu(text, ENGLISH, FACTS)

        assert problems == [
            'The Urdu says "انتہائی شدید", but the assessed severity is severe; '
            'use "شدید".'
        ]

    def test_the_severity_the_english_states_must_be_stated(self) -> None:
        text = urdu(headline="لاہور کے لیے بارش کا انتباہ")

        problems = verify_urdu(text, ENGLISH, FACTS)

        assert problems == ['The Urdu does not state the severity; use "شدید".']

    def test_severity_is_not_required_when_the_english_omits_it(self) -> None:
        english = AlertText("Heavy rain alert for Lahore", ENGLISH.body, "Stay safe.")
        text = urdu(headline="لاہور کے لیے بارش کا انتباہ")

        assert verify_urdu(text, english, FACTS) == []
