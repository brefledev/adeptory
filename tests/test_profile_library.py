"""Observable source retention, retrieval, freshness and profile isolation."""
import json
from pathlib import Path
import tempfile
import unittest
import importlib.util
import sys
import uuid
from unittest.mock import patch

from adapter_hermes.runtime import Runtime
from core.library import KnowledgeLibrary
from core.model import KitError, ToolCapability
from tests.test_build_completion import complete_synthetic_construction
from tests.unit.test_provenance import researched_kit


class ProfileLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.profile = Path(self.temp.name) / 'profiles' / 'research'
        self.runtime = Runtime(self.profile / 'plugin-data' / 'adeptory')
        kit = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'start', 'goal': 'Build a diagnostic reference', 'subject': 'Example site',
            'scope': {'delivery': 'current-chat'}}, 'chat'))
        self.kit = kit['id']

    def complete_construction(self):
        kit = self.runtime.store.load(self.kit)
        researched = researched_kit()
        kit.sources, kit.claims, kit.workflow = researched.sources, researched.claims, researched.workflow
        kit.capabilities = [ToolCapability('reader', 'available', 'Read the synthetic specification',
            ['synthetic specification'], ['preserved text'], ['temporary test directory'], [],
            'Read the synthetic specification and compare its text.')]
        self.runtime.builder.propose(kit.to_dict())
        complete_synthetic_construction(self.runtime.builder, kit.id)
        self.assertTrue(self.runtime.builder.status(kit.id)['ready_for_bundle'])

    def document(self, text='The sample protocol requires an explicit response before interpreting its payload.', **patch):
        return self.runtime.library.document(self.kit, {
            'id': 'protocol', 'title': 'Example protocol specification',
            'url': 'https://example.test/protocol', 'text': text, 'role': 'technical',
            'authority': 'Synthetic specification used only for this test',
            'retrieved_at': '2026-11-11T00:00:00Z', 'retrieval_tool': 'test-fixture',
            'review_after': '2000-01-01', **patch})

    def entry(self):
        return self.runtime.library.entry(self.kit, {
            'id': 'response-triage', 'title': 'Interpret a missing protocol response',
            'kind': 'diagnostic', 'aliases': ['no response', 'connection failure'],
            'content': 'Establish whether a response was received before interpreting a payload. '
                       'Compare the recorded request time and response log, then repeat the sample request.',
            'applicability': 'This synthetic protocol and recorded sample request.',
            'exceptions': ['A previous successful response concerns its recorded time.'],
            'sources': [{'document_id': 'protocol', 'locator': 'Protocol requirement',
                         'passage': 'requires an explicit response'}]})

    def test_search_survives_restart_with_conditions_dates_and_exact_original(self):
        self.document()
        self.entry()
        restarted = Runtime(self.profile / 'plugin-data' / 'adeptory')
        result = json.loads(restarted.tool('adeptory_library', {
            'operation': 'search', 'kit_id': self.kit, 'query': 'connection failure'}, 'other-chat'))
        entry = result['matches'][0]
        self.assertEqual(entry['id'], 'response-triage')
        self.assertIn('recorded sample', entry['applicability'])
        self.assertTrue(entry['exceptions'])
        self.assertEqual(entry['source_states'][0]['freshness'], 'review-due')
        self.assertTrue(entry['review_required'])
        original = restarted.library.document_read(self.kit, 'protocol', limit=20)
        self.assertEqual(original['window']['next_offset'], 20)
        self.assertTrue((self.profile / 'library' / self.kit / '_index.md').exists())

    def test_changed_original_flags_dependent_guidance_and_preserves_history(self):
        old = self.document()
        self.entry()
        self.document('The revised sample protocol accepts a cached response with a timestamp.')
        result = self.runtime.library.read(self.kit, 'response-triage')
        self.assertEqual(result['changed_sources'], ['protocol'])
        self.assertTrue((self.profile / 'library' / self.kit / old['text_path']).exists())
        self.assertTrue(list((self.profile / 'library' / self.kit / 'sources' / 'history').glob('*.json')))
        markdown = (self.profile / 'library' / self.kit / 'references' / 'response-triage.md').read_text(encoding='utf8')
        self.assertIn('https://example.test/protocol', markdown)
        self.assertIn('2026-11-11T00:00:00Z', markdown)
        self.assertIn('Changed sources', markdown)
        self.assertIn('review-due', markdown)

    def test_changed_document_updates_search_and_retains_other_rows(self):
        self.document('The original document describes cobalt widgets.')
        self.document('The second document describes amber widgets.', id='second')
        self.document('The revised document describes violet widgets.')
        matches = self.runtime.library.search(self.kit, 'violet')['matches']
        self.assertEqual([item['id'] for item in matches], ['protocol'])
        self.assertEqual(self.runtime.library.search(self.kit, 'cobalt')['matches'], [])
        self.assertEqual(self.runtime.library.search(self.kit, 'amber')['matches'][0]['id'], 'second')

    def test_second_profile_cannot_search_first_profile_knowledge(self):
        self.document()
        self.entry()
        second = Runtime(self.profile.parent / 'other' / 'plugin-data' / 'adeptory')
        self.assertEqual(second.library.search(self.kit, 'connection')['matches'], [])
        self.assertEqual(second.library.status(self.kit)['documents'], 0)

    def test_false_attribution_and_import_escape_are_rejected(self):
        self.document()
        with self.assertRaisesRegex(KitError, 'passage'):
            self.runtime.library.entry(self.kit, {
                'id': 'invented', 'title': 'Invented claim', 'kind': 'reference', 'content': 'False support',
                'applicability': 'Test', 'sources': [{'document_id': 'protocol', 'locator': 'Test',
                                                    'passage': 'This sentence was never captured.'}]})
        with self.assertRaisesRegex(KitError, 'imports'):
            self.runtime.library.document(self.kit, {'import_path': '../../outside.txt'})

    def test_construction_is_resumable_and_cannot_complete_without_evidence(self):
        self.document()
        self.entry()
        self.runtime.builder.plans.update(self.kit, {
            'outcomes': [{'id': 'triage', 'description': 'Explain a sampled failure', 'acceptance': 'Expected diagnosis'}],
            'requirements': [{'id': 'protocol-law', 'purpose': 'Determine protocol behavior', 'document_ids': ['protocol']}],
            'tasks': [{'id': 'capture', 'description': 'Capture the protocol', 'status': 'complete',
                       'evidence': [{'kind': 'document', 'id': 'protocol'}]}]})
        restarted = Runtime(self.profile / 'plugin-data' / 'adeptory')
        progress = restarted.builder.plans.progress(self.kit)
        self.assertEqual(progress['plan']['requirements'][0]['document_ids'], ['protocol'])
        self.assertEqual(progress['library']['entries'], 1)
        with self.assertRaisesRegex(KitError, 'evidence'):
            restarted.builder.plans.update(self.kit, {'tasks': [
                {'id': 'fake', 'description': 'Unsupported completion', 'status': 'complete', 'evidence': []}]})

    def test_export_carries_library_originals_procedures_and_profile_instructions(self):
        self.document()
        self.entry()
        destination = Path(self.temp.name) / 'exported-specialist'
        self.runtime.store.export(self.kit, destination)
        exported = KnowledgeLibrary(destination / 'library')
        self.assertEqual(exported.search(self.kit, 'connection')['matches'][0]['id'], 'response-triage')
        self.assertIn('profile-owned library', (destination / 'runtime' / 'SOUL.md').read_text(encoding='utf8'))

    def test_native_distribution_contains_own_library_and_proposed_starter(self):
        self.document()
        self.entry()
        self.complete_construction()
        self.runtime.pre_llm_call(session_id='chat', user_message='Build this synthetic diagnostic reference specialist.')
        (self.profile / 'config.yaml').write_text(
            '_config_version: 53\nmodel:\n  provider: example-provider\n'
            '  default: example-model\n  api_key: placeholder\n', encoding='utf8')
        bundle = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'bundle', 'kit_id': self.kit, 'profile_name': 'example-specialist'}, 'chat'))
        path = Path(bundle['directory'])
        import yaml
        config = yaml.safe_load((path / 'config.yaml').read_text(encoding='utf8'))
        self.assertEqual(config['_config_version'], 53)
        self.assertEqual(config['model'], {'provider': 'example-provider', 'default': 'example-model'})
        self.assertIn('adeptory', config['platform_toolsets']['cli'])
        self.assertEqual(bundle['after_install']['operation'], 'refresh_profile')
        self.assertTrue((path / 'distribution.yaml').is_file())
        self.assertTrue((path / 'SOUL.md').is_file())
        starter = json.loads((path / 'plugins' / 'adeptory' / 'starter-kit.json').read_text(encoding='utf8'))
        self.assertEqual(starter['adoption']['status'], 'proposed')
        self.assertTrue((path / 'plugins' / 'adeptory' / 'starter-authority.json').is_file())
        self.assertEqual(starter['version'], 1)
        second = Runtime(self.profile.parent / 'imported' / 'plugin-data' / 'adeptory')
        imported = second.builder.propose(starter)
        self.assertEqual(imported.version, 1)
        self.assertEqual(KnowledgeLibrary(path / 'library').status(self.kit)['entries'], 2)
        self.assertFalse((path / '.env').exists())
        name = 'native_bundle_' + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(name, path / 'plugins' / 'adeptory' / '__init__.py',
                                                     submodule_search_locations=[str(path / 'plugins' / 'adeptory')])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(lambda: [sys.modules.pop(k, None) for k in list(sys.modules) if k == name or k.startswith(name + '.')])
        spec.loader.exec_module(module)
        runtime_class = sys.modules[name + '.adapter_hermes.runtime'].Runtime
        installed_home = self.profile.parent / 'native-boot'
        booted = runtime_class(installed_home / 'plugin-data' / 'adeptory')
        self.assertEqual(booted.library.status(self.kit)['entries'], 2)
        self.assertEqual(booted.store.load(self.kit).adoption.origin, 'verified-user-build-request')
        self.assertTrue((installed_home / 'library' / '_index.md').is_file())
        booted.library.entry(self.kit, {'id': 'own-note', 'title': 'Profile-owned addition', 'kind': 'reference',
                                      'content': 'A later user-owned addition.', 'applicability': 'Synthetic test',
                                      'sources': [], 'inference': True})
        restarted = runtime_class(installed_home / 'plugin-data' / 'adeptory')
        self.assertEqual(restarted.library.status(self.kit)['entries'], 3)
        revised = restarted.store.load(self.kit)
        revised.pending_choices.append('Choose the next dataset')
        revised = restarted.store.save(revised)
        choices = revised.adoption.choices.copy()
        restarted = runtime_class(installed_home / 'plugin-data' / 'adeptory')
        self.assertEqual(restarted.store.load(self.kit).adoption.choices, choices)
        revised = restarted.store.load(self.kit)
        revised.goal = 'A different mission requiring a new authorization'
        restarted.store.save(revised)
        restarted = runtime_class(installed_home / 'plugin-data' / 'adeptory')
        self.assertEqual(restarted.store.load(self.kit).adoption.status, 'proposed')

    def test_bulk_import_resumes_and_reports_a_blocked_item_without_hiding_progress(self):
        incoming = self.runtime.library.root / 'imports'
        incoming.mkdir(exist_ok=True)
        document = {'id': 'import-source', 'url': 'https://example.test/import', 'title': 'Import source',
                    'text': 'A complete sample statement.', 'role': 'reference', 'authority': 'Synthetic fixture',
                    'retrieved_at': '2026-11-11', 'retrieval_tool': 'test-fixture'}
        items = [{'kind': 'document', 'data': document},
                 {'kind': 'entry', 'data': {'id': 'import-entry', 'title': 'Imported sample', 'kind': 'reference',
                    'content': 'Apply the sample statement to the synthetic input.', 'applicability': 'This fixture',
                    'sources': [{'document_id': 'import-source', 'locator': 'Statement', 'passage': 'sample statement'}]}},
                 {'kind': 'entry', 'data': {'id': 'broken'}}]
        (incoming / 'corpus.json').write_text(json.dumps(items), encoding='utf8')
        first = self.runtime.library.import_batch(self.kit, 'corpus.json', limit=1)
        self.assertEqual(first['cursor'], 1)
        restarted = Runtime(self.profile / 'plugin-data' / 'adeptory')
        second = restarted.library.import_batch(self.kit, 'corpus.json', limit=1)
        self.assertEqual(second['cursor'], 2)
        self.assertEqual(second['library']['entries'], 1)
        blocked = restarted.library.import_batch(self.kit, 'corpus.json', limit=1)
        self.assertEqual(blocked['status'], 'blocked')
        self.assertEqual(blocked['cursor'], 2)

    def test_meaningful_library_changes_reopen_adoption_and_identical_capture_preserves_it(self):
        self.document()
        self.entry()
        self.complete_construction()
        self.runtime.store.adopt(self.kit, origin='verified-user-command', actor='test-user')
        old = self.runtime.store.load(self.kit)
        self.document()
        self.assertEqual(self.runtime.store.load(self.kit).adoption.status, 'adopted')
        self.document('A revised protocol changes the response interpretation.')
        current = self.runtime.store.load(self.kit)
        self.assertGreater(current.version, old.version)
        self.assertEqual(current.adoption.status, 'proposed')

    def test_original_text_preserves_windows_line_endings_exactly(self):
        text = 'First operative line.\r\nSecond operative line.\r\n'
        self.document(text)
        readback = self.runtime.library.document_read(self.kit, 'protocol')
        self.assertEqual(readback['text'], text)

    def test_generated_profile_refresh_reports_host_result(self):
        home = Path(self.temp.name) / 'generated-profile'
        starter = home / 'plugins' / 'adeptory' / 'starter-kit.json'
        starter.parent.mkdir(parents=True)
        starter.write_text(json.dumps({'id': self.kit, 'scope': {'import_origin': {'kit_id': self.kit}}}), encoding='utf8')
        with patch('adapter_hermes.profile_bundle._profile_home', return_value=home), \
             patch('adapter_hermes.profile_bundle._reload', return_value={'reloaded': True}) as reload_host:
            result = json.loads(self.runtime.tool('adeptory_build', {
                'operation': 'refresh_profile', 'kit_id': self.kit, 'profile_name': 'generated-profile'}, 'chat'))
            self.assertEqual(result['status'], 'profile-reloaded')
            reload_host.assert_called_once_with(home.resolve())
        with patch('adapter_hermes.profile_bundle._profile_home', return_value=home), \
             patch('adapter_hermes.profile_bundle._reload', return_value={'reloaded': False, 'error': 'busy'}):
            result = json.loads(self.runtime.tool('adeptory_build', {
                'operation': 'refresh_profile', 'kit_id': self.kit, 'profile_name': 'generated-profile'}, 'chat'))
            self.assertEqual(result['status'], 'reload-pending')
            self.assertEqual(result['host_response']['error'], 'busy')

    def test_generated_profile_refresh_rejects_other_specialist(self):
        from adapter_hermes.profile_bundle import refresh
        home = Path(self.temp.name) / 'another-profile'
        starter = home / 'plugins' / 'adeptory' / 'starter-kit.json'
        starter.parent.mkdir(parents=True)
        starter.write_text(json.dumps({'id': 'other-kit'}), encoding='utf8')
        with patch('adapter_hermes.profile_bundle._profile_home', return_value=home), \
             patch('adapter_hermes.profile_bundle._reload') as reload_host:
            with self.assertRaisesRegex(KitError, 'different specialist'):
                refresh(self.kit, 'another-profile')
            reload_host.assert_not_called()

    def test_source_text_is_findable_before_authorship_and_is_labeled_as_a_lead(self):
        self.document('A synthetic memorandum explains inventory valuation and its exceptions.')
        result = self.runtime.library.search(self.kit, 'How do I handle inventory valuation?')
        source = result['matches'][0]
        self.assertEqual(source['result_kind'], 'document')
        self.assertEqual(source['read_parameters']['document_id'], 'protocol')
        self.assertIn('source-search lead', source['evidence_status'])
        self.assertTrue(source['review_required'])


if __name__ == '__main__':
    unittest.main()
