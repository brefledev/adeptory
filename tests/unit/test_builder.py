from pathlib import Path
import tempfile
import unittest

from core.builder import Builder, read_proposal
from core.kitstore import KitStore
from core.model import KitError
from tests.unit.test_provenance import researched_kit
from tests.test_build_completion import complete_synthetic_construction


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = KitStore(self.root / "data")
        self.builder = Builder(self.store)

    def test_novice_intake_is_resumable_and_generic(self):
        kit = self.builder.start("Help investigate a bounded problem", "example.org", {"audience": "novice"})
        status = Builder(KitStore(self.root / "data")).status(kit.id)
        self.assertEqual(status["stage"], "building")
        self.assertEqual(status["scope"]["audience"], "novice")
        self.assertFalse(status["ready_for_review"])
        self.assertFalse(status['ready_for_review'])
        self.assertEqual(status['construction']['library']['documents'], 0)

    def test_full_proposal_review_and_revision_loop(self):
        kit = researched_kit()
        kit.sources.append(type(kit.sources[0])("source-two", "https://example.org/other", "Second source",
            "2026-11-10", "Confirm values from the recorded contract.", "paragraph 1", "host-retrieve"))
        data = kit.to_dict()
        data["capabilities"] = [
            {"id": "local-read", "readiness": "available", "why": "Inspect authorized input",
             "inputs": ["user file"], "outputs": ["observed fields"], "access": ["read-only user scope"],
             "setup": [], "verification": "Recorded a synthetic file read in the isolated test"},
            {"id": "connector", "readiness": "missing", "why": "Supply more evidence",
             "inputs": ["chosen dataset"], "outputs": ["data rows"], "access": ["user authorization"],
             "setup": ["Confirm vendor access", "Review connector", "Run a read-only smoke test"],
             "verification": "List one authorized dataset and inspect its schema"}]
        data["pending_choices"] = ["priority_threshold"]
        kit = self.builder.propose(data)
        self.assertFalse(self.builder.status(kit.id)['ready_for_review'])
        complete_synthetic_construction(self.builder, kit.id)
        kit = self.store.load(kit.id)
        self.assertEqual(self.builder.status(kit.id)["stage"], "needs choice")
        self.assertTrue(self.builder.status(kit.id)["ready_for_review"])
        adopted = self.store.adopt(kit.id, origin="fixture-harness", actor="synthetic-harness",
                                  choices={"priority_threshold": "qualitative ordering"}, fixture_harness=True)
        self.assertEqual(self.builder.status(kit.id)["stage"], "adopted")
        revised = adopted.to_dict()
        revised["adoption"] = {"status": "proposed", "origin": "none"}
        revised["pending_choices"].append("escalation_boundary")
        new = self.builder.propose(revised)
        self.assertEqual(new.version, adopted.version + 1)
        self.assertEqual(new.adoption.status, "proposed")
        with self.assertRaisesRegex(KitError, "stale"):
            self.builder.propose(revised)

    def test_proposals_cannot_adopt(self):
        data = researched_kit().to_dict()
        data["adoption"] = {"status": "adopted", "origin": "verified-user-command"}
        with self.assertRaisesRegex(KitError, "model proposals"):
            self.builder.propose(data)

    def test_source_update_reopens_claim_review_and_adoption(self):
        kit = self.builder.propose(researched_kit().to_dict())
        self.store.adopt(kit.id, origin="fixture-harness", actor="synthetic-harness", fixture_harness=True)
        source = kit.to_dict()["sources"][0]
        source["excerpt"] = "Revised source passage requiring a fresh support review."
        result = self.builder.source(kit.id, source)
        self.assertEqual(result.version, 2)
        self.assertEqual(result.claims[0].support, "unverified")
        self.assertEqual(result.claims[0].review, {})
        self.assertEqual(result.adoption.status, "proposed")
        unchanged = self.builder.source(kit.id, source)
        self.assertEqual(unchanged.version, 2)

    def test_generator_import_excludes_evaluation_paths_and_escape(self):
        (self.root / "evals").mkdir()
        (self.root / "evals/case.json").write_text("{}")
        with self.assertRaisesRegex(KitError, "excluded"):
            read_proposal(self.root / "evals/case.json", allowed_root=self.root)
        with self.assertRaisesRegex(KitError, "workspace"):
            read_proposal(self.root.parent / "other.json", allowed_root=self.root)
        (self.root / "kit.json").write_text('{"goal":"authorized input"}')
        self.assertEqual(read_proposal(self.root / "kit.json", allowed_root=self.root)["goal"], "authorized input")

    def test_maps_reject_unlinked_meanings(self):
        data = researched_kit().to_dict()
        data["data_map"] = [{"key": "report.field", "meaning": "Meaning", "mechanism": "Report field",
                             "exceptions": [], "evidence": ["absent-source"], "decision": "Preserve uncertainty",
                             "priority": "User choice", "consequence": "Affects ordering"}]
        with self.assertRaisesRegex(KitError, "unknown evidence"):
            self.builder.propose(data)
        data["data_map"][0]["evidence"] = ["source-one", "step-one"]
        kit = self.builder.propose(data)
        self.assertEqual(kit.data_map[0]["meaning"], "Meaning")


if __name__ == "__main__":
    unittest.main()
