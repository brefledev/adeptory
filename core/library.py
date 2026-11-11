"""Profile-owned, portable knowledge with intact evidence and retrieval context."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from weakref import WeakValueDictionary

from .model import KitError, valid_id
from .provenance import timestamp_valid

SEARCH_STOPWORDS = set('a an the to for from and or of in on with this that my your please can could would '
                      'should help me you i it its is are was were be as at by we our using use want need '
                      'does do how what why'.split())

_WRITER_LOCKS = WeakValueDictionary()
_WRITER_LOCKS_GUARD = threading.Lock()


class _LibraryWriterLock:
    def __init__(self, root):
        self.root = root
        self.thread = threading.RLock()
        self.depth = 0
        self.connection = None

    def __enter__(self):
        self.thread.acquire()
        try:
            if self.depth == 0:
                self.root.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(self.root / '.adeptory-writer.sqlite', timeout=30)
                try:
                    connection.execute('BEGIN IMMEDIATE')
                except BaseException:
                    connection.close()
                    raise
                self.connection = connection
            self.depth += 1
            return self
        except BaseException:
            self.thread.release()
            raise

    def __exit__(self, *error):
        try:
            self.depth -= 1
            if self.depth == 0:
                self.connection.close()
                self.connection = None
        finally:
            self.thread.release()


def _writer_lock(root):
    with _WRITER_LOCKS_GUARD:
        lock = _WRITER_LOCKS.get(root)
        if lock is None:
            lock = _LibraryWriterLock(root)
            _WRITER_LOCKS[root] = lock
        return lock


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def required_text(data, *keys):
    for key in keys:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise KitError(f'{key} must be nonempty text')


class KnowledgeLibrary:
    """A library belongs to one Hermes profile; searches stay inside one specialist."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = _writer_lock(self.root)
        self.on_change = None

    def fingerprint(self, kit_id):
        state = self.state(kit_id)
        ignored = {'captured_at', 'retrieved_at', 'updated_at', 'receipt', 'revision'}
        content = {key: {identity: {k: v for k, v in record.items() if k not in ignored}
                         for identity, record in state[key].items()}
                   for key in ('documents', 'entries')}
        return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode('utf8')).hexdigest()

    def directory(self, kit_id):
        path = self.root / valid_id(kit_id)
        if not path.resolve().is_relative_to(self.root):
            raise KitError('library path escapes profile')
        return path

    def state(self, kit_id):
        path = self.directory(kit_id) / 'manifest.json'
        return json.loads(path.read_text(encoding='utf8')) if path.exists() else {
            'schema_version': 1, 'kit_id': kit_id, 'documents': {}, 'entries': {}}

    def _save(self, kit_id, state, changed=None):
        base = self.directory(kit_id)
        atomic_json(base / 'manifest.json', state)
        db = sqlite3.connect(base / 'index.sqlite')
        try:
            columns = [row[1] for row in db.execute('pragma table_info(knowledge)')]
            if columns and 'kind' not in columns:
                db.execute('drop table knowledge')
            rebuild = changed is None or not columns or 'kind' not in columns
            db.execute('create virtual table if not exists knowledge using fts5(id UNINDEXED,title,aliases,body,kind UNINDEXED)')
            if rebuild:
                db.execute('delete from knowledge')
            else:
                db.execute('delete from knowledge where id = ? and kind = ?', (changed[1], changed[0]))
            documents = state['documents'].values() if rebuild else (
                [state['documents'][changed[1]]] if changed[0] == 'document' else [])
            entries = state['entries'].values() if rebuild else (
                [state['entries'][changed[1]]] if changed[0] == 'entry' else [])
            for document in documents:
                db.execute('insert into knowledge values(?,?,?,?,?)',
                           (document['id'], document['title'], document.get('role', ''),
                            self._original(kit_id, document), 'document'))
            for entry in entries:
                db.execute('insert into knowledge values(?,?,?,?,?)',
                           (entry['id'], entry['title'], ' '.join(entry.get('aliases', [])),
                            json.dumps(entry, ensure_ascii=False), 'entry'))
            db.commit()
        finally:
            db.close()
        affected = set(state['entries']) if rebuild else {
            entry['id'] for entry in state['entries'].values()
            if changed == ('entry', entry['id']) or any(
                ref['document_id'] == changed[1] for ref in entry.get('sources', []))}
        while True:
            dependents = {entry['id'] for entry in state['entries'].values()
                          if any(dep in affected for dep in entry.get('dependencies', []))}
            if dependents <= affected:
                break
            affected.update(dependents)
        for entry in state['entries'].values():
            if entry['id'] in affected:
                self._write_entry(kit_id, entry['id'], state)
        lines = ['# Specialist library', '', f"Specialist: {kit_id}", '',
                 'Read entries through adeptory_library search/read so source state and conditions travel with the answer.', '',
                 '## Sources', '']
        lines += [f"- {d['title']} — `{d['id']}` ({d['role']}); {d['url']}" for d in state['documents'].values()]
        lines += ['', '## Knowledge and procedures', '']
        for e in state['entries'].values():
            folder = 'procedures' if e['kind'] == 'procedure' else 'examples' if e['kind'] == 'example' else 'references'
            lines.append(f"- [{e['title']}]({folder}/{e['id']}.md) — {e['kind']}")
        lines += ['', '## Maintenance', '',
                  'Retrieval reports source review dates, changes and applicability gaps. Recheck dated requirements before consequential use.',
                  'Original source text is preserved under sources/blobs; authored entries cite exact source passages.', '']
        if (base / 'capability-roadmap.md').is_file():
            lines += ['## Capabilities', '',
                      '[Capability roadmap](capability-roadmap.md) records available tools, planned work and the improvement cycle.', '']
        (base / '_index.md').write_text('\n'.join(lines), encoding='utf8')
        navigation = ['# Profile library', '', 'Each specialist owns its source-backed knowledge and maintenance record.', '']
        for manifest in sorted(self.root.glob('*/manifest.json')):
            if manifest.is_symlink() or not manifest.resolve().is_relative_to(self.root):
                continue
            other = json.loads(manifest.read_text(encoding='utf8'))
            navigation.append(f"- [{other.get('goal', other['kit_id'])}]({other['kit_id']}/_index.md) — "
                              f"{len(other['documents'])} sources, {len(other['entries'])} knowledge entries")
        (self.root / '_index.md').write_text('\n'.join(navigation) + '\n', encoding='utf8')

    def initialize(self, kit_id, goal, subject):
        with self.lock:
            state = self.state(kit_id)
            state.update(goal=goal, subject=subject)
            self._save(kit_id, state)

    def write_capability_roadmap(self, kit):
        """Render the current capability records without changing knowledge evidence."""
        with self.lock:
            base = self.directory(kit.id)
            base.mkdir(parents=True, exist_ok=True)
            capabilities = kit.to_dict()['capabilities']
            cycle = [
                'After useful work, identify a missing tool or procedure that would improve this specialist\'s goal.',
                'Add or revise its capability record with inputs, outputs, access, setup and a verification method. Preserve working capabilities.',
                'Build or configure the improvement through authorized host tools. Keep consequential access and external actions under host permissions.',
                'Run the stated check against independent expected evidence. Save actual input, output, comparison, date and artifact locations in the library.',
                'Record available readiness after that check succeeds. Keep failed or untested work in its appropriate planned state and record the next action.'
            ]
            data = {'schema_version': 1, 'kit_id': kit.id, 'kit_version': kit.version,
                    'goal': kit.goal, 'capabilities': capabilities,
                    'verification_limit': 'Readiness is a recorded assessment. Calling a capability verified requires an observed test result retained in the library.',
                    'improvement_cycle': cycle}
            atomic_json(base / 'capability-roadmap.json', data)
            lines = ['# Capability roadmap', '', f'Specialist: {kit.subject}', '',
                     f'Goal: {kit.goal}', '', f'Package version: {kit.version}', '',
                     'This roadmap is derived from the specialist package capability records. '
                     'Update those records with adeptory_propose so this roadmap stays current.', '',
                     data['verification_limit'], '']
            for title, records in (
                    ('Available capabilities', [c for c in capabilities if c['readiness'] == 'available']),
                    ('Work to build or configure', [c for c in capabilities if c['readiness'] != 'available'])):
                lines.extend(['## ' + title, ''])
                if not records:
                    lines.extend(['No capabilities recorded in this group.', ''])
                for item in records:
                    lines.extend(['### ' + item['id'], '', 'Recorded readiness: ' + item['readiness'], '',
                                  item['why'], '', 'Inputs: ' + ', '.join(item['inputs']), '',
                                  'Outputs: ' + ', '.join(item['outputs']), '',
                                  'Access: ' + ', '.join(item['access']), '',
                                  'Verification method: ' + item['verification'], ''])
                    if item['setup']:
                        lines.extend(['Setup work:', ''] + ['- ' + step for step in item['setup']] + [''])
            lines.extend(['## Continuing improvement', ''] +
                         [f'{number}. {step}' for number, step in enumerate(cycle, 1)] + [''])
            (base / 'capability-roadmap.md').write_text('\n'.join(lines), encoding='utf8')
            navigation = base / '_index.md'
            if navigation.is_file():
                text = navigation.read_text(encoding='utf8')
                if '(capability-roadmap.md)' not in text:
                    navigation.write_text(text + '\n## Capabilities\n\n'
                                          '[Capability roadmap](capability-roadmap.md) records available tools, '
                                          'planned work and the improvement cycle.\n', encoding='utf8')
            return data

    def document(self, kit_id, data):
        data = deepcopy(data)
        if data.get('import_path'):
            incoming = (self.root / 'imports' / data.pop('import_path')).resolve()
            if not incoming.is_relative_to((self.root / 'imports').resolve()) or incoming.is_symlink():
                raise KitError('source imports must stay within this profile library/imports')
            imported = incoming.read_bytes()
            data['text'] = imported.decode('utf-8-sig')
            data.setdefault('receipt', {})['import_file_sha256'] = hashlib.sha256(imported).hexdigest()
        required_text(data, 'id', 'url', 'title', 'text', 'role', 'retrieved_at', 'retrieval_tool', 'authority')
        valid_id(data['id'])
        if data['role'] not in {'governing', 'instructional', 'technical', 'reference', 'worked-example', 'user'}:
            raise KitError('unsupported source role')
        if not timestamp_valid(data['retrieved_at']):
            raise KitError('retrieved_at must be an ISO date or timestamp')
        for key in ('published_at', 'effective_from', 'effective_until', 'review_after'):
            if data.get(key) is not None and not timestamp_valid(data[key]):
                raise KitError(f'{key} must be an ISO date or timestamp, or null')
        if not isinstance(data.get('limitations', []), list):
            raise KitError('limitations must be a list')
        if not isinstance(data.get('receipt', {}), dict):
            raise KitError('receipt must be an object')
        if data.get('license') is not None and not isinstance(data['license'], str):
            raise KitError('license must be text or null')
        digest = hashlib.sha256(data['text'].encode('utf8')).hexdigest()
        with self.lock:
            state = self.state(kit_id)
            old = state['documents'].get(data['id'])
            document = deepcopy(data)
            document.pop('text')
            document.setdefault('capture_scope', 'unknown')
            document.setdefault('authority_type', 'unclassified')
            document.setdefault('normative_force', 'unverified')
            document.update(sha256=digest, text_path=f'sources/blobs/{digest}.txt',
                            captured_at=now(), capture_status='host-reported',
                            revision=(old or {}).get('revision', 0) + (0 if old and old['sha256'] == digest else 1))
            base = self.directory(kit_id)
            blob = base / document['text_path']
            blob.parent.mkdir(parents=True, exist_ok=True)
            if not blob.exists():
                blob.write_bytes(data['text'].encode('utf8'))
            if old and old != document:
                atomic_json(base / 'sources' / 'history' / f"{data['id']}-{old['sha256']}.json", old)
            state['documents'][data['id']] = document
            self._save(kit_id, state, ('document', document['id']))
            if self.on_change:
                self.on_change(kit_id)
            return {k: v for k, v in document.items() if k != 'receipt'}

    def entry(self, kit_id, data):
        required_text(data, 'id', 'title', 'content', 'kind', 'applicability')
        valid_id(data['id'])
        if data['kind'] not in {'reference', 'procedure', 'diagnostic', 'law', 'example'}:
            raise KitError('unsupported knowledge kind')
        for key in ('sources', 'aliases', 'exceptions', 'dependencies', 'gaps'):
            if not isinstance(data.get(key, []), list):
                raise KitError(f'{key} must be a list')
            if key != 'sources' and any(not isinstance(v, str) for v in data.get(key, [])):
                raise KitError(f'{key} must contain text')
        if not data.get('sources') and not data.get('inference'):
            raise KitError('source-backed entries need exact passage references; label independent inference explicitly')
        with self.lock:
            state = self.state(kit_id)
            entry = deepcopy(data)
            for dep in entry.get('dependencies', []):
                if dep == data['id'] or dep not in state['entries']:
                    raise KitError('dependencies must reference existing different entries')
                pending, seen = [dep], set()
                while pending:
                    current = pending.pop()
                    if current == data['id']:
                        raise KitError('knowledge dependencies must remain acyclic')
                    if current not in seen:
                        seen.add(current)
                        pending.extend(state['entries'][current].get('dependencies', []))
            evidence = []
            for ref in entry.get('sources', []):
                if not isinstance(ref, dict):
                    raise KitError('each source reference must be an object')
                required_text(ref, 'document_id', 'passage', 'locator')
                source = state['documents'].get(ref['document_id'])
                if source is None:
                    raise KitError('entry refers to an unknown document')
                text = self._original(kit_id, source)
                if ref['passage'] not in text:
                    raise KitError('cited passage must occur exactly in the captured document')
                evidence.append({**ref, 'source_sha256': source['sha256']})
            entry['sources'] = evidence
            entry['updated_at'] = now()
            entry['support_status'] = 'authored-passages-linked'
            state['entries'][entry['id']] = entry
            self._save(kit_id, state, ('entry', entry['id']))
            if self.on_change:
                self.on_change(kit_id)
            return self.read(kit_id, entry['id'])

    def _write_entry(self, kit_id, entry_id, state):
        entry = self._entry_context(state, entry_id)
        folder = 'procedures' if entry['kind'] == 'procedure' else 'examples' if entry['kind'] == 'example' else 'references'
        path = self.directory(kit_id) / folder / (entry['id'] + '.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# {entry['title']}", '', entry['content'], '',
                 '## Applicability', '', entry['applicability'], '',
                 'Source status below was computed when this file was written. '
                 'Use adeptory_library read for current review dates and dependency status.', '']
        for key in ('aliases', 'exceptions', 'dependencies_context', 'gaps', 'sources',
                    'source_states', 'changed_sources', 'review_required', 'evidence_limit'):
            if key in entry:
                lines += ['## ' + key.replace('_', ' ').capitalize(), '',
                          json.dumps(entry[key], ensure_ascii=False, indent=2), '']
        path.write_text('\n'.join(lines), encoding='utf8')

    def _original(self, kit_id, document):
        path = (self.directory(kit_id) / document['text_path']).resolve()
        if not path.is_relative_to(self.directory(kit_id).resolve()):
            raise KitError('source text path escapes specialist library')
        text = path.read_bytes().decode('utf8')
        if hashlib.sha256(text.encode('utf8')).hexdigest() != document['sha256']:
            raise KitError('captured source integrity check failed')
        return text

    def source_state(self, source, at=None):
        at = at or datetime.now(timezone.utc)
        result = {'id': source['id'], 'url': source['url'], 'title': source['title'],
                  'role': source['role'], 'authority': source['authority'],
                  'retrieved_at': source['retrieved_at'], 'sha256': source['sha256'],
                  'limitations': source.get('limitations', []), 'capture_status': source['capture_status']}
        for key in ('jurisdiction', 'published_at', 'effective_from', 'effective_until', 'review_after', 'license'):
            result[key] = source.get(key)
        result['capture_scope'] = source.get('capture_scope', 'unknown')
        result['authority_type'] = source.get('authority_type', 'unclassified')
        result['normative_force'] = source.get('normative_force', 'unverified')
        result['authority_limit'] = 'Publisher identity, source role and captured text alone do not establish legal force or professional consensus.'
        due = source.get('review_after')
        result['freshness'] = 'review-date-unknown'
        if due:
            parsed = datetime.fromisoformat(due.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            result['freshness'] = 'review-due' if at >= parsed else 'within-declared-review-window'
        result['freshness_limit'] = 'A retrieval or review date alone does not establish current legal or technical validity.'
        return result

    def document_read(self, kit_id, document_id, offset=0, limit=12000):
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20000:
            raise KitError('source window requires nonnegative offset and limit 1-20000 characters')
        source = self.state(kit_id)['documents'].get(document_id)
        if source is None:
            raise KitError('unknown library document')
        text = self._original(kit_id, source)
        return {'source': self.source_state(source), 'text': text[offset:offset + limit],
                'window': {'offset': offset, 'returned_chars': len(text[offset:offset + limit]),
                           'total_chars': len(text), 'next_offset': offset + limit if offset + limit < len(text) else None},
                'context': 'This is an explicit source window. Consult adjoining sections for dependent definitions and exceptions.'}

    def read(self, kit_id, entry_id):
        return self._entry_context(self.state(kit_id), entry_id)

    def _entry_context(self, state, entry_id):
        if entry_id not in state['entries']:
            raise KitError('unknown library entry')
        entry = deepcopy(state['entries'][entry_id])
        entry['source_states'] = []
        entry['changed_sources'] = []
        for ref in entry.get('sources', []):
            source = state['documents'][ref['document_id']]
            entry['source_states'].append(self.source_state(source))
            if ref['source_sha256'] != source['sha256']:
                entry['changed_sources'].append(source['id'])
        entry['dependencies_context'] = [self._dependency(state, dep) for dep in entry.get('dependencies', [])]
        entry['review_required'] = bool(entry['changed_sources']) or any(
            s['freshness'] == 'review-due' for s in entry['source_states']) or any(
            dependency['review_required'] for dependency in entry['dependencies_context'])
        entry['evidence_limit'] = 'Exact passage linkage verifies attribution; substantive claim support needs separate review.'
        return entry

    def _dependency(self, state, entry_id):
        item = state['entries'][entry_id]
        sources = [state['documents'][ref['document_id']] for ref in item.get('sources', [])]
        changed = [ref['document_id'] for ref in item.get('sources', [])
                   if ref['source_sha256'] != state['documents'][ref['document_id']]['sha256']]
        source_states = [self.source_state(source) for source in sources]
        dependencies = [self._dependency(state, dependency) for dependency in item.get('dependencies', [])]
        return {'id': entry_id, 'title': item['title'], 'content': item['content'],
                'applicability': item['applicability'], 'exceptions': item.get('exceptions', []),
                'sources': item.get('sources', []), 'dependencies': item.get('dependencies', []),
                'source_states': source_states, 'changed_sources': changed,
                'dependencies_context': dependencies,
                'review_required': bool(changed) or any(s['freshness'] == 'review-due' for s in source_states)
                                   or any(dependency['review_required'] for dependency in dependencies),
                'retrieval': 'Use read on this ID for current source states and further dependencies.'}

    def search(self, kit_id, query, limit=5):
        if type(limit) is not int or not 1 <= limit <= 10:
            raise KitError('search limit must be between 1 and 10')
        words = [word for word in re.findall(r'[\w-]+', query) if word.lower() not in SEARCH_STOPWORDS]
        if not words:
            return {'matches': [], 'coverage': self.status(kit_id),
                    'query_gap': 'Use a task, symptom, professional term, field or source title.'}
        path = self.directory(kit_id) / 'index.sqlite'
        if not path.exists():
            return {'matches': [], 'coverage': self.status(kit_id)}
        with self.lock:
            db = sqlite3.connect(path)
            try:
                columns = [row[1] for row in db.execute('pragma table_info(knowledge)')]
                if 'kind' not in columns:
                    db.close()
                    self._save(kit_id, self.state(kit_id))
                    db = sqlite3.connect(path)
                match = ' OR '.join('"' + word + '"' for word in words)
                rows = db.execute('select id,kind,snippet(knowledge,3,"[", "]","...",40) '
                                  'from knowledge where knowledge match ? '
                                  'order by case kind when \'entry\' then 0 else 1 end, '
                                  'bm25(knowledge,0,5,3,1,0) limit ?', (match, limit)).fetchall()
            finally:
                db.close()
            state = self.state(kit_id)
            matches = []
            for identity, kind, excerpt in rows:
                if kind == 'entry':
                    matches.append({**self.read(kit_id, identity), 'result_kind': 'entry',
                                    'read_parameters': {'operation': 'read', 'entry_id': identity}})
                else:
                    source = self.source_state(state['documents'][identity])
                    matches.append({'id': identity, 'title': source['title'], 'result_kind': 'document',
                                    'source_states': [source], 'review_required': True,
                                    'matching_excerpt': excerpt,
                                    'evidence_status': 'source-search lead; read the relevant source context and dependencies before drawing conclusions',
                                    'read_parameters': {'operation': 'document_read', 'document_id': identity}})
            return {'matches': matches,
                    'coverage': self.status(kit_id), 'method': 'SQLite FTS5 lexical search; qualified entries first, then source leads'}

    def status(self, kit_id):
        state = self.state(kit_id)
        return {'documents': len(state['documents']), 'entries': len(state['entries']),
                'directory': str(self.directory(kit_id)), 'imports_directory': str(self.root / 'imports'),
                'navigation': str(self.directory(kit_id) / '_index.md'),
                'capability_roadmap': str(self.directory(kit_id) / 'capability-roadmap.md')
                                      if (self.directory(kit_id) / 'capability-roadmap.md').is_file() else None,
                'source_roles': sorted({d['role'] for d in state['documents'].values()}),
                'review_due': [d['id'] for d in state['documents'].values()
                               if self.source_state(d)['freshness'] == 'review-due'],
                'coverage_limit': 'Counts describe captured material. Completeness requires the specialist build plan.'}

    def snapshot(self, kit_id):
        state = self.state(kit_id)
        return {**state, 'originals': {d['id']: self._original(kit_id, d) for d in state['documents'].values()}}

    def import_batch(self, kit_id, filename, limit=10):
        """Resume a prepared corpus without sending every document through model context."""
        if type(limit) is not int or not 1 <= limit <= 25:
            raise KitError('import batch limit must be between 1 and 25')
        path = (self.root / 'imports' / filename).resolve()
        if not path.is_relative_to((self.root / 'imports').resolve()) or path.is_symlink():
            raise KitError('corpus imports must stay within this profile library/imports')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        items = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(items, list):
            raise KitError('corpus must be an ordered list of document/entry items')
        job = self.directory(kit_id) / 'imports' / (digest + '.json')
        with self.lock:
            progress = json.loads(job.read_text(encoding='utf8')) if job.exists() else {
                'source_sha256': digest, 'cursor': 0, 'total': len(items), 'status': 'running'}
            end = min(progress['cursor'] + limit, len(items))
            while progress['cursor'] < end:
                item = items[progress['cursor']]
                try:
                    if not isinstance(item, dict) or item.get('kind') not in {'document', 'entry'}:
                        raise KitError('corpus item kind must be document or entry')
                    if item['kind'] == 'document':
                        self.document(kit_id, item['data'])
                    else:
                        self.entry(kit_id, item['data'])
                except (KitError, KeyError, TypeError, OSError) as exc:
                    progress.update(status='blocked', error=str(exc), updated_at=now())
                    atomic_json(job, progress)
                    return {**progress, 'library': self.status(kit_id)}
                progress.update(cursor=progress['cursor'] + 1, updated_at=now(), status='running')
                progress.pop('error', None)
                atomic_json(job, progress)
            progress['status'] = 'complete' if progress['cursor'] == len(items) else 'running'
            atomic_json(job, progress)
            return {**progress, 'library': self.status(kit_id)}
