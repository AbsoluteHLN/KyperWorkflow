"""Reusable roles and components: fail-closed validation, no hidden defaults."""
import json
import tempfile
import unittest
from pathlib import Path

from kyper_workflow import catalog


def task(**overrides):
    base = {'depends': [], 'writes': ['src/app.py'], 'acceptance': 'accepted',
            'required_checks': ['code'], 'code_mode': 'syntax',
            'complexity': 'standard'}
    base.update(overrides)
    return base


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.catalog = catalog.builtin()

    def tearDown(self):
        self.directory.cleanup()

    def test_builtin_roles_and_components_validate(self):
        self.assertGreaterEqual(len(self.catalog['roles']), 5)
        ids = {entry['id'] for entry in self.catalog['roles']}
        self.assertEqual(ids, {'explorer', 'implementer', 'test-author',
                               'reviewer', 'integrator'})
        for entry in self.catalog['roles']:
            self.assertTrue(entry['required_outputs'])
            self.assertGreaterEqual(entry['max_parallel'], 1)
        for entry in self.catalog['components']:
            self.assertGreaterEqual(entry['version'], 1)
            self.assertIn(entry['role'], ids)

    def test_read_only_roles_cannot_take_writes(self):
        reviewer = catalog.role(self.catalog, 'reviewer')
        with self.assertRaisesRegex(ValueError, 'outside role reviewer'):
            catalog.bind(task(writes=['src/app.py']), reviewer)
        explorer = catalog.role(self.catalog, 'explorer')
        with self.assertRaisesRegex(ValueError, 'outside role explorer'):
            catalog.bind(task(writes=['notes.md'], required_checks=['text'],
                              code_mode=None), explorer)

    def test_test_author_is_confined_to_tests(self):
        role = catalog.role(self.catalog, 'test-author')
        catalog.bind(task(writes=['tests/test_x.py'], code_mode='project_tests'), role)
        with self.assertRaisesRegex(ValueError, 'outside role test-author'):
            catalog.bind(task(writes=['kyper_workflow/cli.py'],
                              code_mode='project_tests'), role)

    def test_checks_and_code_mode_must_be_allowed(self):
        reviewer = catalog.role(self.catalog, 'reviewer')
        with self.assertRaisesRegex(ValueError, 'checks'):
            catalog.bind(task(required_checks=['code'], code_mode='syntax'), reviewer)
        implementer = catalog.role(self.catalog, 'implementer')
        with self.assertRaisesRegex(ValueError, 'code mode'):
            catalog.bind(task(code_mode=None, required_checks=['code']), implementer)

    def test_complexity_must_be_allowed(self):
        integrator = catalog.role(self.catalog, 'integrator')
        with self.assertRaisesRegex(ValueError, 'complexity'):
            catalog.bind(task(writes=['docs/guide.md'], required_checks=['text'],
                              code_mode=None, complexity='complex'), integrator)

    def test_every_builtin_component_instantiates(self):
        samples = {
            'code-change': {'behaviour': 'Handle empty input', 'paths': 'src/app.py'},
            'test-covered-change': {'behaviour': 'Handle empty input',
                                    'paths': ['src/app.py'], 'tests': ['tests/test_app.py']},
            'test-only': {'tests': ['tests/test_app.py'], 'covers': 'empty input'},
            'doc-sync': {'topic': 'the new flag', 'docs': ['docs/guide.md']},
            'review-only': {'target': 'the diff', 'aspects': 'error handling'},
            'investigation': {'question': 'Where is the config loaded?'},
        }
        self.assertEqual({entry['id'] for entry in self.catalog['components']},
                         set(samples))
        for component_id, params in sorted(samples.items()):
            rendered = catalog.instantiate(self.catalog, component_id,
                                           name='t-' + component_id, params=params)
            self.assertEqual(rendered['component'], component_id)
            self.assertTrue(rendered['acceptance'])
            self.assertNotIn('{{', rendered['acceptance'])
            self.assertTrue(rendered['role'])

    def test_component_renders_paths_and_normalizes_them(self):
        rendered = catalog.instantiate(
            self.catalog, 'code-change', name='t',
            params={'behaviour': 'Add a flag', 'paths': ['src\\app.py', 'src/util.py']})
        self.assertEqual(rendered['writes'], ['src/app.py', 'src/util.py'])
        self.assertIn('src/app.py, src/util.py', rendered['acceptance'])
        self.assertEqual(rendered['required_checks'], ['code'])
        self.assertEqual(rendered['code_mode'], 'syntax')

    def test_component_rejects_unknown_and_missing_parameters(self):
        with self.assertRaisesRegex(ValueError, 'Unknown parameters'):
            catalog.instantiate(self.catalog, 'code-change', name='t',
                                params={'behaviour': 'x', 'paths': 'a.py', 'extra': 'y'})
        with self.assertRaisesRegex(ValueError, 'Missing required parameters'):
            catalog.instantiate(self.catalog, 'code-change', name='t',
                                params={'behaviour': 'x'})
        with self.assertRaisesRegex(ValueError, 'Unknown component'):
            catalog.instantiate(self.catalog, 'no-such-component', name='t', params={})

    def test_component_rejects_unsafe_paths(self):
        for unsafe in ('../outside.py', '/abs/path.py', 'C:/Windows/system32/x.dll'):
            with self.assertRaises(ValueError, msg=unsafe):
                catalog.instantiate(self.catalog, 'code-change', name='t',
                                    params={'behaviour': 'x', 'paths': unsafe})

    def test_dependent_component_is_rejected_by_role_scope(self):
        """test-only writes tests/**, so its role and scope must agree."""
        rendered = catalog.instantiate(self.catalog, 'test-only', name='t',
                                       params={'tests': 'tests/test_a.py', 'covers': 'x'})
        self.assertEqual(rendered['writes'], ['tests/test_a.py'])
        self.assertEqual(rendered['role'], 'test-author')

    def test_subagent_card_is_portable_markdown(self):
        card = catalog.export_subagent(catalog.role(self.catalog, 'reviewer'))
        self.assertTrue(card.startswith('# KyperWorkflow role: Reviewer\n'))
        self.assertIn('Role id: `reviewer`', card)
        self.assertIn('Writes: none (read only)', card)
        self.assertIn('Path scopes remain a contract', card)

    def test_markdown_and_digest_are_deterministic(self):
        first = catalog.render_markdown(self.catalog)
        second = catalog.render_markdown(catalog.builtin())
        self.assertEqual(first, second)
        self.assertIn('| `explorer` |', first)
        self.assertIn('## Components', first)
        self.assertEqual(catalog.digest(self.catalog),
                         catalog.digest(catalog.builtin()))

    def test_file_catalog_overrides_by_id_and_rejects_unknown_sections(self):
        path = self.root / 'catalog.json'
        path.write_text(json.dumps({'roles': [{
            'id': 'reviewer', 'title': 'Strict reviewer', 'purpose': 'Stricter review.',
            'allowed_checks': ['text'], 'write_scopes': [], 'code_modes': [],
            'complexity': ['standard'], 'max_parallel': 1,
            'required_outputs': ['findings']}]}), encoding='utf-8')
        loaded = catalog.load(path)
        reviewer = catalog.role(loaded, 'reviewer')
        self.assertEqual(reviewer['title'], 'Strict reviewer')
        self.assertEqual(reviewer['max_parallel'], 1)
        self.assertTrue(catalog.role(loaded, 'explorer'))

        bad = self.root / 'bad.json'
        bad.write_text(json.dumps({'roles': [], 'surprise': 1}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unknown sections'):
            catalog.load(bad)

    def test_invalid_role_is_rejected_not_defaulted(self):
        path = self.root / 'catalog.json'
        path.write_text(json.dumps({'roles': [{
            'id': 'Bad Role', 'title': 'x', 'purpose': 'x',
            'allowed_checks': [], 'write_scopes': [], 'code_modes': [],
            'complexity': [], 'max_parallel': 0, 'required_outputs': []}]}),
            encoding='utf-8')
        with self.assertRaises(ValueError):
            catalog.load(path)


if __name__ == '__main__':
    unittest.main()
