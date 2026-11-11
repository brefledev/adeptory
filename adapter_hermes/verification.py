"""Read a completed native task from its observed CLI invocation and stream."""
import json
from pathlib import PureWindowsPath
import shlex

try:
    from ..core.model import KitError
except ImportError:
    from core.model import KitError


def native_task_result(record, profile_name):
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
    if not isinstance(output, dict) or output.get('exit_code', output.get('returncode')) != 0:
        raise KitError('Wait for the native verification command to finish with exit_code 0.')
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
            or not results[0].get('session_id') or not str(results[0].get('text', '')).strip()
            or not any(event.get('type') == 'tool_result' for event in events)):
        raise KitError('Retain a successful native task result with its session ID and observed tool results; CLI usage text cannot verify a specialist.')
    return results[0]['text']
