"""Native delivery requires task output from the selected installed revision."""
import json
from pathlib import Path
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

    def test_revised_package_and_changed_library_require_refreshed_distribution(self):
        newer = self.fixture.runtime.store.load(self.kit_id)
        newer.capabilities[0].verification += ' Check the retained output.'
        newer = self.fixture.runtime.store.save(newer)
        with self.assertRaisesRegex(KitError, 'refreshed distribution'):
            installed(self.kit_id, 'synthetic-target', newer)
        with self.assertRaisesRegex(KitError, 'installed library differs'):
            installed(self.kit_id, 'synthetic-target', self.kit, 'changed-fingerprint')
