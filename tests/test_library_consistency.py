"""Independent writers retain data and dependency changes reach every reader."""
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from core.builder import Builder
from core.kitstore import KitStore
from core.library import KnowledgeLibrary


def document(identity, **changes):
    return {'id': identity, 'url': 'https://example.test/' + identity,
            'title': 'Synthetic ' + identity, 'text': 'The source requires recorded approval.',
            'role': 'technical', 'authority': 'Synthetic specification',
            'retrieved_at': '2026-11-11T00:00:00Z', 'retrieval_tool': 'synthetic-reader', **changes}


def write_from_process(root, kit_id, identity, ready, read, release, results):
    class PausedReadLibrary(KnowledgeLibrary):
        paused = False

        def state(self, selected):
            state = super().state(selected)
            if not self.paused:
                self.paused = True
                read.set()
                if not release.wait(15):
                    raise RuntimeError('The test did not release the paused writer.')
            return state

    try:
        library = PausedReadLibrary(Path(root) / 'library')
        Builder(KitStore(Path(root) / 'data'), library)
        ready.set()
        library.document(kit_id, document(identity))
        results.put(None)
    except BaseException as error:
        ready.set()
        results.put(repr(error))


class LibraryConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = KnowledgeLibrary(self.root / 'library')
        self.store = KitStore(self.root / 'data')
        self.builder = Builder(self.store, self.library)
        self.kit = self.builder.start('Review synthetic applications', 'Synthetic organization')

    def test_independent_process_writers_serialize_read_modify_index_and_version_binding(self):
        context = multiprocessing.get_context('spawn')
        first_ready, second_ready = context.Event(), context.Event()
        first_read, second_read = context.Event(), context.Event()
        first_release, second_release = context.Event(), context.Event()
        results = context.Queue()
        first = context.Process(target=write_from_process, args=(str(self.root), self.kit.id,
            'alpha', first_ready, first_read, first_release, results))
        second = context.Process(target=write_from_process, args=(str(self.root), self.kit.id,
            'beta', second_ready, second_read, second_release, results))
        first.start()
        second_started = False
        try:
            self.assertTrue(first_ready.wait(15))
            self.assertTrue(first_read.wait(15))
            second.start()
            second_started = True
            self.assertTrue(second_ready.wait(15))
            second_read_while_first_held = second_read.wait(0.5)
            first_release.set()
            first.join(15)
            self.assertFalse(first.is_alive())
            second_release.set()
            second.join(15)
            self.assertFalse(second.is_alive())
            self.assertEqual([results.get(timeout=2), results.get(timeout=2)], [None, None])
            state = self.library.state(self.kit.id)
            self.assertEqual(set(state['documents']), {'alpha', 'beta'})
            found = self.library.search(self.kit.id, 'Synthetic', limit=10)['matches']
            self.assertEqual({item['id'] for item in found}, {'alpha', 'beta'})
            kit = self.store.load(self.kit.id)
            self.assertEqual(kit.version, self.kit.version + 2)
            self.assertEqual(kit.scope['library_fingerprint'], self.library.fingerprint(kit.id))
            self.assertFalse(second_read_while_first_held)
        finally:
            first_release.set()
            second_release.set()
            for process in (first, second) if second_started else (first,):
                process.join(2)
                if process.is_alive():
                    process.terminate()
                    process.join(5)
            results.close()
            results.join_thread()

    def dependency_chain(self, **source_fields):
        source = document('rule', **source_fields)
        self.library.document(self.kit.id, source)
        self.library.entry(self.kit.id, {'id': 'leaf', 'title': 'Leaf procedure', 'kind': 'procedure',
            'content': 'Inspect the recorded approval.', 'applicability': 'Synthetic applications.',
            'sources': [{'document_id': 'rule', 'locator': 'Complete synthetic rule', 'passage': source['text']}]})
        for identity, dependency in [('middle', 'leaf'), ('top', 'middle')]:
            self.library.entry(self.kit.id, {'id': identity, 'title': identity + ' launchgate',
                'kind': 'procedure', 'content': 'Follow the prerequisite procedure before continuing.',
                'applicability': 'Synthetic applications.', 'inference': True,
                'dependencies': [dependency], 'sources': []})
        return source

    def test_independent_instances_allow_nested_writes_and_release_after_failure(self):
        other = KnowledgeLibrary(self.library.root)
        with self.assertRaisesRegex(RuntimeError, 'Synthetic interruption'):
            with self.library.lock:
                other.document(self.kit.id, document('alpha'))
                raise RuntimeError('Synthetic interruption')
        other.document(self.kit.id, document('beta'))
        self.assertEqual(set(self.library.state(self.kit.id)['documents']), {'alpha', 'beta'})

    def test_changed_source_flags_reach_transitive_reads_search_and_readable_files(self):
        source = self.dependency_chain()
        self.assertFalse(self.library.read(self.kit.id, 'top')['review_required'])
        self.library.document(self.kit.id, {**source, 'text': 'The source now requires two approvals.'})
        top = self.library.read(self.kit.id, 'top')
        self.assertTrue(top['review_required'])
        middle = top['dependencies_context'][0]
        self.assertTrue(middle['review_required'])
        self.assertTrue(middle['dependencies_context'][0]['review_required'])
        matches = self.library.search(self.kit.id, 'launchgate')['matches']
        self.assertTrue(all(item['review_required'] for item in matches))
        rendered = self.library.directory(self.kit.id) / 'procedures/top.md'
        self.assertIn('## Review required\n\ntrue', rendered.read_text(encoding='utf8'))

    def test_review_due_source_flags_reach_transitive_dependencies(self):
        self.dependency_chain(review_after='2000-01-01T00:00:00Z')
        top = self.library.read(self.kit.id, 'top')
        self.assertTrue(top['review_required'])
        self.assertTrue(top['dependencies_context'][0]['review_required'])
        self.assertEqual(top['dependencies_context'][0]['dependencies_context'][0]
                         ['source_states'][0]['freshness'], 'review-due')


if __name__ == '__main__':
    unittest.main()
