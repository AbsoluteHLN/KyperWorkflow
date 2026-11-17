"""Roles inside the workflow: scope binding, parallel limits, handoff, planning."""
import tempfile
import unittest
from pathlib import Path

from kyper_workflow import catalog
from kyper_workflow.workflow import Workflow


RECORD = {'sources': ['https://example.org'], 'source': 'user',
          'choice': 'fixture', 'status': 'pass'}


def specification(root, tasks, *, finish=True):
    """Drive a workflow to the specification stage and add the given tasks."""
    workflow = Workflow(root / 'state.json', confirm=lambda shown: shown)
    for stage in ('research', 'direction_review', 'specification'):
        workflow.transition(stage, record=RECORD)
    workflow.revise('Role-aware specification')
    for name, fields in tasks:
        workflow.add_task(name, **fields)
    if finish:
        workflow.transition('specification_qa', record=RECORD)
        workflow.transition('awaiting_confirmation', record=RECORD)
    return workflow


def evidence(workflow, checks, code_mode=None, handoff=None):
    result = {'review': {'revision': workflow.data['revision'], 'allow_completion': True,
                         'code_mode': code_mode,
                         'checks': {name: 'pass' for name in checks}}}
    if handoff is not None:
        result['handoff'] = handoff
    return result


class RoleWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_role_binding_rejects_out_of_scope_writes_at_add_task(self):
        workflow = specification(self.root, [], finish=False)
        with self.assertRaisesRegex(ValueError, 'outside role test-author'):
            workflow.add_task('edit-source', writes=['kyper_workflow/cli.py'],
                              acceptance='x', code_mode='project_tests',
                              role='test-author')

    def test_unknown_role_is_rejected(self):
        workflow = specification(self.root, [], finish=False)
        with self.assertRaisesRegex(ValueError, 'Unknown role'):
            workflow.add_task('x', writes=['src/a.py'], acceptance='x',
                              code_mode='syntax', role='ghost')

    def test_role_and_component_are_part_of_the_approved_proposal(self):
        workflow = specification(self.root, [(
            'build', {'writes': ['src/app.py'], 'acceptance': 'works',
                      'code_mode': 'syntax', 'role': 'implementer',
                      'component': 'code-change', 'component_version': 1})])
        workflow.approve()
        approved = workflow.data['approval']['tasks']['build']
        self.assertEqual(approved['role'], 'implementer')
        self.assertEqual(approved['component'], 'code-change')
        self.assertEqual(approved['component_version'], 1)

    def test_role_parallel_limit_is_enforced_by_start(self):
        tasks = [(name, {'writes': ['src/%s.py' % name], 'acceptance': 'x',
                         'code_mode': 'syntax', 'role': 'implementer'})
                 for name in ('a', 'b', 'c')]
        workflow = specification(self.root, tasks)
        workflow.approve()
        workflow.start('a')
        workflow.start('b')
        with self.assertRaisesRegex(ValueError, 'parallel limit'):
            workflow.start('c')

    def test_handoff_is_required_for_a_role_task(self):
        workflow = specification(self.root, [(
            'build', {'writes': ['src/app.py'], 'acceptance': 'works',
                      'code_mode': 'syntax', 'role': 'implementer'})])
        workflow.approve()
        workflow.start('build')
        workflow.bind_verifier('build', lambda: True)
        with self.assertRaisesRegex(ValueError, 'handoff missing'):
            workflow.finish('build', status='pass',
                            result=evidence(workflow, ['code'], code_mode='syntax'))
        workflow.finish('build', status='pass',
                        result=evidence(workflow, ['code'], code_mode='syntax',
                                        handoff={'changed': ['src/app.py']}))
        self.assertEqual(workflow.data['tasks']['build']['status'], 'pass')

    def test_plan_lists_waves_and_batches_from_approved_tasks(self):
        tasks = [('explore', {'writes': (), 'acceptance': 'answered',
                              'required_checks': ['text'], 'role': 'explorer'}),
                 ('build', {'writes': ['src/app.py'], 'acceptance': 'works',
                            'code_mode': 'syntax', 'role': 'implementer',
                            'depends': ['explore']}),
                 ('review', {'writes': (), 'acceptance': 'reviewed',
                             'required_checks': ['text', 'model'], 'role': 'reviewer',
                             'depends': ['build']})]
        workflow = specification(self.root, tasks)
        workflow.approve()
        model = workflow.plan()
        self.assertEqual(model['waves'], [['explore'], ['build'], ['review']])
        self.assertEqual(model['critical_path'], ['explore', 'build', 'review'])
        self.assertIn('explorer', model['role_limits'])

    def test_plan_requires_tasks(self):
        workflow = specification(self.root, [])
        with self.assertRaisesRegex(ValueError, 'No tasks'):
            workflow.plan()

    def test_component_instantiation_feeds_add_task(self):
        loaded = catalog.builtin()
        rendered = catalog.instantiate(loaded, 'test-only', name='tests',
                                       params={'tests': ['tests/test_app.py'],
                                               'covers': 'the empty case'})
        workflow = specification(self.root, [(rendered.pop('name'), rendered)])
        workflow.approve()
        task = workflow.data['tasks']['tests']
        self.assertEqual(task['role'], 'test-author')
        self.assertEqual(task['component'], 'test-only')
        self.assertEqual(task['writes'], ['tests/test_app.py'])

    def test_role_survives_reload(self):
        workflow = specification(self.root, [(
            'build', {'writes': ['src/app.py'], 'acceptance': 'works',
                      'code_mode': 'syntax', 'role': 'implementer'})])
        workflow.approve()
        reloaded = Workflow(workflow.path)
        self.assertEqual(reloaded.data['tasks']['build']['role'], 'implementer')
        self.assertEqual(reloaded.plan()['role_limits'], {'implementer': 2})


if __name__ == '__main__':
    unittest.main()
