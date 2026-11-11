"""Start the host's normal agent turn from a user-submitted build request."""
from pathlib import Path
import shutil
import subprocess
import sys


def start_reply(ctx, profile_home, brief, *, session_id, session_key, platform, source):
    if ctx is None or not callable(getattr(ctx, 'inject_message', None)):
        return False, 'Automatic replies require the connected Hermes plugin host.'
    message = 'Use Adeptory to build this specialist from my request:\n\n' + brief

    def send():
        return ctx.inject_message(message, session_key=session_key or None)

    if send():
        return True, None
    # The SDK gates automatic gateway turns with an operator-owned setting.
    # A direct local command may ask once; the native choice supplies consent.
    import yaml
    config_path = Path(profile_home) / 'config.yaml'
    config = yaml.safe_load(config_path.read_text(encoding='utf8')) if config_path.is_file() else {}
    entry = ((config or {}).get('plugins', {}).get('entries', {}).get('adeptory', {}))
    if entry.get('allow_gateway_injection') is True:
        return False, 'Hermes could not start the AI response. Your full request is saved.'
    local_user = (platform == 'local' and session_key and session_id
                  and getattr(getattr(source, 'platform', None), 'value', None) == 'local'
                  and getattr(source, 'chat_type', None) == 'dm'
                  and getattr(source, 'chat_id', None) == session_id
                  and bool(getattr(source, 'user_id', None))
                  and not getattr(source, 'is_bot', True))
    choose = getattr(ctx, 'ask_choice', None)
    if not local_user or not callable(choose):
        return False, 'Hermes needs permission for Adeptory to start AI replies. Your full request is saved.'
    consent = choose('Allow Adeptory to start an AI reply when you submit a specialist request? '
                     'It uses your current Hermes model and normal AI usage.',
                     [{'value': 'allow', 'label': 'Allow automatic replies'},
                      {'value': 'decline', 'label': 'Keep automatic replies off'}])
    if consent != 'allow':
        return False, 'Automatic replies remain off. Your full request is saved.'
    sibling = Path(sys.executable).with_name('hermes.exe' if sys.platform == 'win32' else 'hermes')
    executable = str(sibling) if sibling.is_file() else shutil.which('hermes')
    if not executable:
        return False, 'Hermes CLI is required to save the reply permission. Your full request is saved.'
    result = subprocess.run([executable, '-p', ctx.profile_name, 'config', 'set',
                             'plugins.entries.adeptory.allow_gateway_injection', 'true'],
                            capture_output=True, text=True, encoding='utf8', errors='replace', timeout=30)
    if result.returncode or not send():
        return False, 'Hermes could not start the AI response. Your full request is saved.'
    return True, None
