"""Deterministic project structure map: files, imports, doc links and areas.

This is static analysis of local files only. It does not call a model, infer
semantics, store content fingerprints or claim that a dependency is correct.
Output is sorted and timestamp-free so a committed map is byte-stable and can
be checked for staleness in CI.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
             'node_modules', '.venv', 'venv', 'dist', 'build', 'htmlcov', '.kyper'}
MAX_FILES = 2000
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_MERMAID_NODES = 24
MAX_SYMBOLS_LISTED = 8
MAX_GRAPH_NODES = 40

# Fixed palettes so a rendered graph is byte-stable: colour depends on the
# position of an area in sorted order, never on insertion order.
GRAPH_STROKE = ('#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948',
                '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac')
GRAPH_FILL = ('#e8eef6', '#fdefe0', '#fbe7e7', '#e6f1f0', '#e7f2e5', '#faf3d9',
              '#f0e9f1', '#fdeef0', '#f1ebe4', '#f2f0ee')
GRAPH_ENTRY_STROKE = '#111111'

# Written next to the map so graphviz, Gephi or yEd can load the same graph
# without re-deriving it. They live under .kyper/, already skipped by the
# scanner, so the map never describes its own output.
GRAPH_EXPORTS = ('.kyper/project-graph.dot', '.kyper/project-graph.graphml',
                 '.kyper/project-graph.tsv')

LANGUAGES = {
    '.py': 'python', '.pyi': 'python', '.js': 'javascript', '.mjs': 'javascript',
    '.cjs': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript',
    '.md': 'markdown', '.markdown': 'markdown', '.rst': 'rst', '.json': 'json',
    '.toml': 'toml', '.yml': 'yaml', '.yaml': 'yaml', '.ini': 'ini', '.cfg': 'ini',
    '.sh': 'shell', '.ps1': 'powershell', '.css': 'css', '.html': 'html',
    '.rs': 'rust', '.go': 'go', '.java': 'java', '.c': 'c', '.h': 'c',
    '.cpp': 'cpp', '.hpp': 'cpp', '.tex': 'latex', '.sql': 'sql',
}

_LINK = re.compile(r'\[[^\]\n]*\]\(\s*<?([^)>\s]+)>?(?:\s+"[^"]*")?\s*\)')
_EXTERNAL_PREFIX = ('http://', 'https://', 'mailto:', 'ftp://', 'data:')

# The map must not describe its own generated output, or --check could never
# pass twice and every regeneration would churn.
GENERATED_PATHS = ('docs/PROJECT-MAP.md',)


def _language(path):
    return LANGUAGES.get(Path(path).suffix.lower(), 'other')


def _walk(root, max_files, exclude):
    """Bounded file list; symlinks and skipped directories are never followed."""
    names = []
    total = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs
                         if name not in SKIP_DIRS and not name.endswith('.egg-info')
                         and not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative in exclude:
                continue
            total += path.stat().st_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError('Project exceeds the total byte budget for mapping')
            names.append(relative)
            if len(names) > max_files:
                raise ValueError('Project exceeds the file limit for mapping')
    return names


def _module_name(relative):
    """Import name for a project-relative source path."""
    parts = relative[:-3].split('/')
    if parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts) if parts else ''


def _markdown_title(text):
    for line in text.splitlines():
        if line.startswith('# '):
            return line[2:].strip()[:160]
    return ''


def _python_facts(text, relative):
    facts = {'symbols': {'functions': 0, 'classes': 0}, 'names': [],
             'imports': [], 'parse_error': None, 'doc': ''}
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError:
        facts['parse_error'] = 'SyntaxError'
        return facts
    docstring = (ast.get_docstring(tree) or '').strip()
    facts['doc'] = docstring.splitlines()[0][:160] if docstring else ''
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            facts['symbols']['functions'] += 1
            if not node.name.startswith('_'):
                facts['names'].append(node.name + '()')
        elif isinstance(node, ast.ClassDef):
            facts['symbols']['classes'] += 1
            if not node.name.startswith('_'):
                facts['names'].append(node.name)
        elif isinstance(node, ast.Import):
            facts['imports'].extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            for alias in node.names:
                facts['imports'].append((base + '.' + alias.name if base else alias.name, node.level))
    facts['names'] = sorted(set(facts['names']))[:MAX_SYMBOLS_LISTED]
    return facts


def _resolve(name, module_index):
    """Longest resolvable project module prefix, or None for an external import."""
    parts = [part for part in name.split('.') if part]
    for end in range(len(parts), 0, -1):
        found = module_index.get('.'.join(parts[:end]))
        if found:
            return found
    return None


def _relative_module(module, level, is_package):
    parts = module.split('.') if module else []
    if not is_package:
        parts = parts[:-1]
    drop = level - 1
    if drop > len(parts):
        return None
    return '.'.join(parts[:len(parts) - drop])


def _doc_edges(relative, text, known):
    edges = []
    base = Path(relative).parent
    for target in _LINK.findall(text):
        if target.startswith(_EXTERNAL_PREFIX) or target.startswith('#'):
            continue
        clean = target.split('#', 1)[0].split('?', 1)[0]
        if not clean:
            continue
        resolved = (base / clean).as_posix()
        parts = []
        for part in resolved.split('/'):
            if part in ('', '.'):
                continue
            if part == '..':
                if parts:
                    parts.pop()
                continue
            parts.append(part)
        candidate = '/'.join(parts)
        if candidate in known:
            edges.append({'from': relative, 'to': candidate, 'kind': 'doc_link'})
    return edges


def _script_modules(root):
    """Module names declared in pyproject [project.scripts]."""
    path = root / 'pyproject.toml'
    if not path.is_file():
        return []
    try:
        import tomllib
    except ImportError:
        return []
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError):
        return []
    scripts = (data.get('project') or {}).get('scripts') or {}
    return [str(value).split(':', 1)[0] for value in scripts.values() if isinstance(value, str)]


def scan(root, *, name=None, max_files=MAX_FILES, exclude=GENERATED_PATHS):
    """Return a bounded, deterministic description of the project at root."""
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Root must be a directory')
    excluded = {Path(entry).as_posix() for entry in exclude}
    files, texts = [], {}
    for relative in _walk(root, max_files, excluded):
        path = root / relative
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            files.append({'path': relative, 'language': _language(relative),
                          'bytes': size, 'lines': 0, 'skipped': 'file_too_large'})
            continue
        data = path.read_bytes()
        texts[relative] = data
        text = data.decode('utf-8', errors='replace')
        entry = {'path': relative, 'language': _language(relative), 'bytes': size,
                 'lines': text.count('\n') + (0 if text.endswith('\n') or not text else 1)}
        if entry['language'] == 'markdown':
            entry['doc'] = _markdown_title(text)
        files.append(entry)

    module_index = {}
    for entry in files:
        if entry['language'] == 'python' and not entry.get('skipped'):
            module_index[_module_name(entry['path'])] = entry['path']
    for entry in files:
        if entry['language'] == 'python' and not entry.get('skipped'):
            entry.update(_python_facts(texts[entry['path']].decode('utf-8', errors='replace'),
                                       entry['path']))

    edges, external = [], {}
    for entry in files:
        if entry['language'] != 'python' or entry.get('skipped') or entry.get('parse_error'):
            continue
        module = _module_name(entry['path'])
        is_package = entry['path'].endswith('__init__.py')
        seen = set()
        for imported, level in entry['imports']:
            if level:
                base = _relative_module(module, level, is_package)
                if base is None:
                    continue
                target = _resolve(base + ('.' + imported if imported else ''), module_index)
            else:
                target = _resolve(imported, module_index)
            if target:
                if (target, 'import') not in seen:
                    seen.add((target, 'import'))
                    edges.append({'from': entry['path'], 'to': target, 'kind': 'import'})
            else:
                top = imported.split('.')[0]
                if top:
                    external[top] = external.get(top, 0) + 1

    known = {entry['path'] for entry in files}
    for entry in files:
        if entry['language'] in ('markdown', 'rst') and not entry.get('skipped'):
            edges.extend(_doc_edges(entry['path'], texts[entry['path']].decode('utf-8', errors='replace'), known))

    unique = {(edge['from'], edge['to'], edge['kind']): edge for edge in edges}
    edges = [unique[key] for key in sorted(unique)]
    for entry in files:
        entry.pop('imports', None)

    areas = {}
    for entry in files:
        area = entry['path'].split('/', 1)[0] if '/' in entry['path'] else '(root)'
        record = areas.setdefault(area, {'files': 0, 'lines': 0, 'bytes': 0})
        record['files'] += 1
        record['lines'] += entry['lines']
        record['bytes'] += entry['bytes']
    area_of = {entry['path']: (entry['path'].split('/', 1)[0] if '/' in entry['path'] else '(root)')
               for entry in files}
    area_edges = {}
    for edge in edges:
        source, target = area_of[edge['from']], area_of[edge['to']]
        if source != target:
            area_edges[(source, target)] = area_edges.get((source, target), 0) + 1

    scripts = _script_modules(root)
    entries = sorted({entry['path'] for entry in files
                      if entry['path'].endswith('__main__.py') or entry['path'] == 'main.py'})
    for module in scripts:
        found = module_index.get(module)
        if found:
            entries.append(found)
    entries = sorted(set(entries))

    return {'schema': 1, 'name': name or root.name, 'root': str(root), 'files': files,
            'edges': edges, 'areas': areas,
            'area_edges': [{'from': a, 'to': b, 'count': c}
                           for (a, b), c in sorted(area_edges.items())],
            'entry_points': entries, 'scripts': sorted(set(scripts)),
            'external_imports': dict(sorted(external.items())),
            'limits': {'files': max_files, 'file_bytes': MAX_FILE_BYTES,
                       'total_bytes': MAX_TOTAL_BYTES}}


def summary(project):
    """Per-file inbound/outbound counts over the whole graph."""
    inbound, outbound = {}, {}
    for edge in project['edges']:
        outbound[edge['from']] = outbound.get(edge['from'], 0) + 1
        inbound[edge['to']] = inbound.get(edge['to'], 0) + 1
    return inbound, outbound


def isolated(project):
    inbound, outbound = summary(project)
    return [entry['path'] for entry in project['files']
            if not inbound.get(entry['path']) and not outbound.get(entry['path'])]


def _ranked_modules(project, inbound, outbound, *, include_tests=False):
    """Modules ordered by edge degree; tests are excluded unless nothing else exists."""
    modules = [entry for entry in project['files']
               if entry['language'] == 'python' and not entry.get('skipped')]
    if not include_tests:
        source = [entry for entry in modules if not entry['path'].startswith('tests/')]
        modules = source or modules
    modules.sort(key=lambda entry: (-(inbound.get(entry['path'], 0) + outbound.get(entry['path'], 0)),
                                    entry['path']))
    return modules


def _mermaid_id(name):
    """Mermaid-safe id. The prefix keeps ids off reserved keywords such as `end`."""
    return 'g_' + re.sub(r'[^A-Za-z0-9_]', '_', name)


def _area_graph(project):
    areas = sorted(project['areas'])
    nodes = areas[:MAX_MERMAID_NODES]
    lines = ['```mermaid', 'graph LR']
    for area in nodes:
        lines.append('  %s["%s<br/>%d files"]' % (_mermaid_id(area), area, project['areas'][area]['files']))
    for edge in project['area_edges']:
        if edge['from'] in nodes and edge['to'] in nodes:
            label = ' -->|%d| ' % edge['count'] if edge['count'] > 1 else ' --> '
            lines.append('  %s%s%s' % (_mermaid_id(edge['from']), label, _mermaid_id(edge['to'])))
    lines.append('```')
    return lines


def _area_colors(project):
    return {area: index % len(GRAPH_STROKE)
            for index, area in enumerate(sorted(project['areas']))}


def _graph_nodes(project, max_nodes, *, include_isolated):
    """Files ordered by edge degree; isolated files are optional."""
    inbound, outbound = summary(project)
    entries = set(project['entry_points'])
    candidates = []
    for entry in project['files']:
        path = entry['path']
        if entry.get('skipped'):
            continue
        degree = inbound.get(path, 0) + outbound.get(path, 0)
        if not degree and not include_isolated and path not in entries:
            continue
        candidates.append((entry, degree))
    candidates.sort(key=lambda item: (-item[1], item[0]['path']))
    omitted = 0
    if max_nodes is not None and len(candidates) > max_nodes:
        omitted = len(candidates) - max_nodes
        candidates = candidates[:max_nodes]
    return candidates, omitted


def graph(project, *, max_nodes=None, include_isolated=True):
    """Canonical node/edge view: one node per file, one edge per observed link.

    Node ids are repository-relative paths, so the graph joins directly with the
    JSON map, the Markdown tables and a memory server's entities.
    """
    candidates, omitted = _graph_nodes(project, max_nodes, include_isolated=include_isolated)
    entries = set(project['entry_points'])
    colors = _area_colors(project)
    inbound, outbound = summary(project)
    nodes = []
    for entry, _degree in candidates:
        area = entry['path'].split('/', 1)[0] if '/' in entry['path'] else '(root)'
        node = {'id': entry['path'], 'label': entry['path'], 'area': area,
                'language': entry['language'], 'lines': entry['lines'],
                'inbound': inbound.get(entry['path'], 0),
                'outbound': outbound.get(entry['path'], 0),
                'color': GRAPH_STROKE[colors.get(area, 0)],
                'entry_point': entry['path'] in entries}
        if entry.get('doc'):
            node['summary'] = entry['doc']
        if entry.get('parse_error'):
            node['parse_error'] = entry['parse_error']
        nodes.append(node)
    keep = {node['id'] for node in nodes}
    edges = [dict(edge) for edge in project['edges']
             if edge['from'] in keep and edge['to'] in keep]
    return {'name': project['name'], 'nodes': nodes, 'edges': edges,
            'areas': [{'name': area, 'color': GRAPH_STROKE[colors[area]],
                       'files': project['areas'][area]['files'],
                       'lines': project['areas'][area]['lines']}
                      for area in sorted(project['areas'])],
            'omitted_nodes': omitted,
            'stats': {'nodes': len(nodes), 'edges': len(edges),
                      'total_files': len(project['files']),
                      'total_edges': len(project['edges'])}}


def _mermaid_ids(paths):
    """Collision-free Mermaid ids: suffixes are derived from sort order only."""
    ids, used = {}, set()
    for path in paths:
        base = _mermaid_id(path)
        candidate, index = base, 1
        while candidate in used:
            index += 1
            candidate = '%s_%d' % (base, index)
        used.add(candidate)
        ids[path] = candidate
    return ids


def render_graph_mermaid(project, *, max_nodes=MAX_GRAPH_NODES, include_isolated=False):
    """File-level relationship graph as Mermaid, grouped by area."""
    model = graph(project, max_nodes=max_nodes, include_isolated=include_isolated)
    colors = _area_colors(project)
    ids = _mermaid_ids([node['id'] for node in model['nodes']])
    lines = ['```mermaid', 'graph LR']
    for area in sorted({node['area'] for node in model['nodes']}):
        lines.append('  subgraph %s["%s"]' % (_mermaid_id(area), area))
        for node in [item for item in model['nodes'] if item['area'] == area]:
            label = node['label'] + (' (entry)' if node['entry_point'] else '')
            lines.append('    %s["%s<br/>%d lines"]' % (ids[node['id']], label, node['lines']))
        lines.append('  end')
    for edge in model['edges']:
        lines.append('  %s %s %s' % (ids[edge['from']],
                                     '-.->' if edge['kind'] == 'doc_link' else '-->',
                                     ids[edge['to']]))
    classes = {}
    for area in sorted(colors):
        name = _mermaid_id('area_' + area)
        classes[area] = name
        index = colors[area]
        lines.append('  classDef %s fill:%s,stroke:%s,color:#1a1a1a;'
                     % (name, GRAPH_FILL[index], GRAPH_STROKE[index]))
    lines.append('  classDef entry stroke:%s,stroke-width:2px;' % GRAPH_ENTRY_STROKE)
    for node in model['nodes']:
        assigned = [classes[node['area']]]
        if node['entry_point']:
            assigned.append('entry')
        lines.append('  class %s %s;' % (ids[node['id']], ','.join(assigned)))
    lines.append('```')
    if model['omitted_nodes']:
        lines += ['', '_%d lower-degree file node(s) omitted; the complete graph is in'
                  ' the graph exports and the JSON map._' % model['omitted_nodes']]
    return lines


def _dot_escape(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def render_graph_dot(project):
    """Graphviz DOT of every scanned file and edge, clustered by area."""
    model = graph(project)
    colors = _area_colors(project)
    lines = ['digraph "%s" {' % _dot_escape(model['name']),
             '  rankdir=LR;',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];',
             '  edge [color="#666666", fontsize=8];']
    clustered = [node for node in model['nodes'] if node['area'] != '(root)']
    for area in sorted({node['area'] for node in clustered}):
        index = colors[area]
        lines.append('  subgraph "cluster_%s" {' % _dot_escape(area))
        lines.append('    label="%s";' % _dot_escape(area))
        lines.append('    bgcolor="%s";' % GRAPH_FILL[index])
        for node in [item for item in clustered if item['area'] == area]:
            lines.append('    "%s" [fillcolor="%s"%s, label="%s\\n%d lines"];'
                         % (_dot_escape(node['id']), GRAPH_FILL[index],
                            ', penwidth=2.0' if node['entry_point'] else '',
                            _dot_escape(node['label']), node['lines']))
        lines.append('  }')
    for node in [item for item in model['nodes'] if item['area'] == '(root)']:
        lines.append('  "%s" [fillcolor="%s"%s, label="%s\\n%d lines"];'
                     % (_dot_escape(node['id']), GRAPH_FILL[colors['(root)']],
                        ', penwidth=2.0' if node['entry_point'] else '',
                        _dot_escape(node['label']), node['lines']))
    for edge in model['edges']:
        lines.append('  "%s" -> "%s" [style=%s];'
                     % (_dot_escape(edge['from']), _dot_escape(edge['to']),
                        'dashed' if edge['kind'] == 'doc_link' else 'solid'))
    lines.append('}')
    return '\n'.join(lines) + '\n'


def _xml_escape(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def render_graph_graphml(project):
    """GraphML 1.0 export for Gephi, yEd and networkx readers."""
    model = graph(project)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"'
             ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
             ' xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns'
             ' http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
             '  <key id="name" for="graph" attr.name="name" attr.type="string"/>']
    for name, kind in (('label', 'string'), ('area', 'string'), ('language', 'string'),
                       ('lines', 'int'), ('inbound', 'int'), ('outbound', 'int'),
                       ('entryPoint', 'boolean'), ('summary', 'string'),
                       ('parseError', 'string')):
        lines.append('  <key id="%s" for="node" attr.name="%s" attr.type="%s"/>'
                     % (name, name, kind))
    lines.append('  <key id="kind" for="edge" attr.name="kind" attr.type="string"/>')
    lines.append('  <graph id="%s" edgedefault="directed">' % _xml_escape(model['name']))
    lines.append('    <data key="name">%s</data>' % _xml_escape(model['name']))
    for node in model['nodes']:
        lines.append('    <node id="%s">' % _xml_escape(node['id']))
        for name, value in (('label', node['label']), ('area', node['area']),
                            ('language', node['language']), ('lines', node['lines']),
                            ('inbound', node['inbound']), ('outbound', node['outbound']),
                            ('entryPoint', 'true' if node['entry_point'] else 'false')):
            lines.append('      <data key="%s">%s</data>' % (name, _xml_escape(value)))
        for name, value in (('summary', node.get('summary')),
                            ('parseError', node.get('parse_error'))):
            if value:
                lines.append('      <data key="%s">%s</data>' % (name, _xml_escape(value)))
        lines.append('    </node>')
    for position, edge in enumerate(model['edges']):
        lines.append('    <edge id="e%d" source="%s" target="%s">'
                     % (position, _xml_escape(edge['from']), _xml_escape(edge['to'])))
        lines.append('      <data key="kind">%s</data>' % _xml_escape(edge['kind']))
        lines.append('    </edge>')
    lines.append('  </graph>')
    lines.append('</graphml>')
    return '\n'.join(lines) + '\n'


def render_graph_tsv(project):
    """Tab-separated edge list: from, to, kind, areas and count."""
    model = graph(project)
    area_of = {node['id']: node['area'] for node in model['nodes']}
    grouped = {}
    for edge in model['edges']:
        key = (edge['from'], edge['to'], edge['kind'])
        grouped[key] = grouped.get(key, 0) + 1
    lines = ['from\tto\tkind\tfrom_area\tto_area\tcount']
    for source, target, kind in sorted(grouped):
        lines.append('%s\t%s\t%s\t%s\t%s\t%d'
                     % (source, target, kind, area_of[source], area_of[target],
                        grouped[(source, target, kind)]))
    return '\n'.join(lines) + '\n'


def render_graph_exports(project):
    """Relative path -> deterministic text for every graph export file."""
    return {GRAPH_EXPORTS[0]: render_graph_dot(project),
            GRAPH_EXPORTS[1]: render_graph_graphml(project),
            GRAPH_EXPORTS[2]: render_graph_tsv(project)}


def render_markdown(project, *, title=None):
    """Human-readable map. Deterministic: no timestamps and no absolute paths."""
    inbound, outbound = summary(project)
    lines = ['# %s' % (title or ('Project map — ' + project['name'])), '']
    lines += ['Static analysis of local files: paths, line counts, Python imports and relative',
              'document links. No model calls, no semantic claims. Regenerate with',
              '`kyper-workflow map --root . --write`; `--check` fails when this file is stale.',
              '']

    counts = {}
    for entry in project['files']:
        counts[entry['language']] = counts.get(entry['language'], 0) + 1
    lines += ['## Overview', '',
              '- Files: %d' % len(project['files']),
              '- Lines: %d' % sum(entry['lines'] for entry in project['files']),
              '- Languages: %s' % ', '.join('%s %d' % (name, counts[name]) for name in sorted(counts)),
              '- Internal dependency edges: %d' % len(project['edges']),
              '- Entry points: %s' % (', '.join('`%s`' % path for path in project['entry_points']) or 'none detected'),
              '']

    lines += ['## Areas', '', '| Area | Files | Lines | Outbound edges | Inbound edges |',
              '|---|---|---|---|---|']
    area_in, area_out = {}, {}
    for edge in project['area_edges']:
        area_out[edge['from']] = area_out.get(edge['from'], 0) + edge['count']
        area_in[edge['to']] = area_in.get(edge['to'], 0) + edge['count']
    for area in sorted(project['areas']):
        record = project['areas'][area]
        lines.append('| `%s` | %d | %d | %d | %d |' % (area, record['files'], record['lines'],
                                                      area_out.get(area, 0), area_in.get(area, 0)))
    lines.append('')

    model = graph(project, max_nodes=MAX_GRAPH_NODES, include_isolated=False)
    lines += ['## Relationship graph', '',
              'One node per file, one directed edge per observed link. Solid arrows are Python',
              'imports, dashed arrows are relative document links. Colour groups files by area and',
              'a thick border marks a detected entry point. Node ids are the file paths used',
              'throughout this map, so the graph, the tables below and `.kyper/project-map.json`',
              'describe the same graph. Machine-readable copies:',
              '`%s`, `%s`, `%s`.' % GRAPH_EXPORTS, '',
              '- Nodes shown: %d of %d files; edges shown: %d of %d' % (
                  model['stats']['nodes'], model['stats']['total_files'],
                  model['stats']['edges'], model['stats']['total_edges']),
              '']
    lines += render_graph_mermaid(project)
    lines += ['', '### Area summary', '',
              'The same graph collapsed to one node per area, with edge counts.', '']
    lines += _area_graph(project)
    lines.append('')

    lines += ['## Files', '']
    for area in sorted(project['areas']):
        lines += ['### `%s`' % area, '', '| File | Lines | Symbols | Summary | Internal imports |',
                  '|---|---|---|---|---|']
        for entry in project['files']:
            if (entry['path'].split('/', 1)[0] if '/' in entry['path'] else '(root)') != area:
                continue
            if entry.get('skipped'):
                lines.append('| `%s` | — | — | skipped: %s | — |' % (entry['path'], entry['skipped']))
                continue
            symbols = ''
            if 'symbols' in entry:
                symbols = '%d fn / %d cls' % (entry['symbols']['functions'], entry['symbols']['classes'])
                if entry.get('parse_error'):
                    symbols = 'parse error'
            targets = sorted({edge['to'] for edge in project['edges']
                              if edge['from'] == entry['path'] and edge['kind'] == 'import'})
            summary_text = entry.get('doc') or ''
            lines.append('| `%s` | %d | %s | %s | %s |' % (
                entry['path'], entry['lines'], symbols, summary_text or '—',
                ', '.join('`%s`' % path for path in targets[:6]) or '—'))
        lines.append('')

    lines += ['## Feature relationships', '',
              'Edges are observed imports and relative document links, not runtime call',
              'graphs or proof that a dependency is used correctly.', '']
    for area in sorted(project['areas']):
        out = [edge for edge in project['area_edges'] if edge['from'] == area]
        into = [edge for edge in project['area_edges'] if edge['to'] == area]
        lines.append('- `%s`: depends on %s; used by %s' % (
            area,
            ', '.join('`%s` (%d)' % (edge['to'], edge['count']) for edge in out) or 'nothing outside itself',
            ', '.join('`%s` (%d)' % (edge['from'], edge['count']) for edge in into) or 'nothing outside itself'))
    lines.append('')

    lines += ['## Isolated files', '',
              'No internal import or document-link edge in either direction. Some are data or',
              'configuration files that legitimately have none.', '']
    orphans = isolated(project)
    lines += ['- `%s`' % path for path in orphans[:80]]
    if len(orphans) > 80:
        lines.append('- … %d more' % (len(orphans) - 80))
    if not orphans:
        lines.append('- none')
    lines.append('')

    lines += ['## External imports', '',
              'Top-level names that do not resolve to a project file.', '']
    for name in sorted(project['external_imports']):
        stdlib = ' (stdlib)' if name in getattr(sys, 'stdlib_module_names', ()) else ''
        lines.append('- `%s`%s — %d site(s)' % (name, stdlib, project['external_imports'][name]))
    if not project['external_imports']:
        lines.append('- none detected')
    lines.append('')
    return '\n'.join(lines) + '\n'


def render_json(project):
    return json.dumps(project, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def digest(project, *, max_modules=24):
    """Compact text intended for a shared-memory entry or a session brief."""
    inbound, outbound = summary(project)
    counts = {}
    for entry in project['files']:
        counts[entry['language']] = counts.get(entry['language'], 0) + 1
    lines = ['# %s — project map' % project['name'], '',
             '- Files: %d; lines: %d; internal edges: %d' % (
                 len(project['files']), sum(entry['lines'] for entry in project['files']),
                 len(project['edges'])),
             '- Languages: %s' % ', '.join('%s %d' % (name, counts[name]) for name in sorted(counts)),
             '- Entry points: %s' % (', '.join(project['entry_points']) or 'none detected'),
             '', '## Areas', '']
    for area in sorted(project['areas']):
        record = project['areas'][area]
        out = [edge['to'] for edge in project['area_edges'] if edge['from'] == area]
        lines.append('- %s: %d files / %d lines; depends on %s' % (
            area, record['files'], record['lines'], ', '.join(out) or 'nothing outside itself'))
    modules = _ranked_modules(project, inbound, outbound)
    lines += ['', '## Central modules', '']
    for entry in modules[:max_modules]:
        lines.append('- %s (%d in / %d out)%s' % (
            entry['path'], inbound.get(entry['path'], 0), outbound.get(entry['path'], 0),
            ' — ' + entry['doc'] if entry.get('doc') else ''))
    if project['external_imports']:
        lines += ['', '## External imports', '',
                  ', '.join(sorted(project['external_imports']))]
    lines += ['', '## Limits', '',
              'Static analysis only: imports and relative document links observed on disk.',
              'It does not prove runtime behavior, ownership or that a dependency is correct.']
    return '\n'.join(lines) + '\n'


def memory_payload(project, *, doc_path='docs/PROJECT-MAP.md', max_modules=40):
    """Entity/relation payload in the common MCP knowledge-graph memory shape.

    Writing it is the host's decision: this function only prepares data. Pass
    it to a memory server's create-entities/create-relations tools.
    """
    inbound, outbound = summary(project)
    entities = [{'name': project['name'], 'entityType': 'project',
                 'observations': [
                     'files: %d' % len(project['files']),
                     'lines: %d' % sum(entry['lines'] for entry in project['files']),
                     'internal edges: %d' % len(project['edges']),
                     'entry points: %s' % (', '.join(project['entry_points']) or 'none detected'),
                     'map document: ' + doc_path]}]
    relations = []
    for area in sorted(project['areas']):
        record = project['areas'][area]
        entities.append({'name': area, 'entityType': 'area',
                         'observations': ['files: %d' % record['files'],
                                          'lines: %d' % record['lines']]})
        relations.append({'from': project['name'], 'to': area, 'relationType': 'contains'})
    for edge in project['area_edges']:
        relations.append({'from': edge['from'], 'to': edge['to'], 'relationType': 'depends_on'})
    modules = _ranked_modules(project, inbound, outbound)
    for entry in modules[:max_modules]:
        observations = ['lines: %d' % entry['lines']]
        if 'symbols' in entry:
            observations.append('functions: %d' % entry['symbols']['functions'])
            observations.append('classes: %d' % entry['symbols']['classes'])
        if entry.get('doc'):
            observations.append('summary: ' + entry['doc'])
        entities.append({'name': entry['path'], 'entityType': 'module',
                         'observations': observations})
    for edge in project['edges']:
        if edge['kind'] == 'import':
            relations.append({'from': edge['from'], 'to': edge['to'], 'relationType': 'imports'})
    return {'entities': entities, 'relations': relations}
