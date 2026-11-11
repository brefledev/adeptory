"""Evaluation suite validation and artifact-only comparison helpers.

This module never starts a model or Hermes process. Supplied arm artifacts are
the sole source of response data; missing artifacts remain missing.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile
from typing import Any

ARMS = ("base", "static", "runtime")
CASES = ("D1", "D2", "D3")
MECHANICS = tuple(f"M{i}" for i in range(1, 9))


def _load_data(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("YAML suite requires installed PyYAML; use JSON otherwise") from exc
        value = yaml.safe_load(raw)
    else:
        value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("suite root must be an object")
    return value


def _artifact_path(root: Path, case_id: str, arm: str) -> Path:
    return root / "artifacts" / case_id / f"{arm}.json"


def load_artifacts(suite_path: str | Path) -> dict[str, Any]:
    """Load only pre-existing response artifacts; no inference or invocation."""
    path = Path(suite_path).resolve()
    suite = _load_data(path)
    artifact_root = path.parent
    loaded: dict[str, Any] = {}
    for case in suite.get("cases", []):
        case_id = case.get("id")
        if not isinstance(case_id, str):
            continue
        loaded[case_id] = {}
        for arm in ARMS:
            candidate = _artifact_path(artifact_root, case_id, arm)
            if candidate.is_file():
                item = _load_data(candidate)
                item["_artifact_path"] = str(candidate)
                loaded[case_id][arm] = item
    return loaded


def _case_dimensions(case: dict[str, Any]) -> list[dict[str, Any]]:
    dimensions = case.get("dimensions", [])
    if not isinstance(dimensions, list):
        raise ValueError(f"case {case.get('id')}: dimensions must be a list")
    return dimensions


def _heuristic_scores(case: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    """Score explicit rubric phrases in a response; never claim semantic review."""
    response = artifact.get("response", "")
    if not isinstance(response, str):
        response = json.dumps(response, ensure_ascii=False)
    normalized = re.sub(r"\s+", " ", response.casefold())
    scores: dict[str, int] = {}
    reasons: dict[str, str] = {}
    for dimension in _case_dimensions(case):
        dimension_id = str(dimension["id"])
        pass_terms = [str(term).casefold() for term in dimension.get("pass_terms", [])]
        partial_terms = [str(term).casefold() for term in dimension.get("partial_terms", [])]
        if pass_terms and any(term in normalized for term in pass_terms):
            scores[dimension_id] = 2
            reasons[dimension_id] = "Heuristic phrase match only; semantic support unreviewed."
        elif partial_terms and any(term in normalized for term in partial_terms):
            scores[dimension_id] = 1
            reasons[dimension_id] = "Heuristic partial phrase match only; semantic support unreviewed."
        else:
            scores[dimension_id] = 0
            reasons[dimension_id] = "No configured phrase matched; this is not a semantic failure finding."
    return {"scores": scores, "reasons": reasons, "scoring_status": "provisional_phrase_heuristic"}


def score_response(case: dict[str, Any], response: str) -> dict[str, Any]:
    """Return phrase-match suggestions; never a human or semantic judgment."""
    return _heuristic_scores(case, {"response": response})


def _event_names(artifact: dict[str, Any]) -> set[str]:
    events = artifact.get("events", [])
    result: set[str] = set()
    if isinstance(events, list):
        for event in events:
            if isinstance(event, str):
                result.add(event)
            elif isinstance(event, dict) and isinstance(event.get("name"), str):
                result.add(event["name"])
    return result


def _mechanics(suite: dict[str, Any], artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        modules = _runtime_modules()
    except (ImportError, AttributeError) as exc:
        return [{"id": check_id, "status": "unverified", "scope": "core_behavior", "issues": [f"runtime core modules unavailable: {exc}"]} for check_id in MECHANICS[:-1]] + [
            {"id": "M8", "status": "unverified", "scope": "guarded_host_runtime", "issues": ["coordinator guard evidence not supplied"]}
        ]
    outcomes = _exercise_core(modules)
    outcomes.append(_check_guard_receipt(suite, artifacts))
    return outcomes


def _runtime_modules():
    from core.kitstore import KitStore, kit_from_dict, validate_kit
    from core.builder import Builder, read_proposal
    from core.select import select_context
    from core.notes import NoteStore
    from core.rules import check_consequences
    from core.model import KitError, Observation
    return locals()


def _exercise_core(api: dict[str, Any]) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []

    def record(check_id: str, condition: bool, issue: str, scope: str = "core_behavior"):
        outcomes.append({"id": check_id, "status": "pass" if condition else "fail", "scope": scope, "issues": [] if condition else [issue]})

    KitStore = api["KitStore"]
    kit_from_dict = api["kit_from_dict"]
    validate_kit = api["validate_kit"]
    Builder = api["Builder"]
    read_proposal = api["read_proposal"]
    select_context = api["select_context"]
    NoteStore = api["NoteStore"]
    check_consequences = api["check_consequences"]
    KitError = api["KitError"]
    Observation = api["Observation"]
    source = {
        "id": "eval-source", "url": "https://example.gov/guide", "title": "Official test guide",
        "retrieved_at": "2026-11-11", "excerpt": "Long redirect chains can hinder crawling.",
        "locator": "Redirect guidance, paragraph 2", "retrieval_tool": "fixture source loader",
        "effective_or_published": None, "quality": "primary", "limitations": [], "jurisdiction": None,
        "receipt": {}
    }
    claim = {
        "id": "eval-claim", "text": "Long chains warrant investigation.", "source_ids": ["eval-source"],
        "support": "supported", "review": {"reviewer": "mechanics-fixture", "reason": "Exact passage supports this narrow claim.",
            "passage_checks": [{"source_id": "eval-source", "passage": "Long redirect chains can hinder crawling.", "reason": "The passage states the supported proposition."}]},
        "contradictions": [], "inference": False
    }
    step = {"id": "chain-step", "instruction": "Investigate redirect chain and final target.", "reason": "Finds redirect chains.",
            "evidence_requirements": ["source row"], "exceptions": [], "priority": "high", "consequence": "May reduce crawl efficiency.",
            "claim_ids": ["eval-claim"], "keywords": ["redirect chain", "final target"]}
    raw = {"id": "eval-kit", "goal": "Test evaluation mechanics", "subject": "fixture-site", "version": 1,
           "schema_version": 1, "fixture": True, "scope": {}, "sources": [source], "claims": [claim], "workflow": [step],
           "capabilities": [], "data_map": [], "pending_choices": [],
           "adoption": {"status": "proposed", "origin": "none", "actor": None, "at": None, "version": None, "choices": {}},
           "rules": [{"id": "asset-rule", "kind": "asset-removal", "asset": "/assets/cinder-mark.png"}], "gaps": []}
    errors: list[str] = []
    try:
        kit_from_dict({**raw, "unexpected": True})
        errors.append("unsupported field was accepted")
    except KitError:
        pass
    try:
        kit_from_dict({key: value for key, value in raw.items() if key != "goal"})
        errors.append("missing required field was accepted")
    except KitError:
        pass
    record("M1", not errors, "; ".join(errors) if errors else "", "package_shape_validation")

    support_errors = validate_kit(kit_from_dict(raw))
    bad_claim = {**raw, "claims": [{**claim, "review": {**claim["review"], "passage_checks": [{"source_id": "eval-source", "passage": "unseen wording", "reason": "bad"}]}}]}
    bad_passage_rejected = False
    try:
        kit_from_dict(bad_claim)
    except KitError:
        bad_passage_rejected = True
    with tempfile.TemporaryDirectory() as temp:
        store = KitStore(temp)
        proposed = kit_from_dict(raw)
        store.save(proposed)
        proposal_kept = store.load("eval-kit").adoption.status == "proposed"
        real_adoption_rejected = False
        try:
            store.adopt("eval-kit", origin="model-tool", actor="model")
        except KitError:
            real_adoption_rejected = True
        fixture_adopted = store.adopt("eval-kit", origin="fixture-harness", actor="isolated-test", fixture_harness=True).adoption.status == "adopted"
        record("M2", not support_errors and bad_passage_rejected and proposal_kept and real_adoption_rejected and fixture_adopted,
               "support passage, proposal/adoption boundary, or fixture-only adoption check failed", "provenance_and_adoption_behavior")

        builder_refused_eval_path = False
        eval_dir = Path(temp) / "evals"
        eval_dir.mkdir()
        eval_file = eval_dir / "answers.json"
        eval_file.write_text("{}", encoding="utf-8")
        try:
            read_proposal(eval_file, allowed_root=temp)
        except KitError:
            builder_refused_eval_path = True
        record("M3", builder_refused_eval_path, "builder imported a file from the evaluation directory", "generator_input_boundary")

        kit = store.load("eval-kit")
        selected = select_context(kit, "Please investigate redirect chain and final target", "fixture-site")
        unrelated = select_context(kit, "Write a recipe for soup", "fixture-site")
        record("M4", bool(selected["receipt"]["selected"]) and not unrelated["receipt"]["selected"]
               and "task matches declared workflow terms" in selected["receipt"]["selected"][0]["reason"],
               "relevant selection or unrelated-task omission failed", "selection_behavior")

        note_store = NoteStore(temp)
        observation = Observation("asset-observation", "eval-kit", "fixture-site",
            "Two pages reference /assets/cinder-mark.png.", "fixture pages: /guild and /about",
            "synthetic_eval", "2026-11-11T04:00:00+00:00", "2026-12-11T04:00:00+00:00",
            ["cinder-mark.png", "asset reference"])
        note_store.add(observation)
        resurfaced = note_store.relevant("eval-kit", "fixture-site", "Check pages referencing cinder-mark.png before deleting")
        unrelated_notes = note_store.relevant("eval-kit", "fixture-site", "Review page title")
        record("M5", [item.id for item in resurfaced] == ["asset-observation"] and not unrelated_notes,
               "observation did not resurface only on a relevant task", "note_loop_behavior")

        delete_check = check_consequences(kit, {"operation": "delete", "asset": "/assets/cinder-mark.png"}, resurfaced)
        benign_check = check_consequences(kit, {"operation": "read", "asset": "/assets/cinder-mark.png"}, resurfaced)
        record("M6", delete_check.decision == "ask" and delete_check.observation_ids == ["asset-observation"]
               and benign_check.decision == "allow" and not benign_check.observation_ids,
               "asset deletion did not ask with matching note or benign read was blocked", "consequence_behavior")

    malformed_rejected = bool(validate_kit(kit_from_dict(raw)))
    try:
        kit_from_dict({**raw, "schema_version": 999})
        malformed_rejected = False
    except KitError:
        malformed_rejected = True
    missing_source_rejected = False
    try:
        kit_from_dict({**raw, "claims": [{**claim, "source_ids": ["not-present"], "review": {}}]})
    except KitError as exc:
        missing_source_rejected = "unknown source" in str(exc) or "invalid kit" in str(exc)
    record("M7", malformed_rejected and missing_source_rejected, "malformed state or missing source did not remain an explicit error", "failure_handling")
    return outcomes


def _check_guard_receipt(suite: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    spec = suite.get("mechanics", {}).get("M8", {})
    case_id = spec.get("case") if isinstance(spec, dict) else None
    artifact = artifacts.get(case_id, {}).get("runtime") if case_id else None
    if not artifact:
        return {"id": "M8", "status": "unverified", "scope": "guarded_host_runtime", "issues": ["coordinator guard evidence and authorized-run receipt not supplied"]}
    evidence = artifact.get("guard_evidence")
    if not isinstance(evidence, dict):
        return {"id": "M8", "status": "unverified", "scope": "guarded_host_runtime", "issues": ["event labels alone do not prove clone state; structured guard_evidence is absent"]}
    required = ("clone_verified", "guards_preserved", "live_call_authorized", "verification_scope", "source_path", "sha256")
    missing = [field for field in required if not evidence.get(field)]
    if evidence.get("verification_scope") not in {"runtime-observed", "configuration-inheritance-and-live-call"}:
        missing.append("configuration-inheritance and observed live-call verification scope")
    if missing:
        return {"id": "M8", "status": "unverified", "scope": "guarded_host_runtime", "issues": ["missing or insufficient structured guard evidence: " + ", ".join(missing)]}
    return {"id": "M8", "status": "pass", "scope": "guarded_host_runtime", "issues": []}


def _case_results(suite: dict[str, Any], artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for case in suite.get("cases", []):
        case_id = case["id"]
        arms = {}
        for arm in ARMS:
            artifact = artifacts.get(case_id, {}).get(arm)
            if artifact is None:
                arms[arm] = {"status": "unavailable", "reason": "No response artifact supplied; no model call was made."}
                continue
            scored = _heuristic_scores(case, artifact)
            arms[arm] = {
                "status": "artifact_loaded",
                "artifact": artifact.get("_artifact_path"),
                "model": artifact.get("model", "unknown"),
                "prompt_id": artifact.get("prompt_id", "unknown"),
                "task_id": artifact.get("task_id"),
                "package_version": artifact.get("package_version", "unknown"),
                "runtime": artifact.get("runtime", "unknown"),
                "tool_access": artifact.get("tool_access"),
                "costs": artifact.get("costs", {"status": "unknown"}),
                **scored,
            }
        present = [arms[arm] for arm in ARMS if arms[arm].get("status") == "artifact_loaded"]
        comparisons = {"status": "not_comparable", "issues": []}
        if len(present) == len(ARMS):
            models = {item.get("model") for item in present}
            tasks = {item.get("task_id") for item in present}
            toolsets = {json.dumps(item.get("tool_access", None), sort_keys=True) for item in present}
            issues = []
            if "unknown" in models or len(models) != 1:
                issues.append("arm model identifiers are missing or differ")
            if None in tasks or len(tasks) != 1:
                issues.append("arm task_id is missing or differs")
            if "null" in toolsets or len(toolsets) != 1:
                issues.append("arm tool_access is missing or differs")
            comparisons = {"status": "comparable" if not issues else "not_comparable", "issues": issues}
        results.append({"id": case_id, "visibility": case.get("visibility", "implementation_visible"), "arms": arms, "comparability": comparisons})
    return results


def run_suite(suite_path: str | Path, mechanics_only: bool = False, **kwargs: Any) -> dict[str, Any]:
    """Validate the suite, inspect supplied artifacts and emit an artifact report."""
    path = Path(suite_path).resolve()
    suite = _load_data(path)
    artifacts = load_artifacts(path)
    mechanics = _mechanics(suite, artifacts)
    report: dict[str, Any] = {
        "schema_version": 1,
        "suite_id": suite.get("id", path.stem),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_mode": "mechanics_only" if mechanics_only else "artifact_loader_only",
        "live_model_calls": 0,
        "mechanics": mechanics,
        "mechanics_summary": {state: sum(c["status"] == state for c in mechanics) for state in ("pass", "fail", "unverified")},
        "cases": [] if mechanics_only else _case_results(suite, artifacts),
        "comparison_status": "not_evaluated",
        "independent_review": "unavailable",
        "limitations": [
            "No Hermes/model subprocess is invoked by this runner.",
            "Phrase scoring is heuristic and is not semantic judgment or expert review.",
            "Fixed cases are implementation-visible; no blinded-result claim is made.",
            "Implementation visibility and host-wide isolation remain unverified by this loader.",
            "Costs are unknown unless supplied in an arm artifact.",
        ],
    }
    if not mechanics_only:
        arm_presence = [bool(artifacts) and all(case.get(arm) for case in artifacts.values()) for arm in ARMS]
        if all(arm_presence) and all(row["comparability"]["status"] == "comparable" for row in report["cases"]):
            report["comparison_status"] = "provisional_artifact_comparison"
        elif all(arm_presence):
            report["comparison_status"] = "artifacts_present_but_arms_not_comparable"
        else:
            report["comparison_status"] = "incomplete_artifacts"
    if kwargs:
        report["ignored_options"] = sorted(kwargs)
    return report
