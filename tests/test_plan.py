"""Deterministic scheduling: waves, write-scope conflicts, role limits."""
import unittest

from kyper_workflow import catalog, plan


ROLES = catalog.builtin()['roles']


def t(depends=(), writes=(), role=None, status='not_run'):
    task = {'depends': list(depends), 'writes': list(writes),
            'acceptance': 'accepted', 'required_checks': ['code'],
            'status': status}
    if role:
        task['role'] = role
    return task


class PlanTests(unittest.TestCase):
    def test_chain_becomes_one_task_per_wave(self):
        tasks = {'a': t(), 'b': t(['a'], ['src/b.py']), 'c': t(['b'], ['src/c.py'])}
        model = plan.analyze(tasks, roles=ROLES)
        self.assertEqual(model['waves'], [['a'], ['b'], ['c']])
        self.assertEqual(model['critical_path'], ['a', 'b', 'c'])
        self.assertEqual(model['batches'], [['a'], ['b'], ['c']])

    def test_independent_tasks_share_a_wave_and_batch(self):
        tasks = {'a': t(writes=['src/a.py']), 'b': t(writes=['src/b.py'])}
        model = plan.analyze(tasks, roles=ROLES)
        self.assertEqual(model['waves'], [['a', 'b']])
        self.assertEqual(model['batches'], [['a', 'b']])
        self.assertEqual(model['conflicts'], [])

    def test_diamond_puts_siblings_together(self):
        tasks = {'root': t(writes=['src/root.py']),
                 'left': t(['root'], ['src/left.py']),
                 'right': t(['root'], ['src/right.py']),
                 'join': t(['left', 'right'], ['src/join.py'])}
        model = plan.analyze(tasks, roles=ROLES)
        self.assertEqual(model['waves'], [['root'], ['left', 'right'], ['join']])
        self.assertEqual(model['critical_path'], ['root', 'left', 'join'])

    def test_write_overlap_is_serialised_and_reported(self):
        tasks = {'a': t(writes=['src']), 'b': t(writes=['src/app.py'])}
        model = plan.analyze(tasks, roles=ROLES)
        self.assertEqual(model['waves'], [['a', 'b']])
        self.assertEqual(model['batches'], [['a'], ['b']])
        self.assertEqual(model['conflicts'], [{'tasks': ['a', 'b'], 'kind': 'write_scope'}])

    def test_role_parallel_limit_splits_batches(self):
        tasks = {name: t(writes=['src/%s.py' % name], role='implementer')
                 for name in ('a', 'b', 'c')}
        model = plan.analyze(tasks, roles=ROLES)
        self.assertEqual(model['role_limits'], {'implementer': 2})
        self.assertEqual(len(model['batches']), 2)
        joined = [name for batch in model['batches'] for name in batch]
        self.assertEqual(joined, ['a', 'b', 'c'])

    def test_unknown_role_is_an_error_not_a_default(self):
        tasks = {'a': t(role='ghost')}
        with self.assertRaisesRegex(ValueError, 'unknown role'):
            plan.analyze(tasks, roles=ROLES)

    def test_cycle_and_missing_dependency_are_errors(self):
        with self.assertRaisesRegex(ValueError, 'cycle'):
            plan.analyze({'a': t(['b']), 'b': t(['a'])}, roles=ROLES)
        with self.assertRaisesRegex(ValueError, 'unknown task'):
            plan.analyze({'a': t(['ghost'])}, roles=ROLES)

    def test_next_runnable_respects_dependencies_and_running_writes(self):
        tasks = {'a': t(writes=['src']), 'b': t(['a'], ['src/b.py']),
                 'c': t(writes=['docs/guide.md'])}
        self.assertEqual(plan.next_runnable(tasks), ['a', 'c'])
        tasks['a']['status'] = 'running'
        self.assertEqual(plan.next_runnable(tasks), ['c'])
        tasks['a']['status'] = 'pass'
        self.assertEqual(plan.next_runnable(tasks), ['b', 'c'])

    def test_failed_upstream_blocks_downstream(self):
        tasks = {'a': t(writes=['src/a.py'], status='fail'),
                 'b': t(['a'], ['src/b.py'])}
        model = plan.analyze(tasks, roles=ROLES)
        self.assertIn('b', model['blocked'])
        self.assertIn('a', model['blocked']['b'])
        # A failed task may be retried under the same approval; its dependants may not.
        self.assertEqual(plan.next_runnable(tasks), ['a'])

    def test_renders_are_deterministic_and_explain_serialisation(self):
        tasks = {'a': t(writes=['src']), 'b': t(writes=['src/app.py'])}
        model = plan.analyze(tasks, roles=ROLES)
        text = plan.render_markdown(model)
        self.assertEqual(text, plan.render_markdown(plan.analyze(tasks, roles=ROLES)))
        self.assertIn('## Execution plan', text)
        self.assertIn('### Serialised by write scope', text)
        self.assertIn('critical path', plan.digest(model))


if __name__ == '__main__':
    unittest.main()
