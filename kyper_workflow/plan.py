"""Deterministic execution plan for approved tasks.

Given the task graph the user already approved, this module answers three
questions without calling a model: which tasks may run at the same time, which
ones must be serialised because their write scopes or role limits collide, and
which chain is on the critical path. Nothing here starts work; it only refuses
to hide a conflict.
"""
from __future__ import annotations

from collections import defaultdict

PASS = 'pass'
RUNNABLE = ('not_run', 'fail', 'blocked')


def _overlap(a, b):
    """Same rule as Workflow.start: equal, or one path inside the other."""
    if a == '.' or b == '.':
        return True
    return a == b or a.startswith(b.rstrip('/') + '/') or b.startswith(a.rstrip('/') + '/')


def _scope_conflict(left, right):
    return any(_overlap(a, b) for a in left for b in right)


def _validate(tasks):
    if not isinstance(tasks, dict) or not tasks:
        raise ValueError('At least one task is required')
    for name, task in tasks.items():
        if not isinstance(name, str) or not name:
            raise ValueError('Invalid task name')
        if not isinstance(task, dict):
            raise ValueError('Task %r must be a mapping' % name)
        depends = task.get('depends') or []
        if not isinstance(depends, list):
            raise ValueError('Task %r dependencies must be a list' % name)
        for dep in depends:
            if dep not in tasks:
                raise ValueError('Task %r depends on unknown task %r' % (name, dep))
        if not isinstance(task.get('writes') or [], list):
            raise ValueError('Task %r write scopes must be a list' % name)


def _order(tasks):
    """Topological order by depth, ties broken by task name."""
    depth = {}

    def visit(name, trail):
        if name in depth:
            return depth[name]
        if name in trail:
            raise ValueError('Dependency cycle at %r' % name)
        trail.add(name)
        depends = tasks[name].get('depends') or []
        value = 1 + max([visit(dep, trail) for dep in depends], default=0)
        trail.discard(name)
        depth[name] = value
        return value

    for name in tasks:
        visit(name, set())
    return depth


def _critical_path(tasks, depth):
    """Longest dependency chain; ties settle on the lexicographically smallest."""
    best = {}

    def chain(name):
        if name in best:
            return best[name]
        depends = tasks[name].get('depends') or []
        if not depends:
            best[name] = [name]
            return best[name]
        candidates = [chain(dep) for dep in depends]
        candidates.sort(key=lambda item: (-len(item), item))
        best[name] = candidates[0] + [name]
        return best[name]

    for name in tasks:
        chain(name)
    winner = sorted(best.values(), key=lambda item: (-len(item), item))[0]
    return winner


def _role_limits(tasks, roles):
    """Role id -> parallel limit, or an error for an unknown role."""
    limits = {}
    for name, task in tasks.items():
        role_id = task.get('role')
        if not role_id:
            continue
        entry = next((item for item in roles if item['id'] == role_id), None)
        if entry is None:
            raise ValueError('Task %r names unknown role %r' % (name, role_id))
        limits[role_id] = entry['max_parallel']
    return limits


def _batches(names, tasks, limits):
    """Greedy packing: a batch is a set that may start together."""
    batches, running_scopes, running_roles = [], [], {}
    for name in names:
        task = tasks[name]
        scopes = task.get('writes') or []
        role_id = task.get('role')
        cap = limits.get(role_id, 10 ** 6)
        if any(_scope_conflict(scopes, other) for other in running_scopes) or \
                (role_id and running_roles.get(role_id, 0) >= cap):
            batches.append([name])
            running_scopes, running_roles = [list(scopes)], ({role_id: 1} if role_id else {})
        else:
            if batches:
                batches[-1].append(name)
            else:
                batches.append([name])
            running_scopes.append(list(scopes))
            if role_id:
                running_roles[role_id] = running_roles.get(role_id, 0) + 1
    return batches


