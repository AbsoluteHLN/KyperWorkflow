"""First-run configuration items are explicit, complete and never silently defaulted."""
import tempfile
import unittest
from pathlib import Path

from kyper_workflow import onboarding


class OnboardingTests(unittest.TestCase):
    def test_every_item_has_the_fields_a_session_needs(self):
        ids = [item['id'] for item in onboarding.ALL_ITEMS]
        self.assertEqual(len(ids), len(set(ids)))
        for item in onboarding.ALL_ITEMS:
            self.assertTrue(item['title'])
            self.assertTrue(item['why'])
            self.assertTrue(item['how'])
            self.assertTrue(item['question'].endswith(('？', '?')))
            self.assertIsInstance(item['required'], bool)

    def test_subagents_and_dependency_paths_are_covered(self):
        ids = {item['id'] for item in onboarding.ALL_ITEMS}
        self.assertIn('model_routes', ids)
        self.assertIn('dependency_paths', ids)
        self.assertIn('host_checks', ids)
        self.assertIn('state_dir', ids)
        table = onboarding.markdown()
        self.assertIn('子智能体与模型路由', table)
        self.assertIn('依赖库路径', table)

    def test_nothing_is_reported_ready_without_user_input(self):
        result = onboarding.checklist()
        self.assertFalse(result['ready'])
        self.assertIn('project_root', result['needs_input'])
        self.assertIn('state_dir', result['needs_input'])
        self.assertIn('host_checks', result['needs_input'])
        self.assertIn('项目根目录', result['prompt'])

    def test_detected_items_flip_to_ok_only_with_real_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            result = onboarding.checklist(Path(directory), state_dir=Path(directory) / 'state',
                                          environ={'PYTHONPATH': 'lib'})
        statuses = {item['id']: item['status'] for item in result['items']}
        self.assertEqual(statuses['python_runtime'], 'ok')
        self.assertEqual(statuses['project_root'], 'ok')
        self.assertEqual(statuses['state_dir'], 'ok')
        self.assertEqual(statuses['dependency_paths'], 'ok')
        self.assertNotIn('project_root', result['needs_input'])
        self.assertIn('host_checks', result['needs_input'])

    def test_project_tests_are_platform_reported(self):
        result = onboarding.checklist()
        status = {item['id']: item['status'] for item in result['items']}['project_tests']
        self.assertIn(status, ('ok', 'platform_limited'))

    def test_prompt_lists_required_items_first_and_blocks_planning(self):
        result = onboarding.checklist()
        self.assertIn('未确认前', result['prompt'])
        self.assertIn('（必填）', result['prompt'])


if __name__ == '__main__':
    unittest.main()
