import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from core.kitstore import KitStore, kit_from_dict, validate_kit
from core.model import Kit, KitError, AdoptionRecord


class KitStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = KitStore(self.root / "data")
        self.kit = self.store.save(Kit("example", "Research a bounded task", "example.org"))

    def test_round_trip_and_listing(self):
        self.assertEqual(self.store.load("example"), self.kit)
        self.assertEqual([kit.id for kit in self.store.list()], ["example"])

    def test_export_validates_directory_yaml_and_json_through_cli(self):
        from core.cli import main
        exported = self.store.export("example", self.root / "exported")
        for path in (exported, exported / "kit.yaml", self.root / "data/kits/example/kit.json"):
            with self.subTest(path=path), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["validate", "--kit", str(path)]), 0)
                self.assertEqual(json.loads(output.getvalue())["kit_id"], "example")

    def test_unknown_fields_and_versions_have_clear_errors(self):
        for field, value, message in (("surprise", True, "unsupported"),
                                       ("schema_version", 8, "schema_version"),
                                       ("version", True, "positive integer")):
            with self.subTest(field=field):
                data = self.kit.to_dict()
                data[field] = value
                with self.assertRaisesRegex(KitError, message):
                    kit_from_dict(data)
        data = self.kit.to_dict()
        del data["goal"]
        with self.assertRaisesRegex(KitError, "missing fields: goal"):
            kit_from_dict(data)

    def test_revisions_preserve_history_and_reopen_adoption(self):
        adopted = self.store.adopt("example", origin="verified-user-command", actor="test-user")
        adopted.goal = "Research a revised bounded task"
        revised = self.store.save(adopted)
        self.assertEqual(revised.version, 2)
        self.assertEqual(revised.adoption.status, "proposed")
        historical = json.loads((self.root / "data/kits/example/history/1.json").read_text())
        self.assertEqual(historical["adoption"]["status"], "adopted")
        self.assertEqual(historical["goal"], self.kit.goal)
        self.assertEqual(self.store.save(revised).version, 2)
        with self.assertRaisesRegex(KitError, "stale"):
            self.store.save(self.kit)

    def test_model_and_fixture_adoption_boundaries(self):
        for origin, harness in (("model-tool", False), ("fixture-harness", False), ("none", False)):
            with self.subTest(origin=origin):
                with self.assertRaises(KitError):
                    self.store.adopt("example", origin=origin, actor="model", fixture_harness=harness)
        with self.assertRaisesRegex(KitError, "fixture:true"):
            self.store.adopt("example", origin="fixture-harness", actor="synthetic", fixture_harness=True)
        fixture = self.store.save(Kit("fixture", "Synthetic test", "synthetic", fixture=True))
        adopted = self.store.adopt(fixture.id, origin="fixture-harness", actor="synthetic-harness", fixture_harness=True)
        self.assertEqual(adopted.adoption.origin, "fixture-harness")
        fixture.fixture = False
        with self.assertRaisesRegex(KitError, "immutable"):
            self.store.save(fixture)

    def test_pending_thresholds_require_explicit_choices(self):
        self.kit.pending_choices = ["review_threshold"]
        self.store.save(self.kit)
        with self.assertRaisesRegex(KitError, "review_threshold"):
            self.store.adopt("example", origin="verified-user-command", actor="user")
        adopted = self.store.adopt("example", origin="verified-user-command", actor="user", choices={"review_threshold": 0})
        self.assertEqual(adopted.adoption.choices["review_threshold"], 0)

    def test_save_cannot_self_adopt(self):
        self.kit.adoption = AdoptionRecord("adopted", "verified-user-command", "forged", "2026-11-10", 1)
        with self.assertRaisesRegex(KitError, "cannot change adoption"):
            self.store.save(self.kit)
        self.assertEqual(self.store.load("example").adoption.status, "proposed")

    def test_ids_and_escape_paths_are_rejected(self):
        for kit_id in ("../outside", "C:/outside", "UPPER", "", "a/b", "a\\b", "a" * 65, "con", "com1"):
            with self.subTest(kit_id=kit_id):
                with self.assertRaises(KitError):
                    self.store.load(kit_id)
        try:
            (self.root / "data/kits/escape").symlink_to(self.root, target_is_directory=True)
        except OSError:
            return
        with self.assertRaisesRegex(KitError, "escapes"):
            self.store.save(Kit("escape", "test", "subject"))

    def test_export_is_portable_and_preserves_history(self):
        import yaml
        self.kit.goal = "Revised research task"
        self.store.save(self.kit)
        path = self.store.export("example", self.root / "export")
        for name in ("kit.yaml", "charter.md", "workflows/records.json", "maps/records.json",
                     "tools/records.json", "sources/records.json", "sources/claims.json",
                     "decisions/records.json", "tests/README.md", "history/1.json"):
            self.assertTrue((path / name).is_file(), name)
        reloaded = kit_from_dict(yaml.safe_load((path / "kit.yaml").read_text()))
        self.assertEqual(reloaded, self.store.load("example"))
        with self.assertRaisesRegex(KitError, "empty"):
            self.store.export("example", path)
        with self.assertRaisesRegex(KitError, "separate"):
            self.store.export("example", self.root / "data/export")

    def test_malformed_nested_records_are_explicit_errors(self):
        for name, value in (("sources", [3]), ("claims", {}), ("adoption", "adopted"),
                            ("scope", []), ("data_map", [{"key": "field"}])):
            data = self.kit.to_dict()
            data[name] = value
            with self.subTest(name=name), self.assertRaises(KitError):
                kit_from_dict(data)

    def test_malformed_disk_state_is_rejected(self):
        path = self.root / "data/kits/example/kit.json"
        path.write_text("{broken", encoding="utf-8")
        with self.assertRaisesRegex(KitError, "cannot load kit"):
            self.store.load("example")


if __name__ == "__main__":
    unittest.main()
