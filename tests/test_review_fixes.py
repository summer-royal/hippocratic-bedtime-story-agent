"""Regression tests for the milestone 11 fixes. Every model call is stubbed."""

import contextlib
import io
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

import anthropic

import feedback
import guard
import llm
import refine
import revision
from devlog import developer_log
from feedback import FeedbackRoute, check_feedback
from guard import GuardResult, Route, check_request
from helpers import CLOSING, GOOD_STORY, judge_reply, make_outline, safety_reply
from judge import Judgement
from prompts.judge import CRITERIA, build_judge_prompt
from review import Review, review_safety, review_story
from revision import ImprovedStory


def guard_reply(**fields):
    return json.dumps(fields)


class TitleIsReviewedTests(unittest.TestCase):
    def test_banned_word_in_title_fails_even_when_story_is_fine(self):
        outline = make_outline(title="The Blood Moon Bunny")
        guard_result = GuardResult(Route.STORY, "animal_friends", (), "")
        with mock.patch("review.call_model", return_value=safety_reply(True, [])):
            result = review_story(GOOD_STORY, outline, guard_result, "a bunny")
        self.assertFalse(result.passed)
        self.assertTrue(any("title" in p for p in result.problems))

    def test_title_is_sent_to_the_safety_reviewer(self):
        with mock.patch("review.call_model", return_value=safety_reply(True, [])) as call:
            review_safety(GOOD_STORY, "Lily's Calm Morning")
        prompt = call.call_args.args[0]
        self.assertIn("<title>\nLily's Calm Morning\n</title>", prompt)


class MalformedSafetyTests(unittest.TestCase):
    def test_non_object_issue_fails_closed(self):
        reply = json.dumps({"safe": True, "issues": ["unsafe content"]})
        with mock.patch("review.call_model", return_value=reply):
            problems = review_safety(GOOD_STORY)
        self.assertTrue(problems, "a malformed issue must not be read as a pass")
        self.assertIn("unreadable form", problems[0])


class GuardPrecedenceTests(unittest.TestCase):
    def test_missing_risk_flags_declines(self):
        reply = guard_reply(route="story", category="animal_friends", reason="x")
        with mock.patch("guard.call_model", return_value=reply):
            self.assertEqual(check_request("a bunny").route, Route.DECLINE)

    def test_non_list_risk_flags_declines(self):
        reply = guard_reply(route="story", category="animal_friends", risk_flags="abuse", reason="x")
        with mock.patch("guard.call_model", return_value=reply):
            self.assertEqual(check_request("a bunny").route, Route.DECLINE)

    def test_non_text_risk_flag_declines(self):
        reply = guard_reply(route="story", category="animal_friends", risk_flags=[1], reason="x")
        with mock.patch("guard.call_model", return_value=reply):
            self.assertEqual(check_request("a bunny").route, Route.DECLINE)

    def test_abuse_flag_escalates_despite_invalid_category(self):
        reply = guard_reply(route="story", category="invalid", risk_flags=["abuse"], reason="x")
        with mock.patch("guard.call_model", return_value=reply):
            self.assertEqual(check_request("a bunny").route, Route.ESCALATE)

    def test_escalate_route_survives_malformed_flags(self):
        reply = guard_reply(route="escalate", category=None, reason="x")
        with mock.patch("guard.call_model", return_value=reply):
            self.assertEqual(check_request("a bunny").route, Route.ESCALATE)


class FeedbackPrecedenceTests(unittest.TestCase):
    def test_abuse_flag_escalates_despite_invalid_route(self):
        reply = json.dumps({"route": "maybe", "risk_flags": ["abuse"], "reason": "x"})
        with mock.patch("feedback.call_model", return_value=reply):
            self.assertEqual(check_feedback("make it nice").route, FeedbackRoute.ESCALATE)

    def test_missing_flags_declines(self):
        reply = json.dumps({"route": "apply", "reason": "x"})
        with mock.patch("feedback.call_model", return_value=reply):
            self.assertEqual(check_feedback("make it longer").route, FeedbackRoute.DECLINE)

    def test_escalate_route_survives_malformed_flags(self):
        reply = json.dumps({"route": "escalate", "risk_flags": "nope", "reason": "x"})
        with mock.patch("feedback.call_model", return_value=reply):
            self.assertEqual(check_feedback("make it nice").route, FeedbackRoute.ESCALATE)


class JudgeSeesFeedbackTests(unittest.TestCase):
    def test_feedback_block_is_included_when_requested(self):
        prompt = build_judge_prompt("a bunny", "animal_friends", (), "{}", "story", "make it longer")
        self.assertIn("<feedback>\nmake it longer\n</feedback>", prompt)

    def test_feedback_block_is_absent_for_a_first_draft(self):
        prompt = build_judge_prompt("a bunny", "animal_friends", (), "{}", "story")
        self.assertNotIn("<feedback>", prompt)

    def test_improve_story_passes_feedback_to_the_judge(self):
        guard_result = GuardResult(Route.STORY, "animal_friends", (), "")
        judgement = Judgement(scores={name: 9 for name in CRITERIA}, overall=9.0, notes=())
        with mock.patch("revision.review_story", return_value=Review(True, ())), \
             mock.patch("revision.judge_story", return_value=judgement) as judge:
            revision.improve_story(GOOD_STORY, make_outline(), guard_result, "a bunny", feedback="make it longer")
        self.assertEqual(judge.call_args.args[-1], "make it longer")

    def test_refine_passes_feedback_to_improve_story(self):
        decision = SimpleNamespace(route=FeedbackRoute.APPLY, risk_flags=(), reason="")
        current = ImprovedStory(story=GOOD_STORY, overall=8.0, rounds=())
        guard_result = GuardResult(Route.STORY, "animal_friends", (), "")
        with mock.patch("refine.check_feedback", return_value=decision), \
             mock.patch("refine.plan_outline", return_value=make_outline("New")), \
             mock.patch("refine.write_story", return_value=GOOD_STORY), \
             mock.patch("refine.improve_story", return_value=current) as improve:
            refine.apply_feedback(make_outline(), current, guard_result, "a bunny", "make it longer")
        self.assertEqual(improve.call_args.kwargs["feedback"], "make it longer")


class DeveloperLogTests(unittest.TestCase):
    def test_silent_by_default(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(buf):
            developer_log("secret story quote")
        self.assertEqual(buf.getvalue(), "")

    def test_prints_to_stderr_when_enabled(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"DEVELOPER_LOG": "1"}), contextlib.redirect_stderr(buf):
            developer_log("visible")
        self.assertIn("Developer log: visible", buf.getvalue())


class ApiErrorTests(unittest.TestCase):
    def _client_raising(self, error):
        messages = mock.Mock()
        messages.create.side_effect = error
        return SimpleNamespace(messages=messages)

    def test_rate_limit_becomes_friendly_runtime_error(self):
        class FakeRateLimit(anthropic.RateLimitError):
            def __init__(self):
                Exception.__init__(self, "slow down")

        with mock.patch("llm.get_client", return_value=self._client_raising(FakeRateLimit())):
            with self.assertRaisesRegex(RuntimeError, "busy"):
                llm.call_model("hi")

    def test_other_api_errors_become_runtime_errors(self):
        class FakeApiError(anthropic.APIError):
            def __init__(self):
                Exception.__init__(self, "server trouble")

        with mock.patch("llm.get_client", return_value=self._client_raising(FakeApiError())):
            with self.assertRaisesRegex(RuntimeError, "returned an error"):
                llm.call_model("hi")


if __name__ == "__main__":
    unittest.main()
