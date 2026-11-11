"""Synthetic builds must finish supported work before their review handoff."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from core.builder import Builder
from core.buildplan import PHASE_IDS
from core.kitstore import KitStore
from core.model import KitError, ToolCapability
from tests.unit.test_provenance import researched_kit


def synthetic_demonstration():
    sample = {}
    actual = 'unknown' if 'amount' not in sample else 'present'
    return {'kind': 'demonstration', 'input': '{}',
            'input_provenance': 'An empty dictionary created for this synthetic unit exercise.',
            'actual_result': actual, 'expected_result': 'unknown',
            'expected_provenance': 'The independent synthetic specification states that a missing field represents an unknown value.',
            'comparison': 'The classifier output equals the expected missing-field classification.',
            'independent': True, 'passed': actual == 'unknown'}


def complete_synthetic_construction(builder, kit_id):
    source = builder.store.load(kit_id).sources[0]
    builder.library.document(kit_id, {
        'id': 'synthetic-spec', 'url': source.url, 'title': source.title, 'text': source.excerpt,
        'role': 'technical', 'authority': 'Synthetic test specification',
        'retrieved_at': source.retrieved_at, 'retrieval_tool': 'unit-fixture'})
    builder.library.entry(kit_id, {
        'id': 'missing-field-procedure', 'title': 'Classify a synthetic missing field', 'kind': 'procedure',
        'content': 'Inspect the amount field. Record unknown when the field is absent.',
        'applicability': 'The synthetic missing-field specification and this unit exercise.',
        'sources': [{'document_id': 'synthetic-spec', 'locator': source.locator, 'passage': source.excerpt}]})
    observed = builder.library.document_read(kit_id, 'synthetic-spec')
    receipt = {'kind': 'host-receipt', 'tool': 'unit-library-read', 'result': observed['text'],
               'observed_at': '2026-11-11T00:00:00Z'}
    evidence = {'discover': [{'kind': 'document', 'id': 'synthetic-spec'}],
                'acquire': [{'kind': 'document', 'id': 'synthetic-spec'}],
                'organize': [{'kind': 'entry', 'id': 'missing-field-procedure'}],
                'configure': [receipt], 'demonstrate': [synthetic_demonstration()]}
    tasks = builder.plans.read(kit_id)['tasks']
    for task in tasks:
        if task['id'] in PHASE_IDS:
            task.update(status='complete', evidence=evidence[task['id']])
    return builder.plans.update(kit_id, {
        'outcomes': [{'id': 'classify', 'description': 'Classify a synthetic missing field',
                      'acceptance': 'An absent amount field is recorded as unknown.'}],
        'requirements': [{'id': 'semantics', 'purpose': 'Establish missing-field meaning',
                          'document_ids': ['synthetic-spec']}], 'tasks': tasks})


class BuildCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.builder = Builder(KitStore(Path(self.temp.name) / 'data'))
        kit = researched_kit()
        kit.capabilities = [ToolCapability('reader', 'available', 'Read the synthetic specification',
            ['synthetic specification'], ['preserved text'], ['temporary test directory'], [],
            'Read the synthetic specification and compare its text.')]
        self.kit = self.builder.propose(kit.to_dict())

    def test_acquisition_and_one_procedure_cannot_complete_a_specialist(self):
        complete_synthetic_construction(self.builder, self.kit.id)
        kit = self.builder.store.load(self.kit.id)
        kit.claims, kit.workflow, kit.capabilities = [], [], []
        kit.pending_choices = ['Choose a toy task']
        self.builder.store.save(kit)
        tasks = self.builder.plans.read(kit.id)['tasks']
        for task in tasks:
            if task['id'] in {'configure', 'demonstrate'}:
                task.update(status='pending', evidence=[])
        self.builder.plans.update(kit.id, {'tasks': tasks})
        status = self.builder.status(kit.id)
        self.assertFalse(status['ready_for_review'])
        self.assertEqual(status['stage'], 'building')
        self.assertTrue(any('researched claims' in gap for gap in status['completion_gaps']))
        self.assertTrue(any('workflow' in gap for gap in status['completion_gaps']))
        self.assertTrue(any('demonstrate' in gap for gap in status['completion_gaps']))
        self.assertIsNotNone(status['next_executable_task'])
        self.assertIn('Continue construction', status['next_action'])

    def test_missing_plan_and_replacement_tasks_keep_all_mandatory_phases(self):
        complete_synthetic_construction(self.builder, self.kit.id)
        self.builder.plans._path(self.kit.id).unlink()
        self.assertFalse(self.builder.status(self.kit.id)['ready_for_review'])
        progress = self.builder.plans.update(self.kit.id, {'tasks': [
            {'id': 'capture-only', 'description': 'Capture a source', 'status': 'complete',
             'evidence': [{'kind': 'document', 'id': 'synthetic-spec'}]}]})
        self.assertTrue(PHASE_IDS.issubset({task['id'] for task in progress['plan']['tasks']}))
        self.assertFalse(progress['required_tasks_complete'])
        self.assertFalse(self.builder.status(self.kit.id)['ready_for_review'])

    def test_demonstration_requires_independent_expected_and_actual_results(self):
        bare = {'kind': 'host-receipt', 'tool': 'synthetic-check', 'result': 'It passed',
                'observed_at': '2026-11-11T00:00:00Z'}
        with self.assertRaisesRegex(KitError, 'demonstrate completion requires demonstration'):
            self.builder.plans.update(self.kit.id, {'tasks': [
                {'id': 'demonstrate', 'description': 'Compare a representative result',
                 'status': 'complete', 'evidence': [bare]}]})
        for key, value in [('input_provenance', ''), ('actual_result', ''), ('expected_result', ''),
                           ('expected_provenance', ''), ('comparison', ''), ('independent', False), ('passed', False)]:
            evidence = synthetic_demonstration()
            evidence[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(KitError, 'demonstration'):
                self.builder.plans.update(self.kit.id, {'tasks': [
                    {'id': 'demonstrate', 'description': 'Compare a representative result',
                     'status': 'complete', 'evidence': [evidence]}]})

    def test_configuration_and_organization_require_relevant_evidence(self):
        complete_synthetic_construction(self.builder, self.kit.id)
        for phase in ['configure', 'organize']:
            with self.subTest(phase=phase), self.assertRaisesRegex(KitError, 'completion requires'):
                self.builder.plans.update(self.kit.id, {'tasks': [
                    {'id': phase, 'description': 'Complete this phase', 'status': 'complete',
                     'evidence': [{'kind': 'document', 'id': 'synthetic-spec'}]}]})
        self.builder.library.entry(self.kit.id, {
            'id': 'unlinked', 'title': 'Unlinked suggestion', 'kind': 'procedure',
            'content': 'A synthetic unlinked suggestion.', 'applicability': 'Only this unit exercise.',
            'inference': True, 'sources': []})
        with self.assertRaisesRegex(KitError, 'current source links'):
            self.builder.plans.update(self.kit.id, {'tasks': [
                {'id': 'organize', 'description': 'Author source-linked guidance', 'status': 'complete',
                 'evidence': [{'kind': 'entry', 'id': 'unlinked'}]}]})

    def test_real_user_blocker_leaves_independent_work_executable(self):
        progress = self.builder.plans.update(self.kit.id, {
            'questions': [{'id': 'access', 'question': 'Which toy file may be read?',
                           'why': 'The requested toy file needs its owner to identify it.', 'requires_user': True}],
            'tasks': [{'id': 'acquire', 'description': 'Acquire the identified toy file', 'status': 'blocked',
                       'blocked_by': ['access'], 'evidence': []}]})
        self.assertEqual(progress['next_executable_task']['id'], 'discover')
        self.assertEqual([q['id'] for q in progress['user_blockers']], ['access'])
        self.assertFalse(progress['required_tasks_complete'])

    def test_external_blockers_do_not_invent_an_executable_task(self):
        tasks = self.builder.plans.read(self.kit.id)['tasks']
        for task in tasks:
            task.update(status='blocked', blocked_by=['synthetic-provider-outage'])
        self.builder.plans.update(self.kit.id, {'tasks': tasks})
        status = self.builder.status(self.kit.id)
        self.assertEqual(status['stage'], 'building')
        self.assertFalse(status['ready_for_review'])
        self.assertIsNone(status['next_executable_task'])
        self.assertEqual(status['user_blockers'], [])
        self.assertEqual(len(status['construction']['blocked_tasks']), len(PHASE_IDS))

    def test_complete_synthetic_build_can_be_ready_with_conditional_applicability(self):
        complete_synthetic_construction(self.builder, self.kit.id)
        progress = self.builder.plans.update(self.kit.id, {
            'requirements': [
                {'id': 'semantics', 'purpose': 'Establish missing-field meaning', 'document_ids': ['synthetic-spec']},
                {'id': 'optional-format', 'purpose': 'A second format only when selected',
                 'conditional': True, 'condition': 'The user later selects the optional toy format.'}],
            'tasks': [{'id': 'optional-example', 'description': 'Prepare optional format guidance',
                       'status': 'pending', 'evidence': [], 'conditional': True,
                       'condition': 'The user later selects the optional toy format.'}]})
        self.assertTrue(progress['required_tasks_complete'])
        self.assertFalse(progress['all_tasks_recorded_complete'])
        status = self.builder.status(self.kit.id)
        self.assertTrue(status['ready_for_review'], status['gaps'])
        self.assertEqual(status['stage'], 'review')
        self.assertEqual(status['completion_gaps'], [])
        self.assertEqual(len(status['construction']['conditional_requirements']), 1)

    def test_completed_knowledge_can_bundle_while_required_delivery_is_pending(self):
        complete_synthetic_construction(self.builder, self.kit.id)
        progress = self.builder.plans.update(self.kit.id, {'tasks': [
            {'id': 'install-profile', 'description': 'Install and verify the separate native profile',
             'status': 'pending', 'evidence': [], 'delivery': True}]})
        self.assertTrue(progress['knowledge_complete'])
        self.assertEqual(progress['knowledge_completion_gaps'], [])
        self.assertFalse(progress['required_tasks_complete'])
        status = self.builder.status(self.kit.id)
        self.assertTrue(status['ready_for_bundle'], status['knowledge_completion_gaps'])
        self.assertFalse(status['ready_for_review'])
        self.assertEqual(status['stage'], 'building')
        self.assertEqual(status['next_executable_task']['id'], 'install-profile')
        receipt = {'kind': 'host-receipt', 'tool': 'synthetic-installer',
                   'result': 'Synthetic target profile installed and its task output checked.',
                   'observed_at': '2026-11-11T00:00:00Z'}
        self.builder.plans.update(self.kit.id, {'tasks': [
            {'id': 'install-profile', 'description': 'Install and verify the separate native profile',
             'status': 'complete', 'evidence': [receipt], 'delivery': True}]})
        self.assertTrue(self.builder.status(self.kit.id)['ready_for_review'])

    def test_delivery_flag_is_boolean_and_cannot_hide_mandatory_knowledge(self):
        for task in [
            {'id': 'install-profile', 'description': 'Install the profile', 'status': 'pending', 'delivery': 'yes'},
            {'id': 'demonstrate', 'description': 'Demonstrate useful work', 'status': 'pending', 'delivery': True}]:
            with self.subTest(task=task), self.assertRaisesRegex(KitError, 'delivery'):
                self.builder.plans.update(self.kit.id, {'tasks': [task]})
        status = self.builder.status(self.kit.id)
        self.assertFalse(status['ready_for_bundle'])
        self.assertFalse(status['construction']['knowledge_complete'])

    def test_replacing_model_tasks_preserves_required_adapter_delivery(self):
        complete_synthetic_construction(self.builder, self.kit.id)
        self.builder.plans.update(self.kit.id, {'tasks': [
            {'id': 'install-profile', 'description': 'Install the selected target profile',
             'status': 'pending', 'delivery': True}]})
        progress = self.builder.plans.update(self.kit.id, {'tasks': []})
        self.assertEqual([task['id'] for task in progress['delivery_tasks']], ['install-profile'])
        self.assertTrue(self.builder.status(self.kit.id)['ready_for_bundle'])
        self.assertFalse(self.builder.status(self.kit.id)['ready_for_review'])
        for change in [{'delivery': False}, {'conditional': True, 'condition': 'Skip installation'}]:
            task = {'id': 'install-profile', 'description': 'Install the selected target profile',
                    'status': 'pending', **change}
            with self.subTest(change=change), self.assertRaisesRegex(KitError, 'delivery task'):
                self.builder.plans.update(self.kit.id, {'tasks': [task]})

    def test_mandatory_phases_cannot_be_made_conditional_or_duplicated(self):
        task = {'id': 'demonstrate', 'description': 'Demonstrate useful work', 'status': 'pending',
                'conditional': True, 'condition': 'Pretend the demonstration is optional.'}
        with self.assertRaisesRegex(KitError, 'cannot be conditional'):
            self.builder.plans.update(self.kit.id, {'tasks': [task]})
        task.pop('conditional')
        with self.assertRaisesRegex(KitError, 'duplicate'):
            self.builder.plans.update(self.kit.id, {'tasks': [task, deepcopy(task)]})
