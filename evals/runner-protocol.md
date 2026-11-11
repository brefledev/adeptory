# D1-D3 comparison and artifact protocol

This document defines a future coordinator-run evaluation. Lane C did not invoke Hermes or any model. The host runtime, profile, and guards need coordinator verification before any live turn.

## Conditions

Run each case under three conditions using the same model identifier, model settings, tools, task text, and fixture bytes:

1. **base** supplies no Adeptory package or persisted notes.
2. **static** supplies the same reviewed package text as fixed context. It does not run Adeptory selection or note/consequence tools.
3. **runtime** loads the same fixture-adopted package through Adeptory and runs the note/consequence flow.

Use a fresh conversation and data directory per arm. For D3, retain state across the two turns within an arm and reset it before the next arm. Record the exact model, profile, runtime build, prompt revision, package version, tool availability, fixture hash, arm start time, and result path. If any arm differs in model or host tools, report the arms separately and set the three-way comparison to incomplete.

Before a runtime arm, capture evidence that the approved scratch clone retains the required guards. Do not proceed if the coordinator cannot verify that state or does not have live-call authority. M8 needs the events `scratch_clone_verified`, `guards_preserved`, and `live_call_authorized` in the runtime receipt. The last event records authorization state; a mechanics test cannot create it.

## Data boundary

The builder receives the separate development brief and development fixture. Do not include `evals/`, this suite, expected decisions, rubric terms, or evaluator artifacts in generator prompts, tools, package sources, or runtime lookup. Inspect captured input/tool traces for accidental suite exposure. The lane implementation agent has read these cases, so the evaluation is explicitly implementation-visible. Host-wide isolation is unverified until coordinator trace inspection.

## Artifact format

Save one UTF-8 JSON object per case/arm at `artifacts/<case-id>/<arm>.json`. Required fields:

```json
{
  "response": "verbatim response or structured response object",
  "model": "full provider model identifier",
  "prompt_id": "prompt revision identifier",
  "task_id": "same task identifier across the three arms",
  "package_version": "version or null",
  "runtime": "Hermes and plugin version, or baseline host identifier",
  "tool_access": ["same authorized tool names and access scope across arms"],
  "events": [
    {"name": "observation_captured", "evidence": "receipt path or bounded excerpt"}
  ],
  "costs": {"status": "unknown"},
  "started_at": "ISO-8601 timestamp",
  "fixture_sha256": "SHA-256 of fixture input bytes"
}
```

Preserve output, tool calls, and event receipts needed to audit each dimension. If usage/cost metadata is unavailable, use `{"status":"unknown"}`. Never estimate missing costs. The loader reads existing artifacts only and does not spawn commands, sessions, profiles, or model calls.

## Scoring

Each case rubric has five named dimensions. The target human review scale is 0 (miss), 1 (partial), or 2 (pass), with a short reason linked to response/tool evidence. A human-review record must include reviewer identity or role, review time, reviewed artifact hash, score, and reason for every dimension. Record the reviewer as independent only when they did not implement the code or author the fixture. If no independent reviewer is available, write `independent_review: unavailable`; do not fabricate human scores.

The included `pass_terms` and `partial_terms` enable a quick phrase-match scan only. `core.evalcheck.score_response` and report scores are explicitly `provisional_phrase_heuristic`; a phrase match cannot establish factual support, reasoning quality, source use, or expert correctness. A reviewer can replace the heuristic by a separate signed-off score record. Report all arm outcomes and misses; do not collapse them into one confidence score.

## Mechanics versus product outcome

M1, M2, M3, and M7 suite checks validate declarations and fixtures only. A pass is scoped to `suite_contract`, not to the eventual builder/runtime implementation. M4, M5, M6, and M8 require event receipts from a run and remain unverified without artifacts. Mechanics-only output never makes a model-performance comparison. Product-quality scoring remains unavailable until model outputs are supplied and assessed.
