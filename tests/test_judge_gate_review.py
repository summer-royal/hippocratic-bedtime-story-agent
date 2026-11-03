"""Tests for the judge, the code gate, and the safety reviewer."""

import json
import unittest
from unittest import mock

from gate import MAX_WORDS, gate_problems
from guard import GuardResult, Route
from helpers import CLOSING, GOOD_STORY, judge_reply, make_outline, safety_reply
from judge import judge_story
from prompts.judge import CRITERIA
from review import review_safety, review_story


class JudgeTests(unittest.TestCase):
    def _judge(self, replies):
        with mock.patch("judge.call_model", side_effect=replies) as call:
            result = judge_story(GOOD_STORY, make_outline(), "a bunny", "animal_friends")
        return result, call

    def test_overall_is_mean_of_criteria(self):
        scores = {name: 8 for name in CRITERIA}
        scores["vocabulary"] = 7
        reply = json.dumps({"scores": scores, "revision_notes": []})
        result, _ = self._judge([reply])
        self.assertEqual(result.overall, 7.8)

    def test_one_retry_after_unreadable_reply(self):
        result, call = self._judge(["not json", judge_reply(9)])
        self.assertEqual(result.overall, 9.0)
        self.assertEqual(call.call_count, 2)

    def test_two_unreadable_replies_raise(self):
        with mock.patch("judge.call_model", return_value="still not json") as call:
            with self.assertRaises(ValueError):
                judge_story(GOOD_STORY, make_outline(), "a bunny", "animal_friends")
        self.assertEqual(call.call_count, 2)

    def test_out_of_range_score_rejected(self):
        scores = {name: 8 for name in CRITERIA}
        scores["engagement"] = 11
        reply = json.dumps({"scores": scores, "revision_notes": []})
        with mock.patch("judge.call_model", return_value=reply):
            with self.assertRaises(ValueError):
                judge_story(GOOD_STORY, make_outline(), "a bunny", "animal_friends")

    def test_boolean_score_rejected(self):
        scores = {name: 8 for name in CRITERIA}
        scores["structure"] = True
        reply = json.dumps({"scores": scores, "revision_notes": []})
        with mock.patch("judge.call_model", return_value=reply):
            with self.assertRaises(ValueError):
                judge_story(GOOD_STORY, make_outline(), "a bunny", "animal_friends")

    def test_missing_criterion_rejected(self):
        scores = {name: 8 for name in CRITERIA if name != "bedtime_calm"}
        reply = json.dumps({"scores": scores, "revision_notes": []})
        with mock.patch("judge.call_model", return_value=reply):
            with self.assertRaises(ValueError):
                judge_story(GOOD_STORY, make_outline(), "a bunny", "animal_friends")

    def test_notes_are_trimmed_and_capped_at_five(self):
        notes = [f"  note {i}  " for i in range(9)] + ["", "   "]
        result, _ = self._judge([judge_reply(8, notes)])
        self.assertEqual(len(result.notes), 5)
        self.assertEqual(result.notes[0], "note 0")

    def test_risk_flags_reach_the_judge_prompt(self):
        with mock.patch("judge.call_model", return_value=judge_reply(9)) as call:
            judge_story(GOOD_STORY, make_outline(), "a bunny", "animal_friends", ("personal_info",))
        self.assertIn("Risk flags: personal_info", call.call_args.args[0])


