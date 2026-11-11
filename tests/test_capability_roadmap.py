"""Durable capability plans and authorization continuity within the original mission."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from core.builder import Builder
from core.kitstore import KitStore
from core.library import KnowledgeLibrary
from core.model import ToolCapability


def capability(identity, readiness='available'):
    return ToolCapability(identity, readiness, 'Check the supplied evidence for the selected task.',
                          ['synthetic records'], ['qualified findings'], ['profile workspace'],
                          [] if readiness == 'available' else ['Implement the adapter in the profile workspace.'],
                          'Compare the actual findings with an independently prepared expected result.')


class CapabilityRoadmapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = KitStore(self.root / 'data')
        self.library = KnowledgeLibrary(self.root / 'profile/library')
        self.builder = Builder(self.store, self.library)
        self.kit = self.builder.start('Review synthetic filings', 'Sample organization',
                                      {'delivery': 'current-chat', 'jurisdiction': 'synthetic'})

    def propose(self, capabilities, **changes):
        current = self.store.load(self.kit.id)
        return self.builder.propose({'id': current.id, 'version': current.version,
                                     'capabilities': [item.__dict__ for item in capabilities], **changes})

    def roadmap(self):
        return json.loads((self.library.directory(self.kit.id) / 'capability-roadmap.json').read_text(encoding='utf8'))

    def adopt(self, origin='verified-user-build-request', choices=None):
        return self.store.adopt(self.kit.id, origin=origin, actor='synthetic-owner', choices=choices)

    def test_roadmap_persists_capability_records_and_keeps_knowledge_counts_separate(self):
        kit = self.propose([capability('reader'), capability('connector', 'build-required')])
        data = self.roadmap()
        self.assertEqual(data['kit_version'], kit.version)
        self.assertEqual(data['capabilities'], kit.to_dict()['capabilities'])
        text = (self.library.directory(kit.id) / 'capability-roadmap.md').read_text(encoding='utf8')
        available, planned = text.split('## Work to build or configure')
        self.assertIn('### reader', available)
        self.assertIn('### connector', planned)
        self.assertIn('observed test result retained in the library', text)
        state = self.library.status(kit.id)
        self.assertEqual((state['documents'], state['entries']), (0, 0))
        self.assertEqual(Path(state['capability_roadmap']).read_text(encoding='utf8'), text)
        self.assertIn('(capability-roadmap.md)', Path(state['navigation']).read_text(encoding='utf8'))

    def test_capability_revision_updates_roadmap_and_retains_working_capabilities(self):
        first = self.propose([capability('reader'), capability('connector', 'build-required')])
        self.adopt()
        second = self.propose([capability('reader'), capability('connector')])
        data = self.roadmap()
        self.assertEqual(second.version, first.version + 1)
        self.assertEqual(data['kit_version'], second.version)
        self.assertEqual([item['id'] for item in data['capabilities']], ['reader', 'connector'])
        self.assertEqual(data['capabilities'][1]['readiness'], 'available')
        self.assertIn('observed test result', data['verification_limit'])
        self.assertEqual(second.adoption.origin, 'verified-user-build-request')
        self.assertEqual(second.adoption.version, second.version)

    def test_derived_roadmap_refresh_keeps_version_adoption_and_library_fingerprint(self):
        self.propose([capability('reader')])
        adopted = self.adopt()
        before = self.roadmap()
        fingerprint = self.library.fingerprint(adopted.id)
        self.store.save(adopted)
        restarted = Builder(KitStore(self.store.root), KnowledgeLibrary(self.library.root))
        current = restarted.store.load(adopted.id)
        self.assertEqual(current.to_dict(), adopted.to_dict())
        self.assertEqual(self.roadmap(), before)
        self.assertEqual(self.library.fingerprint(adopted.id), fingerprint)

    def test_export_carries_roadmap_and_continuing_improvement_instructions(self):
        self.propose([capability('reader'), capability('connector', 'configurable')])
        output = self.store.export(self.kit.id, self.root / 'exported')
        copied = output / 'library' / self.kit.id
        self.assertEqual(json.loads((copied / 'capability-roadmap.json').read_text()), self.roadmap())
        self.assertIn('(capability-roadmap.md)', (copied / '_index.md').read_text(encoding='utf8'))
        instructions = (output / 'runtime/SOUL.md').read_text(encoding='utf8')
        self.assertIn('capability-roadmap.md', instructions)
        self.assertIn('independent expected evidence', instructions)
        self.assertIn('host permissions', instructions)

    def test_same_mission_upgrade_preserves_actual_choices_and_marks_new_unknowns(self):
        self.propose([capability('reader')], pending_choices=['Retention period'])
        self.adopt(choices={'Retention period': '30 days'})
        changed = self.propose([capability('reader'), capability('connector', 'missing')],
                               pending_choices=['Retention period', 'Data owner'])
        self.assertEqual(changed.adoption.actor, 'synthetic-owner')
        self.assertEqual(changed.adoption.choices['Retention period'], '30 days')
        self.assertEqual(changed.adoption.choices['Data owner'],
                         {'status': 'unresolved', 'origin': 'ask-at-use'})

    def test_changed_mission_and_legacy_authorization_reopen_adoption(self):
        self.propose([capability('reader')])
        baseline = self.adopt()
        for field, value in [('goal', 'A different goal'), ('subject', 'Another organization'),
                             ('scope', {'delivery': 'profile', 'jurisdiction': 'synthetic'})]:
            with self.subTest(field=field):
                current = self.store.load(baseline.id)
                if current.adoption.status != 'adopted':
                    current.goal, current.subject, current.scope = baseline.goal, baseline.subject, deepcopy(baseline.scope)
                    self.store.save(current)
                    current = self.adopt()
                setattr(current, field, value)
                saved = self.store.save(current)
                self.assertEqual(saved.adoption.status, 'proposed')
        current = self.store.load(baseline.id)
        self.store.adopt(current.id, origin='verified-user-command', actor='legacy-owner')
        saved = self.propose([capability('reader'), capability('connector', 'missing')])
        self.assertEqual(saved.adoption.status, 'proposed')

    def test_changed_source_retains_request_authority_and_exposes_review_flags(self):
        self.propose([capability('reader')])
        data = {'id': 'official-rule', 'url': 'https://example.test/rule', 'title': 'Synthetic rule',
                'text': 'The synthetic rule requires a signed record.', 'role': 'technical',
                'authority': 'Synthetic test specification', 'retrieved_at': '2026-11-11T00:00:00Z',
                'retrieval_tool': 'synthetic-reader'}
        self.library.document(self.kit.id, data)
        self.library.entry(self.kit.id, {'id': 'review-record', 'title': 'Review the signed record',
            'kind': 'procedure', 'content': 'Check the signature before using the record.',
            'applicability': 'Synthetic records only.', 'sources': [{'document_id': data['id'],
                'locator': 'Rule text', 'passage': data['text']}]})
        adopted = self.adopt()
        self.library.document(self.kit.id, {**data, 'text': 'The synthetic rule now requires two signed records.'})
        current = self.store.load(self.kit.id)
        self.assertEqual(current.adoption.origin, 'verified-user-build-request')
        self.assertGreater(current.version, adopted.version)
        self.assertEqual(current.adoption.version, current.version)
        self.assertTrue(self.library.read(self.kit.id, 'review-record')['review_required'])


if __name__ == '__main__':
    unittest.main()
