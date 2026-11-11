"""Read a completed native task from its observed CLI invocation and stream."""
import json
from pathlib import Path, PureWindowsPath
import shlex

try:
    from ..core.model import KitError
except ImportError:
    from core.model import KitError


def native_profile_name(command):
    if not isinstance(command, str):
        return None
    try:
        tokens = [part.strip('\"\'') for part in shlex.split(command, posix=False)]
    except ValueError:
        return None
    if tokens and tokens[0] == '&':
        tokens.pop(0)
    if (len(tokens) >= 4 and PureWindowsPath(tokens[0]).name.lower() in {'hermes', 'hermes.exe'}
            and tokens[1] in {'-p', '--profile'} and tokens[3] == 'chat'):
        return tokens[2]
    return None


def native_task_result(record, profile_name, *, completion=None, profile_home=None, retained_path=None):
    error = 'Run the returned verification_cli directly with --query or --query-file and retain its complete stream-json result.'
    command = record.get('args', {}).get('command')
    if record.get('tool') != 'terminal' or not isinstance(command, str):
        raise KitError(error)
    try:
        tokens = [part.strip('\"\'') for part in shlex.split(command, posix=False)]
    except ValueError as exc:
        raise KitError(error) from exc
    if tokens and tokens[0] == '&':
        tokens.pop(0)
    output_path = None
    if '>' in tokens:
        redirect = tokens.index('>')
        if redirect != len(tokens) - 2 or profile_home is None:
            raise KitError(error)
        output_path = Path(tokens[-1])
        workspace = Path(profile_home) / 'workspace'
        if (not output_path.is_absolute() or not output_path.resolve().is_relative_to(workspace.resolve())
                or not output_path.is_file()):
            raise KitError('Native verification output must be retained inside the builder profile workspace.')
        tokens = tokens[:redirect]
    if (len(tokens) < 5 or PureWindowsPath(tokens[0]).name.lower() not in {'hermes', 'hermes.exe'}
            or tokens[1] not in {'-p', '--profile'} or tokens[2:4] != [profile_name, 'chat']):
        raise KitError(error)
    values, index = {}, 4
    while index < len(tokens):
        flag = tokens[index]
        if flag == '--oneshot':
            values[flag] = True
            index += 1
        elif flag in {'--format', '--query', '-q', '--query-file'} and index + 1 < len(tokens):
            if flag in values:
                raise KitError(error)
            values[flag] = tokens[index + 1]
            index += 2
        else:
            raise KitError(error)
    if (values.get('--format') != 'stream-json' or not values.get('--oneshot')
            or sum(bool(values.get(key)) for key in ('--query', '-q', '--query-file')) != 1):
        raise KitError(error)
    output = record.get('result')
    if completion is not None:
        process_id = output.get('session_id') if isinstance(output, dict) else None
        finished = completion.get('result')
        if (not process_id or completion.get('tool') not in {'process_manage', 'process'}
                or completion.get('args', {}).get('session_id') != process_id
                or completion.get('args', {}).get('action') not in {'wait', 'poll', 'log'}
                or not isinstance(finished, dict) or finished.get('session_id') != process_id
                or finished.get('status') not in {'exited', 'completed'}
                or finished.get('command', command) != command):
            raise KitError('Use the completed host process receipt belonging to the original native verification invocation.')
        output = finished
    if not isinstance(output, dict) or output.get('exit_code', output.get('returncode')) != 0:
        raise KitError('Wait for the native verification command to finish with exit_code 0.')
    if output_path is not None:
        if output_path.stat().st_size > 50 * 1024 * 1024:
            raise KitError('Native verification transcript exceeds 50 MiB; use a focused representative task.')
        raw = output_path.read_bytes()
        text = raw.decode('utf16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    else:
        text = output.get('output', output.get('stdout', ''))
    events = []
    for line in str(text).splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    results = [event for event in events if event.get('type') == 'result']
    if (len(results) != 1 or results[0].get('exit_code') != 0 or results[0].get('error')
            or not results[0].get('session_id') or not isinstance(results[0].get('text'), str)
            or not results[0]['text'].strip()
            or not any(event.get('type') == 'tool_result' for event in events)):
        raise KitError('Retain a successful native task result with its session ID and observed tool results; CLI usage text cannot verify a specialist.')
    if retained_path is not None:
        retained_path = Path(retained_path)
        retained_path.parent.mkdir(parents=True, exist_ok=True)
        retained_path.write_bytes(text.encode('utf8'))
    return results[0]['text']
