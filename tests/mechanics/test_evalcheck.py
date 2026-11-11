import json
import tempfile
import unittest
from pathlib import Path

from core.evalcheck import load_artifacts, run_suite


ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "evals" / "heldout-suite.json"


class EvalcheckTests(unittest.TestCase):
    def test_mechanics_only_never_compares_model_arms(self):
        report = run_suite(SUITE, mechanics_only=True)
        self.assertEqual(report["execution_mode"], "mechanics_only")
        self.assertEqual(report["live_model_calls"], 0)
        self.assertEqual(report["cases"], [])
        self.assertEqual(report["comparison_status"], "not_evaluated")

    def test_absent_arm_artifacts_remain_unavailable(self):
        report = run_suite(SUITE)
        self.assertEqual(report["comparison_status"], "incomplete_artifacts")
        self.assertEqual(report["live_model_calls"], 0)
        self.assertTrue(all(row["arms"]["base"]["status"] == "unavailable" for row in report["cases"]))

    def test_loader_only_reads_expected_artifact_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "artifacts" / "D1").mkdir(parents=True)
            (folder / "artifacts" / "D1" / "base.json").write_text(json.dumps({"response": "test", "model": "model-x"}), encoding="utf-8")
            suite = {"schema_version": 1, "id": "loader-test", "cases": [{"id": "D1"}]}
            path = folder / "suite.json"
            path.write_text(json.dumps(suite), encoding="utf-8")
            loaded = load_artifacts(path)
            self.assertEqual(loaded["D1"]["base"]["response"], "test")
            self.assertNotIn("static", loaded["D1"])

    def test_core_mechanics_run_and_host_guard_remains_unverified(self):
        report = run_suite(SUITE, mechanics_only=True)
        indexed = {item["id"]: item for item in report["mechanics"]}
        for check_id in ("M1", "M2", "M3", "M4", "M5", "M6", "M7"):
            self.assertEqual(indexed[check_id]["status"], "pass", indexed[check_id])
        self.assertEqual(indexed["M8"]["status"], "unverified")

    def test_event_labels_alone_do_not_pass_guard_check(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "artifacts" / "D3").mkdir(parents=True)
            (folder / "artifacts" / "D3" / "runtime.json").write_text(json.dumps({
                "events": ["scratch_clone_verified", "guards_preserved", "live_call_authorized"]
            }), encoding="utf-8")
            path = folder / "suite.json"
            path.write_text(json.dumps({"id": "guard-test", "mechanics": {"M8": {"case": "D3"}}, "cases": []}), encoding="utf-8")
            indexed = {item["id"]: item for item in run_suite(path, mechanics_only=True)["mechanics"]}
            self.assertEqual(indexed["M8"]["status"], "unverified")

    def test_heuristic_scores_never_claim_semantic_review(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            artifact_dir = folder / "artifacts" / "D1"
            artifact_dir.mkdir(parents=True)
            suite = {
                "id": "phrase-test", "cases": [{"id": "D1", "dimensions": [
                    {"id": "priority", "pass_terms": ["investigate the chain"], "partial_terms": []}
                ]}]
            }
            (folder / "suite.json").write_text(json.dumps(suite), encoding="utf-8")
            (artifact_dir / "base.json").write_text(json.dumps({"response": "Investigate the chain first.", "model": "test-model"}), encoding="utf-8")
            report = run_suite(folder / "suite.json")
            scored = report["cases"][0]["arms"]["base"]
            self.assertEqual(scored["scoring_status"], "provisional_phrase_heuristic")
            self.assertIn("semantic support unreviewed", scored["reasons"]["priority"])


if __name__ == "__main__":
    unittest.main()
