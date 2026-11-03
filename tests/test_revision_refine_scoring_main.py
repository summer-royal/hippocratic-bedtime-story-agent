"""Tests for the revision loop, keep-or-revert, the eval scorer, and the CLI."""

import builtins
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
import refine
import revision
from evals.scoring import CaseResult, summarize
from feedback import FeedbackRoute
from guard import GuardResult, Route
from helpers import CLOSING, GOOD_STORY, make_outline
from judge import Judgement
from messages import ESCALATION_MESSAGE, FEEDBACK_DECLINE_MESSAGE, FEEDBACK_FAILED_MESSAGE, FEEDBACK_KEPT_MESSAGE, STORY_NOT_READY_MESSAGE
from prompts.judge import CRITERIA
from review import Review
from revision import ImprovedStory, improve_story
from storyteller import write_story


def judgement(overall, notes=("tighten one sentence",)):
    return Judgement(scores={name: round(overall) for name in CRITERIA}, overall=overall, notes=tuple(notes))


def passed(problems=()):
    return Review(passed=True, problems=tuple(problems))


def failed(problems=("problem",)):
    return Review(passed=False, problems=tuple(problems))


GUARD = GuardResult(Route.STORY, "animal_friends", (), "")


class ImproveStoryTests(unittest.TestCase):
    def run_loop(self, reviews, judgements, revisions=None):
        review_iter = iter(reviews)
        judge_iter = iter(judgements)
        revise_calls = []

        def fake_revise(previous, outline, category, notes):
            revise_calls.append(list(notes))
            return f"draft{len(revise_calls)}"

        def fake_judge(*args, **kwargs):
            item = next(judge_iter)
            if isinstance(item, Exception):
                raise item
            return item

        with mock.patch("revision.review_story", side_effect=lambda *a, **k: next(review_iter)), \
             mock.patch("revision.judge_story", side_effect=fake_judge), \
             mock.patch("revision.revise_story", side_effect=fake_revise):
            result = improve_story("draft0", make_outline(), GUARD, "a bunny")
        return result, revise_calls

    def test_good_first_draft_stops_at_once(self):
        result, revisions = self.run_loop([passed()], [judgement(8.5)])
        self.assertEqual(result.story, "draft0")
        self.assertEqual(len(result.rounds), 1)
        self.assertEqual(revisions, [])

    def test_failed_review_is_revised_then_best_passing_draft_wins(self):
        result, revisions = self.run_loop(
            [failed(["length"]), passed(), passed()],
            [judgement(7.0), judgement(9.0)],
        )
        self.assertEqual(result.story, "draft2")
        self.assertEqual(result.overall, 9.0)
        self.assertEqual(len(revisions), 2)
        self.assertEqual(revisions[0][0], "length")

    def test_revision_gets_judge_notes_too(self):
        _, revisions = self.run_loop([passed(), passed(), passed()], [judgement(6.0, ["fix A"]), judgement(6.5, ["fix B"]), judgement(6.0)])
        self.assertIn("fix A", revisions[0])

    def test_never_reaching_threshold_keeps_best_of_three_rounds(self):
        result, revisions = self.run_loop([passed()] * 3, [judgement(6.0), judgement(7.0), judgement(6.0)])
        self.assertEqual(result.story, "draft1")
        self.assertEqual(result.overall, 7.0)
        self.assertEqual(len(result.rounds), 3)
        self.assertEqual(len(revisions), 2)

    def test_judge_failure_keeps_passing_draft_and_stops(self):
        result, revisions = self.run_loop([passed()], [ValueError("bad json")])
        self.assertEqual(result.story, "draft0")
        self.assertIsNone(result.overall)
        self.assertEqual(revisions, [])

    def test_no_notes_means_nothing_to_revise(self):
        result, revisions = self.run_loop([passed()], [judgement(6.5, notes=())])
        self.assertEqual(result.story, "draft0")
        self.assertEqual(revisions, [])

    def test_no_passing_draft_gives_no_story(self):
        result, revisions = self.run_loop([failed()] * 3, [])
        self.assertIsNone(result.story)
        self.assertEqual(len(result.rounds), 3)
        self.assertEqual(len(revisions), 2)

    def test_save_run_writes_json_to_runs_dir(self):
        result = ImprovedStory(story="draft0", overall=8.5, rounds=())
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("revision.RUNS_DIR", Path(tmp)):
                path = revision.save_run("a bunny", "animal_friends", result)
            record = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(record["passed"])
        self.assertEqual(record["final_overall"], 8.5)


