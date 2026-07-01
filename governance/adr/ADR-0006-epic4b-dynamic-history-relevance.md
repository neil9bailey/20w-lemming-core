# ADR-0006: Epic 4B Dynamic History Relevance

Status: Approved
Date: 2026-07-02
Gate: G1 Architecture
Epic: Epic 4 - Tranche 4B Dynamic Weight Tuning

## Context

Epic 4A added an evidence context channel to the 20W Lemming substrate. Epic 4B extends the
historical retrieval layer so prior successful runs are ranked by vocabulary overlap with the
incoming target instead of being consumed as a static recent-history list.

The current persistence layer stores successful run history in `runs` and exposes the compatible
`cognitive_history` view. The current graph response is the LangGraph state dictionary rather than
a dedicated Pydantic response model.

## Decision

- Add `calculate_relevance_score(target_prompt, historical_intent)` to `memory_store.py`.
- Tokenize strings into unique lowercase alphanumeric words.
- Score history by intersection size normalized by the log-length of the current target vector.
- Refactor `load_successful_runs()` to query the latest successful rows from `cognitive_history`,
  score each candidate, sort by descending score, and return the top 3 ranked rows by default.
- Add `historical_context` and `max_history_relevance_score` to `LemmingState`.
- Populate those state fields during graph initialization and return them in the `/run` response
  dictionary.
- Default `max_history_relevance_score` to `0.0` when no history exists or no overlap is found.

## Consequences

- Existing callers remain compatible because the `/run` request schema is unchanged.
- The response contract expands with a deterministic technical metric:
  `max_history_relevance_score`.
- Bias profile construction still works because `load_successful_runs()` remains the retrieval
  entry point.
- Dynamic retrieval is deterministic and local; it introduces no external service or credential
  dependency.

## Verification

- `python -m compileall main.py memory_store.py`
- `docker compose up -d --build`
- POST `/run` with a target containing terms already present in prior successful runs, such as
  `RACI` or `IT services market`; confirm `max_history_relevance_score > 0.0`.
- Confirm no private host paths or credential literals are introduced.
