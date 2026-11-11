"""Synthetic host payloads keep task display and human decisions consistent."""
from copy import deepcopy
import json
import unittest

from adapter_hermes.native_flow import clarify_args, force_tool_use, submitted_answer, task_items


class NativeTaskTests(unittest.TestCase):
    def test_tasks_preserve_order_and_map_each_construction_status(self):
        progress = {'kit_id': 'example', 'plan': {'tasks': [
            {'id': 'sources', 'description': 'Research reliable sources', 'status': 'complete'},
            {'id': 'procedures', 'description': 'Write usable procedures', 'status': 'running'},
            {'id': 'setup', 'description': 'Connect required tools', 'status': 'blocked'},
            {'id': 'demonstrate', 'description': 'Demonstrate useful work', 'status': 'pending'}]}}
        original = deepcopy(progress)
        items = task_items(progress)
        self.assertEqual([item['status'] for item in items],
                         ['completed', 'in_progress', 'pending', 'pending'])
        self.assertEqual(items[0], {'id': 'adeptory-example-sources',
                                   'content': 'Research reliable sources', 'status': 'completed'})
        self.assertEqual(items[2]['content'], 'Connect required tools (waiting)')
        self.assertEqual(progress, original)
        self.assertEqual(items, task_items(progress))

    def test_unknown_status_stays_pending_and_other_kits_keep_distinct_ids(self):
        plan = {'tasks': [{'id': 'read-source', 'status': 'invented'}]}
        a = task_items({'kit_id': 'first', 'plan': plan})
        b = task_items({'kit_id': 'second', 'plan': plan})
        self.assertNotEqual(a[0]['id'], b[0]['id'])
        self.assertEqual(a[0]['status'], 'pending')
        self.assertEqual(a[0]['content'], 'read source')
        self.assertEqual(task_items({}), [])


class ForcedToolTests(unittest.TestCase):
    def request(self):
        return {'model': 'example', 'messages': [{'role': 'user', 'content': 'Synthetic task'}],
                'tools': [{'type': 'function', 'function': {'name': 'example'}}],
                'stream': True, 'temperature': 0.2, 'extra_body': {'example': ['preserve']}}

    def test_openai_codex_and_gemini_preserve_payload_and_require_a_tool(self):
        for provider, mode in [('', ''), ('openai', 'chat_completions'),
                               ('openai-codex', 'codex_responses'), ('google', 'chat_completions')]:
            with self.subTest(provider=provider, mode=mode):
                original = self.request()
                updated = force_tool_use(original, provider=provider, api_mode=mode)
                self.assertEqual(updated['tool_choice'], 'required')
                self.assertEqual({k: v for k, v in updated.items() if k != 'tool_choice'}, original)
                updated['messages'][0]['content'] = 'Changed copy'
                updated['extra_body']['example'].append('new')
                self.assertEqual(original, self.request())

    def test_native_anthropic_uses_native_choice_and_preserves_thinking(self):
        request = self.request()
        request['thinking'] = {'type': 'adaptive'}
        for kwargs in [{'api_mode': 'anthropic_messages'}, {'provider': 'anthropic'}]:
            updated = force_tool_use(request, **kwargs)
            self.assertEqual(updated['tool_choice'], {'type': 'any'})
            self.assertEqual(updated['thinking'], request['thinking'])
        self.assertEqual(force_tool_use(request, provider='anthropic',
                                        api_mode='chat_completions')['tool_choice'], 'required')

    def test_bedrock_uses_native_tool_config_and_independent_copy(self):
        request = {'modelId': 'example', 'toolConfig': {'tools': [{'toolSpec': {'name': 'example'}}],
                                                     'toolChoice': {'auto': {}}},
                   'messages': [{'role': 'user', 'content': [{'text': 'Synthetic task'}]}]}
        original = deepcopy(request)
        updated = force_tool_use(request, api_mode='bedrock_converse')
        self.assertEqual(updated['toolConfig']['toolChoice'], {'any': {}})
        self.assertNotIn('tool_choice', updated)
        updated['toolConfig']['tools'][0]['toolSpec']['name'] = 'copy'
        self.assertEqual(request, original)

    def test_missing_tools_and_unknown_modes_preserve_the_payload(self):
        for tools in [None, [], '', {}]:
            request = self.request()
            request['tools'] = tools
            self.assertEqual(force_tool_use(request), request)
        for config in [None, {}, {'tools': []}]:
            request = {'toolConfig': config}
            self.assertEqual(force_tool_use(request, api_mode='bedrock_converse'), request)
        request = self.request()
        self.assertEqual(force_tool_use(request, api_mode='unsupported_native_mode'), request)