class RefineTests(unittest.TestCase):
    def setUp(self):
        self.current = ImprovedStory(story=GOOD_STORY, overall=8.5, rounds=())
        self.current_outline = make_outline("Old")

    def apply(self, route, attempt=None, flags=()):
        decision = mock.Mock(route=FeedbackRoute(route), risk_flags=flags, reason="")
        new_outline = make_outline("New")
        with mock.patch("refine.check_feedback", return_value=decision), \
             mock.patch("refine.plan_outline", return_value=new_outline) as plan, \
             mock.patch("refine.write_story", return_value=GOOD_STORY), \
             mock.patch("refine.improve_story", return_value=attempt) as improve:
            outcome = refine.apply_feedback(self.current_outline, self.current, GUARD, "a bunny", "make it longer")
        return outcome, plan, improve

    def test_higher_score_is_kept(self):
        attempt = ImprovedStory(story=GOOD_STORY, overall=9.0, rounds=())
        outcome, _, _ = self.apply("apply", attempt)
        self.assertEqual(outcome.action, "updated")
        self.assertEqual(outcome.outline.title, "New")

    def test_lower_score_keeps_previous_story(self):
        attempt = ImprovedStory(story=GOOD_STORY, overall=8.0, rounds=())
        outcome, _, _ = self.apply("apply", attempt)
        self.assertEqual(outcome.action, "kept_previous")
        self.assertIs(outcome.outline, self.current_outline)
        self.assertIs(outcome.attempt, attempt)

    def test_failed_review_keeps_previous_story(self):
        attempt = ImprovedStory(story=None, overall=None, rounds=())
        outcome, _, _ = self.apply("apply", attempt)
        self.assertEqual(outcome.action, "kept_previous")

    def test_declined_feedback_never_plans(self):
        outcome, plan, _ = self.apply("decline")
        self.assertEqual(outcome.action, "declined")
        plan.assert_not_called()

    def test_escalated_feedback_never_plans(self):
        decision = mock.Mock(route=FeedbackRoute.ESCALATE, risk_flags=("abuse",), reason="")
        with mock.patch("refine.check_feedback", return_value=decision), mock.patch("refine.plan_outline") as plan:
            outcome = refine.apply_feedback(self.current_outline, self.current, GUARD, "a bunny", "x")
        self.assertEqual(outcome.action, "escalate")
        plan.assert_not_called()

    def test_soften_uses_gentle_route_for_planning_and_review(self):
        attempt = ImprovedStory(story=GOOD_STORY, overall=9.0, rounds=())
        _, plan, improve = self.apply("soften", attempt)
        planner_guard = plan.call_args.args[1]
        review_guard = improve.call_args.args[2]
        self.assertIs(planner_guard.route, Route.GENTLE)
        self.assertIs(review_guard.route, Route.GENTLE)


class ScoringTests(unittest.TestCase):
    def cr(self, cid, group, expected, got, critical):
        return CaseResult(cid, group, "t", tuple(expected), got, critical)

    def test_failure_kinds(self):
        results = [
            self.cr("a", "benign_story", ["story"], "story", False),
            self.cr("b", "decline", ["decline"], "story", True),
            self.cr("c", "escalate", ["escalate"], "decline", True),
            self.cr("d", "benign_story", ["story"], "escalate", False),
            self.cr("e", "decline", ["decline", "gentle"], "gentle", False),
        ]
        summary = summarize(results)
        self.assertEqual(summary.passed, 2)
        self.assertEqual(summary.total, 5)
        self.assertEqual(summary.failure_kinds, {"unsafe_leak": 1, "missed_escalation": 1, "false_escalation": 1})
        self.assertEqual(summary.critical_total, 2)
        self.assertEqual(summary.critical_passed, 0)

    def test_group_counts(self):
        summary = summarize([self.cr("a", "gentle", ["gentle"], "gentle", False), self.cr("b", "gentle", ["gentle"], "story", False)])
        self.assertEqual(summary.by_group["gentle"], (1, 2))

    def test_unsafe_leak_counts_only_critical_declines(self):
        summary = summarize([self.cr("x", "decline", ["decline"], "story", False)])
        self.assertEqual(summary.failure_kinds, {"wrong_route": 1})


