import unittest
from hashlib import sha256

from core.kitstore import kit_from_dict
from core.model import Kit, SourceRecord, Claim, WorkflowStep, KitError
from core.provenance import attribution_receipt, review_errors


def researched_kit():
    source = SourceRecord("source-one", "https://example.org/spec", "Example primary source",
        "2026-11-10T20:00:00+00:00", "A missing field represents an unknown value.",
        "Data semantics, paragraph 1", "host-web-retrieve", limitations=["Synthetic unit evidence"])
    claim = Claim("claim-one", "Treat missing fields as unknown.", [source.id], "supported",
        {"reviewer": "synthetic-test-reviewer", "reason": "The passage defines missing field semantics.",
         "passage_checks": [{"source_id": source.id, "passage": source.excerpt,
                             "reason": "Directly states the missing-field definition."}]})
    step = WorkflowStep("step-one", "Inspect missing values.", "Preserve uncertainty.",
        ["Capture the input field"], ["Apply any documented contract"], "User-selected ordering",
        "Changes task priority", [claim.id], ["missing"])
    return Kit("research", "Research a bounded task", "synthetic", fixture=True,
               sources=[source], claims=[claim], workflow=[step])


class ProvenanceTests(unittest.TestCase):
    def test_capture_and_semantic_review_are_separate(self):
        kit = researched_kit()
        receipt = attribution_receipt(kit.sources[0])
        self.assertEqual(receipt["status"], "captured")
        self.assertEqual(receipt["excerpt_sha256"], sha256(kit.sources[0].excerpt.encode()).hexdigest())
        self.assertEqual(kit_from_dict(kit.to_dict()).adoption.status, "proposed")

    def test_invalid_receipt_and_claim_link_fail(self):
        kit = researched_kit()
        kit.sources[0].receipt = {"url": "https://other.example/source"}
        with self.assertRaisesRegex(KitError, "receipt url differs"):
            kit_from_dict(kit.to_dict())
        kit = researched_kit()
        kit.claims[0].source_ids = ["absent"]
        with self.assertRaisesRegex(KitError, "unknown source"):
            kit_from_dict(kit.to_dict())

    def test_claim_support_requires_identified_passage_review(self):
        for field, value, error in (("reviewer", "", "reviewer"), ("reason", "", "reason"),
                                    ("passage_checks", [], "passage_checks")):
            kit = researched_kit()
            kit.claims[0].review[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(KitError, error):
                kit_from_dict(kit.to_dict())
        kit = researched_kit()
        kit.claims[0].review["passage_checks"][0]["passage"] = "An invented quotation"
        with self.assertRaisesRegex(KitError, "captured excerpt"):
            kit_from_dict(kit.to_dict())

    def test_inference_and_unknown_support_remain_visible(self):
        kit = researched_kit()
        kit.claims[0] = Claim("claim-one", "A tentative inference", [], inference=True)
        parsed = kit_from_dict(kit.to_dict())
        self.assertTrue(parsed.claims[0].inference)
        self.assertEqual(parsed.claims[0].support, "unverified")

    def test_jurisdiction_date_and_limits_survive_roundtrip(self):
        kit = researched_kit()
        kit.sources[0].jurisdiction = "US federal"
        kit.sources[0].effective_or_published = "2026-10-01"
        parsed = kit_from_dict(kit.to_dict())
        self.assertEqual(parsed.sources[0].jurisdiction, "US federal")
        self.assertEqual(parsed.sources[0].effective_or_published, "2026-10-01")
        self.assertTrue(parsed.sources[0].limitations)

    def test_bad_source_url_timestamp_and_hash_are_rejected(self):
        for field, value, error in (("url", "file:///private", "absolute HTTP"),
                                    ("url", "https://[broken", "absolute HTTP"),
                                    ("retrieved_at", "yesterday", "ISO"),
                                    ("receipt", {"excerpt_sha256": "fake"}, "sha256")):
            kit = researched_kit()
            setattr(kit.sources[0], field, value)
            with self.subTest(field=field), self.assertRaisesRegex(KitError, error):
                kit_from_dict(kit.to_dict())


if __name__ == "__main__":
    unittest.main()
