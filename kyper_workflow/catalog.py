"""Reusable role cards and task components.

Both are inert data: nothing here calls a model, spawns an agent or writes a
file. A role says what one agent is allowed to touch and which tests it must
pass; a component is a parameterised task template. Validation is deterministic
and fail-closed, so an unknown role, an out-of-scope write or a missing
parameter stops the plan instead of being silently defaulted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from . import __version__

CHECK_KINDS = ('code', 'text', 'model', 'browser', 'native')
CODE_MODES = ('syntax', 'project_tests')
COMPLEXITIES = ('trivial', 'standard', 'complex')
PARAM_TYPES = ('text', 'path', 'paths', 'choice')

_PLACEHOLDER = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}')

# Built-in cards mirror the roles the workflow already assumes: explore, build,
# test, review, integrate. They are deliberately narrow so a task cannot widen
# its own blast radius by naming a role.
ROLES = (
    {'id': 'explorer', 'title': 'Explorer', 'purpose':
     'Read the project and report structure, constraints and open questions.',
     'allowed_checks': ['text'], 'write_scopes': [], 'code_modes': [],
     'complexity': ['trivial', 'standard'], 'max_parallel': 3,
     'required_outputs': ['findings']},
    {'id': 'implementer', 'title': 'Implementer', 'purpose':
     'Change source files and keep the declared checks passing.',
     'allowed_checks': ['code'], 'write_scopes': ['**'], 'code_modes': list(CODE_MODES),
     'complexity': ['standard', 'complex'], 'max_parallel': 2,
     'required_outputs': ['changed']},
    {'id': 'test-author', 'title': 'Test author', 'purpose':
     'Write or repair tests only, without touching production source.',
     'allowed_checks': ['code'], 'write_scopes': ['tests/**'],
     'code_modes': ['project_tests'], 'complexity': ['standard', 'complex'],
     'max_parallel': 2, 'required_outputs': ['tests']},
    {'id': 'reviewer', 'title': 'Reviewer', 'purpose':
     'Read a change and report findings and a verdict; never writes.',
     'allowed_checks': ['text', 'model'], 'write_scopes': [], 'code_modes': [],
     'complexity': ['trivial', 'standard', 'complex'], 'max_parallel': 3,
     'required_outputs': ['findings', 'verdict']},
    {'id': 'integrator', 'title': 'Integrator', 'purpose':
     'Update documentation and wire the finished pieces together.',
     'allowed_checks': ['text'], 'write_scopes': ['docs/**', 'README.md', '*.md'],
     'code_modes': [], 'complexity': ['trivial', 'standard'], 'max_parallel': 1,
     'required_outputs': ['summary']},
)

# Components are task shapes, not project-specific content: the caller supplies
# the paths and the behaviour, the template supplies scope, checks and the
# acceptance sentence that will appear in the approved specification.
COMPONENTS = (
    {'id': 'code-change', 'version': 1, 'title': 'Code change',
     'description': 'Implement one behaviour in existing source files.',
     'role': 'implementer',
     'params': {'behaviour': {'type': 'text', 'required': True,
                              'description': 'What must change, in one sentence.'},
                'paths': {'type': 'paths', 'required': True,
                         'description': 'Workspace-relative files to edit.'}},
     'acceptance': '{{behaviour}} — implemented in {{paths}} and accepted by the code checker.',
     'required_checks': ['code'], 'code_mode': 'syntax', 'complexity': 'standard',
     'writes_from': 'paths'},
    {'id': 'test-covered-change', 'version': 1, 'title': 'Test-covered change',
     'description': 'Change source files together with the tests that cover them.',
     'role': 'implementer',
     'params': {'behaviour': {'type': 'text', 'required': True,
                              'description': 'What must change.'},
                'paths': {'type': 'paths', 'required': True,
                         'description': 'Source files to edit.'},
                'tests': {'type': 'paths', 'required': True,
                          'description': 'Test files that must pass.'}},
     'acceptance': '{{behaviour}} — covered by {{tests}} and accepted by project tests.',
     'required_checks': ['code'], 'code_mode': 'project_tests', 'complexity': 'complex',
     'writes_from': 'paths'},
    {'id': 'test-only', 'version': 1, 'title': 'Test-only change',
     'description': 'Add or repair tests without touching production source.',
     'role': 'test-author',
     'params': {'tests': {'type': 'paths', 'required': True,
                          'description': 'Test files to create or edit.'},
                'covers': {'type': 'text', 'required': True,
                           'description': 'Behaviour under test.'}},
     'acceptance': '{{tests}} cover {{covers}} and the project test run passes.',
     'required_checks': ['code'], 'code_mode': 'project_tests', 'complexity': 'standard',
     'writes_from': 'tests'},
    {'id': 'doc-sync', 'version': 1, 'title': 'Documentation sync',
     'description': 'Update documentation so it matches current behaviour.',
     'role': 'integrator',
     'params': {'topic': {'type': 'text', 'required': True,
                          'description': 'Subject the documents must describe.'},
                'docs': {'type': 'paths', 'required': True,
                         'description': 'Documents to update.'}},
     'acceptance': '{{docs}} describe {{topic}} without contradicting the project map.',
     'required_checks': ['text'], 'code_mode': None, 'complexity': 'trivial',
     'writes_from': 'docs'},
    {'id': 'review-only', 'version': 1, 'title': 'Review only',
     'description': 'Independent read-only review of a finished change.',
     'role': 'reviewer',
     'params': {'target': {'type': 'text', 'required': True,
                           'description': 'Change or artifact under review.'},
                'aspects': {'type': 'text', 'required': True,
                            'description': 'What the review must cover.'}},
     'acceptance': '{{target}} reviewed for {{aspects}} with findings and an explicit verdict.',
     'required_checks': ['text', 'model'], 'code_mode': None, 'complexity': 'standard',
     'writes_from': None},
    {'id': 'investigation', 'version': 1, 'title': 'Investigation',
     'description': 'Answer one bounded question by reading the project; no writes.',
     'role': 'explorer',
     'params': {'question': {'type': 'text', 'required': True,
                             'description': 'The question to answer.'}},
     'acceptance': '{{question}} — answered with file-level evidence and no writes.',
     'required_checks': ['text'], 'code_mode': None, 'complexity': 'trivial',
     'writes_from': None},
)


def _scope_allows(pattern, path):
    """Match a role's declared scope against one workspace-relative path."""
    if pattern == '**':
        return True
    if pattern.endswith('/**'):
        prefix = pattern[:-3].rstrip('/')
        return path == prefix or path.startswith(prefix + '/')
    if pattern.startswith('*.'):
        return '/' not in path and path.endswith(pattern[1:])
    return path == pattern


