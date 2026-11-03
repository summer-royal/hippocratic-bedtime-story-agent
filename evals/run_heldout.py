"""Run the held-out set once and check what the child would see.

The held-out set (evals/heldout.jsonl) was written before any tuning and must
not be used to tune prompts. If a prompt changes after a run, that run no
longer counts as held-out evidence and must be labelled as a development run.

For each request: the route is compared with the expected routes. For a story
route, the full pipeline runs, and the displayed title and story are checked for
forbidden details and for the closing line. For escalate and decline, the fixed
message is what the child would see.

Usage (from the project folder):
    .venv/bin/python -m evals.run_heldout
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from evals.scoring import CaseResult, summarize
from feedback import FeedbackRoute, check_feedback
from guard import Route, check_request
from messages import DECLINE_MESSAGE, ESCALATION_MESSAGE, FEEDBACK_DECLINE_MESSAGE, STORY_NOT_READY_MESSAGE
from outline import plan_outline
from revision import improve_story
from storyteller import write_story

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HELDOUT_PATH = PROJECT_ROOT / "evals" / "heldout.jsonl"
RUNS_DIR = PROJECT_ROOT / "runs"


def load_cases(path: Path = HELDOUT_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_case(case: dict) -> tuple[CaseResult, dict]:
    """Return the scored result and a record of what the child would see."""
    if case["kind"] == "feedback":
        route = check_feedback(case["text"]).route
        shown = {
            FeedbackRoute.ESCALATE: ESCALATION_MESSAGE,
            FeedbackRoute.DECLINE: FEEDBACK_DECLINE_MESSAGE,
        }.get(route, "(a change would be applied; no story was generated for this check)")
        got = route.value
        display_problems: list[str] = []
        record = {"shown": shown, "display_problems": display_problems}
    else:
        guard = check_request(case["text"])
        got = guard.route.value
        display_problems = []
        if guard.route is Route.ESCALATE:
            shown = ESCALATION_MESSAGE
        elif guard.route is Route.DECLINE:
            shown = DECLINE_MESSAGE
        else:
            outline = plan_outline(case["text"], guard)
            improved = improve_story(write_story(outline, guard.category or "calm_and_cozy"), outline, guard, case["text"])
            if improved.story is None:
                shown = STORY_NOT_READY_MESSAGE
            else:
                shown = f"{outline.title}\n\n{improved.story}"
                for forbidden in case["must_not_contain"]:
                    if forbidden in shown:
                        display_problems.append(f"shown text contains '{forbidden}'")
                if not improved.story.endswith(outline.closing_line):
                    display_problems.append("story does not end with the closing line")
        record = {"shown": shown, "display_problems": display_problems}

    result = CaseResult(
        case_id=case["id"],
        group=case["group"],
        text=case["text"],
        expected=tuple(case["expected"]),
        got=got,
        critical=case["critical"],
    )
    return result, record


def main() -> None:
    cases = load_cases()
    rows = []
    results = []
    for case in cases:
        result, record = run_case(case)
        results.append(result)
        rows.append({"id": case["id"], "group": case["group"], "text": case["text"], **asdict(result), **record})
        status = "yes" if result.passed else "NO"
        display = "ok" if not record["display_problems"] else "; ".join(record["display_problems"])
        print(f"{result.case_id:4} {result.group:20} expected={','.join(result.expected):18} got={result.got:9} route={status:3} display={display}")

    summary = summarize(results)
    display_failures = [row["id"] for row in rows if row["display_problems"]]
    print()
    print(f"Route accuracy: {summary.passed}/{summary.total} ({summary.accuracy:.0%})")
    print(f"Safety-critical routes passed: {summary.critical_passed}/{summary.critical_total}")
    print(f"Failure kinds: {summary.failure_kinds or 'none'}")
    print(f"Display check failures: {display_failures or 'none'}")

    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"heldout-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
