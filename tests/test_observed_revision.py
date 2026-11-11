"""Verification receipts retain the package exercised when the host tool started."""
import json
from pathlib import Path
import tempfile
import unittest

from adapter_hermes.construction import Construction
from core.builder import Builder
from core.kitstore import KitStore
from tests.unit.test_provenance import researched_kit


class ObservedRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.builder = Builder(KitStore(self.root / 'kits'))
        self.kit = self.builder.propose(researched_kit().to_dict())
        self.session = 'synthetic-revision-session'
        self.states = {}
        self.control = Construction(self.root, self.builder,
                                    lambda sid: self.states.setdefault(sid, {}))
        self.control.start(self.session, self.kit.id)
        self.sync_tasks()
        self.args = {'command': 'hermes --profile synthetic chat -q "Check the toy CSV."'}

    def sync_tasks(self):
        items = self.control.progress(self.session, self.kit.id)['native_tasks']['todos']
        self.states[self.session]['native_task_signature'] = items

    def package_state(self):
        return {'version': self.builder.store.load(self.kit.id).version,
                'library_fingerprint': self.builder.library.fingerprint(self.kit.id)}

    def observe(self, tool='terminal', args=None, call_id=None):
        self.control.post_tool(tool, self.args if args is None else args,
                               {'exit_code': 0, 'output': 'Checked the synthetic CSV.'},
                               self.session, tool_call_id=call_id, status='success')
        ident = self.states[self.session]['observed_tools'][-1]['receipt_id']
        return json.loads((self.root / 'build-observations' / (ident + '.json')).read_text())

    def change_revision(self):
        kit = self.builder.store.load(self.kit.id)
        kit.goal += ' Include the next synthetic requirement.'
        self.builder.store.save(kit)

    def change_library(self):
        self.builder.library.document(self.kit.id, {
            'id': 'new-spec', 'url': 'https://example.com/spec', 'title': 'Synthetic CSV spec',
            'text': 'A missing amount is unknown.', 'role': 'technical',
            'authority': 'Synthetic specification', 'retrieved_at': '2026-11-11T00:00:00Z',
            'retrieval_tool': 'synthetic-fixture'})

    def test_receipt_keeps_pre_invocation_revision_and_fingerprint(self):
        before = self.package_state()
        self.assertIsNone(self.control.pre_tool('terminal', self.args, self.session, 'call-1'))
        self.change_revision()
        self.change_library()
        self.assertNotEqual(before, self.package_state())
        receipt = self.observe(call_id='call-1')
        self.assertEqual(receipt['package_state'], before)
        self.assertEqual(receipt['kit_id'], self.kit.id)
        self.assertTrue(receipt['invoked_at'])
        self.assertEqual(self.states[self.session]['pending_observations'], [])

    def test_next_invocation_captures_current_package(self):
        self.change_revision()
        self.change_library()
        before = self.package_state()
        self.control.pre_tool('process', {'action': 'poll', 'session_id': 'toy-process'}, self.session, 'call-2')
        receipt = self.observe(tool='process', args={'action': 'poll', 'session_id': 'toy-process'}, call_id='call-2')
        self.assertEqual(receipt['package_state'], before)

    def test_pending_invocation_survives_session_reload(self):
        before = self.package_state()
        self.control.pre_tool('terminal', self.args, self.session, 'reload-call')
        self.change_revision()
        restored = self.control.read(self.session)
        self.states = {self.session: restored}
        self.control = Construction(self.root, self.builder,
                                    lambda sid: self.states.setdefault(sid, {}))
        receipt = self.observe(call_id='reload-call')
        self.assertEqual(receipt['package_state'], before)
        self.assertEqual(self.control.read(self.session)['pending_observations'], [])

    def test_missing_call_ids_pair_by_canonical_tool_and_arguments(self):
        args = {'command': self.args['command'], 'timeout': 30}
        self.control.pre_tool('terminal', args, self.session)
        before = self.package_state()
        self.change_revision()
        receipt = self.observe(args={'timeout': 30, 'command': self.args['command']})
        self.assertEqual(receipt['package_state'], before)
        self.assertEqual(self.states[self.session]['pending_observations'], [])

    def test_post_call_id_can_pair_with_an_unidentified_pre_call(self):
        before = self.package_state()
        self.control.pre_tool('terminal', self.args, self.session)
        self.change_revision()
        self.assertEqual(self.observe(call_id='later-host-id')['package_state'], before)

    def test_post_without_an_id_pairs_with_the_identified_pre_call(self):
        before = self.package_state()
        self.control.pre_tool('terminal', self.args, self.session, 'pre-only-id')
        self.change_revision()
        self.assertEqual(self.observe()['package_state'], before)

    def test_original_kit_identity_survives_a_build_switch_during_the_call(self):
        before = self.package_state()
        self.control.pre_tool('terminal', self.args, self.session, 'original-build-call')
        other = researched_kit().to_dict()
        other['id'] = 'different-synthetic-specialist'
        other = self.builder.propose(other)
        self.control.start(self.session, other.id)
        receipt = self.observe(call_id='original-build-call')
        self.assertEqual(receipt['kit_id'], self.kit.id)
        self.assertEqual(receipt['package_state'], before)

    def test_identified_calls_finish_out_of_order_with_their_own_revisions(self):
        first = self.package_state()
        self.control.pre_tool('terminal', self.args, self.session, 'first-call')
        self.change_revision()
        second = self.package_state()
        self.control.pre_tool('terminal', self.args, self.session, 'second-call')
        self.assertEqual(self.observe(call_id='second-call')['package_state'], second)
        self.assertEqual(self.observe(call_id='first-call')['package_state'], first)

    def test_concurrent_identical_calls_without_ids_cannot_attest_either_revision(self):
        self.control.pre_tool('terminal', self.args, self.session)
        self.change_revision()
        self.control.pre_tool('terminal', self.args, self.session)
        self.assertIsNone(self.observe()['package_state'])
        self.assertIsNone(self.observe()['package_state'])

    def test_repeated_pre_hook_cannot_rebind_an_existing_call(self):
        before = self.package_state()
        self.control.pre_tool('terminal', self.args, self.session, 'same-call')
        self.change_revision()
        self.control.pre_tool('terminal', self.args, self.session, 'same-call')
        self.assertEqual(self.observe(call_id='same-call')['package_state'], before)

    def test_legacy_and_mismatched_calls_have_no_package_attestation(self):
        self.assertIsNone(self.observe()['package_state'])
        self.control.pre_tool('terminal', self.args, self.session, 'expected-call')
        receipt = self.observe(call_id='different-call')
        self.assertIsNone(receipt['package_state'])
        self.assertEqual(len(self.states[self.session]['pending_observations']), 1)

    def test_unexecuted_call_clears_pending_metadata_after_pause(self):
        self.control.pre_tool('terminal', self.args, self.session, 'paused-call')
        self.states[self.session]['build_active'] = False
        self.control.post_tool('terminal', self.args, {'error': 'Stopped.'}, self.session,
                               tool_call_id='paused-call', status='interrupted')
        self.assertEqual(self.control.read(self.session)['pending_observations'], [])


if __name__ == '__main__':
    unittest.main()
