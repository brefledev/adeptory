"""Resumable, evidence-linked specialist construction, independent of conversation history."""
from copy import deepcopy
import json

from .library import atomic_json, now, required_text
from .model import KitError, valid_id
from .provenance import timestamp_valid

PHASES = (
    ('discover', 'Identify governing authorities, technical references and suitable instructional material.'),
    ('acquire', 'Acquire relevant source sections with scope, dates, reuse terms and preserved originals.'),
    ('organize', 'Author searchable knowledge, procedures and worked examples with conditions and evidence attached.'),
    ('configure', 'Map and implement the authorized records, tools and setup needed for the selected work.'),
    ('demonstrate', 'Perform representative work and compare its result with independent evidence.'),
)
PHASE_IDS = {key for key, _description in PHASES}


def _phase_tasks(tasks, previous=()):
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise KitError('tasks must be a list of objects')
    ids = set()
    for task in tasks:
        valid_id(task.get('id'))
        if task['id'] in ids:
            raise KitError('duplicate build task ID')
        ids.add(task['id'])
    prior = {task.get('id'): task for task in previous if task.get('id') in PHASE_IDS}
    incoming = {task.get('id'): task for task in tasks if task.get('id') in PHASE_IDS}
    phases = [deepcopy(incoming.get(key, prior.get(key, {
        'id': key, 'description': description, 'status': 'pending', 'evidence': [], 'blocked_by': []})))
        for key, description in PHASES]
    delivery = {task['id']: task for task in previous if _delivery(task)}
    others = []
    for task in tasks:
        if task['id'] in PHASE_IDS:
            continue
        item = deepcopy(task)
        if task['id'] in delivery:
            prior = delivery[task['id']]
            if 'delivery' in item and item['delivery'] is not True:
                raise KitError('existing delivery task must retain delivery: true')
            if not _conditional(prior) and item.get('conditional'):
                raise KitError('required delivery task cannot be made conditional')
            item['delivery'] = True
            if _conditional(prior) and 'conditional' not in item:
                item.update(conditional=True, condition=prior['condition'])
        others.append(item)
    return phases + others + [deepcopy(task) for task_id, task in delivery.items() if task_id not in ids]


def _conditional(item):
    return (item.get('conditional') is True and isinstance(item.get('condition'), str)
            and bool(item['condition'].strip()) and item.get('id') not in PHASE_IDS)


def _delivery(task):
    return task.get('delivery') is True and task.get('id') not in PHASE_IDS


def _evidence_errors(task, state):
    evidence = task.get('evidence', [])
    if not isinstance(evidence, list) or not evidence:
        return ['completed build tasks require evidence']
    errors, kinds = [], set()
    for item in evidence:
        if not isinstance(item, dict):
            errors.append('task evidence must be typed document, entry, host-receipt or demonstration objects')
            continue
        kind = item.get('kind')
        if not isinstance(kind, str):
            errors.append('task evidence requires a text kind')
            continue
        kinds.add(kind)
        if kind == 'document':
            if not isinstance(item.get('id'), str) or item['id'] not in state['documents']:
                errors.append('task evidence refers to an uncaptured document')
        elif kind == 'entry':
            entry = state['entries'].get(item['id']) if isinstance(item.get('id'), str) else None
            if entry is None:
                errors.append('task evidence refers to an unknown library entry')
            elif task['id'] == 'organize' or task.get('phase') == 'organize':
                sources = entry.get('sources', [])
                if not sources or any(ref.get('document_id') not in state['documents']
                                      or ref.get('source_sha256') != state['documents'][ref['document_id']]['sha256']
                                      for ref in sources):
                    errors.append('organization requires an authored entry with current source links')
        elif kind == 'host-receipt':
            for key in ('tool', 'result', 'observed_at'):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append('host-receipt requires tool, result and observed_at')
                    break
            if not timestamp_valid(item.get('observed_at')):
                errors.append('host-receipt observed_at must be an ISO date or timestamp')
        elif kind == 'demonstration':
            for key in ('input', 'input_provenance', 'actual_result', 'expected_result',
                        'expected_provenance', 'comparison'):
                if not isinstance(item.get(key), str) or not item[key].strip():
                    errors.append('demonstration requires ' + key)
            if item.get('independent') is not True:
                errors.append('demonstration expected evidence must be independent: true')
            if item.get('passed') is not True:
                errors.append('completed demonstration requires passed: true')
        else:
            errors.append('task evidence kind must be document, entry, host-receipt or demonstration')
    phase = task['id'] if task['id'] in PHASE_IDS else task.get('phase')
    required = {'discover': {'document', 'host-receipt'}, 'acquire': {'document'},
                'organize': {'entry'}, 'configure': {'host-receipt'}, 'demonstrate': {'demonstration'}}
    if phase in required and not kinds.intersection(required[phase]):
        errors.append(phase + ' completion requires ' + ' or '.join(sorted(required[phase])) + ' evidence')
    return errors


