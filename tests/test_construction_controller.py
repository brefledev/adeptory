"""Synthetic host callbacks enforce build completion and preserve human provenance."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from adapter_hermes.runtime import Runtime
from core.model import KitError
from tests.test_build_completion import complete_synthetic_construction
from tests.unit.test_provenance import researched_kit


class ConstructionControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'profile' / 'plugin-data' / 'adeptory'
        self.context = SimpleNamespace(inject_message=Mock(return_value=True))
        self.runtime = Runtime(self.root, context=self.context)
        self.session = 'synthetic-chat'
        self.goal = 'Build a specialist that classifies missing fields in synthetic records.'

    def start(self, session=None, authorize=True):
        session = session or self.session
        if authorize:
            self.runtime.pre_llm_call(session_id=session, user_message=self.goal)
        response = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'start', 'goal': self.goal, 'subject': 'Synthetic missing-field classification',
            'scope': {'delivery': 'current-chat'}}, session))
        self.assertNotIn('error', response)
        return response['id']

    def test_repeated_host_refusal_before_construction_releases_required_tools(self):
        state = self.runtime._session(self.session)
        state.update(build_active=True, build_turn=None)
        refusal = {'error': 'Host policy refused this session origin.'}
        for name in ('tool_describe', 'skill_view'):
            self.runtime.post_tool_call(tool_name=name, args={}, result=refusal,
                                        session_id=self.session, status='blocked')
        self.assertTrue(state['build_paused'])
        self.assertIn('Host policy refused', state['build_pause_reason'])
        self.assertIsNone(self.runtime.construction.llm_request(
            {'tools': [{'name': 'read_file'}]}, session_id=self.session, turn_id='refused-turn'))
        saved = Runtime(self.root, context=self.context)._session(self.session)
        self.assertEqual(saved['build_pause_reason'], state['build_pause_reason'])

    def test_unknown_delivery_cannot_silently_skip_profile_installation(self):
        result = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'start', 'goal': self.goal, 'subject': 'Synthetic records',
            'scope': {'delivery': 'installed-profile'}}, self.session))
        self.assertIn('scope.delivery', result['error'])
        self.assertEqual(self.runtime.store.list(), [])

    def test_required_profile_delivery_survives_changed_scope_metadata(self):
        self.runtime.pre_llm_call(session_id=self.session, user_message=self.goal)
        result = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'start', 'goal': self.goal, 'subject': 'Synthetic records'}, self.session))
        kit_id = result['id']
        self.complete(kit_id)
        kit = self.runtime.store.load(kit_id)
        kit.scope['delivery'] = 'current-chat'
        self.runtime.store.save(kit)
        result = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'finish', 'kit_id': kit_id}, self.session))
        self.assertIn('receipt_id', result['error'])
        self.assertEqual(self.runtime.store.load(kit_id).adoption.status, 'proposed')

    def complete(self, kit_id, session=None):
        session = session or self.session
        kit = self.runtime.store.load(kit_id)
        proposal = researched_kit().to_dict()
        proposal.update(id=kit.id, version=kit.version, fixture=False, scope=kit.scope)
        proposal['capabilities'] = [{'id': 'reader', 'readiness': 'available',
            'why': 'Read synthetic input in the isolated test directory', 'inputs': ['toy record'],
            'outputs': ['missing-field classification'], 'access': ['temporary directory only'],
            'setup': [], 'verification': 'Read the toy record and compare the preserved text.'}]
        self.runtime.builder.propose(proposal)
        complete_synthetic_construction(self.runtime.builder, kit_id)
        path = Path(self.temp.name) / 'toy-record.json'
        path.write_text('{}', encoding='utf8')
        configure = self.observe('read_file', {'path': str(path)}, {'text': path.read_text()}, session)
        sample = json.loads(path.read_text())
        actual = 'unknown' if 'amount' not in sample else 'present'
        demonstrate = self.observe('synthetic_classifier', {'input': sample}, {'classification': actual}, session)
        tasks = self.runtime.builder.plans.read(kit_id)['tasks']
        for task in tasks:
            if task['id'] == 'configure':
                task['evidence'][0]['receipt_id'] = configure
            if task['id'] == 'demonstrate':
                task['evidence'][0]['actual_receipt_id'] = demonstrate
        self.runtime.builder.plans.update(kit_id, {'tasks': tasks})
        return self.runtime.builder.status(kit_id)

    def observe(self, tool, args, result, session=None, status='success'):
        session = session or self.session
        self.runtime.post_tool_call(tool_name=tool, args=args, result=result, session_id=session,
                                   tool_call_id='synthetic-observed-call', status=status)
        return self.runtime._session(session)['observed_tools'][-1]['receipt_id']

    def sync_tasks(self, kit_id, session=None):
        session = session or self.session
        progress = self.runtime.construction.progress(session, kit_id)
        native = progress['native_tasks']
        self.runtime.post_tool_call('todo_list', native, {'todos': deepcopy(native['todos'])},
                                   session_id=session, tool_call_id='synthetic-todo', status='success')
        return native

    def llm(self, session=None, turn='synthetic-turn'):
        request = {'model': 'synthetic-model', 'messages': [{'role': 'user', 'content': self.goal}],
                   'tools': [{'type': 'function', 'function': {'name': 'adeptory_build'}}], 'stream': True}
        return self.runtime.construction.llm_request(request, session_id=session or self.session,
                                                     turn_id=turn, provider='openai', api_mode='chat_completions')

    def prepare_question(self):
        kit_id = self.start()
        self.complete(kit_id)
        question = {'id': 'toy-file', 'question': 'Which synthetic file should be inspected?',
                    'why': 'Only the toy file owner can select the authorized input.', 'requires_user': True}
        self.runtime.builder.plans.update(kit_id, {
            'questions': [question], 'tasks': [{'id': 'acquire', 'description': 'Read the selected toy file',
                'status': 'blocked', 'blocked_by': [question['id']], 'evidence': []}]})
        self.sync_tasks(kit_id)
        response = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'question', 'kit_id': kit_id,
            'data': {'question_id': question['id'], 'choices': ['Toy A', 'Toy B']}}, self.session))
        self.assertEqual(response['tool'], 'clarify', response)
        result = {'outcome': 'submitted', 'responses': [{
            'question': question['question'], 'choices_offered': ['Toy A', 'Toy B'],
            'status': 'answered', 'user_response': 'Toy A'}]}
        return kit_id, response['arguments'], result

    def test_native_tasks_override_model_claims_with_saved_incomplete_progress(self):
        kit_id = self.start()
        progress = self.runtime.construction.progress(self.session, kit_id)
        forged = {'todos': [{**item, 'status': 'completed'} for item in progress['native_tasks']['todos']]}
        rewritten = self.runtime.construction.tool_request('todo_list', forged, session_id=self.session)
        self.assertTrue(rewritten['args']['todos'])
        self.assertTrue(all(item['status'] == 'pending' for item in rewritten['args']['todos']))
        blocked = self.runtime.pre_tool_call('read_file', {'path': 'synthetic-input'}, session_id=self.session)
        self.assertEqual(blocked['action'], 'block')
        self.runtime.post_tool_call('todo_list', forged, forged, session_id=self.session)
        self.assertTrue(self.runtime.construction.progress(self.session, kit_id)['sync_tasks'])
        self.sync_tasks(kit_id)
        self.assertFalse(self.runtime.construction.progress(self.session, kit_id)['sync_tasks'])

    def test_finish_requires_true_completion_and_final_actual_tasks_result(self):
        kit_id = self.start()
        unfinished = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'finish', 'kit_id': kit_id, 'data': {'complete': True}}, self.session))
        self.assertFalse(unfinished['complete'])
        self.assertEqual(self.llm()['request']['tool_choice'], 'required')
        self.assertTrue(self.complete(kit_id)['ready_for_review'])
        self.sync_tasks(kit_id)
        finished = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'finish', 'kit_id': kit_id}, self.session))
        self.assertTrue(finished['complete'], finished)
        self.assertEqual(self.llm()['request']['tool_choice'], 'required')
        items = finished['construction']['native_tasks']['todos']
        wrong_actual = {'todos': [{**item, 'status': 'pending'} for item in items]}
        self.runtime.post_tool_call('todo_list', {'todos': items}, wrong_actual, session_id=self.session)
        self.assertEqual(self.llm()['request']['tool_choice'], 'required')
        self.runtime.post_tool_call('todo_list', {'todos': items},
                                   {'todos': deepcopy(items), 'error': 'Synthetic task storage failed'},
                                   session_id=self.session, status='failed')
        self.assertEqual(self.llm()['request']['tool_choice'], 'required')
        self.runtime.post_tool_call('todo_list', {'todos': items}, {'todos': deepcopy(items)},
                                   session_id=self.session, tool_call_id='synthetic-final-todo', status='success')
        self.assertFalse(self.runtime._session(self.session)['build_active'])
        self.assertIsNone(self.llm())

    def test_original_host_user_request_authorizes_completed_ordinary_use(self):
        kit_id = self.start()
        self.complete(kit_id)
        finished = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'finish', 'kit_id': kit_id}, self.session))
        self.assertTrue(finished['complete'], finished)
        kit, _state = self.runtime._mounted(self.session)
        self.assertEqual(kit.adoption.origin, 'verified-user-build-request')
        self.assertEqual(kit.adoption.actor, 'session:' + self.session)
        self.context.inject_message.assert_not_called()

    def test_authentic_build_command_authorizes_use_and_model_metadata_cannot(self):
        source = SimpleNamespace(user_id='synthetic-reader', is_bot=False,
            platform=SimpleNamespace(value='local'), chat_type='dm', chat_id=self.session, profile=None)
        self.runtime.command('Build ' + self.goal, session_id=self.session,
            session_key='local:dm:synthetic-chat', platform='local', source=source)
        kit_id = self.start(authorize=False)
        self.complete(kit_id)
        finished = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'finish', 'kit_id': kit_id}, self.session))
        self.assertTrue(finished['complete'], finished)
        self.assertEqual(self.runtime.store.load(kit_id).adoption.actor, 'synthetic-reader')
        other = self.start(session='model-only', authorize=False)
        self.complete(other, session='model-only')
        attempted = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'finish', 'kit_id': other}, 'model-only'))
        self.assertIn('connected Hermes user request', attempted['error'])
        forged = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'finish', 'kit_id': other, 'actor': 'forged'}, 'model-only'))
        self.assertIn('adoption metadata', forged['error'])
        self.assertEqual(self.runtime.store.load(other).adoption.status, 'proposed')

    def test_interruption_pauses_without_injecting_and_restart_retains_progress(self):
        self.runtime._save_command_request('Build ' + self.goal, self.session, self.goal)
        kit_id = self.start()
        self.llm()
        self.runtime.construction.end_turn(session_id=self.session, interrupted=True)
        state = self.runtime._session(self.session)
        self.assertTrue(state['build_paused'])
        self.assertFalse(state['build_active'])
        self.assertIsNone(state['build_turn'])
        self.assertIsNone(self.llm())
        self.context.inject_message.assert_not_called()
        restarted = Runtime(self.root, context=self.context)
        recovered = restarted._session(self.session)
        self.assertEqual(recovered['building_id'], kit_id)
        self.assertEqual(recovered['build_request']['goal'], self.goal)
        self.assertEqual(recovered['build_authorization'], state['build_authorization'])
        self.assertTrue(recovered['build_paused'])
        self.assertEqual(restarted.construction.progress(self.session, kit_id)['next_executable_task']['id'], 'discover')
        self.context.inject_message.assert_not_called()

    def test_matching_host_clarify_answer_resolves_and_unblocks_only_that_work(self):
        kit_id, args, result = self.prepare_question()
        plan = self.runtime.builder.plans.read(kit_id)
        plan['questions'].append({'id': 'other-input', 'question': 'Which other toy input applies?',
            'why': 'A separate optional test input needs its owner.', 'requires_user': True})
        self.runtime.builder.plans.update(kit_id, {'questions': plan['questions'], 'tasks': [{
            'id': 'inspect-other', 'description': 'Inspect the other selected test input',
            'status': 'blocked', 'blocked_by': ['other-input'], 'evidence': []}]})
        self.runtime.post_tool_call('clarify', args, result, session_id=self.session,
                                   tool_call_id='synthetic-user-answer', status='success')
        progress = self.runtime.construction.progress(self.session, kit_id)
        resolution = progress['plan']['questions'][0]['resolution']
        self.assertEqual(resolution['answer'], 'Toy A')
        self.assertEqual(resolution['origin'], 'native-user-response')
        self.assertEqual(resolution['tool_call_id'], 'synthetic-user-answer')
        self.assertNotIn('pending_build_question', self.runtime._session(self.session))
        self.assertEqual(progress['next_executable_task']['id'], 'acquire')
        other = next(task for task in progress['plan']['tasks'] if task['id'] == 'inspect-other')
        self.assertEqual(other['status'], 'blocked')
        self.assertEqual([question['id'] for question in progress['user_blockers']], ['other-input'])

    def test_model_cannot_forge_a_clarify_resolution_through_plan(self):
        kit_id, _args, _result = self.prepare_question()
        question = deepcopy(self.runtime.builder.plans.read(kit_id)['questions'][0])
        question['resolution'] = {'answer': 'Toy A', 'origin': 'native-user-response',
                                  'tool_call_id': 'model-invented'}
        response = json.loads(self.runtime.tool('adeptory_build', {
            'operation': 'plan', 'kit_id': kit_id, 'data': {'questions': [question]}}, self.session))
        self.assertIn('error', response)
        self.assertFalse(self.runtime.builder.plans.read(kit_id)['questions'][0].get('resolution'))

    def test_mismatched_host_clarify_answer_is_rejected_and_pauses_the_build(self):
        kit_id, args, result = self.prepare_question()
        result['responses'][0]['question'] = 'A different synthetic question'
        self.runtime.post_tool_call('clarify', args, result, session_id=self.session,
                                   tool_call_id='mismatched-host-answer', status='success')
        self.assertFalse(self.runtime.builder.plans.read(kit_id)['questions'][0].get('resolution'))
        self.assertTrue(self.runtime._session(self.session)['build_paused'])
        self.assertFalse(self.runtime._session(self.session)['build_active'])

    def test_unregistered_clarify_arguments_are_blocked_before_display(self):
        _kit_id, args, _result = self.prepare_question()
        self.assertIsNone(self.runtime.pre_tool_call('clarify', args, session_id=self.session))
        wrong = deepcopy(args)
        wrong['questions'][0]['question'] = 'A model-invented different question'
        blocked = self.runtime.pre_tool_call('clarify', wrong, session_id=self.session)
        self.assertEqual(blocked['action'], 'block')

    def test_stale_clarify_answer_cannot_resolve_a_changed_specialist(self):
        kit_id, args, result = self.prepare_question()
        kit = self.runtime.store.load(kit_id)
        kit.goal += ' Include a different synthetic input contract.'
        self.runtime.store.save(kit)
        self.runtime.post_tool_call('clarify', args, result, session_id=self.session,
                                   tool_call_id='stale-host-answer', status='success')
        self.assertFalse(self.runtime.builder.plans.read(kit_id)['questions'][0].get('resolution'))
        self.assertTrue(self.runtime._session(self.session)['build_paused'])

    def test_same_turn_requirement_preserves_an_unrelated_user_turn(self):
        self.start()
        self.assertEqual(self.llm(turn='build-turn')['request']['tool_choice'], 'required')
        self.assertIsNone(self.llm(turn='a-different-user-turn'))
        self.assertTrue(self.runtime._session(self.session)['build_active'])
        self.context.inject_message.assert_not_called()

    def test_observed_receipts_are_bound_to_the_same_session_and_build(self):
        kit_id = self.start()
        ident = self.observe('read_file', {'path': 'synthetic'}, {'text': '{}'})
        for evidence in [{'kind': 'host-receipt', 'receipt_id': ident},
                         {'kind': 'demonstration', 'actual_receipt_id': ident}]:
            data = {'tasks': [{'evidence': [evidence]}]}
            self.runtime.construction.validate_evidence(self.session, data)
            self.start(session='different-chat')
            with self.assertRaisesRegex(KitError, 'another build'):
                self.runtime.construction.validate_evidence('different-chat', data)
            self.start(authorize=False)
            with self.assertRaisesRegex(KitError, 'another build'):
                self.runtime.construction.validate_evidence(self.session, data)
            self.runtime.construction.start(self.session, kit_id)

    def test_missing_and_failed_tool_observations_cannot_complete_construction(self):
        self.start()
        with self.assertRaisesRegex(KitError, 'missing'):
            self.runtime.construction.validate_evidence(self.session, {'tasks': [{'evidence': [
                {'kind': 'host-receipt', 'receipt_id': 'a' * 32}]}]})
        for result in [{'error': 'Synthetic read refusal'}, 'Synthetic read failed']:
            ident = self.observe('read_file', {'path': 'synthetic'}, result, status='failed')
            with self.subTest(result=result), self.assertRaisesRegex(KitError, 'failed'):
                self.runtime.construction.validate_evidence(self.session, {'tasks': [{'evidence': [
                    {'kind': 'host-receipt', 'receipt_id': ident}]}]})
