import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from adapter_hermes.runtime import register


class FakeContext:
    def __init__(self):
        self.tools, self.commands, self.hooks, self.skills = {}, {}, {}, {}
        self.middleware = {}

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def register_command(self, name, handler, description="", args_hint="", **kwargs):
        self.commands[name] = handler

    def register_hook(self, hook_name, callback, **kwargs):
        self.hooks[hook_name] = callback

    def register_skill(self, name, path, **kwargs):
        self.skills[name] = path

    def register_middleware(self, kind, callback):
        self.middleware[kind] = callback


class RegistrationTests(unittest.TestCase):
    def test_public_registration_and_tool_json_contract(self):
        with tempfile.TemporaryDirectory() as root:
            storage = types.ModuleType("plugins.plugin_storage")
            storage.plugin_data_dir = lambda name: Path(root) / name
            ctx = FakeContext()
            with patch.dict(sys.modules, {"plugins.plugin_storage": storage}):
                runtime = register(ctx)
            self.assertIn('adeptory_library', ctx.tools)
            self.assertEqual(set(ctx.commands), {"adeptory"})
            self.assertEqual(set(ctx.hooks), {"pre_llm_call", "pre_tool_call", "post_tool_call", 'on_session_end'})
            self.assertEqual(set(ctx.middleware), {'llm_request', 'tool_request'})
            self.assertTrue(ctx.skills["build"].is_file())
            self.assertFalse(runtime.fixture_harness)
            tool = ctx.tools["adeptory_build"]
            result = json.loads(tool["handler"]({"operation": "start", "goal": "Investigate a bounded task",
                                                 "subject": "synthetic-subject"}, session_id="one", future_key=True))
            self.assertEqual(result["adoption"]["status"], "proposed")
            self.assertIn("Describe the job", ctx.commands["adeptory"]("build", session_id="one", future_key=True))
            guidance = ctx.hooks["pre_llm_call"](session_id="one", user_message="redirect", future_key=True)
            self.assertIn("one step at a time", guidance["context"])
            self.assertEqual(runtime.store.list()[0].adoption.status, "proposed")


if __name__ == "__main__":
    unittest.main()
