"""Provider-shaped requests exercise documented model and thinking restrictions."""
from copy import deepcopy
import unittest

from adapter_hermes.native_flow import force_tool_use


class ModelToolChoiceTests(unittest.TestCase):
    def request(self, model, thinking=None):
        request = {
            'model': model,
            'system': [{'type': 'text', 'text': 'Build the requested specialist.'}],
            'messages': [{'role': 'user', 'content': 'Build a CSV specialist.'}],
            'tools': [{'name': 'adeptory_build', 'description': 'Build a specialist.',
                       'input_schema': {'type': 'object', 'properties': {}}}],
            'max_tokens': 4096,
        }
        if thinking is not None:
            request['thinking'] = thinking
        return request

    def test_restricted_models_use_auto_with_a_build_instruction(self):
        for model in ['claude-opus-5-5', 'claude-sonnet-5-5',
                      'claude-fable-5-1', 'claude-fable-5-2',
                      'claude-mythos-5-1', 'claude-mythos-5-2']:
            for thinking in [None, {'type': 'disabled'}, {'type': 'adaptive'}]:
                with self.subTest(model=model, thinking=thinking):
                    request = self.request(model, thinking)
                    original = deepcopy(request)
                    updated = force_tool_use(request, api_mode='anthropic_messages')
                    self.assertEqual(updated['tool_choice'], {'type': 'auto'})
                    self.assertIn('adeptory_build finish', updated['messages'][-1]['content'])
                    self.assertEqual(updated['tools'], request['tools'])
                    self.assertEqual(updated['system'], request['system'])
                    self.assertEqual(request, original)
                    if thinking:
                        self.assertEqual(updated['thinking'], thinking)

    def test_model_aliases_dates_and_provider_prefixes_keep_the_restriction(self):
        for model in ['anthropic/claude-opus-5.5', 'claude-sonnet-5-5-20261101',
                      'us.anthropic.claude-sonnet-5-5-v1:0',
                      'claude-fable-5.2@20261101', 'claude-mythos-5-1']:
            with self.subTest(model=model):
                self.assertEqual(force_tool_use(self.request(model), provider='anthropic')['tool_choice'],
                                 {'type': 'auto'})

    def test_supported_models_keep_forced_tool_use(self):
        for model in ['claude-opus-5', 'claude-haiku-5-5', 'claude-sonnet-5',
                      'claude-opus-4-6', 'claude-sonnet-4-5-20250929']:
            with self.subTest(model=model):
                request = self.request(model, {'type': 'adaptive'})
                updated = force_tool_use(request, provider='anthropic')
                self.assertEqual(updated['tool_choice'], {'type': 'any'})
                self.assertEqual(updated['messages'], request['messages'])

    def test_manual_thinking_uses_auto_and_keeps_the_budget(self):
        request = self.request('claude-sonnet-4-5-20250929',
                               {'type': 'enabled', 'budget_tokens': 2048})
        updated = force_tool_use(request, api_mode='anthropic_messages')
        self.assertEqual(updated['tool_choice'], {'type': 'auto'})
        self.assertEqual(updated['thinking'], request['thinking'])
        self.assertEqual(updated['max_tokens'], request['max_tokens'])

    def test_tool_results_stay_first_and_rewriting_is_idempotent(self):
        request = self.request('claude-sonnet-5-5')
        result = {'type': 'tool_result', 'tool_use_id': 'call-1', 'content': 'Saved progress.'}
        request['messages'] = [{'role': 'user', 'content': [result]}]
        updated = force_tool_use(request, provider='anthropic')
        self.assertEqual(updated['messages'][0]['content'][0], result)
        self.assertEqual(updated['messages'][0]['content'][1]['type'], 'text')
        self.assertIn('next useful tool call', updated['messages'][0]['content'][1]['text'])
        self.assertEqual(force_tool_use(updated, provider='anthropic'), updated)
        self.assertEqual(request['messages'][0]['content'], [result])

    def test_assistant_last_receives_a_user_instruction(self):
        request = self.request('claude-opus-5-5')
        request['messages'] = [{'role': 'assistant', 'content': 'Sources acquired.'}]
        updated = force_tool_use(request, api_mode='anthropic_messages')
        self.assertEqual(updated['messages'][0], request['messages'][0])
        self.assertEqual(updated['messages'][-1]['role'], 'user')
        self.assertEqual(updated['messages'][-1]['content'][0]['type'], 'text')

    def test_claude_chat_completions_uses_compatible_auto(self):
        request = self.request('anthropic/claude-sonnet-5.5')
        updated = force_tool_use(request, api_mode='chat_completions')
        self.assertEqual(updated['tool_choice'], 'auto')
        self.assertIn('next useful tool call', updated['messages'][-1]['content'])
        manual = self.request('claude-sonnet-4-5-20250929')
        manual['extra_body'] = {'thinking': {'type': 'enabled', 'budget_tokens': 2048}}
        updated = force_tool_use(manual, api_mode='chat_completions')
        self.assertEqual(updated['tool_choice'], 'auto')
        self.assertEqual(updated['extra_body'], manual['extra_body'])

    def test_bedrock_model_and_thinking_use_native_auto_and_text_blocks(self):
        for model, thinking in [('us.anthropic.claude-sonnet-5-5-v1:0', None),
                                ('anthropic.claude-sonnet-4-5-v1:0',
                                 {'type': 'enabled', 'budget_tokens': 2048})]:
            with self.subTest(model=model):
                request = {'modelId': model,
                           'messages': [{'role': 'user', 'content': [{'toolResult': {
                               'toolUseId': 'call-1', 'content': [{'text': 'Saved progress.'}]}}]}],
                           'toolConfig': {'tools': [{'toolSpec': {'name': 'adeptory_build'}}]}}
                if thinking:
                    request['additionalModelRequestFields'] = {'thinking': thinking}
                original = deepcopy(request)
                updated = force_tool_use(request, api_mode='bedrock_converse')
                self.assertEqual(updated['toolConfig']['toolChoice'], {'auto': {}})
                self.assertEqual(updated['messages'][0]['content'][0], request['messages'][0]['content'][0])
                self.assertIn('next useful tool call', updated['messages'][0]['content'][1]['text'])
                self.assertNotIn('type', updated['messages'][0]['content'][1])
                self.assertEqual(request, original)
                self.assertEqual(force_tool_use(updated, api_mode='bedrock_converse'), updated)

    def test_absent_tools_and_unknown_modes_preserve_requests(self):
        request = self.request('claude-sonnet-5-5')
        request['tools'] = []
        self.assertEqual(force_tool_use(request, provider='anthropic'), request)
        request = self.request('claude-sonnet-5-5')
        self.assertEqual(force_tool_use(request, api_mode='unknown'), request)

    def test_non_claude_openai_requests_keep_required_choice(self):
        request = self.request('gpt-example', {'type': 'enabled'})
        updated = force_tool_use(request, api_mode='chat_completions')
        self.assertEqual(updated['tool_choice'], 'required')
        self.assertEqual(updated['messages'], request['messages'])


if __name__ == '__main__':
    unittest.main()
