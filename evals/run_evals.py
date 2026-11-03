"""Run the eval set against the live guard and feedback guard.

Usage (from the project folder):
    .venv/bin/python -m evals.run_evals                  # guard and feedback routing only
    .venv/bin/python -m evals.run_evals --with-stories 3  # also run full stories for 3 benign cases

Each guard case costs one model call. Each story costs about ten calls.
Results are written to runs/ as JSON, which is gitignored.
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from evals.scoring import CaseResult, summarize
from feedback import check_feedback
from guard import check_request
from outline import plan_outline
from revision import improve_story
from storyteller import write_story

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = PROJECT_ROOT / "evals" / "cases.jsonl"
RUNS_DIR = PROJECT_ROOT / "runs"
STORY_GROUPS = {"benign_story", "gentle", "edge", "personal_info"}


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    """Read one JSON case per line."""
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_route_case(case: dict) -> CaseResult:
    """Route one request or feedback case through the matching guard."""
    if case["kind"] == "feedback":
        got = check_feedback(case["text"]).route.value
    else:
        got = check_request(case["text"]).route.value
    return CaseResult(
        case_id=case["id"],
        group=case["group"],
        text=case["text"],
        expected=tuple(case["expected"]),
        got=got,
        critical=case["critical"],
    )


def run_story_case(case: dict) -> dict:
    """Run the full story pipeline for one benign request and record what the review decided."""
    guard = check_request(case["text"])
    outline = plan_outline(case["text"], guard)
    improved = improve_story(write_story(outline, guard.category or "calm_and_cozy"), outline, guard, case["text"])
    story = improved.story
    return {
        "id": case["id"],
        "passed_review": story is not None,
        "overall": improved.overall,
        "words": len(story.split()) if story else 0,
        "closing_ok": bool(story) and story.endswith(outline.closing_line),
    }


def print_table(results: list[CaseResult]) -> None:
    print(f"{'id':5} {'group':16} {'expected':22} {'got':10} {'ok':3} failure")
    for result in results:
        print(
            f"{result.case_id:5} {result.group:16} {','.join(result.expected):22} "
            f"{result.got:10} {'yes' if result.passed else 'NO':3} {result.failure_kind or ''}"
        )


def print_summary(summary) -> None:
    print()
    print(f"Accuracy: {summary.passed}/{summary.total} ({summary.accuracy:.0%})")
    print(f"Safety-critical cases passed: {summary.critical_passed}/{summary.critical_total}")
    print("By group:")
    for group, (passed, total) in sorted(summary.by_group.items()):
        print(f"  {group:16} {passed}/{total}")
    print(f"Failure kinds: {summary.failure_kinds or 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bedtime-story eval set.")
    parser.add_argument("--with-stories", type=int, default=0, help="also run full stories for this many benign cases")
    args = parser.parse_args()

    cases = load_cases()
    results = [run_route_case(case) for case in cases]
    print_table(results)
    summary = summarize(results)
    print_summary(summary)

    story_results = []
    if args.with_stories:
        story_cases = [case for case in cases if case["kind"] == "request" and case["group"] in STORY_GROUPS]
        for case in story_cases[: args.with_stories]:
            story_results.append(run_story_case(case))
        if story_results:
            print()
            print("Full stories:")
            for entry in story_results:
                print(
                    f"  {entry['id']}: passed_review={entry['passed_review']} overall={entry['overall']} "
                    f"words={entry['words']} closing_ok={entry['closing_ok']}"
                )

    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    record = {
        "accuracy": summary.accuracy,
        "passed": summary.passed,
        "total": summary.total,
        "critical_passed": summary.critical_passed,
        "critical_total": summary.critical_total,
        "failure_kinds": summary.failure_kinds,
        "results": [asdict(result) for result in results],
        "stories": story_results,
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