class MainTests(unittest.TestCase):
    def run_main(self, inputs):
        answers = iter(inputs)
        buf = io.StringIO()
        with mock.patch("builtins.input", side_effect=lambda _prompt="": next(answers)), \
             contextlib.redirect_stdout(buf):
            main.main()
        return buf.getvalue()

    def patch_pipeline(self, route=Route.STORY, improved=None):
        improved = improved or ImprovedStory(story=GOOD_STORY, overall=8.5, rounds=())
        decision = GuardResult(route, "animal_friends" if route in (Route.STORY, Route.GENTLE) else None, (), "")
        return [
            mock.patch("main.check_request", return_value=decision),
            mock.patch("main.plan_outline", return_value=make_outline("First")),
            mock.patch("main.write_story", return_value=GOOD_STORY),
            mock.patch("main.improve_story", return_value=improved),
            mock.patch("main.save_run"),
        ]

    def test_escalation_prints_escalation_message(self):
        with contextlib.ExitStack() as stack:
            for patcher in self.patch_pipeline(route=Route.ESCALATE):
                stack.enter_context(patcher)
            self.assertIn(ESCALATION_MESSAGE, self.run_main(["my dad hits me"]))

    def test_story_not_ready_when_no_draft_passes(self):
        improved = ImprovedStory(story=None, overall=None, rounds=())
        with contextlib.ExitStack() as stack:
            for patcher in self.patch_pipeline(improved=improved):
                stack.enter_context(patcher)
            self.assertIn(STORY_NOT_READY_MESSAGE, self.run_main(["a bunny"]))

    def test_enter_at_feedback_prompt_finishes(self):
        with contextlib.ExitStack() as stack:
            for patcher in self.patch_pipeline():
                stack.enter_context(patcher)
            out = self.run_main(["a bunny", ""])
        self.assertIn("First", out)
        self.assertNotIn(FEEDBACK_KEPT_MESSAGE, out)

    def test_declined_feedback_prints_decline_and_keeps_asking(self):
        declined = ("declined", make_outline("First"), ImprovedStory(GOOD_STORY, 8.5, ()), None)
        with contextlib.ExitStack() as stack:
            for patcher in self.patch_pipeline():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("main.apply_feedback", side_effect=lambda *a: refine.RefineOutcome(*declined)))
            out = self.run_main(["a bunny", "add a fight", ""])
        self.assertIn(FEEDBACK_DECLINE_MESSAGE, out)

    def test_at_most_three_feedback_rounds(self):
        declined = refine.RefineOutcome("declined", make_outline("First"), ImprovedStory(GOOD_STORY, 8.5, ()), None)
        with contextlib.ExitStack() as stack:
            for patcher in self.patch_pipeline():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("main.apply_feedback", return_value=declined))
            out = self.run_main(["a bunny", "one", "two", "three", "four"])
        self.assertEqual(out.count(FEEDBACK_DECLINE_MESSAGE), 3)

    def test_failed_feedback_keeps_story_and_says_so(self):
        with contextlib.ExitStack() as stack:
            for patcher in self.patch_pipeline():
                stack.enter_context(patcher)
            stack.enter_context(mock.patch("main.apply_feedback", side_effect=ValueError("bad planner reply")))
            out = self.run_main(["a bunny", "make it longer", ""])
        self.assertIn(FEEDBACK_FAILED_MESSAGE, out)
        self.assertIn("First", out)

    def test_runtime_error_exits_with_status_one(self):
        with mock.patch("main.check_request", side_effect=RuntimeError("no key")), \
             mock.patch("builtins.input", return_value="a bunny"), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as exit_info:
                main.main()
        self.assertEqual(exit_info.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
