"""Durable build progress, native task projection and same-turn completion control."""
from datetime import datetime, timezone
import hashlib
import json
import uuid

from .native_flow import task_items, force_tool_use, clarify_args, submitted_answer

try:
    from ..core.library import atomic_json
    from ..core.model import KitError
except ImportError:
    from core.library import atomic_json
    from core.model import KitError


FIELDS = ('building_id', 'build_active', 'build_turn', 'build_paused', 'build_authorization',
          'native_task_signature', 'finish_requested', 'pending_build_question', 'observed_tools',
          'profile_name', 'profile_bundle', 'bundle_version', 'host_refusal', 'build_pause_reason')


class Construction:
    def __init__(self, root, builder, state):
        self.root, self.builder, self.state = root, builder, state

    def _path(self, session_id):
        key = hashlib.sha256(session_id.encode('utf8')).hexdigest()
        return self.root / 'build-sessions' / (key + '.json')

    def read(self, session_id):
        path = self._path(session_id)
        return json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}

    def save(self, session_id):
        state = self.state(session_id) if session_id else {}
        atomic_json(self._path(session_id), {k: state[k] for k in FIELDS if k in state})

    def start(self, session_id, kit_id):
        state = self.state(session_id)
        state.update(building_id=kit_id, build_active=True, build_paused=False,
                     build_turn=state.get('current_turn'), finish_requested=False)
        state.pop('native_task_signature', None)
        self.save(session_id)

    def progress(self, session_id, kit_id):
        progress = self.builder.plans.progress(kit_id)
        items = task_items(progress)
        state = self.state(session_id) if session_id else {}
        return {**progress, 'native_tasks': {'todos': items, 'merge': True},
                'sync_tasks': state.get('native_task_signature') != items,
                'profile_name': state.get('profile_name'), 'profile_bundle': state.get('profile_bundle'),
                'observed_tools': state.get('observed_tools', [])[-8:]}

    def llm_request(self, request, session_id=None, turn_id=None, provider='', api_mode='', **kwargs):
        if not session_id:
            return None
        state = self.state(session_id)
        state['current_turn'] = turn_id
        if not state.get('build_active') or state.get('build_paused'):
            return None
        if state.get('build_turn') not in (None, turn_id):
            return None
        state['build_turn'] = turn_id
        self.save(session_id)
        rewritten = force_tool_use(request, provider, api_mode)
        if rewritten == request:
            return None
        return {'request': rewritten, 'source': 'adeptory',
                'reason': 'Finish and verify the specialist before completing this build turn.'}

    def tool_request(self, tool_name, args, session_id=None, **kwargs):
        if tool_name not in {'todo_list', 'clarify'} or not session_id:
            return None
        state = self.state(session_id)
        if not state.get('build_active') or not state.get('building_id'):
            return None
        if tool_name == 'clarify':
            prepared = state.get('pending_build_question')
            if prepared:
                return {'args': clarify_args(prepared['question'], prepared['choices']),
                        'source': 'adeptory', 'reason': 'Ask the saved blocking question with native controls.'}
            return None
        progress = self.progress(session_id, state['building_id'])
        return {'args': progress['native_tasks'], 'source': 'adeptory',
                'reason': 'Display the saved build progress in the native Tasks panel.'}

    def pre_tool(self, tool_name, args, session_id):
        state = self.state(session_id)
        if not state.get('build_active') or not state.get('building_id'):
            return None
        progress = self.progress(session_id, state['building_id'])
        allowed = {'todo_list', 'tool_describe', 'tool_search'}
        if tool_name == 'adeptory_build' and args.get('operation') in {'status', 'progress'}:
            allowed.add(tool_name)
        if progress['sync_tasks'] and tool_name not in allowed:
            return {'action': 'block', 'message': 'Update the native Tasks panel first: call todo_list '
                    'with the native_tasks returned by adeptory_build progress. Then continue building.'}
        if tool_name == 'clarify' and not state.get('pending_build_question'):
            task = progress.get('next_executable_task')
            return {'action': 'block', 'message': ('Continue independent construction: ' + task['description'])
                    if task else 'Prepare the genuinely blocking question with adeptory_build question first.'}
        if tool_name == 'clarify' and state.get('pending_build_question'):
            prepared = state['pending_build_question']
            if args != clarify_args(prepared['question'], prepared['choices']):
                return {'action': 'block', 'message': 'Ask the saved blocking question with its prepared native clarify arguments.'}
        return None

    def question(self, session_id, kit_id, question_id, choices):
        progress = self.progress(session_id, kit_id)
        if progress.get('next_executable_task'):
            raise KitError('Continue independent construction before asking a blocking question: '
                           + progress['next_executable_task']['description'])
        question = next((q for q in progress['user_blockers'] if q['id'] == question_id), None)
        if question is None:
            raise KitError('the question must identify an unresolved user blocker in the saved plan')
        kit = self.builder.store.load(kit_id)
        prepared = {'kit_id': kit_id, 'version': kit.version,
                    'fingerprint': self.builder.library.fingerprint(kit_id),
                    'question_id': question_id, 'question': question['question'], 'choices': choices}
        call = clarify_args(prepared['question'], choices)
        self.state(session_id)['pending_build_question'] = prepared
        self.save(session_id)
        return {'tool': 'clarify', 'arguments': call, 'why': question['why']}

    def post_tool(self, tool_name, args, result, session_id, tool_call_id=None, status=None):
        state = self.state(session_id)
        if not state.get('build_active'):
            return
        try:
            value = json.loads(result) if isinstance(result, str) else result
        except (TypeError, ValueError):
            value = result
        if not state.get('building_id'):
            if status == 'blocked':
                detail = json.dumps(value, sort_keys=True, ensure_ascii=False)
                previous = state.get('host_refusal', {})
                count = previous.get('count', 0) + 1 if previous.get('detail') == detail else 1
                state['host_refusal'] = {'detail': detail, 'count': count}
                if count >= 2:
                    state.update(build_active=False, build_paused=True,
                                 build_pause_reason='The host repeatedly refused tool access. Your request is saved. '
                                 'Resolve the host response before resuming: ' + detail)
            else:
                state.pop('host_refusal', None)
            self.save(session_id)
            return
        kit_id = state['building_id']
        if tool_name == 'todo_list':
            if (status in {'failed', 'error', 'blocked', 'cancelled', 'interrupted'}
                    or (isinstance(value, dict) and value.get('error'))):
                return
            expected = task_items(self.builder.plans.progress(kit_id))
            actual = {item.get('id'): item for item in value.get('todos', [])} if isinstance(value, dict) else {}
            if all(actual.get(item['id']) == item for item in expected):
                state['native_task_signature'] = expected
                if state.get('finish_requested'):
                    state['build_active'] = False
            self.save(session_id)
            return
        if tool_name == 'clarify':
            if status in {'failed', 'error', 'blocked', 'cancelled', 'interrupted'}:
                state.update(build_active=False, build_paused=True)
                self.save(session_id)
                return
            prepared = state.get('pending_build_question')
            if prepared:
                kit = self.builder.store.load(kit_id)
                answer = submitted_answer(args, value, prepared['question'], prepared['choices'])
                current_question = next((q for q in self.builder.plans.read(kit_id)['questions']
                                         if q['id'] == prepared['question_id']), {})
                if (answer is not None and kit.version == prepared['version']
                        and current_question.get('question') == prepared['question']
                        and self.builder.library.fingerprint(kit_id) == prepared['fingerprint']):
                    plan = self.builder.plans.read(kit_id)
                    question = next(q for q in plan['questions'] if q['id'] == prepared['question_id'])
                    question['resolution'] = {'answer': answer, 'origin': 'native-user-response',
                                              'tool_call_id': tool_call_id}
                    resolved = {q['id'] for q in plan['questions'] if q.get('resolution')}
                    completed = {task['id'] for task in plan['tasks'] if task['status'] == 'complete'}
                    for task in plan['tasks']:
                        if (task['status'] == 'blocked' and prepared['question_id'] in task.get('blocked_by', [])
                                and all(dep in resolved | completed for dep in task.get('blocked_by', []))):
                            task['status'] = 'pending'
                    self.builder.plans.update(kit_id, {'questions': plan['questions'], 'tasks': plan['tasks']})
                    state.pop('pending_build_question', None)
                else:
                    state.update(build_active=False, build_paused=True)
            self.save(session_id)
            return
        if tool_name in {'adeptory_build', 'tool_describe', 'tool_search'}:
            return
        ident = uuid.uuid4().hex
        receipt = {'id': ident, 'kit_id': kit_id, 'session_id': session_id, 'tool': tool_name,
                   'args': args, 'result': value, 'tool_call_id': tool_call_id, 'status': status,
                   'observed_at': datetime.now(timezone.utc).isoformat()}
        atomic_json(self.root / 'build-observations' / (ident + '.json'), receipt)
        state.setdefault('observed_tools', []).append({'receipt_id': ident, 'tool': tool_name,
                                                      'observed_at': receipt['observed_at']})
        self.save(session_id)

    def validate_evidence(self, session_id, data):
        for task in data.get('tasks', []):
            for evidence in task.get('evidence', []):
                if evidence.get('kind') not in {'host-receipt', 'demonstration'}:
                    continue
                key = 'actual_receipt_id' if evidence['kind'] == 'demonstration' else 'receipt_id'
                ident = evidence.get(key)
                if not isinstance(ident, str) or len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
                    raise KitError(key + ' must identify an observed tool receipt from build progress')
                path = self.root / 'build-observations' / (ident + '.json')
                if not path.is_file():
                    raise KitError('the supporting tool observation is missing')
                record = json.loads(path.read_text(encoding='utf8'))
                if record['session_id'] != session_id or record['kit_id'] != self.state(session_id)['building_id']:
                    raise KitError('the supporting observation belongs to another build')
                if record.get('status') in {'failed', 'error', 'blocked', 'cancelled', 'interrupted'}:
                    raise KitError('a failed tool observation cannot complete construction')
                if isinstance(record['result'], dict) and record['result'].get('error'):
                    raise KitError('a failed tool observation cannot complete construction')

    def end_turn(self, session_id=None, turn_id=None, interrupted=False, completed=False, failed=False, **kwargs):
        if not session_id:
            return
        state = self.state(session_id)
        if turn_id and state.get('build_turn') not in (None, turn_id):
            return
        if state.get('build_active'):
            state.update(build_active=False, build_paused=True)
            state['build_turn'] = None
            self.save(session_id)
