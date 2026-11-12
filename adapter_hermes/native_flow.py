"""Pure payload adapters for Hermes task display, tool use and human choices."""
from copy import deepcopy
import json
import re


# https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools#forcing-tool-use
_AUTO_TOOL_MODELS = re.compile(
    r'\bclaude-(?:(?:fable|mythos)-5-[12]|(?:opus|sonnet)-5-5)(?:[^0-9]|$)')


def _auto_tool_choice(request, mode):
    model = str(request.get('model') or request.get('modelId') or '').lower().replace('.', '-')
    if _AUTO_TOOL_MODELS.search(model):
        return True
    thinking = request.get('thinking')
    extra = request.get('additionalModelRequestFields' if mode == 'bedrock_converse' else 'extra_body')
    if thinking is None and isinstance(extra, dict):
        thinking = extra.get('thinking')
    return (mode in {'anthropic_messages', 'bedrock_converse'} or 'claude-' in model) and (
        isinstance(thinking, dict) and thinking.get('type') == 'enabled')


def task_items(progress):
    """Project the saved construction plan into the host's todo_list item shape."""
    statuses = {'pending': 'pending', 'running': 'in_progress',
                'complete': 'completed', 'blocked': 'pending'}
    kit_id = str(progress.get('kit_id') or '').strip()
    prefix = 'adeptory-' + (kit_id + '-' if kit_id else '')
    items = []
    for task in progress.get('plan', {}).get('tasks', []):
        ident = str(task['id'])
        description = str(task.get('description') or ident.replace('_', ' ').replace('-', ' ')).strip()
        if task.get('status') == 'blocked':
            description += ' (waiting)'
        items.append({'id': prefix + ident, 'content': description,
                      'status': statuses.get(task.get('status'), 'pending')})
    return items


def force_tool_use(request, provider='', api_mode=''):
    """Select supported tool use while preserving conversation messages for prompt caching."""
    rewritten = deepcopy(request)
    mode = api_mode or ('anthropic_messages' if provider == 'anthropic' else
                        'bedrock_converse' if provider == 'bedrock' else '')
    if mode == 'bedrock_converse':
        config = rewritten.get('toolConfig')
        if isinstance(config, dict) and isinstance(config.get('tools'), list) and config['tools']:
            auto = _auto_tool_choice(rewritten, mode)
            config['toolChoice'] = {'auto' if auto else 'any': {}}
    elif mode in {'', 'chat_completions', 'codex_responses', 'anthropic_messages'}:
        tools = rewritten.get('tools')
        if isinstance(tools, list) and tools:
            auto = _auto_tool_choice(rewritten, mode)
            choice = 'auto' if auto else 'any' if mode == 'anthropic_messages' else 'required'
            rewritten['tool_choice'] = {'type': choice} if mode == 'anthropic_messages' else choice
    return rewritten


def clarify_args(question, choices):
    """Build a single-choice question for the host's ordinary clarify tool."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError('a question is required')
    if (not isinstance(choices, (list, tuple)) or not 1 <= len(choices) <= 4
            or any(not isinstance(choice, str) or not choice.strip() for choice in choices)
            or len(set(choices)) != len(choices)):
        raise ValueError('provide one to four distinct text choices')
    return {'questions': [{'question': question, 'choices': list(choices)}]}


def submitted_answer(args, result, question, choices):
    """Match a host-returned clarify answer to a prepared decision.

    Callers must supply result from the trusted post_tool_call observation.
    A model-supplied object carries no human provenance by itself.
    """
    try:
        expected = clarify_args(question, choices)['questions'][0]
    except (TypeError, ValueError):
        return None
    if not isinstance(args, dict) or set(args) != {'questions'}:
        return None
    questions = args['questions']
    if not isinstance(questions, list) or len(questions) != 1 or not isinstance(questions[0], dict):
        return None
    asked = questions[0]
    if (set(asked) - {'question', 'choices', 'multi_select'}
            or asked.get('question') != expected['question']
            or asked.get('choices') != expected['choices']
            or ('multi_select' in asked and asked['multi_select'] is not False)):
        return None
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            return None
    if (not isinstance(result, dict) or 'error' in result
            or result.get('outcome') != 'submitted'):
        return None
    responses = result.get('responses')
    if not isinstance(responses, list) or len(responses) != 1 or not isinstance(responses[0], dict):
        return None
    response = responses[0]
    answer = response.get('user_response')
    if (response.get('status') == 'answered'
            and response.get('question') == expected['question']
            and response.get('choices_offered') == expected['choices']
            and isinstance(answer, str) and answer in expected['choices']):
        return answer
    return None
