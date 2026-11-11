import tempfile
from types import SimpleNamespace
import unittest

from adapter_hermes.runtime import Runtime
from core.model import ToolCapability
from tests.test_build_completion import complete_synthetic_construction
from tests.unit.test_provenance import researched_kit


class GuidedConversationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.runtime = Runtime(directory.name)
        source = SimpleNamespace(platform=SimpleNamespace(value="local"), chat_type="dm",
                                 chat_id="guided", user_id="reader", is_bot=False, profile=None)
        self.context = dict(session_id="guided", session_key="local:dm:guided", platform="local", source=source)
        kit = researched_kit()
        kit.id, kit.goal, kit.subject, kit.fixture = 'guide-kit', 'Review a collection', 'Sample collection', False
        kit.scope = {'delivery': 'current-chat'}
        kit.capabilities = [ToolCapability('reader', 'available', 'Read the synthetic specification',
            ['synthetic specification'], ['preserved text'], ['temporary test directory'], [],
            'Read the synthetic specification and compare its text.')]
        kit.pending_choices = ["retention_days: How long should observations be retained?"]
        self.runtime.builder.propose(kit.to_dict())
        complete_synthetic_construction(self.runtime.builder, kit.id)
        self.assertTrue(self.runtime.builder.status(kit.id)['ready_for_review'])

    def test_welcome_continues_as_guided_chat_before_activation(self):
        self.runtime.command("", **self.context)
        context = self.runtime.pre_llm_call(session_id="guided", user_message="Help me get started")
        self.assertIsNotNone(context)
        self.assertIn("one step at a time", context["context"])
        self.assertIn("adeptory_library", context["context"])
        self.assertEqual(self.runtime.store.load("guide-kit").adoption.status, "proposed")

    def test_ordinary_language_adeptory_request_loads_guide(self):
        context = self.runtime.pre_llm_call(session_id="fresh", user_message="Help me start Adeptory")
        self.assertIsNotNone(context)
        self.assertIn("ordinary language", context["context"])
        self.assertNotIn('Current construction progress', self.runtime.pre_llm_call(
            session_id="unrelated", user_message="Write a poem")['context'])

    def test_choose_value_without_user_json_then_activate(self):
        self.runtime.command("review guide-kit", **self.context)
        result = self.runtime.command("choose guide-kit 1 14", **self.context)
        self.assertIn("Recorded", result)
        self.assertFalse(result.lstrip().startswith("{"))
        self.assertEqual(self.runtime.store.load("guide-kit").adoption.status, "proposed")
        result = self.runtime.command("activate guide-kit", **self.context)
        self.assertIn("Activated", result)
        kit = self.runtime.store.load("guide-kit")
        self.assertEqual(kit.adoption.choices[kit.pending_choices[0]], 14)

    def test_stale_review_cannot_record_wrong_choice(self):
        self.runtime.command("review guide-kit", **self.context)
        kit = self.runtime.store.load("guide-kit")
        kit.goal = "A changed collection review"
        self.runtime.store.save(kit)
        result = self.runtime.command("choose guide-kit 1 14", **self.context)
        self.assertIn("review", result.lower())
        self.assertNotIn("Recorded", result)

    def test_choose_requires_trusted_user_and_finite_value(self):
        self.runtime.command("review guide-kit", **self.context)
        for value in ("NaN", "null", "{}", "[]"):
            self.assertNotIn("Recorded", self.runtime.command("choose guide-kit 1 " + value, **self.context))
        untrusted = {**self.context, "source": None}
        self.assertIn("direct command", self.runtime.command("choose guide-kit 1 14", **untrusted))
        self.assertEqual(self.runtime.sessions["guided"].get("decisions", {}), {})

    def test_fresh_profile_starts_with_a_plain_language_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Runtime(directory)
            welcome = runtime.command("", **self.context)
            self.assertIn("Describe the job", welcome)
            self.assertNotIn("seo-redirect-demo", welcome)
            self.assertFalse(welcome.lstrip().startswith("{"))
            self.assertEqual(runtime.store.list(), [])

    def test_current_specialist_review_choice_and_activation_need_no_internal_id(self):
        self.runtime.tool('adeptory_lookup', {'kit_id': 'guide-kit'}, 'guided')
        review = self.runtime.command('review', **self.context)
        self.assertIn('Your specialist is ready.', review)
        self.assertNotIn('/adeptory review guide-kit', review)
        self.assertIn('Retention days', review)
        self.assertNotIn('/adeptory activate', review)
        self.assertNotIn('/adeptory choose', review)
        self.assertIn('Recorded', self.runtime.command('choose 1 --defer', **self.context))
        self.assertIn('Activated', self.runtime.command('activate --defer-choices', **self.context))
        kit = self.runtime.store.load('guide-kit')
        self.assertEqual(kit.adoption.origin, 'verified-user-command')
        self.assertEqual(kit.adoption.choices[kit.pending_choices[0]]['status'], 'deferred')


if __name__ == "__main__":
    unittest.main()
