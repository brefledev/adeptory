"""Command journeys assert visible guidance alongside persisted decisions."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from adapter_hermes.runtime import Runtime
from core.model import Claim, Kit, SourceRecord, ToolCapability, WorkflowStep
from tests.test_build_completion import complete_synthetic_construction


class CommandWalkthrough(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.runtime = Runtime(self.directory.name)
        self.source = SimpleNamespace(platform=SimpleNamespace(value="local"), chat_type="dm",
                                      chat_id="chat", user_id="reader", is_bot=False, profile=None)
        self.context = dict(session_id="chat", session_key="local:dm:chat", platform="local", source=self.source)
        self.injected = []
        self.runtime.context = SimpleNamespace(inject_message=self.inject)

    def inject(self, message, **kwargs):
        self.injected.append((message, kwargs))
        return True

    def kit(self, choices=False):
        kit = Kit("research-kit", "Inspect a document collection", "Document collection")
        kit.sources = [SourceRecord("guide", "https://example.test/guide", "Collection guide",
                                    "2026-11-10", "A missing field represents an unknown value.",
                                    "Inventory section", "host-web")]
        kit.claims = [Claim("inventory", "Treat missing inventory fields as unknown.", ["guide"], 'supported',
            {'reviewer': 'synthetic-unit-reviewer', 'reason': 'The specification defines absent-field semantics.',
             'passage_checks': [{'source_id': 'guide', 'passage': kit.sources[0].excerpt,
                                'reason': 'The captured text explicitly defines missing fields.'}]})]
        kit.workflow = [WorkflowStep("inspect", "Inspect the collection inventory", "Establish the collection scope",
                                    ["Inventory report"], ["Ask for access when restricted"],
                                    "first", "Review before changes", ["inventory"], ["inventory"])]
        kit.capabilities = [ToolCapability("reader", "available", "Read the inventory", ["collection"],
                                           ["inventory"], ["read permission"], [], "Check a read result")]
        if choices:
            kit.pending_choices = ["Retention period"]
        self.runtime.builder.propose(kit.to_dict())
        complete_synthetic_construction(self.runtime.builder, kit.id)
        self.assertTrue(self.runtime.builder.status(kit.id)['ready_for_review'])
        return self.runtime.store.load(kit.id)

    def run_command(self, command, **overrides):
        context = {**self.context, **overrides}
        output = self.runtime.command(command, **context)
        self.assertFalse(output.lstrip().startswith(("{", "[")), output)
        self.assertTrue(output.strip())
        self.assertNotIn('"schema_version"', output)
        self.assertNotIn("A missing field represents an unknown value.", output)
        return output

    def test_whole_walkthrough_and_restart(self):
        welcome = self.run_command("")
        self.assertIn("library", welcome)
        self.assertIn("Describe the job", welcome)
        self.assertIn("who it serves", self.run_command("build"))
        self.kit()
        available = self.run_command("list")
        self.assertIn("Inspect a document collection", available)
        review = self.run_command("review research-kit")
        for visible in ["Collection guide", "https://example.test/guide", "Inspect the collection inventory",
                        "available"]:
            self.assertIn(visible, review)
        self.assertNotIn('/adeptory activate', review)
        self.assertNotIn('/adeptory choose', review)
        self.assertEqual(self.runtime.store.load("research-kit").adoption.status, "proposed")
        activated = self.run_command("activate research-kit")
        self.assertIn("Activated the specialist for Document collection", activated)
        self.assertIn("ordinary language", activated)
        kit = self.runtime.store.load("research-kit")
        self.assertEqual(kit.adoption.origin, "verified-user-command")
        self.assertEqual(kit.adoption.actor, "local:reader:chat")
        self.assertEqual(self.runtime.sessions["chat"]["subject"], "Document collection")
        self.assertIn("active in this chat", self.run_command(""))
        second = Kit("second-kit", "Review another collection", "Second collection")
        self.runtime.store.save(second)
        self.assertIn("second-kit", self.run_command("list"))
        adopted_at = kit.adoption.at
        self.run_command("activate research-kit")
        self.assertEqual(self.runtime.store.load(kit.id).adoption.at, adopted_at)
        self.runtime.pre_llm_call(session_id="chat", user_message="inventory")
        why = self.run_command("why")
        self.assertIn("historical", why)
        self.assertIn("inspect", why)
        resumed = Runtime(self.directory.name)
        self.assertIn("Describe the job", resumed.command("", **self.context))
        self.assertNotIn("kit_id", resumed.sessions.get("chat", {}))
        self.assertIn("Activated", resumed.command("activate research-kit", **self.context))

    def test_substantive_choices_require_explicit_deferral(self):
        self.kit(choices=True)
        self.assertIn("needs your decision", self.run_command("review research-kit"))
        self.assertIn("Retention period", self.run_command("activate research-kit"))
        self.assertEqual(self.runtime.store.load("research-kit").adoption.status, "proposed")
        self.assertNotIn("kit_id", self.runtime.sessions["chat"])
        result = self.run_command("activate research-kit --defer-choices")
        self.assertIn("deferred by you", result)
        kit = self.runtime.store.load("research-kit")
        self.assertEqual(kit.pending_choices, ["Retention period"])
        self.assertEqual(kit.adoption.choices["Retention period"],
                         {"status": "deferred", "origin": "explicit-user-command"})
        self.run_command("activate research-kit")
        self.assertEqual(self.runtime.store.load(kit.id).adoption.choices, kit.adoption.choices)

    def test_legacy_commands_subject_constraint_and_dismissal(self):
        self.kit()
        self.assertIn("Adopted", self.run_command("adopt research-kit"))
        self.assertNotIn("kit_id", self.runtime.sessions["chat"])
        rejected = self.run_command("mount research-kit --subject Other collection")
        self.assertIn("matching subject", rejected)
        self.assertNotIn("kit_id", self.runtime.sessions["chat"])
        mounted = self.run_command('mount research-kit --subject "Document collection"')
        self.assertIn("Mounted", mounted)
        self.assertIn("ordinary language", mounted)
        self.runtime.tool("adeptory_note", {"text": "Inventory may be incomplete", "evidence": "Read report",
                                           "keywords": ["inventory"]}, "chat")
        self.runtime.pre_llm_call(session_id="chat", user_message="inventory")
        why = self.run_command("why")
        self.assertIn("Unverified lead", why)
        note = next((Path(self.directory.name) / "notes").glob("*.json"))
        note_id = json.loads(note.read_text())["id"]
        self.assertIn("Dismissed", self.run_command("dismiss " + note_id))
        self.assertEqual(json.loads(note.read_text())["status"], "dismissed")

    def test_untrusted_transport_has_no_mutations(self):
        self.kit()
        for operation in ["activate research-kit", "activate research-kit --defer-choices", "adopt research-kit",
                          'mount research-kit --subject "Document collection"', "dismiss lead"]:
            for overrides in [{"source": None}, {"source": {}}, {"session_id": None},
                              {"session_key": None}, {"platform": "telegram"}]:
                with self.subTest(operation=operation, overrides=overrides):
                    output = self.run_command(operation, **overrides)
                    self.assertIn("attention", output)
                    self.assertEqual(self.runtime.store.load("research-kit").adoption.status, "proposed")
                    self.assertFalse(any("kit_id" in state for state in self.runtime.sessions.values()))
        for name, value in [("chat_id", "foreign"), ("profile", "foreign"), ("is_bot", True)]:
            old = getattr(self.source, name)
            setattr(self.source, name, value)
            self.assertIn("verified session", self.run_command("activate research-kit"))
            setattr(self.source, name, old)

    def test_readable_invalid_commands_and_why_failures(self):
        for command in ['review "unterminated', "review", "activate", "unknown", "why extra",
                        "review missing-kit", "review ../foreign", "dismiss missing-note"]:
            with self.subTest(command=command):
                self.assertIn("attention", self.run_command(command))
        self.assertIn("yet to select", self.run_command("why"))
        self.assertIn("host session ID", self.run_command("why", session_id=None))
        self.assertIn("arguments must be text", self.run_command(None))
        self.kit()
        self.run_command("activate research-kit")
        self.runtime.pre_llm_call(session_id="chat", user_message="inventory")
        changed = self.runtime.store.load("research-kit")
        changed.goal = "Revised inventory inspection"
        self.runtime.store.save(changed)
        self.assertIn("needs your review", self.run_command(""))
        self.runtime.pre_llm_call(session_id="chat", user_message="inventory")
        self.assertIn("renewed adoption", self.run_command("why"))
        path = Path(self.directory.name) / "kits" / "research-kit" / "kit.json"
        path.write_text("{bad", encoding="utf-8")
        self.assertIn("could not be read", self.run_command("activate research-kit"))

    def test_build_description_preserves_quotes_newlines_and_restart(self):
        goal = 'Help my service business.\nExplain "refund rules" plainly. Keep my unfinished quote: "'
        raw = 'Build ' + goal
        output = self.run_command(raw)
        self.assertIn('Welcome to Adeptory', output)
        self.assertIn('starting your specialist', output)
        self.assertNotIn('Continue', output)
        self.assertEqual(self.injected, [('Use Adeptory to build this specialist from my request:\n\n' + goal,
                                         {'session_key': 'local:dm:chat'})])
        records = list((Path(self.directory.name) / 'requests').glob('*.json'))
        self.assertEqual(len(records), 1)
        saved = json.loads(records[0].read_text(encoding='utf8'))
        self.assertEqual(saved['raw_args'], raw)
        self.assertEqual(saved['goal'], goal)
        resumed = Runtime(self.directory.name)
        context = resumed.pre_llm_call(session_id='chat', user_message='Continue')['context']
        self.assertIn(json.dumps(goal, ensure_ascii=False), context)
        self.assertNotIn(goal.splitlines()[0], resumed.pre_llm_call(
            session_id='different-chat', user_message='Continue')['context'])

    def test_rejected_command_retains_exact_original(self):
        raw = 'review "Unfinished argument\nwith the complete description'
        output = self.run_command(raw)
        self.assertIn('Your complete command was saved at', output)
        path = next((Path(self.directory.name) / 'requests').glob('*.json'))
        self.assertEqual(json.loads(path.read_text(encoding='utf8'))['raw_args'], raw)

    def test_command_names_accept_capitals(self):
        self.assertIn('who it serves', self.run_command('BUILD'))
        self.assertIn('starting your specialist', self.run_command('bUiLd Write a guide'))

    def test_storage_failure_returns_original_for_recovery(self):
        raw = 'Build My complete request with an unfinished "quote'
        with patch('adapter_hermes.runtime.atomic_json', side_effect=OSError('Disk full')):
            output = self.run_command(raw)
        self.assertIn(raw, output)
        self.assertIn('storage is repaired', output)
        self.assertNotIn('was saved at', output)

    def test_model_cannot_activate_and_fixtures_stay_hidden(self):
        self.kit()
        result = json.loads(self.runtime.tool("adeptory_activate", {"kit_id": "research-kit"}, "model-chat"))
        self.assertIn("error", result)
        self.assertEqual(self.runtime.store.load("research-kit").adoption.status, "proposed")
        fixture = Kit("isolated-fixture", "Private evaluation case", "Evaluation subject", fixture=True)
        self.runtime.store.save(fixture)
        self.assertNotIn("isolated-fixture", self.run_command("list"))
        self.assertNotIn("isolated-fixture", self.runtime.tool("adeptory_lookup", {}, "model-chat"))

    def test_json_is_explicit_and_model_tools_stay_structured(self):
        self.kit()
        self.assertEqual(json.loads(self.runtime.command("review research-kit --json"))["id"], "research-kit")
        self.assertEqual(json.loads(self.runtime.tool("adeptory_lookup", {"kit_id": "research-kit"}))["id"], "research-kit")
        self.assertEqual(json.loads(self.runtime.command("activate research-kit --json"))["status"], "gap")


if __name__ == "__main__":
    unittest.main()