class BuildPlan:
    def __init__(self, library):
        self.library = library

    def _path(self, kit_id):
        return self.library.directory(kit_id) / 'build-plan.json'

    def read(self, kit_id):
        path = self._path(kit_id)
        if path.exists():
            plan = json.loads(path.read_text(encoding='utf8'))
            plan['tasks'] = _phase_tasks(plan.get('tasks', []))
            return plan
        return {'kit_id': kit_id, 'outcomes': [], 'requirements': [], 'questions': [],
                'tasks': _phase_tasks([])}

    def update(self, kit_id, data):
        with self.library.lock:
            plan = self.read(kit_id)
            if not isinstance(data, dict):
                raise KitError('plan must be an object')
            if set(data) - {'outcomes', 'requirements', 'questions', 'tasks'}:
                raise KitError('plan fields: outcomes, requirements, questions, tasks')
            previous_tasks = plan['tasks']
            plan.update(deepcopy(data))
            plan['tasks'] = _phase_tasks(plan['tasks'], previous_tasks)
            for key in ('outcomes', 'requirements', 'questions', 'tasks'):
                if not isinstance(plan[key], list) or any(not isinstance(x, dict) for x in plan[key]):
                    raise KitError(f'{key} must be a list of objects')
            ids = set()
            for task in plan['tasks']:
                required_text(task, 'id', 'description', 'status')
                valid_id(task['id'])
                if task['id'] in ids:
                    raise KitError('duplicate build task ID')
                ids.add(task['id'])
                if task['status'] not in {'pending', 'running', 'blocked', 'complete'}:
                    raise KitError('unsupported task status')
                if not isinstance(task.get('blocked_by', []), list) or any(
                        not isinstance(item, str) or not item.strip() for item in task.get('blocked_by', [])):
                    raise KitError('task blocked_by must be a list of dependency IDs')
                if task.get('phase') is not None and task['phase'] not in PHASE_IDS:
                    raise KitError('task phase must name a mandatory construction phase')
                if 'delivery' in task and type(task['delivery']) is not bool:
                    raise KitError('task delivery must be boolean')
                if task.get('delivery') and task['id'] in PHASE_IDS:
                    raise KitError('mandatory construction phases cannot be delivery tasks')
                if 'conditional' in task and type(task['conditional']) is not bool:
                    raise KitError('task conditional must be boolean')
                if task.get('conditional'):
                    if task['id'] in PHASE_IDS:
                        raise KitError('mandatory construction phases cannot be conditional')
                    required_text(task, 'condition')
                if task['status'] == 'complete' and not task.get('evidence'):
                    raise KitError('completed build tasks require evidence')
            state = self.library.state(kit_id)
            for task in plan['tasks']:
                if task['status'] != 'complete':
                    continue
                errors = _evidence_errors(task, state)
                if errors:
                    raise KitError(task['id'] + ': ' + '; '.join(errors))
            for outcome in plan['outcomes']:
                required_text(outcome, 'id', 'description', 'acceptance')
                valid_id(outcome['id'])
            for requirement in plan['requirements']:
                required_text(requirement, 'id', 'purpose')
                valid_id(requirement['id'])
                if not isinstance(requirement.get('document_ids', []), list):
                    raise KitError('requirement document_ids must be a list')
                for doc_id in requirement.get('document_ids', []):
                    if doc_id not in state['documents']:
                        raise KitError('knowledge requirement refers to an uncaptured document')
                if 'conditional' in requirement and type(requirement['conditional']) is not bool:
                    raise KitError('requirement conditional must be boolean')
                if requirement.get('conditional'):
                    required_text(requirement, 'condition')
            for question in plan['questions']:
                required_text(question, 'id', 'question', 'why')
                valid_id(question['id'])
                if 'requires_user' in question and type(question['requires_user']) is not bool:
                    raise KitError('question requires_user must be boolean')
            plan['updated_at'] = now()
            atomic_json(self._path(kit_id), plan)
            return self.progress(kit_id)

    def progress(self, kit_id):
        plan = self.read(kit_id)
        library = self.library.status(kit_id)
        state = self.library.state(kit_id)
        unresolved = [r for r in plan['requirements'] if not r.get('document_ids')
                      and not r.get('exclusion_reason') and not _conditional(r)]
        completion_gaps, knowledge_gaps, completed = [], [], set()
        required = [task for task in plan['tasks'] if not _conditional(task)]
        knowledge_tasks = [task for task in required if not _delivery(task)]
        for task in plan['tasks']:
            task_gaps = []
            if task['status'] == 'complete':
                errors = _evidence_errors(task, state)
                if not errors:
                    completed.add(task['id'])
                elif not _conditional(task):
                    task_gaps.extend(task['id'] + ': ' + error for error in errors)
            elif not _conditional(task):
                task_gaps.append('Finish ' + task['id'] + ': ' + task['description'])
            completion_gaps.extend(task_gaps)
            if not _delivery(task):
                knowledge_gaps.extend(task_gaps)
        resolved = {q['id'] for q in plan['questions'] if q.get('resolution')}
        blocked = [task for task in required if task['id'] not in completed and (
            task['status'] == 'blocked' or any(dep not in completed | resolved for dep in task.get('blocked_by', [])))]
        blocked_ids = {task['id'] for task in blocked}
        next_task = next((task for task in required if task['id'] not in completed
                          and task['id'] not in blocked_ids), None)
        user_blockers = [q for q in plan['questions'] if q.get('requires_user') is True
                         and not q.get('resolution') and any(
                             q['id'] in task.get('blocked_by', []) or q.get('dependent_task') == task['id']
                             for task in blocked)]
        return {'kit_id': kit_id, 'plan': plan, 'library': library,
                'unresolved_requirements': unresolved,
                'conditional_requirements': [r for r in plan['requirements'] if _conditional(r)],
                'conditional_work': [task for task in plan['tasks'] if _conditional(task)],
                'delivery_tasks': [task for task in plan['tasks'] if _delivery(task)],
                'next_task': next_task, 'next_executable_task': next_task,
                'user_blockers': user_blockers, 'blocked_tasks': blocked,
                'completion_gaps': completion_gaps,
                'knowledge_completion_gaps': knowledge_gaps,
                'knowledge_complete': bool(knowledge_tasks) and all(
                    task['id'] in completed for task in knowledge_tasks),
                'required_tasks_complete': bool(required) and all(task['id'] in completed for task in required),
                'all_tasks_recorded_complete': bool(plan['tasks']) and all(
                    task['id'] in completed for task in plan['tasks']),
                'acceptance': 'Phase evidence records build completion; user adoption and affected-site results retain their own evidence.'}
