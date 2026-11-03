# Block diagram

This diagram shows what happens at runtime and which module does each job. Every arrow matches a call or an import in the code. Type-only imports, such as `GuardResult` and `Outline` used only in annotations, are drawn only where the module also uses the data at runtime.

```mermaid
flowchart TD
    User([User: parent or child, typing in the terminal])
    Main["main.py<br/>CLI: request, then up to 3 feedback rounds"]
    Messages["messages.py<br/>fixed child-facing messages"]

    subgraph Guards
        Guard["guard.py<br/>request guard: crisis pre-screen, code overrides"]
        Feedback["feedback.py<br/>feedback guard: crisis pre-screen, code overrides"]
    end

    subgraph Generation
        Outline["outline.py<br/>planner reply parsed and validated"]
        Storyteller["storyteller.py<br/>write_story and revise_story"]
    end

    subgraph Checks
        Review["review.py<br/>review_story: code gate and safety reviewer"]
        Gate["gate.py<br/>code gate: length, sentences, banned words, closing line"]
        Judge["judge.py<br/>quality judge, six criteria, one retry"]
    end

    subgraph Loop
        Revision["revision.py<br/>improve_story: review, judge, revise, keep best"]
        Refine["refine.py<br/>apply_feedback: keep new story only if it scores as well"]
    end

    subgraph Prompts
        PG["prompts/guard.py"]
        PF["prompts/feedback.py"]
        PP["prompts/planner.py"]
        PS["prompts/storyteller.py"]
        PJ["prompts/judge.py"]
        PSafe["prompts/safety.py"]
    end

    LLM["llm.py<br/>call_model: the only place that calls the API"]
    Parsing["parsing.py<br/>parse_json_object"]
    Claude[("Anthropic API<br/>claude-haiku-5-5")]
    Runs[("runs/<br/>JSON run logs, gitignored")]

    User -->|request| Main
    User -->|feedback| Main
    Main -->|check_request| Guard
    Main -->|plan_outline| Outline
    Main -->|write_story| Storyteller
    Main -->|improve_story, save_run| Revision
    Main -->|apply_feedback| Refine
    Main -->|escalate, decline, not ready| Messages

    Guard -->|system prompt| PG
    Feedback -->|has_crisis_phrase| Guard
    Feedback -->|system prompt| PF
    Feedback -->|risk flag list| PG

    Outline -->|guard decision| Guard
    Outline -->|system prompt| PP

    Storyteller -->|outline| Outline
    Storyteller -->|system prompt| PS

    Review -->|guard decision| Guard
    Review -->|code gate| Gate
    Review -->|outline| Outline
    Review -->|system prompt| PSafe

    Judge -->|outline| Outline
    Judge -->|system prompt| PJ

    Revision -->|review_story| Review
    Revision -->|judge_story| Judge
    Revision -->|revise_story| Storyteller
    Revision -->|guard decision| Guard
    Revision -->|outline| Outline
    Revision -->|save_run| Runs

    Refine -->|check_feedback| Feedback
    Refine -->|plan_outline, previous outline| Outline
    Refine -->|write_story| Storyteller
    Refine -->|improve_story| Revision
    Refine -->|guard decision| Guard

    Guard -->|call_model| LLM
    Feedback -->|call_model| LLM
    Outline -->|call_model| LLM
    Storyteller -->|call_model| LLM
    Judge -->|call_model| LLM
    Review -->|call_model| LLM
    LLM -->|HTTPS| Claude

    Guard -->|parse reply| Parsing
    Feedback -->|parse reply| Parsing
    Outline -->|parse reply| Parsing
    Judge -->|parse reply| Parsing
    Review -->|parse reply| Parsing
```

## Reading the diagram

- **One request, start to finish.** `main.py` runs the guard first. An escalate or decline route ends with a fixed message, and no story is written. A story route goes to the planner, then the storyteller, then the revision loop. `save_run` writes every round to `runs/`.
- **The revision loop.** Each draft is reviewed first. `review_story` runs the code gate (`gate.py`) and the safety reviewer (`prompts/safety.py`). Only a draft that passes review is judged. A score of 8 or higher ends the loop. Otherwise the storyteller revises the draft using the review problems and judge notes, for at most two revisions.
- **Feedback.** Each change goes through `check_feedback` first. An applied change is re-planned from the previous outline, written, and run through the same loop. The new story replaces the old one only if it passes review and scores at least as high.
- **Safety layers.** The crisis phrase pre-screen runs before any model call. The code gate and code overrides cannot be argued with. The safety reviewer is strict, and any issue it lists fails the story.
- **One place for the API.** Every model call goes through `llm.py`, so the model name, the key handling, and the cut-off check live in one file.

## Not drawn

- **Evals.** `evals/run_evals.py` calls the guard and feedback guard, and optionally the full story pipeline. It scores the results with `evals/scoring.py` and reads cases from `evals/cases.jsonl`.
- **Tests.** `tests/` stubs the model, so the unit tests make no live calls. They check the logic in every module except `storyteller.py`, whose functions are stubbed rather than checked directly. The storyteller is covered only through the live runs.
- **Environment.** `llm.py` reads `ANTHROPIC_API_KEY` from `.env`, through python-dotenv.
