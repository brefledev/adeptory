"""Native delivery requires task output from the selected installed revision."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from adapter_hermes.profile_bundle import installed
from adapter_hermes.verification import native_task_result
from core.model import KitError
from tests import test_construction_controller as fixtures


class NativeTaskResultTests(unittest.TestCase):
    def receipt(self, command=None, **result):
        events = [{'type': 'tool_result', 'name': 'adeptory_library', 'result': {'id': 'procedure'}},
                  {'type': 'result', 'session_id': 'native-session', 'exit_code': 0,
                   'text': 'The supplied record lacks the required amount.'}]
        return {'tool': 'terminal', 'args': {'command': command or
            '& "C:/Hermes/hermes.exe" -p synthetic-target chat --oneshot --format stream-json --query-file "C:/case prompt.txt"'},
            'result': {'exit_code': 0, 'output': '\n'.join(json.dumps(event) for event in events), **result}}

    def test_native_task_result_preserves_actual_final_text(self):
        self.assertEqual(native_task_result(self.receipt(), 'synthetic-target'),
                         'The supplied record lacks the required amount.')

    def test_help_wrong_profile_wrappers_and_policy_overrides_fail(self):
        for command in [
            'hermes -p synthetic-target chat --help',
            'hermes -p another-target chat --oneshot --format stream-json -q "Check this"',
            'python check-hermes-synthetic-target-chat.py',
            'hermes -p synthetic-target chat --oneshot --format stream-json -q "Check this" --yolo',
            'hermes -p synthetic-target chat --oneshot --format stream-json -q "Check this" ; echo done']:
            with self.subTest(command=command), self.assertRaises(KitError):
                native_task_result(self.receipt(command), 'synthetic-target')

    def test_usage_failed_truncated_and_unobserved_results_fail(self):
        for output in ['usage: hermes chat', '{"type":"result","exit_code":0}',
                       '{"type":"result","session_id":"s","exit_code":0,"text":"done"}',
                       '{"type":"result","session_id":"s","exit_code":1,"text":"failed"}']:
            with self.subTest(output=output), self.assertRaises(KitError):
                native_task_result(self.receipt(output=output), 'synthetic-target')
        with self.assertRaises(KitError):
            native_task_result(self.receipt(exit_code=1), 'synthetic-target')

    def test_retained_transcript_survives_output_truncation_and_utf16_redirection(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            workspace = home / 'workspace'
            workspace.mkdir()
            path = workspace / 'native-check.jsonl'
            answer = 'A' * 72000
            text = json.dumps({'type': 'tool_result', 'name': 'adeptory_library', 'result': 'read'}) + '\n'
            text += json.dumps({'type': 'result', 'session_id': 'native-long', 'exit_code': 0, 'text': answer})
            path.write_text(text, encoding='utf16')
            record = self.receipt(output='[host output truncated]')
            record['args']['command'] += ' > "' + str(path) + '"'
            retained = home / 'observations' / 'native.jsonl'
            result = native_task_result(record, 'synthetic-target', profile_home=home, retained_path=retained)
            self.assertEqual(result, answer)
            self.assertEqual(retained.read_text(encoding='utf8'), text)

    def test_background_check_requires_its_own_successful_completion(self):
        original = self.receipt(exit_code=None, session_id='proc-native')
        completion = {'tool': 'process_manage', 'args': {'action': 'wait', 'session_id': 'proc-native'},
                      'result': {**self.receipt()['result'], 'status': 'exited', 'session_id': 'proc-native'}}
        self.assertEqual(native_task_result(original, 'synthetic-target', completion=completion),
                         'The supplied record lacks the required amount.')
        for change in [{'session_id': 'proc-other'}, {'status': 'running'}, {'exit_code': 1}]:
            with self.subTest(change=change), self.assertRaises(KitError):
                altered = {**completion, 'result': {**completion['result'], **change}}
                native_task_result(original, 'synthetic-target', completion=altered)
        with self.assertRaises(KitError):
            native_task_result(original, 'synthetic-target')

    def test_retained_output_cannot_read_outside_builder_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            path = home / 'outside.jsonl'
            path.write_text(self.receipt()['result']['output'], encoding='utf8')
            record = self.receipt()
            record['args']['command'] += ' > "' + str(path) + '"'
            with self.assertRaisesRegex(KitError, 'builder profile workspace'):
                native_task_result(record, 'synthetic-target', profile_home=home)


class InstalledRevisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ConstructionControllerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        fixture = self.fixture
        self.kit_id = fixture.start()
        fixture.complete(self.kit_id)
        self.kit = fixture.runtime._activate_built_request(fixture.runtime.store.load(self.kit_id), fixture.session)
        from adapter_hermes.profile_bundle import prepare
        self.bundle = prepare(fixture.runtime.store, fixture.runtime.library, self.kit_id, 'synthetic-target', {})
        self.home = Path(self.bundle['directory'])
        active = self.home / 'plugin-data' / 'adeptory' / 'kits' / self.kit_id / 'kit.json'
        active.parent.mkdir(parents=True)
        seed = json.loads((self.home / 'plugins' / 'adeptory' / 'starter-kit.json').read_text(encoding='utf8'))
        seed['adoption'] = self.kit.to_dict()['adoption']
        active.write_text(json.dumps(seed), encoding='utf8')
        self.home_patch = patch('adapter_hermes.profile_bundle._profile_home', return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def test_current_distribution_and_library_are_accepted(self):
        result = installed(self.kit_id, 'synthetic-target', self.kit,
                           self.fixture.runtime.library.fingerprint(self.kit_id))
        self.assertEqual(result['kit_id'], self.kit_id)

    def test_generic_plugin_update_keeps_persisted_specialist_identity(self):
        from adapter_hermes.profile_bundle import refresh
        (self.home / 'plugins' / 'adeptory' / 'starter-kit.json').unlink()
        self.assertEqual(installed(self.kit_id, 'synthetic-target', self.kit)['kit_id'], self.kit_id)
        with patch('adapter_hermes.profile_bundle._reload', return_value={'reloaded': True}):
            self.assertEqual(refresh(self.kit_id, 'synthetic-target')['status'], 'profile-reloaded')

    def test_revised_package_and_changed_library_require_refreshed_distribution(self):
        newer = self.fixture.runtime.store.load(self.kit_id)
        newer.capabilities[0].verification += ' Check the retained output.'
        newer = self.fixture.runtime.store.save(newer)
        with self.assertRaisesRegex(KitError, 'refreshed distribution'):
            installed(self.kit_id, 'synthetic-target', newer)
        with self.assertRaisesRegex(KitError, 'installed library differs'):
            installed(self.kit_id, 'synthetic-target', self.kit, 'changed-fingerprint')

    def observe_native_task(self):
        fixture = self.fixture
        fixture.runtime.builder.plans.update(self.kit_id, {'tasks': [{
            'id': 'install-profile', 'description': 'Verify the synthetic installed profile',
            'delivery': True, 'status': 'pending'}]})
        fixture.sync_tasks(self.kit_id)
        fixture.runtime._session(fixture.session)['profile_name'] = 'synthetic-target'
        record = NativeTaskResultTests().receipt()
        fixture.runtime.pre_tool_call('terminal', record['args'], session_id=fixture.session,
                                      tool_call_id='native-task')
        fixture.runtime.post_tool_call('terminal', record['args'], record['result'],
            session_id=fixture.session, tool_call_id='native-task', status='success')
        receipt = fixture.runtime._session(fixture.session)['observed_tools'][-1]['receipt_id']
        actual = native_task_result(record, 'synthetic-target')
        data = {'native_receipt_id': receipt, 'native_verification': {
            'input': '{}', 'input_provenance': 'Synthetic empty record.', 'actual_result': actual,
            'expected_result': 'Report the absent amount.',
            'expected_provenance': 'Independent synthetic specification requires an amount.',
            'comparison': 'The final answer identifies the missing amount.',
            'independent': True, 'passed': True}}
        return {'operation': 'finish', 'kit_id': self.kit_id, 'profile_name': 'synthetic-target', 'data': data}

    def test_finish_accepts_current_observed_task_and_retains_comparison(self):
        args = self.observe_native_task()
        result = self.fixture.runtime._finish_build(self.kit, args, self.fixture.session)
        self.assertTrue(result['complete'])
        delivery = self.fixture.runtime.builder.plans.read(self.kit_id)['tasks'][-1]
        self.assertEqual(delivery['evidence'][-1]['kind'], 'demonstration')
        self.assertTrue(Path(delivery['evidence'][0]['transcript']).is_file())

    def test_finish_rejects_old_task_even_after_installing_new_content(self):
        args = self.observe_native_task()
        current = self.fixture.runtime.store.load(self.kit_id)
        current.workflow[0].instruction += ' Check the revised procedure.'
        current = self.fixture.runtime.store.save(current)
        seed = current.to_dict()
        seed['version'] = 1
        seed['scope']['import_origin'] = {'kit_id': self.kit_id, 'version': current.version}
        for path in [self.home / 'plugins' / 'adeptory' / 'starter-kit.json',
                     self.home / 'plugin-data' / 'adeptory' / 'kits' / self.kit_id / 'kit.json']:
            path.write_text(json.dumps(seed), encoding='utf8')
        with self.assertRaisesRegex(KitError, 'fresh native check'):
            self.fixture.runtime._finish_build(current, args, self.fixture.session)

    def test_native_task_cannot_start_against_an_older_installed_profile(self):
        self.observe_native_task()
        current = self.fixture.runtime.store.load(self.kit_id)
        current.workflow[0].instruction += ' Use the new procedure.'
        self.fixture.runtime.store.save(current)
        record = NativeTaskResultTests().receipt()
        blocked = self.fixture.runtime.pre_tool_call('terminal', record['args'],
            session_id=self.fixture.session, tool_call_id='stale-installed-task')
        self.assertEqual(blocked['action'], 'block')
        self.assertIn('Refresh the generated specialist', blocked['message'])