def analyze(tasks, *, roles=()):
    """Return waves, runnable batches, conflicts, critical path and blockers."""
    _validate(tasks)
    depth = _order(tasks)
    limits = _role_limits(tasks, roles)
    waves = defaultdict(list)
    for name, level in depth.items():
        waves[level].append(name)
    ordered = [[name for name in sorted(waves[level])] for level in sorted(waves)]

    conflicts = []
    for wave in ordered:
        for index, left in enumerate(wave):
            for right in wave[index + 1:]:
                if _scope_conflict(tasks[left].get('writes') or [],
                                   tasks[right].get('writes') or []):
                    conflicts.append({'tasks': [left, right], 'kind': 'write_scope'})

    batches = []
    for wave in ordered:
        batches.extend(_batches(wave, tasks, limits))

    reasons = {}
    for name, task in sorted(tasks.items()):
        if task.get('status') not in (None,) + RUNNABLE:
            continue
        failed = [dep for dep in task.get('depends') or []
                  if (tasks[dep].get('status') in ('fail', 'blocked'))]
        if failed:
            reasons[name] = 'upstream %s did not pass' % ', '.join(sorted(failed))

    return {'waves': ordered, 'batches': batches,
            'critical_path': _critical_path(tasks, depth),
            'depths': {name: depth[name] for name in sorted(depth)},
            'conflicts': conflicts,
            'blocked': reasons,
            'role_limits': {key: limits[key] for key in sorted(limits)}}


def next_runnable(tasks):
    """Tasks that may start now without violating dependencies or write scopes."""
    _validate(tasks)
    running_scopes = [task.get('writes') or [] for task in tasks.values()
                      if task.get('status') == 'running']
    ready = []
    for name, task in sorted(tasks.items()):
        status = task.get('status') or 'not_run'
        if status not in RUNNABLE:
            continue
        depends = task.get('depends') or []
        if any((tasks[dep].get('status') or 'not_run') != PASS for dep in depends):
            continue
        scopes = task.get('writes') or []
        if any(_scope_conflict(scopes, other) for other in running_scopes):
            continue
        ready.append(name)
    return ready


def render_markdown(plan_model):
    """Human-readable plan, deterministic and free of machine paths."""
    lines = ['## Execution plan', '',
             '- Waves: %d; start batches: %d' % (len(plan_model['waves']),
                                                len(plan_model['batches'])),
             '- Critical path: %s' % ' -> '.join('`%s`' % name
                                                 for name in plan_model['critical_path']),
             '']
    for index, wave in enumerate(plan_model['waves'], 1):
        lines.append('### Wave %d' % index)
        lines.append('')
        lines.append('- ' + ', '.join('`%s`' % name for name in wave))
        lines.append('')
    lines += ['### Start batches', '',
              'Tasks in one batch have no dependency, write-scope or role-limit',
              'conflict and may run together; each later batch waits for the previous one.', '']
    for index, batch in enumerate(plan_model['batches'], 1):
        lines.append('%d. %s' % (index, ', '.join('`%s`' % name for name in batch)))
    if plan_model['conflicts']:
        lines += ['', '### Serialised by write scope', '']
        for conflict in plan_model['conflicts']:
            lines.append('- %s conflicts with %s' % (
                '`%s`' % conflict['tasks'][0], '`%s`' % conflict['tasks'][1]))
    if plan_model['role_limits']:
        lines += ['', '### Role limits', '']
        for role_id, limit in plan_model['role_limits'].items():
            lines.append('- `%s`: at most %d at a time' % (role_id, limit))
    if plan_model['blocked']:
        lines += ['', '### Blocked by upstream', '']
        for name, reason in plan_model['blocked'].items():
            lines.append('- `%s`: %s' % (name, reason))
    return '\n'.join(lines) + '\n'


def digest(plan_model):
    return ('waves %d; batches %d; critical path %s; conflicts %d; blocked %d'
            % (len(plan_model['waves']), len(plan_model['batches']),
               ' -> '.join(plan_model['critical_path']),
               len(plan_model['conflicts']), len(plan_model['blocked'])))
