"""Conservative projections of KyperWorkflow role cards onto coding hosts.

The role catalog is the single source of truth. A host adapter only renders the
fields that host documents, and records what it deliberately omitted. It never
installs itself, never guesses a model id, and never claims that instructions
enforce a path scope.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import __version__

FORMAT_VERSION = 1
PREFIX = 'kyper-'
MANIFEST = '.kyper-export.json'

# `enforcement` is intentionally descriptive rather than aspirational. Only
# Cursor exposes a read-only flag and only Claude/Gemini/Copilot expose a tool
# allowlist; none of them enforce a workspace-relative write scope from the role
# card alone.
HOSTS = (
    {'id': 'claude', 'label': 'Claude Code', 'format': 'markdown_yaml',
     'default_dir': '.claude/agents', 'path_template': '{name}.md',
     'native_subagents': True, 'nesting': 'host_policy',
     'read_only': 'tool_allowlist', 'tool_filter': 'allowlist',
     'write_scope': 'contract_only', 'prompt_limit': None,
     'docs': 'https://code.claude.com/docs/en/sub-agents',
     'note': 'Tool allowlist; write scopes and max_parallel are not enforced.'},
    {'id': 'cursor', 'label': 'Cursor', 'format': 'markdown_yaml',
     'default_dir': '.cursor/agents', 'path_template': '{name}.md',
     'native_subagents': True, 'nesting': 'one_level',
     'read_only': 'readonly_flag', 'tool_filter': 'none',
     'write_scope': 'contract_only', 'prompt_limit': None,
     'docs': 'https://cursor.com/docs/subagents',
     'note': 'readonly=true blocks edits and state-changing shell; no path scope.'},
    {'id': 'codex', 'label': 'Codex', 'format': 'toml',
     'default_dir': '.codex/agents', 'path_template': '{name}.toml',
     'native_subagents': True, 'nesting': 'host_policy',
     'read_only': 'instruction_only', 'tool_filter': 'limited_features',
     'write_scope': 'contract_only', 'prompt_limit': None,
     'docs': 'https://learn.chatgpt.com/codex/agent-configuration/subagents',
     'note': 'Inherits parent sandbox and approvals; no separate read-only sandbox.'},
    {'id': 'gemini', 'label': 'Gemini CLI', 'format': 'markdown_yaml',
     'default_dir': '.gemini/agents', 'path_template': '{name}.md',
     'native_subagents': True, 'nesting': 'forbidden',
     'read_only': 'partial_tool_allowlist', 'tool_filter': 'allowlist',
     'write_scope': 'contract_only', 'prompt_limit': None,
     'docs': 'https://geminicli.com/docs/core/subagents/',
     'note': 'Subagents cannot spawn subagents; path scopes are not enforced.'},
    {'id': 'copilot', 'label': 'GitHub Copilot', 'format': 'markdown_yaml',
     'default_dir': '.github/agents', 'path_template': '{name}.agent.md',
     'native_subagents': True, 'nesting': 'not_asserted',
     'read_only': 'partial_tool_allowlist', 'tool_filter': 'allowlist',
     'write_scope': 'contract_only', 'prompt_limit': 30000,
     'docs': 'https://docs.github.com/en/copilot/reference/custom-agents-configuration',
     'note': 'Tool aliases only; prompt body is capped at 30,000 characters.'},
    {'id': 'generic', 'label': 'Generic prompt pack', 'format': 'markdown',
     'default_dir': 'kyper-roles', 'path_template': '{name}.md',
     'native_subagents': False, 'nesting': 'parent_policy',
     'read_only': 'none', 'tool_filter': 'none',
     'write_scope': 'contract_only', 'prompt_limit': None,
     'docs': None,
     'note': 'Manual role pack for hosts without native agent files.'},
)

HOST_IDS = tuple(host['id'] for host in HOSTS)

_CLAUDE_TOOLS = {
    'read': ['Read', 'Grep', 'Glob', 'Skill', 'mcp__kyper-workflow__*'],
    'docs': ['Read', 'Grep', 'Glob', 'Edit', 'Write', 'Skill',
             'mcp__kyper-workflow__*'],
    'test': ['Read', 'Grep', 'Glob', 'Edit', 'Write', 'Bash', 'PowerShell',
             'Skill', 'mcp__kyper-workflow__*'],
    'code': ['Read', 'Grep', 'Glob', 'Edit', 'Write', 'Bash', 'PowerShell',
             'Skill', 'mcp__kyper-workflow__*'],
}
_GEMINI_TOOLS = {
    'read': ['read_file', 'grep_search', 'mcp_kyper-workflow_*'],
    'docs': ['*'],
    'test': ['*'],
    'code': ['*'],
}
_COPILOT_TOOLS = {
    'read': ['read', 'search', 'kyper-workflow/*'],
    'docs': ['read', 'search', 'edit', 'kyper-workflow/*'],
    'test': ['read', 'search', 'edit', 'execute', 'todo', 'kyper-workflow/*'],
    'code': ['read', 'search', 'edit', 'execute', 'todo', 'kyper-workflow/*'],
}


def host(host_id):
    for entry in HOSTS:
        if entry['id'] == host_id:
            return dict(entry)
    raise ValueError('Unknown host: %r (choose %s)'
                     % (host_id, ', '.join(HOST_IDS)))


def capabilities():
    """Capability matrix, including limits the adapter does not pretend to fix."""
    return {'hosts': [dict(entry) for entry in HOSTS],
            'prefix': PREFIX,
            'manifest': MANIFEST,
            'degradation': ('Without native subagents, give one role card and one '
                            'approved task to the main agent at a time; the plan '
                            'still applies.'),
            'install_policy': ('Export writes only below the caller-supplied --out '
                               'directory. It never edits host configuration.')}


def _kind(role):
    if not role['write_scopes']:
        return 'read'
    scopes = list(role['write_scopes'])
    if all(scope == 'tests/**' or scope.startswith('tests/') for scope in scopes):
        return 'test'
    docs = {'docs/**', 'README.md', '*.md'}
    if all(scope in docs or scope.startswith('docs/') for scope in scopes):
        return 'docs'
    return 'code'


def _card_name(role):
    return role['id'] if role['id'].startswith(PREFIX) else PREFIX + role['id']


def _description(role):
    return ('%s Use only for an approved KyperWorkflow task bound to the %s role.'
            % (role['purpose'].strip(), role['title']))


def _yaml(value):
    # A JSON string is also a valid YAML double-quoted scalar and escapes
    # control characters without pulling in a YAML dependency.
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_list(name, values):
    return [name + ':'] + ['  - ' + _yaml(value) for value in values]


def _contract_lines(role, host_entry):
    writes = ', '.join('`%s`' % scope for scope in role['write_scopes']) or 'none (read only)'
    lines = [
        '## Contract',
        '',
        '- Role id: `%s`' % role['id'],
        '- Writes: %s' % writes,
        '- Allowed checks: %s' % ', '.join(role['allowed_checks']),
        '- Code modes: %s' % (', '.join(role['code_modes']) or 'none'),
        '- Complexity: %s' % ', '.join(role['complexity']),
        '- Parallel limit: %d (a planning hint, not a host max-turns value)'
        % role['max_parallel'],
        '- Required handoff: %s' % ', '.join(role['required_outputs']),
        '',
        'Host enforcement: %s Path scopes remain a contract even when the host '
        'has a tool filter.' % host_entry['note'],
    ]
    return lines


def _rules_lines(role, host_entry):
    lines = [
        '## Operating rules',
        '',
        '- You are one leaf worker. Do not create or delegate to further agents '
        'unless the main agent explicitly grants that tool and asks for it.',
        '- The approved specification and the delegation prompt are authoritative. '
        'A missing acceptance criterion or target path is a reason to report '
        'blocked, not to invent one.',
        '- Stay inside this role. If the task needs a write outside the contract, '
        'stop and ask the main agent to bind the task to the correct role.',
        '- Do not add, remove or approve tasks. Do not widen scope because the '
        'work seems easy.',
        '- Distinguish pass, fail, blocked and not_run. A check you cannot run is '
        'not a pass.',
    ]
    if host_entry['native_subagents']:
        lines.append('- Treat this file as a reusable role projection; the role '
                     'catalog remains the source of truth.')
    else:
        lines.append('- This host has no native agent file. Run this role '
                     'sequentially in the main agent and keep the same contract.')
    return lines


def _handoff_lines(role):
    meanings = {
        'changed': 'what changed and which workspace-relative files were touched',
        'tests': 'tests added or updated and the exact command/result',
        'findings': 'findings ordered by severity with file/line evidence',
        'verdict': 'pass, fail or blocked with a one-sentence reason',
        'summary': 'what was documented or integrated and what remains',
    }
    lines = ['## Handoff', '']
    for output in role['required_outputs']:
        meaning = meanings.get(output, 'this output, stated explicitly')
        lines.append('- `%s`: %s.' % (output, meaning))
    lines += ['', 'Report only observed evidence. Do not claim a check ran when it did not.']
    return lines


def _body(role, host_entry):
    lines = ['# KyperWorkflow role: %s' % role['title'], '', role['purpose'].strip(), '']
    lines += _contract_lines(role, host_entry)
    lines += ['']
    lines += _rules_lines(role, host_entry)
    lines += ['']
    lines += _handoff_lines(role)
    return '\n'.join(lines) + '\n'


def _markdown(role, host_entry):
    kind = _kind(role)
    fields = ['name', 'description']
    omitted = ['model', 'permissionMode', 'maxTurns', 'max_parallel']
    if host_entry['id'] == 'claude':
        tools = _CLAUDE_TOOLS[kind]
        fields.append('tools')
    elif host_entry['id'] == 'cursor':
        tools = None
        fields.append('readonly')
        omitted.append('tools')
    elif host_entry['id'] == 'gemini':
        tools = _GEMINI_TOOLS[kind]
        fields += ['kind', 'tools']
    elif host_entry['id'] == 'copilot':
        tools = _COPILOT_TOOLS[kind]
        fields.append('tools')
    else:
        raise ValueError('No Markdown adapter for host %r' % host_entry['id'])
    lines = ['---', 'name: ' + _yaml(_card_name(role)),
             'description: ' + _yaml(_description(role))]
    if tools is not None:
        lines += _yaml_list('tools', tools)
    if host_entry['id'] == 'cursor':
        lines.append('readonly: %s' % ('true' if kind == 'read' else 'false'))
    if host_entry['id'] == 'gemini':
        lines.append('kind: local')
    lines += ['---', '', _body(role, host_entry)]
    content = '\n'.join(lines)
    if host_entry['prompt_limit'] is not None:
        body_length = len(_body(role, host_entry))
        if body_length > host_entry['prompt_limit']:
            raise ValueError('Role %s body exceeds %s prompt limit (%d > %d)'
                             % (role['id'], host_entry['label'], body_length,
                                host_entry['prompt_limit']))
    return content, fields, omitted


def _toml(role, host_entry):
    kind = _kind(role)
    lines = [
        'name = ' + json.dumps(_card_name(role), ensure_ascii=False),
        'description = ' + json.dumps(_description(role), ensure_ascii=False),
    ]
    if kind in ('read', 'docs'):
        lines += ['features.shell_tool = false',
                  'features.request_permissions_tool = false']
    lines += ['developer_instructions = ' + json.dumps(
        _body(role, host_entry), ensure_ascii=False)]
    fields = ['name', 'description', 'developer_instructions']
    if kind in ('read', 'docs'):
        fields += ['features.shell_tool', 'features.request_permissions_tool']
    omitted = ['model', 'model_reasoning_effort', 'sandbox_mode',
               'approval_policy', 'mcp_servers']
    return '\n'.join(lines) + '\n', fields, omitted


def render(host_id, role):
    """Render one role card without touching the filesystem."""
    entry = host(host_id)
    if not isinstance(role, dict):
        raise ValueError('Role must be a validated catalog entry')
    required = ('id', 'title', 'purpose', 'allowed_checks', 'write_scopes',
                'code_modes', 'complexity', 'max_parallel', 'required_outputs')
    missing = [key for key in required if key not in role]
    if missing:
        raise ValueError('Role is missing fields: %s' % ', '.join(missing))
    if not isinstance(role['id'], str) or not re.fullmatch(
            r'[a-z0-9][a-z0-9-]*', role['id']):
        raise ValueError('Role id is not a safe lowercase slug')
    name = _card_name(role)
    if host_id == 'codex':
        content, fields, omitted = _toml(role, entry)
    elif host_id == 'generic':
        content = _body(role, entry)
        fields, omitted = ['body'], ['host_fields']
    else:
        content, fields, omitted = _markdown(role, entry)
    return {'host': host_id, 'role': role['id'], 'name': name,
            'path': entry['path_template'].format(name=name),
            'format': entry['format'], 'fields': fields,
            'omitted': omitted, 'content': content}


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    return 'sha256:' + hashlib.sha256(encoded).hexdigest()


def _canonical(data):
    """Compare text as LF so a Git CRLF checkout is not a false drift."""
    return data.replace(b'\r\n', b'\n')


def _selected_roles(catalog, role_ids):
    available = {role['id']: role for role in catalog['roles']}
    if role_ids:
        unknown = sorted(set(role_ids) - set(available))
        if unknown:
            raise ValueError('Unknown role(s): %s' % ', '.join(unknown))
        chosen = [available[name] for name in role_ids]
    else:
        chosen = list(catalog['roles'])
    return sorted(chosen, key=lambda role: role['id'])


def files(host_id, catalog, role_ids=None):
    """Return every expected relative path and its exact LF-terminated text."""
    entry = host(host_id)
    chosen = _selected_roles(catalog, role_ids)
    cards = [render(host_id, role) for role in chosen]
    result = {card['path']: card['content'] for card in cards}
    manifest = {
        'format_version': FORMAT_VERSION,
        'generator': 'KyperWorkflow',
        'generator_version': __version__,
        'host': host_id,
        'host_path': entry['default_dir'],
        'contract_digest': _digest(chosen),
        'roles': [{'role': card['role'], 'name': card['name'],
                   'path': card['path'], 'fields': card['fields'],
                   'omitted': card['omitted'],
                   'sha256': hashlib.sha256(card['content'].encode('utf-8')).hexdigest()}
                  for card in cards],
        'install_policy': ('Explicit output directory only; no host configuration '
                           'was modified.'),
    }
    result[MANIFEST] = json.dumps(manifest, ensure_ascii=False, indent=2,
                                  sort_keys=True) + '\n'
    return result


def check(host_id, catalog, out, role_ids=None):
    """Report missing or byte-different expected files, without writing."""
    root = Path(out)
    selected = role_ids or None
    if selected is None:
        manifest_path = root / MANIFEST
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                if manifest.get('host') == host_id:
                    selected = [item['role'] for item in manifest.get('roles', [])]
            except (ValueError, KeyError, TypeError, UnicodeError):
                # A broken manifest is reported as drift below; do not turn it
                # into an exception that hides the missing card files.
                selected = None
    expected = files(host_id, catalog, selected)
    stale = []
    for relative, content in sorted(expected.items()):
        path = root / relative
        if not path.is_file():
            stale.append({'path': relative, 'reason': 'missing'})
        elif _canonical(path.read_bytes()) != content.encode('utf-8'):
            stale.append({'path': relative, 'reason': 'differs'})
    return {'host': host_id, 'out': str(root), 'clean': not stale,
            'stale': stale, 'files': sorted(expected)}


def write(host_id, catalog, out, role_ids=None):
    """Write exactly the expected cards and manifest into a caller-supplied local path."""
    expected = files(host_id, catalog, role_ids)
    root = Path(out)
    root.mkdir(parents=True, exist_ok=True)
    changed = []
    for relative, content in sorted(expected.items()):
        path = root / relative
        old = _canonical(path.read_bytes()) if path.is_file() else None
        new = content.encode('utf-8')
        if old != new:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('w', encoding='utf-8', newline='') as stream:
                stream.write(content)
            changed.append(relative)
    return {'host': host_id, 'out': str(root), 'files': sorted(expected),
            'changed': changed}
