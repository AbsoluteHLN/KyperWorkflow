"""Deterministic project map: files, imports, doc links, areas and memory payload."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from kyper_workflow import structure


def build(root):
    (root / 'pkg').mkdir()
    (root / 'pkg' / '__init__.py').write_text('"""Package doc."""\n', encoding='utf-8')
    (root / 'pkg' / 'core.py').write_text(
        '"""Core behaviour."""\nimport json\nfrom . import helper\n\n'
        'def run():\n    return helper.value\n\nclass Engine:\n    pass\n', encoding='utf-8')
    (root / 'pkg' / 'helper.py').write_text('value = 1\n', encoding='utf-8')
    (root / 'docs').mkdir()
    (root / 'docs' / 'guide.md').write_text(
        '# Guide\n\nSee [core](../pkg/core.py) and [site](https://example.org).\n', encoding='utf-8')
    (root / 'README.md').write_text('See [guide](docs/guide.md).\n', encoding='utf-8')
    (root / '.git').mkdir()
    (root / '.git' / 'config').write_text('ignored\n', encoding='utf-8')
    (root / 'pkg.egg-info').mkdir()
    (root / 'pkg.egg-info' / 'PKG-INFO').write_text('ignored\n', encoding='utf-8')


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        build(self.root)
        self.project = structure.scan(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def test_files_exclude_build_and_vcs_directories(self):
        paths = {entry['path'] for entry in self.project['files']}
        self.assertIn('pkg/core.py', paths)
        self.assertIn('README.md', paths)
        self.assertNotIn('.git/config', paths)
        self.assertFalse(any(path.startswith('pkg.egg-info') for path in paths))

    def test_python_imports_become_internal_edges(self):
        pairs = {(edge['from'], edge['to'], edge['kind']) for edge in self.project['edges']}
        self.assertIn(('pkg/core.py', 'pkg/helper.py', 'import'), pairs)

    def test_markdown_links_become_doc_edges_and_urls_are_ignored(self):
        pairs = {(edge['from'], edge['to'], edge['kind']) for edge in self.project['edges']}
        self.assertIn(('docs/guide.md', 'pkg/core.py', 'doc_link'), pairs)
        self.assertIn(('README.md', 'docs/guide.md', 'doc_link'), pairs)
        self.assertFalse(any('example.org' in edge['to'] for edge in self.project['edges']))

    def test_external_imports_are_recorded_not_linked(self):
        self.assertIn('json', self.project['external_imports'])
        self.assertFalse(any(edge['to'] == 'json' for edge in self.project['edges']))

    def test_symbols_and_docstring_are_captured(self):
        core = next(entry for entry in self.project['files'] if entry['path'] == 'pkg/core.py')
        self.assertEqual(core['doc'], 'Core behaviour.')
        self.assertEqual(core['symbols'], {'functions': 1, 'classes': 1})
        self.assertIn('Engine', core['names'])

    def test_areas_and_entry_points(self):
        self.assertEqual(sorted(self.project['areas']), ['(root)', 'docs', 'pkg'])
        self.assertEqual(self.project['entry_points'], [])
        self.assertEqual(self.project['name'], self.root.name)
        self.assertEqual(structure.scan(self.root, name='Demo')['name'], 'Demo')

    def test_markdown_is_deterministic_and_free_of_absolute_paths(self):
        first = structure.render_markdown(self.project)
        second = structure.render_markdown(structure.scan(self.root))
        self.assertEqual(first, second)
        self.assertNotIn(str(self.root), first)
        self.assertIn('## Feature relationships', first)
        self.assertIn('```mermaid', first)

    def test_digest_and_memory_payload_shape(self):
        text = structure.digest(self.project)
        self.assertIn('pkg', text)
        self.assertIn('Static analysis only', text)
        payload = structure.memory_payload(self.project)
        kinds = {entity['entityType'] for entity in payload['entities']}
        self.assertEqual(kinds, {'project', 'area', 'module'})
        relations = {relation['relationType'] for relation in payload['relations']}
        self.assertIn('contains', relations)
        self.assertIn('imports', relations)
        core = next(entity for entity in payload['entities'] if entity['name'] == 'pkg/core.py')
        self.assertIn('functions: 1', core['observations'])

    def test_serialized_map_carries_no_absolute_path(self):
        """Committed maps are shared; they must not reveal the operator's layout."""
        payload = structure.render_json(self.project)
        self.assertNotIn(str(self.root), payload)
        self.assertNotIn('"root"', payload)
        self.assertIn('"name"', payload)
        document = structure.render_markdown(self.project)
        for relative, text in structure.render_graph_exports(self.project).items():
            self.assertNotIn(str(self.root), text, relative)
        self.assertNotIn(str(self.root), structure.digest(self.project))

    def test_unparsable_file_is_reported_not_hidden(self):
        (self.root / 'pkg' / 'broken.py').write_text('def (\n', encoding='utf-8')
        project = structure.scan(self.root)
        broken = next(entry for entry in project['files'] if entry['path'] == 'pkg/broken.py')
        self.assertEqual(broken['parse_error'], 'SyntaxError')

    def test_file_limit_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'file limit'):
            structure.scan(self.root, max_files=1)

    def test_cli_writes_then_detects_staleness(self):
        run = lambda *args: subprocess.run([sys.executable, '-m', 'kyper_workflow.cli', 'map',
                                            '--root', str(self.root)] + list(args),
                                           capture_output=True, text=True,
                                           cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(run('--write').returncode, 0)
        self.assertTrue((self.root / 'docs' / 'PROJECT-MAP.md').is_file())
        data = json.loads((self.root / '.kyper' / 'project-map.json').read_text(encoding='utf-8'))
        self.assertEqual(data['name'], self.root.name)
        self.assertNotIn('docs/PROJECT-MAP.md', {entry['path'] for entry in data['files']})
        self.assertEqual(run('--check').returncode, 0)
        (self.root / 'pkg' / 'extra.py').write_text('extra = True\n', encoding='utf-8')
        self.assertEqual(run('--check').returncode, 1)


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        build(self.root)
        self.project = structure.scan(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def test_graph_nodes_are_files_and_edges_are_observed_links(self):
        model = structure.graph(self.project)
        ids = {node['id'] for node in model['nodes']}
        self.assertEqual(ids, {entry['path'] for entry in self.project['files']})
        self.assertIn({'from': 'pkg/core.py', 'to': 'pkg/helper.py', 'kind': 'import'},
                      model['edges'])
        for node in model['nodes']:
            self.assertTrue(node['color'].startswith('#'))
            self.assertEqual(node['area'],
                             node['id'].split('/')[0] if '/' in node['id'] else '(root)')
        self.assertEqual(model['stats']['nodes'], len(model['nodes']))
        self.assertEqual(model['stats']['total_edges'], len(self.project['edges']))

    def test_graph_collapse_keeps_both_endpoints(self):
        model = structure.graph(self.project, max_nodes=2, include_isolated=False)
        ids = {node['id'] for node in model['nodes']}
        self.assertLessEqual(len(ids), 2)
        self.assertTrue(all(edge['from'] in ids and edge['to'] in ids
                            for edge in model['edges']))
        self.assertGreater(model['omitted_nodes'], 0)

    def test_renders_are_deterministic_and_cover_the_same_graph(self):
        model = structure.graph(self.project)
        mermaid = '\n'.join(structure.render_graph_mermaid(self.project))
        exports = structure.render_graph_exports(self.project)
        self.assertEqual(exports, structure.render_graph_exports(structure.scan(self.root)))
        self.assertIn('```mermaid', mermaid)
        self.assertIn('subgraph g_pkg["pkg"]', mermaid)
        self.assertIn('g_pkg_core_py --> g_pkg_helper_py', mermaid)
        self.assertIn('g_docs_guide_md -.-> g_pkg_core_py', mermaid)
        self.assertIn('class g_pkg_core_py g_area_pkg;', mermaid)
        self.assertTrue(exports[structure.GRAPH_EXPORTS[0]].startswith('digraph '))
        self.assertIn('subgraph "cluster_pkg"', exports[structure.GRAPH_EXPORTS[0]])
        self.assertIn('<graphml', exports[structure.GRAPH_EXPORTS[1]])
        rows = exports[structure.GRAPH_EXPORTS[2]].strip().splitlines()
        self.assertEqual(rows[0], 'from\tto\tkind\tfrom_area\tto_area\tcount')
        self.assertEqual(len(rows) - 1, len(model['edges']))
        self.assertIn('pkg/core.py\tpkg/helper.py\timport\tpkg\tpkg\t1', rows)

    def test_graphml_is_well_formed_xml(self):
        import xml.etree.ElementTree as ET
        text = structure.render_graph_graphml(self.project)
        root = ET.fromstring(text)
        namespace = '{http://graphml.graphdrawing.org/xmlns}'
        nodes = root.findall('./%sgraph/%snode' % (namespace, namespace))
        edges = root.findall('./%sgraph/%sedge' % (namespace, namespace))
        self.assertEqual(len(nodes), len(structure.graph(self.project)['nodes']))
        self.assertEqual(len(edges), len(self.project['edges']))

    def test_reserved_word_area_names_stay_valid_mermaid(self):
        (self.root / 'end').mkdir()
        (self.root / 'end' / 'notes.md').write_text('# Notes\n\nSee [core](../pkg/core.py).\n',
                                                    encoding='utf-8')
        mermaid = '\n'.join(structure.render_graph_mermaid(structure.scan(self.root)))
        self.assertIn('subgraph g_end["end"]', mermaid)
        self.assertNotIn('\n  end["end"]', mermaid)
        for line in mermaid.splitlines():
            stripped = line.strip()
            if stripped.startswith('g_') and '["' not in stripped:
                self.assertNotEqual(stripped.split()[0], 'end')

    def test_mermaid_blocks_have_balanced_subgraphs(self):
        for project in (self.project, structure.scan(Path(__file__).resolve().parent.parent)):
            body = structure.render_graph_mermaid(project)
            self.assertEqual(body[0], '```mermaid')
            close = body.index('```')
            block = body[1:close]
            self.assertEqual(sum(1 for line in block if line.startswith('  subgraph ')),
                             sum(1 for line in block if line == '  end'))
            self.assertEqual(block[0], 'graph LR')

    def test_map_document_embeds_the_graph_and_is_stable(self):
        document = structure.render_markdown(self.project)
        self.assertEqual(document, structure.render_markdown(structure.scan(self.root)))
        self.assertIn('## Relationship graph', document)
        self.assertIn('### Area summary', document)
        self.assertIn('.kyper/project-graph.dot', document)
        self.assertEqual(document.count('```mermaid'), 2)

    def test_cli_graph_formats_and_staleness_covers_exports(self):
        run = lambda *args: subprocess.run([sys.executable, '-m', 'kyper_workflow.cli', 'map',
                                            '--root', str(self.root)] + list(args),
                                           capture_output=True, text=True,
                                           cwd=Path(__file__).resolve().parent.parent)
        model = json.loads(run('--graph').stdout)
        self.assertEqual(model['stats']['nodes'], len(model['nodes']))
        small = json.loads(run('--graph', '--max-nodes', '2').stdout)
        self.assertEqual(len(small['nodes']), 2)
        self.assertEqual(json.loads(run('--graph', '--graph-format', 'tsv').stdout)['tsv']
                         .strip().splitlines()[0], 'from\tto\tkind\tfrom_area\tto_area\tcount')
        self.assertEqual(run('--write').returncode, 0)
        for relative in structure.GRAPH_EXPORTS:
            self.assertTrue((self.root / relative).is_file(), relative)
        self.assertEqual(run('--check').returncode, 0)
        (self.root / '.kyper' / 'project-graph.tsv').write_text('tampered\n', encoding='utf-8')
        self.assertEqual(run('--check').returncode, 1)


if __name__ == '__main__':
    unittest.main()