def _normalize_scope(raw):
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError('Write scope must be a non-empty string')
    text = raw.strip().replace('\\', '/')
    if re.match(r'^[A-Za-z]:', text) or text.startswith('//'):
        raise ValueError('Unsafe write scope: %s' % raw)
    if text in ('**',) or text.endswith('/**') or text.startswith('*.'):
        return text
    path = PurePosixPath(text)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe write scope: %s' % raw)
    return str(path)


def _validate_role(role):
    required = ('id', 'title', 'purpose', 'allowed_checks', 'write_scopes',
                'code_modes', 'complexity', 'max_parallel', 'required_outputs')
    missing = [key for key in required if key not in role]
    if missing:
        raise ValueError('Role %r missing %s' % (role.get('id'), ', '.join(missing)))
    extra = set(role) - set(required) - {'notes'}
    if extra:
        raise ValueError('Role %r has unknown fields: %s' % (role['id'], ', '.join(sorted(extra))))
    if not isinstance(role['id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', role['id']):
        raise ValueError('Role id must be lowercase words separated by dashes')
    if not set(role['allowed_checks']) <= set(CHECK_KINDS):
        raise ValueError('Role %r declares an unknown check' % role['id'])
    if not set(role['code_modes']) <= set(CODE_MODES):
        raise ValueError('Role %r declares an unknown code mode' % role['id'])
    if 'code' in role['allowed_checks'] and not role['code_modes']:
        raise ValueError('Role %r allows code checks but no code mode' % role['id'])
    if not set(role['complexity']) <= set(COMPLEXITIES):
        raise ValueError('Role %r declares an unknown complexity' % role['id'])
    if type(role['max_parallel']) is not int or role['max_parallel'] < 1:
        raise ValueError('Role %r needs max_parallel >= 1' % role['id'])
    if not isinstance(role['required_outputs'], list) or any(
            not isinstance(name, str) or not name for name in role['required_outputs']):
        raise ValueError('Role %r has invalid required_outputs' % role['id'])
    role = dict(role)
    role['write_scopes'] = [_normalize_scope(scope) for scope in role['write_scopes']]
    return role


def _validate_component(component):
    required = ('id', 'version', 'title', 'description', 'role', 'params',
                'acceptance', 'required_checks', 'code_mode', 'complexity',
                'writes_from')
    missing = [key for key in required if key not in component]
    if missing:
        raise ValueError('Component %r missing %s'
                         % (component.get('id'), ', '.join(missing)))
    if not isinstance(component['id'], str) or not re.fullmatch(
            r'[a-z0-9][a-z0-9-]*', component['id']):
        raise ValueError('Component id must be lowercase words separated by dashes')
    if type(component['version']) is not int or component['version'] < 1:
        raise ValueError('Component %r needs version >= 1' % component['id'])
    if component['code_mode'] is not None and component['code_mode'] not in CODE_MODES:
        raise ValueError('Component %r has an unknown code mode' % component['id'])
    if not set(component['required_checks']) <= set(CHECK_KINDS):
        raise ValueError('Component %r declares an unknown check' % component['id'])
    if 'code' in component['required_checks'] and component['code_mode'] is None:
        raise ValueError('Component %r requires code but no code mode' % component['id'])
    if component['complexity'] not in COMPLEXITIES:
        raise ValueError('Component %r has an unknown complexity' % component['id'])
    params = component['params']
    if not isinstance(params, dict) or not params:
        raise ValueError('Component %r needs at least one parameter' % component['id'])
    for name, spec in params.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            raise ValueError('Component %r has an invalid parameter name' % component['id'])
        if not isinstance(spec, dict) or spec.get('type') not in PARAM_TYPES:
            raise ValueError('Component %r parameter %r has an invalid type'
                             % (component['id'], name))
        if spec.get('type') == 'choice' and not spec.get('choices'):
            raise ValueError('Component %r choice parameter %r needs choices'
                             % (component['id'], name))
    filled = set(_PLACEHOLDER.findall(component['acceptance']))
    if filled - set(params):
        raise ValueError('Component %r acceptance uses undeclared parameters: %s'
                         % (component['id'], ', '.join(sorted(filled - set(params)))))
    if component['writes_from'] is not None:
        if component['writes_from'] not in params:
            raise ValueError('Component %r writes_from is not a parameter' % component['id'])
        if component['params'][component['writes_from']]['type'] not in ('path', 'paths'):
            raise ValueError('Component %r writes_from must be a path parameter'
                             % component['id'])
    return dict(component)


def builtin():
    """Validated built-in catalog, independent of any file on disk."""
    return {'version': __version__,
            'roles': [_validate_role(role) for role in ROLES],
            'components': [_validate_component(component) for component in COMPONENTS]}


def load(path=None):
    """Merge a JSON catalog over the built-ins; later entries win by id.

    A malformed or unknown field is an error, never a silent fallback: a role
    that cannot be validated must not be used to authorise writes.
    """
    catalog = builtin()
    if path is None:
        return catalog
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Catalog must be a JSON object')
    unknown = set(data) - {'version', 'roles', 'components'}
    if unknown:
        raise ValueError('Catalog has unknown sections: %s' % ', '.join(sorted(unknown)))
    roles = {role['id']: role for role in catalog['roles']}
    for role in data.get('roles', []):
        validated = _validate_role(role)
        roles[validated['id']] = validated
    components = {component['id']: component for component in catalog['components']}
    for component in data.get('components', []):
        validated = _validate_component(component)
        components[validated['id']] = validated
    return {'version': data.get('version') or catalog['version'],
            'roles': [roles[key] for key in sorted(roles)],
            'components': [components[key] for key in sorted(components)]}


def role(catalog, role_id):
    for entry in catalog['roles']:
        if entry['id'] == role_id:
            return entry
    raise ValueError('Unknown role: %r' % role_id)


def component(catalog, component_id):
    for entry in catalog['components']:
        if entry['id'] == component_id:
            return entry
    raise ValueError('Unknown component: %r' % component_id)


def bind(task, role_entry):
    """Check that a task stays inside the role's declared blast radius."""
    problems = []
    checks = set(task.get('required_checks', ()))
    if not checks <= set(role_entry['allowed_checks']):
        problems.append('checks %s outside role %s'
                        % (sorted(checks - set(role_entry['allowed_checks'])), role_entry['id']))
    if 'code' in checks and task.get('code_mode') not in role_entry['code_modes']:
        problems.append('code mode %r not allowed for role %s'
                        % (task.get('code_mode'), role_entry['id']))
    if task.get('complexity') and task['complexity'] not in role_entry['complexity']:
        problems.append('complexity %r outside role %s'
                        % (task['complexity'], role_entry['id']))
    for scope in task.get('writes', ()):
        if not any(_scope_allows(pattern, scope) for pattern in role_entry['write_scopes']):
            problems.append('write %r outside role %s scopes' % (scope, role_entry['id']))
    if problems:
        raise ValueError('Role binding rejected: ' + '; '.join(problems))
    return True


def _render(template, values):
    return _PLACEHOLDER.sub(lambda match: str(values[match.group(1)]), template)


def instantiate(catalog, component_id, *, name, params, depends=()):
    """Render a component into keyword arguments accepted by `add_task`.

    Paths are normalized and rejected if unsafe, so a preview cannot show a
    scope that `add_task` would later refuse.
    """
    template = component(catalog, component_id)
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Task name required')
    supplied = dict(params or {})
    unknown = set(supplied) - set(template['params'])
    if unknown:
        raise ValueError('Unknown parameters for %s: %s'
                         % (component_id, ', '.join(sorted(unknown))))
    values, missing = {}, []
    for key, spec in sorted(template['params'].items()):
        if key not in supplied or supplied[key] in (None, '', []):
            if spec.get('required'):
                missing.append(key)
            continue
        value = supplied[key]
        if spec['type'] == 'text':
            if not isinstance(value, str):
                raise ValueError('Parameter %s must be text' % key)
            values[key] = value.strip()
        elif spec['type'] == 'choice':
            if value not in spec['choices']:
                raise ValueError('Parameter %s must be one of %s'
                                 % (key, ', '.join(spec['choices'])))
            values[key] = value
        else:
            items = value if isinstance(value, list) else [value]
            normalized = []
            for item in items:
                if not isinstance(item, str):
                    raise ValueError('Parameter %s must be a path or list of paths' % key)
                normalized.append(_normalize_scope(item))
            if not normalized:
                raise ValueError('Parameter %s must name at least one path' % key)
            values[key] = normalized if spec['type'] == 'paths' else normalized[0]
    if missing:
        raise ValueError('Missing required parameters for %s: %s'
                         % (component_id, ', '.join(missing)))
    writes = values[template['writes_from']] if template['writes_from'] else []
    if isinstance(writes, str):
        writes = [writes]
    display = dict(values)
    for key, value in display.items():
        if isinstance(value, list):
            display[key] = ', '.join(value)
    result = {'name': name, 'depends': list(depends), 'writes': list(writes),
              'acceptance': _render(template['acceptance'], display),
              'required_checks': list(template['required_checks']),
              'code_mode': template['code_mode'], 'complexity': template['complexity'],
              'role': template['role'], 'component': component_id,
              'component_version': template['version']}
    bind({'writes': result['writes'], 'required_checks': result['required_checks'],
          'code_mode': result['code_mode'], 'complexity': result['complexity']},
         role(catalog, result['role']))
    return result


def export_role_card(role_entry):
    """Host-neutral card for manual use; it carries no invented host fields."""
    from . import hosts
    return hosts.render('generic', role_entry)['content']


def export_subagent(role_entry):
    """Deprecated alias for :func:`export_role_card`.

    A host-specific subagent should be produced by `kyper_workflow.hosts`, which
    documents the fields it emits and omits for that host.
    """
    return export_role_card(role_entry)


def render_markdown(catalog):
    """Deterministic table used in docs and by the CLI."""
    lines = ['## Roles', '', '| Role | Writes | Checks | Complexity | Parallel | Handoff |',
             '|---|---|---|---|---|---|']
    for entry in catalog['roles']:
        lines.append('| `%s` | %s | %s | %s | %d | %s |' % (
            entry['id'],
            ', '.join('`%s`' % scope for scope in entry['write_scopes']) or 'none',
            ', '.join(entry['allowed_checks']), ', '.join(entry['complexity']),
            entry['max_parallel'], ', '.join(entry['required_outputs'])))
    lines += ['', '## Components', '', '| Component | Version | Role | Parameters | Checks |',
              '|---|---|---|---|---|']
    for entry in catalog['components']:
        params = ', '.join('%s%s' % (name, '' if spec.get('required') else '?')
                           for name, spec in sorted(entry['params'].items()))
        lines.append('| `%s` | %d | `%s` | %s | %s |' % (
            entry['id'], entry['version'], entry['role'], params,
            ', '.join(entry['required_checks'])))
    lines += ['', '`?` marks an optional parameter. Components only render task fields;',
              'they never add, remove or approve a task on their own.']
    return '\n'.join(lines) + '\n'


def digest(catalog):
    return '%d roles (%s); %d components (%s)' % (
        len(catalog['roles']), ', '.join(entry['id'] for entry in catalog['roles']),
        len(catalog['components']), ', '.join(entry['id'] for entry in catalog['components']))
