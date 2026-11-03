"""Tests for JSON parsing, outline validation, and the Anthropic call wrapper."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

import anthropic

import llm
from helpers import CLOSING, outline_reply
from outline import parse_outline, plan_outline
from guard import GuardResult, Route
from parsing import parse_json_object
from prompts.planner import BEAT_NAMES


class ParseJsonObjectTests(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(parse_json_object('{"a": 1}'), {"a": 1})

    def test_code_fence_and_surrounding_prose(self):
        self.assertEqual(parse_json_object('Sure!\n```json\n{"a": 1}\n```\nDone.'), {"a": 1})

    def test_no_braces_raises(self):
        with self.assertRaises(ValueError):
            parse_json_object("no json here")

    def test_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            parse_json_object('{"a": }')

    def test_object_inside_a_list_is_extracted(self):
        # The parser takes the text between the first "{" and the last "}", so a wrapping list is accepted.
        self.assertEqual(parse_json_object('[{"a": 1}]'), {"a": 1})

    def test_bare_list_without_an_object_raises(self):
        with self.assertRaises(ValueError):
            parse_json_object("[1, 2, 3]")


class ParseOutlineTests(unittest.TestCase):
    def test_valid_outline_parses(self):
        outline = parse_outline(outline_reply("Lily"))
        self.assertEqual(outline.title, "Lily")
        self.assertEqual([beat.name for beat in outline.beats], list(BEAT_NAMES))
        self.assertEqual(outline.closing_line, CLOSING)

    def test_beats_out_of_order_rejected(self):
        data = outline_reply()
        bad = data.replace('"setup"', '"ending"', 1)
        with self.assertRaises(ValueError):
            parse_outline(bad)

    def test_word_target_out_of_range_rejected(self):
        bad = outline_reply().replace('"word_target": 70', '"word_target": 10', 1)
        with self.assertRaises(ValueError):
            parse_outline(bad)

    def test_boolean_word_target_rejected(self):
        bad = outline_reply().replace('"word_target": 70', '"word_target": true', 1)
        with self.assertRaises(ValueError):
            parse_outline(bad)

    def test_no_characters_rejected(self):
        bad = outline_reply().replace('"characters": ["Bunny"]', '"characters": []')
        with self.assertRaises(ValueError):
            parse_outline(bad)

    def test_empty_closing_line_rejected(self):
        bad = outline_reply().replace(CLOSING, "   ")
        with self.assertRaises(ValueError):
            parse_outline(bad)

    def test_plan_outline_sends_previous_outline_and_feedback_when_revising(self):
        guard = GuardResult(Route.STORY, "animal_friends", (), "")
        previous = parse_outline(outline_reply("Old"))
        with mock.patch("outline.call_model", return_value=outline_reply("New")) as call:
            plan_outline("a bunny story", guard, previous=previous, feedback="make it longer")
        prompt = call.call_args.args[0]
        self.assertIn("<previous_outline>", prompt)
        self.assertIn("<feedback>\nmake it longer", prompt)

    def test_plan_outline_first_draft_has_no_revision_tags(self):
        guard = GuardResult(Route.STORY, "animal_friends", (), "")
        with mock.patch("outline.call_model", return_value=outline_reply()) as call:
            plan_outline("a bunny story", guard)
        self.assertNotIn("<previous_outline>", call.call_args.args[0])


class CallModelTests(unittest.TestCase):
    def _client(self, stop_reason="end_turn", content=None, error=None):
        messages = mock.Mock()
        if error is not None:
            messages.create.side_effect = error
        else:
            if content is None:
                content = [SimpleNamespace(type="text", text="Hello there")]
            messages.create.return_value = SimpleNamespace(stop_reason=stop_reason, content=content)
        return SimpleNamespace(messages=messages)

    def test_text_blocks_are_joined_and_thinking_skipped(self):
        content = [
            SimpleNamespace(type="thinking", thinking="private notes"),
            SimpleNamespace(type="text", text="Hello "),
            SimpleNamespace(type="text", text="there"),
        ]
        with mock.patch("llm.get_client", return_value=self._client(content=content)):
            self.assertEqual(llm.call_model("hi"), "Hello there")

    def test_refusal_raises(self):
        with mock.patch("llm.get_client", return_value=self._client(stop_reason="refusal")):
            with self.assertRaises(RuntimeError):
                llm.call_model("hi")

    def test_cut_off_reply_raises(self):
        with mock.patch("llm.get_client", return_value=self._client(stop_reason="max_tokens")):
            with self.assertRaisesRegex(RuntimeError, "cut off"):
                llm.call_model("hi")

    def test_rejected_key_becomes_runtime_error(self):
        class FakeAuthError(anthropic.AuthenticationError):
            def __init__(self):
                Exception.__init__(self, "bad key")

        with mock.patch("llm.get_client", return_value=self._client(error=FakeAuthError())):
            with self.assertRaisesRegex(RuntimeError, "rejected"):
                llm.call_model("hi")

    def test_missing_key_gives_clear_message(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch("llm.load_dotenv"):
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY is not set"):
                llm.get_client()

    def test_system_prompt_is_omitted_when_not_given(self):
        client = self._client()
        with mock.patch("llm.get_client", return_value=client):
            llm.call_model("hi")
        self.assertIs(client.messages.create.call_args.kwargs["system"], llm.anthropic.NOT_GIVEN)

    def test_model_name_is_haiku_5_5(self):
        client = self._client()
        with mock.patch("llm.get_client", return_value=client):
            llm.call_model("hi", system="be kind")
        self.assertEqual(client.messages.create.call_args.kwargs["model"], "claude-haiku-5-5")
        self.assertEqual(client.messages.create.call_args.kwargs["system"], "be kind")


if __name__ == "__main__":
    unittest.main()
