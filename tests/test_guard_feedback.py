"""Tests for the request guard and the feedback guard. The model is stubbed, so no live calls."""

import json
import unittest
from unittest import mock

import feedback
import guard
from feedback import FeedbackRoute, check_feedback
from guard import Route, check_request, has_crisis_phrase


def guard_reply(route, category=None, flags=(), reason="reason"):
    return json.dumps({"route": route, "category": category, "risk_flags": list(flags), "reason": reason})


class RequestGuardTests(unittest.TestCase):
    def test_empty_request_declined_without_model_call(self):
        with mock.patch("guard.call_model") as call:
            self.assertEqual(check_request("   ").route, Route.DECLINE)
        call.assert_not_called()

    def test_crisis_phrase_escalates_without_model_call(self):
        with mock.patch("guard.call_model") as call:
            self.assertEqual(check_request("I want to die").route, Route.ESCALATE)
        call.assert_not_called()

    def test_story_route_with_category(self):
        with mock.patch("guard.call_model", return_value=guard_reply("story", "animal_friends")):
            result = check_request("A story about a cat.")
        self.assertEqual(result.route, Route.STORY)
        self.assertEqual(result.category, "animal_friends")

    def test_unknown_route_declines(self):
        with mock.patch("guard.call_model", return_value=guard_reply("maybe", "animal_friends")):
            self.assertEqual(check_request("x").route, Route.DECLINE)

    def test_unknown_category_declines(self):
        with mock.patch("guard.call_model", return_value=guard_reply("story", "space_wizards")):
            self.assertEqual(check_request("x").route, Route.DECLINE)

    def test_abuse_flag_escalates_even_for_story(self):
        with mock.patch("guard.call_model", return_value=guard_reply("story", "silly_adventure", ["abuse"])):
            result = check_request("x")
        self.assertEqual(result.route, Route.ESCALATE)
        self.assertIsNone(result.category)

    def test_jailbreak_flag_declines_a_gentle_request(self):
        with mock.patch("guard.call_model", return_value=guard_reply("gentle", "make_believe_quest", ["jailbreak_attempt"])):
            self.assertEqual(check_request("x").route, Route.DECLINE)

    def test_sexual_flag_declines_a_story(self):
        with mock.patch("guard.call_model", return_value=guard_reply("story", "calm_and_cozy", ["sexual_content"])):
            self.assertEqual(check_request("x").route, Route.DECLINE)

    def test_personal_info_alone_keeps_the_story_route(self):
        with mock.patch("guard.call_model", return_value=guard_reply("story", "animal_friends", ["personal_info"])):
            result = check_request("x")
        self.assertEqual(result.route, Route.STORY)
        self.assertEqual(result.risk_flags, ("personal_info",))

    def test_unknown_flags_are_dropped(self):
        with mock.patch("guard.call_model", return_value=guard_reply("story", "animal_friends", ["made_up"])):
            self.assertEqual(check_request("x").risk_flags, ())

    def test_unreadable_reply_fails_closed(self):
        with mock.patch("guard.call_model", return_value="Sure, here is a story!"):
            self.assertEqual(check_request("x").route, Route.DECLINE)

    def test_crisis_phrase_matches_whole_words_only(self):
        self.assertTrue(has_crisis_phrase("My dad hits me."))
        self.assertFalse(has_crisis_phrase("The hurts memory faded."))


class FeedbackGuardTests(unittest.TestCase):
    def feedback_reply(self, route, flags=()):
        return json.dumps({"route": route, "risk_flags": list(flags), "reason": "reason"})

    def test_empty_feedback_declined_without_model_call(self):
        with mock.patch("feedback.call_model") as call:
            self.assertEqual(check_feedback("").route, FeedbackRoute.DECLINE)
        call.assert_not_called()

    def test_crisis_feedback_escalates_without_model_call(self):
        with mock.patch("feedback.call_model") as call:
            self.assertEqual(check_feedback("My dad hits me").route, FeedbackRoute.ESCALATE)
        call.assert_not_called()

    def test_apply_and_soften_routes(self):
        with mock.patch("feedback.call_model", return_value=self.feedback_reply("apply")):
            self.assertEqual(check_feedback("longer please").route, FeedbackRoute.APPLY)
        with mock.patch("feedback.call_model", return_value=self.feedback_reply("soften", ["scary_content"])):
            self.assertEqual(check_feedback("grumpy but friendly").route, FeedbackRoute.SOFTEN)

    def test_violence_flag_declines_even_an_apply(self):
        with mock.patch("feedback.call_model", return_value=self.feedback_reply("apply", ["violence"])):
            self.assertEqual(check_feedback("add a fight").route, FeedbackRoute.DECLINE)

    def test_abuse_flag_escalates(self):
        with mock.patch("feedback.call_model", return_value=self.feedback_reply("apply", ["abuse"])):
            self.assertEqual(check_feedback("x").route, FeedbackRoute.ESCALATE)

    def test_personal_info_declines(self):
        with mock.patch("feedback.call_model", return_value=self.feedback_reply("apply", ["personal_info"])):
            self.assertEqual(check_feedback("put my address in").route, FeedbackRoute.DECLINE)

    def test_unknown_route_and_bad_reply_decline(self):
        with mock.patch("feedback.call_model", return_value=self.feedback_reply("maybe")):
            self.assertEqual(check_feedback("x").route, FeedbackRoute.DECLINE)
        with mock.patch("feedback.call_model", return_value="not json"):
            self.assertEqual(check_feedback("x").route, FeedbackRoute.DECLINE)

    def test_feedback_is_wrapped_in_tags(self):
        with mock.patch("feedback.call_model", return_value=self.feedback_reply("apply")) as call:
            check_feedback("make it longer")
        self.assertIn("<feedback>\nmake it longer\n</feedback>", call.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