class HumanChoiceTests(unittest.TestCase):
    def setUp(self):
        self.question = 'Use this completed specialist?'
        self.choices = ['Use the specialist', 'Request changes']
        self.args = clarify_args(self.question, self.choices)
        self.result = {'outcome': 'submitted', 'responses': [{
            'question': self.question, 'choices_offered': self.choices.copy(),
            'status': 'answered', 'user_response': self.choices[0]}]}

    def answer(self, args=None, result=None):
        return submitted_answer(self.args if args is None else args,
                                self.result if result is None else result,
                                self.question, self.choices)

    def test_native_shape_is_independent_and_valid_answers_match(self):
        self.assertEqual(self.args, {'questions': [{'question': self.question, 'choices': self.choices}]})
        self.assertIsNot(self.args['questions'][0]['choices'], self.choices)
        self.assertEqual(self.answer(), self.choices[0])
        self.assertEqual(self.answer(result=json.dumps(self.result)), self.choices[0])
        self.result['responses'][0]['user_response'] = self.choices[1]
        self.assertEqual(self.answer(), self.choices[1])
        self.args['questions'][0]['multi_select'] = False
        self.assertEqual(self.answer(), self.choices[1])

    def test_unsubmitted_and_unanswered_results_supply_no_decision(self):
        for outcome in ['cancelled', 'timed_out', 'undelivered', '', None]:
            result = deepcopy(self.result)
            result['outcome'] = outcome
            self.assertIsNone(self.answer(result=result))
        for status in ['skipped', 'unanswered', '', None]:
            result = deepcopy(self.result)
            result['responses'][0]['status'] = status
            self.assertIsNone(self.answer(result=result))
        for value in [None, '', ['Use the specialist'], True, 'Use the specialist (Recommended)',
                      'Use the specialist ', 'use the specialist', 'Yes']:
            result = deepcopy(self.result)
            result['responses'][0]['user_response'] = value
            self.assertIsNone(self.answer(result=result))

    def test_mismatched_or_forged_question_and_offered_choices_are_rejected(self):
        for target in ['args', 'result']:
            for field, value in [('question', 'A different question'), ('choices', list(reversed(self.choices)))]:
                args, result = deepcopy(self.args), deepcopy(self.result)
                if target == 'args':
                    args['questions'][0][field] = value
                else:
                    result['responses'][0]['choices_offered' if field == 'choices' else field] = value
                self.assertIsNone(self.answer(args=args, result=result))
        args = deepcopy(self.args)
        args['questions'][0]['multi_select'] = True
        self.assertIsNone(self.answer(args=args))

    def test_malformed_payloads_and_extra_responses_are_rejected(self):
        for value in [[], {}, 'invalid JSON', 'null', '[]', {'outcome': 'submitted', 'responses': []},
                      {**self.result, 'error': 'Synthetic error'},
                      {**self.result, 'responses': self.result['responses'] * 2}]:
            self.assertIsNone(self.answer(result=value))
        for value in [{}, [], {'questions': []}, {'questions': [None]},
                      {'questions': self.args['questions'] * 2}, {**self.args, 'user_response': self.choices[0]}]:
            self.assertIsNone(self.answer(args=value))

    def test_question_factory_rejects_ambiguous_or_empty_choices(self):
        for question, choices in [('', self.choices), (None, self.choices), (self.question, []),
                                  (self.question, ['']), (self.question, ['same', 'same']),
                                  (self.question, ['1', '2', '3', '4', '5'])]:
            with self.assertRaises(ValueError):
                clarify_args(question, choices)


if __name__ == '__main__':
    unittest.main()
