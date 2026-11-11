"""User-submitted requests start one host turn; setup preserves the original brief."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from adapter_hermes.conversation import start_reply
from adapter_hermes.runtime import Runtime


class AutomaticReplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = SimpleNamespace(platform=SimpleNamespace(value='local'), chat_type='dm',
                                      chat_id='chat', user_id='reader', is_bot=False)
        self.args = dict(session_id='chat', session_key='local:dm:chat', platform='local', source=self.source)

    def test_first_request_immediately_starts_one_agent_turn(self):
        ctx = SimpleNamespace(inject_message=Mock(return_value=True))
        runtime = Runtime(self.home, context=ctx)
        output = runtime.command('Build a specialist for my business', **self.args)
        self.assertIn('Welcome to Adeptory', output)
        self.assertIn('starting your specialist', output)
        self.assertNotIn('Continue', output)
        ctx.inject_message.assert_called_once_with(
            'Use Adeptory to build this specialist from my request:\n\na specialist for my business',
            session_key='local:dm:chat')

    def test_bare_command_welcomes_and_pending_request_resumes_once(self):
        ctx = SimpleNamespace(inject_message=Mock(return_value=True))
        runtime = Runtime(self.home, context=ctx)
        output = runtime.command('', **self.args)
        self.assertIn('Welcome to Adeptory', output)
        self.assertIn('Describe the job', output)
        ctx.inject_message.assert_not_called()
        runtime._save_command_request('Build my saved brief', 'chat', 'my saved brief')
        runtime = Runtime(self.home, context=ctx)
        self.assertIn('starting your specialist', runtime.command('', **self.args))
        runtime.command('', **self.args)
        ctx.inject_message.assert_called_once()

    def test_operator_can_allow_replies_once_without_retyping_the_request(self):
        ctx = SimpleNamespace(inject_message=Mock(side_effect=[False, True]),
                              ask_choice=Mock(return_value='allow'), profile_name='example')
        with patch('adapter_hermes.conversation.shutil.which', return_value='hermes'), patch(
                'adapter_hermes.conversation.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            started, error = start_reply(ctx, self.home, 'my full brief', **self.args)
        self.assertTrue(started)
        self.assertIsNone(error)
        self.assertEqual(run.call_args.args[0][-6:],
                         ['-p', 'example', 'config', 'set',
                          'plugins.entries.adeptory.allow_gateway_injection', 'true'])
        self.assertEqual(ctx.inject_message.call_count, 2)
        self.assertEqual(ctx.inject_message.call_args_list[0], ctx.inject_message.call_args_list[1])

    def test_declined_permission_keeps_the_saved_request_and_reports_the_gap(self):
        ctx = SimpleNamespace(inject_message=Mock(return_value=False), ask_choice=Mock(return_value='decline'))
        runtime = Runtime(self.home, context=ctx)
        output = runtime.command('Build my full brief', **self.args)
        self.assertIn('Automatic replies remain off', output)
        self.assertEqual(runtime._session('chat')['build_request']['goal'], 'my full brief')
        self.assertNotIn('starting your specialist', output)