class GateTests(unittest.TestCase):
    REQUEST = "A story about a bunny."

    def problems(self, story, flags=(), request=None):
        return gate_problems(story, CLOSING, flags, request or self.REQUEST)

    def test_good_story_passes(self):
        self.assertEqual(self.problems(GOOD_STORY), [])

    def test_empty_story_fails(self):
        self.assertEqual(self.problems("   "), ["The story is empty."])

    def test_short_story_fails(self):
        self.assertTrue(any("Length" in p for p in self.problems("Short. " + CLOSING)))

    def test_long_story_fails(self):
        too_long = ("The little bunny hopped through the soft green meadow. " * 60) + CLOSING
        self.assertGreater(len(too_long.split()), MAX_WORDS)
        self.assertTrue(any("Length" in p for p in self.problems(too_long)))

    def test_average_sentence_too_long_fails(self):
        long_sentences = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty. " * 16)
        self.assertTrue(any("Average sentence" in p for p in self.problems(long_sentences + CLOSING)))

    def test_single_long_sentence_fails(self):
        long_one = "word " * 30 + "end. "
        filler = "The bunny hopped. " * 100
        self.assertTrue(any("A sentence has" in p for p in self.problems(long_one + filler + CLOSING)))

    def test_banned_word_fails(self):
        story = GOOD_STORY.replace("meadow.", "meadow with blood.", 1)
        self.assertTrue(any("banned words" in p for p in self.problems(story)))

    def test_banned_word_inside_another_word_does_not_match(self):
        story = GOOD_STORY.replace("meadow.", "bloodhound-free meadow.", 1)
        self.assertFalse(any("banned words" in p for p in self.problems(story)))

    def test_web_address_fails(self):
        self.assertTrue(any("web address" in p for p in self.problems(GOOD_STORY + " See www.example.com")))

    def test_digits_fail(self):
        self.assertTrue(any("digits" in p for p in self.problems(GOOD_STORY + " Call 555")))

    def test_closing_line_missing_fails(self):
        self.assertTrue(any("closing line" in p for p in self.problems(GOOD_STORY.replace(CLOSING, "The end."))))

    def test_closing_line_in_quotes_passes(self):
        self.assertEqual(self.problems(GOOD_STORY.replace(CLOSING, '"' + CLOSING + '"')), [])

    def test_personal_details_fail_only_when_flagged(self):
        request = "My name is Sam and I live on Maple Street. Tell a story about a bunny."
        story = GOOD_STORY.replace("bunny", "bunny Maple Street", 1)
        self.assertTrue(any("Repeats details" in p for p in self.problems(story, ("personal_info",), request)))
        self.assertEqual(self.problems(story, (), request), [])


class SafetyReviewTests(unittest.TestCase):
    def review_reply(self, reply):
        with mock.patch("review.call_model", return_value=reply):
            return review_safety(GOOD_STORY)

    def test_safe_with_no_issues_has_no_problems(self):
        self.assertEqual(self.review_reply(safety_reply(True, [])), [])

    def test_issue_is_described_with_category_and_quote(self):
        issues = [{"category": "weapons", "quote": "drew his sword", "reason": "A weapon."}]
        problems = self.review_reply(safety_reply(False, issues))
        self.assertEqual(len(problems), 1)
        self.assertIn("weapons", problems[0])
        self.assertIn("drew his sword", problems[0])

    def test_unknown_category_becomes_other(self):
        issues = [{"category": "made_up", "quote": "x", "reason": "y"}]
        self.assertTrue(self.review_reply(safety_reply(False, issues))[0].startswith("other:"))

    def test_safe_true_with_issue_still_fails(self):
        issues = [{"category": "age_fit", "quote": "x", "reason": "Too advanced."}]
        self.assertEqual(len(self.review_reply(safety_reply(True, issues))), 1)

    def test_unsafe_without_reason_still_fails(self):
        self.assertEqual(len(self.review_reply(safety_reply(False, []))), 1)

    def test_unreadable_reply_fails_closed(self):
        self.assertIn("unreadable", self.review_reply("looks fine")[0])

    def test_wrong_shape_fails_closed(self):
        self.assertIn("wrong shape", self.review_reply('{"safe": "yes", "issues": []}')[0])


class ReviewStoryTests(unittest.TestCase):
    def guard(self, flags=()):
        return GuardResult(Route.STORY, "animal_friends", flags, "")

    def test_passes_only_when_gate_and_safety_both_pass(self):
        with mock.patch("review.call_model", return_value=safety_reply(True, [])):
            result = review_story(GOOD_STORY, make_outline(), self.guard(), "a bunny")
        self.assertTrue(result.passed)

    def test_gate_failure_fails_even_when_safety_passes(self):
        with mock.patch("review.call_model", return_value=safety_reply(True, [])):
            result = review_story("Too short. " + CLOSING, make_outline(), self.guard(), "a bunny")
        self.assertFalse(result.passed)
        self.assertTrue(any("Length" in p for p in result.problems))

    def test_safety_failure_fails_even_when_gate_passes(self):
        issues = [{"category": "violence", "quote": "x", "reason": "Too much."}]
        with mock.patch("review.call_model", return_value=safety_reply(False, issues)):
            result = review_story(GOOD_STORY, make_outline(), self.guard(), "a bunny")
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
