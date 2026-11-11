from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from adapter_hermes.runtime import Runtime
from core.model import AdoptionRecord, Claim, Kit, KitError, Observation, WorkflowStep
from core.notes import NoteStore
from core.rules import check_consequences
from core.select import select_context


def fixture_kit(kit_id="test-kit", subject="synthetic-site"):
    kit = Kit(kit_id, "Synthetic runtime check", subject, fixture=True)
    kit.claims = [Claim("test-claim", "Synthetic runtime fixture", [], inference=True)]
    kit.workflow = [WorkflowStep("test-step", "Inspect redirect data", "Synthetic check", ["fixture"],
                                 ["synthetic"], "user decision", "Review evidence", ["test-claim"],
                                 ["redirect", "chain"])]
    kit.rules = [{"id": "asset-check", "kind": "asset-removal", "asset": "/assets/logo.svg"}]
    return kit


def note(kit_id="test-kit", subject="synthetic-site", note_id="test-note", expired=False):
    now = datetime.now(timezone.utc)
    return Observation(note_id, kit_id, subject, "Two synthetic pages reference /assets/logo.svg",
                       "Synthetic read result from pages /alpha and /beta", "synthetic-fixture-tool-output",
                       (now - timedelta(days=2)).isoformat(),
                       (now + timedelta(days=-1 if expired else 1)).isoformat(), ["/assets/logo.svg"])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runtime = Runtime(self.temp.name, fixture_harness=True)
        self.runtime.store.save(fixture_kit())

    def adopted(self):
        return self.runtime.store.adopt("test-kit", origin="fixture-harness", actor="test-harness",
                                        fixture_harness=True)

    def test_authenticated_local_command_route_and_foreign_sources(self):
        source = SimpleNamespace(platform=SimpleNamespace(value="local"), chat_type="dm",
                                 chat_id="local-session", user_id="synthetic-operator",
                                 is_bot=False, profile=None)
        result = json.loads(self.runtime.command("--json adopt test-kit", session_id="local-session",
                            session_key="agent:test:local:dm:local-session", platform="local", source=source))
        self.assertEqual(result["adoption"]["status"], "adopted")
        self.assertIn("synthetic-operator", result["adoption"]["actor"])
        source.chat_id = "foreign-session"
        result = json.loads(self.runtime.command("--json mount test-kit --subject synthetic-site",
                            session_id="local-session", session_key="route", platform="local", source=source))
        self.assertEqual(result["status"], "gap")

    def test_partial_proposals_preserve_captured_sources_and_lookup_windows(self):
        self.runtime.store.save(Kit("builder-kit", "Build a synthetic research workflow", "synthetic-site"))
        source = {"id":"synthetic-source","url":"https://example.test/source","title":"Synthetic source fixture",
                  "retrieved_at":"2026-11-10","excerpt":"x"*4000,"locator":"synthetic passage",
                  "retrieval_tool":"test-fixture","quality":"unknown"}
        saved = json.loads(self.runtime.tool("adeptory_source", {"kit_id":"builder-kit","data":source}))
        updated = json.loads(self.runtime.tool("adeptory_propose", {"data":{"id":"builder-kit","version":saved["version"],"goal":"Revised goal"}}))
        self.assertEqual(updated["goal"], "Revised goal")
        kit = self.runtime.store.load("builder-kit")
        self.assertEqual(kit.subject, "synthetic-site")
        self.assertEqual(kit.sources[0].excerpt, "x"*4000)
        window = json.loads(self.runtime.tool("adeptory_lookup", {"kit_id":"builder-kit","section":"sources","record_id":"synthetic-source"}))
        self.assertEqual(len(window["records"][0]["excerpt"]), 1500)
        self.assertEqual(window["records"][0]["excerpt_window"]["total_chars"], 4000)

    def test_builder_sessions_cannot_read_or_revise_evaluation_fixtures(self):
        self.assertEqual(json.loads(self.runtime.tool("adeptory_lookup", {"kit_id":"test-kit"}, "generator"))["status"], "gap")
        self.assertEqual(json.loads(self.runtime.tool("adeptory_lookup", {}, "generator")), [])
        result = self.runtime.tool("adeptory_propose", {"data":{"id":"test-kit","version":1,"goal":"Overwrite"}}, "generator")
        self.assertEqual(json.loads(result)["status"], "gap")
        self.mounted("task")
        self.assertEqual(json.loads(self.runtime.tool("adeptory_lookup", {"kit_id":"test-kit"}, "task"))["id"], "test-kit")

    def test_explicit_choice_deferral_keeps_thresholds_unassigned(self):
        kit = self.runtime.store.load("test-kit")
        kit.pending_choices = ["max_redirect_hops"]
        self.runtime.store.save(kit)
        source = SimpleNamespace(platform=SimpleNamespace(value="local"),chat_type="dm",chat_id="one",
                                 user_id="synthetic-user",is_bot=False,profile=None)
        result = json.loads(self.runtime.command("--json adopt test-kit --defer-choices", session_id="one",
                            session_key="local:dm:one",platform="local",source=source))
        self.assertEqual(result["adoption"]["choices"]["max_redirect_hops"]["status"], "deferred")
        self.assertEqual(result["pending_choices"], ["max_redirect_hops"])

    def mounted(self, session="one"):
        self.adopted()
        self.runtime.mount_fixture("test-kit", "synthetic-site", session)

    def test_proposed_and_stale_versions_select_nothing(self):
        kit = fixture_kit()
        self.assertEqual(select_context(kit, "redirect", kit.subject)["context"], "")
        kit.adoption = AdoptionRecord(status="adopted", version=1)
        kit.version = 2
        self.assertEqual(select_context(kit, "redirect", kit.subject)["context"], "")

    def test_selection_matches_subject_task_and_budget(self):
        kit = self.adopted()
        kit.adoption.choices = {"max_hops": 3}
        selected = select_context(kit, "inspect redirect", kit.subject)
        self.assertIn("test-step", selected["context"])
        self.assertIn('"max_hops": 3', selected["context"])
        self.assertEqual(selected["receipt"]["selected"][0]["id"], "test-step")
        self.assertEqual(select_context(kit, "cook dinner", kit.subject)["context"], "")
        self.assertEqual(select_context(kit, "redirect", "other-site")["context"], "")
        self.assertEqual(select_context(kit, "redirect", kit.subject, budget=1)["context"], "")

    def test_notes_expire_dismiss_and_scope(self):
        store = self.runtime.notes
        store.add(note())
        store.add(note(note_id="expired", expired=True))
        store.add(note(subject="other-site", note_id="other-site-note"))
        store.add(note(kit_id="other-kit", note_id="other-kit-note"))
        self.assertEqual([n.id for n in store.relevant("test-kit", "synthetic-site", "delete /assets/logo.svg")], ["test-note"])
        self.assertEqual(store.relevant("test-kit", "synthetic-site", "cook dinner"), [])
        store.dismiss("test-note")
        self.assertEqual(store.relevant("test-kit", "synthetic-site", "/assets/logo.svg"), [])

    def test_note_requires_expiry_evidence_and_unverified_status(self):
        observation = note()
        observation.status = "supported"
        with self.assertRaises(KitError):
            self.runtime.notes.add(observation)
        observation.status = "unverified"
        observation.expires_at = observation.at
        with self.assertRaises(KitError):
            self.runtime.notes.add(observation)

    def test_malformed_notes_surface_gap(self):
        root = Path(self.temp.name) / "notes"
        root.mkdir()
        (root / "broken.json").write_text("{bad", encoding="utf-8")
        with self.assertRaises(KitError):
            self.runtime.notes.relevant("test-kit", "synthetic-site", "redirect")

    def test_declared_asset_rule_and_read_countercase(self):
        kit = self.adopted()
        result = check_consequences(kit, {"operation": "delete", "asset": "/assets/logo.svg"}, [note()])
        self.assertEqual(result.decision, "ask")
        self.assertEqual(result.observation_ids, ["test-note"])
        self.assertIn("/alpha", result.message)
        self.assertEqual(check_consequences(kit, {"operation": "read", "asset": "/assets/logo.svg"}, [note()]).decision, "allow")
        self.assertEqual(check_consequences(kit, {"operation": "delete", "asset": "/assets/other.svg"}, []).decision, "allow")

    def test_tools_cannot_adopt_or_mount(self):
        for name, args in [("adeptory_build", {"operation": "adopt", "kit_id": "test-kit"}),
                           ("adeptory_propose", {"data": {"adoption": {"status": "adopted"}}}),
                           ("adeptory_lookup", {"kit_id": "test-kit", "origin": "verified-user-command"}),
                           ("adeptory_adopt", {"kit_id": "test-kit"})]:
            self.assertIn("error", json.loads(self.runtime.tool(name, args, "one")))
        self.assertEqual(self.runtime.store.load("test-kit").adoption.status, "proposed")
        self.assertNotIn("kit_id", self.runtime.sessions.get("one", {}))

    def test_command_transport_requires_local_interactive_context(self):
        for metadata in [{}, {"session_id": "one", "session_key": "one", "platform": "telegram"},
                         {"session_id": "one", "session_key": "one", "platform": "cli", "source": {"actor": "user"}},
                         {"session_id": "one", "session_key": "other", "platform": "cli"}]:
            self.assertIn("error", json.loads(self.runtime.command("--json adopt test-kit", **metadata)))
        self.assertEqual(self.runtime.store.load("test-kit").adoption.status, "proposed")

    def test_user_command_adopts_and_mounts_with_actor(self):
        source = SimpleNamespace(platform=SimpleNamespace(value="local"), chat_type="dm",
                                 chat_id="one", user_id="fixture-user", is_bot=False, profile=None)
        context = {"session_id": "one", "session_key": "local:dm:one", "platform": "local", "source": source}
        adopted = json.loads(self.runtime.command("--json adopt test-kit", **context))
        self.assertEqual(adopted["adoption"]["origin"], "verified-user-command")
        self.assertEqual(adopted["adoption"]["actor"], "local:fixture-user:one")
        mounted = json.loads(self.runtime.command("--json mount test-kit --subject synthetic-site", **context))
        self.assertEqual(mounted["mounted"], "test-kit")
        self.assertNotIn('test-step', self.runtime.pre_llm_call(session_id="two", user_message="redirect")['context'])
        self.assertIn("test-step", self.runtime.pre_llm_call(session_id="one", user_message="redirect")["context"])

    def test_fixture_mount_requires_opt_in_fixture_origin_and_matching_subject(self):
        self.adopted()
        with self.assertRaises(KitError):
            Runtime(self.temp.name).mount_fixture("test-kit", "synthetic-site", "one")
        with self.assertRaises(KitError):
            self.runtime.mount_fixture("test-kit", "other-subject", "one")
        self.runtime.store.save(Kit("real-kit", "Real brief", "synthetic-site"))
        self.runtime.store.adopt("real-kit", origin="verified-user-command", actor="test")
        with self.assertRaises(KitError):
            self.runtime.mount_fixture("real-kit", "synthetic-site", "one")

    def test_observation_capture_resurface_receipt_and_explicit_unverified_tool(self):
        self.mounted()
        payload = {"adeptory_observation": {"synthetic": True,
                   "text": "Synthetic page references /assets/logo.svg", "keywords": ["/assets/logo.svg"]}}
        self.runtime.post_tool_call(tool_name="read_file", args={"path": "synthetic.html"},
                                    result=json.dumps(payload), session_id="one")
        context = self.runtime.pre_llm_call(session_id="one", user_message="delete /assets/logo.svg")
        self.assertIn("Synthetic page", context["context"])
        why = json.loads(self.runtime.command("--json why", session_id="one"))
        self.assertEqual(why["notes"][0]["origin"], "synthetic-fixture-tool-output")
        self.assertEqual(why["notes"][0]["status"], "unverified")
        self.assertTrue(list((Path(self.temp.name) / "receipts").rglob("*.json")))
        unrelated = self.runtime.pre_llm_call(session_id="one", user_message="cook dinner")["context"]
        self.assertNotIn("test-step", unrelated)
        self.assertNotIn("Two synthetic pages", unrelated)
        result = json.loads(self.runtime.tool("adeptory_note", {"text": "Another lead",
            "evidence": "Tool output fragment", "keywords": ["another"]}, "one"))
        self.assertEqual(result["origin"], "model-tool-unverified")

    def test_ordinary_tool_output_requires_explicit_note(self):
        self.mounted()
        self.runtime.post_tool_call(tool_name="read_file", result="ordinary unstructured output", session_id="one")
        self.assertEqual(self.runtime.notes.relevant("test-kit", "synthetic-site", "ordinary"), [])

    def test_removal_hook_fires_for_exact_file_and_terminal_removal(self):
        self.mounted()
        self.runtime.notes.add(note())
        for tool_name, args in [("delete_file", {"path": "/assets/logo.svg"}),
                                ("terminal", {"command": "rm /assets/logo.svg"}),
                                ("terminal", {"command": "Remove-Item -LiteralPath /assets/logo.svg"})]:
            result = self.runtime.pre_tool_call(tool_name=tool_name, args=args, session_id="one")
            self.assertEqual(result["action"], "approve")
            self.assertIn("/alpha", result["message"])
        self.assertIsNone(self.runtime.pre_tool_call(tool_name="read_file", args={"path": "/assets/logo.svg"}, session_id="one"))
        self.assertIsNone(self.runtime.pre_tool_call(tool_name="terminal", args={"command": "cat /assets/logo.svg"}, session_id="one"))
        self.assertIsNone(self.runtime.pre_tool_call(tool_name="terminal", args={"command": "echo rm /assets/logo.svg"}, session_id="one"))

    def test_revision_reopens_context_and_note_tools_require_mount(self):
        self.mounted()
        kit = self.runtime.store.load("test-kit")
        kit.goal = "Revised synthetic goal"
        self.runtime.store.save(kit)
        result = self.runtime.pre_llm_call(session_id="one", user_message="redirect")
        self.assertIn("requires renewed adoption", result["context"])
        self.assertIn("error", json.loads(self.runtime.tool("adeptory_note", {"text": "lead", "evidence": "read"}, "two")))

    def test_lookup_serializes_list_and_rejects_paths(self):
        self.mounted("one")
        self.assertEqual(json.loads(self.runtime.tool("adeptory_lookup", {}, "one"))[0]["id"], "test-kit")
        self.assertIn("error", json.loads(self.runtime.tool("adeptory_lookup", {"kit_id": "../evals/answers"}, "one")))


if __name__ == "__main__":
    unittest.main()
