"""First-run configuration items are explicit, complete and never silently defaulted."""
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from kyper_workflow import onboarding


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        """Never read this machine's real local config during tests."""
        self._directory = tempfile.TemporaryDirectory()
        absent = Path(self._directory.name) / 'absent-setup.json'
        patcher_home = mock.patch.object(Path, 'home',
                                                  return_value=Path(self._directory.name))
        patcher_env = mock.patch.dict(onboarding.os.environ,
                                               {onboarding.LOCAL_CONFIG_ENV: str(absent)})
        patcher_home.start()
        patcher_env.start()
        self.addCleanup(patcher_env.stop)
        self.addCleanup(patcher_home.stop)
        self.addCleanup(self._directory.cleanup)

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
        self.assertIn('execution_topology', ids)
        self.assertIn('dependency_paths', ids)
        self.assertIn('host_checks', ids)
        self.assertIn('state_dir', ids)
        table = onboarding.markdown()
        self.assertIn('子智能体与模型路由', table)
        self.assertIn('子智能体执行方式', table)
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

    def test_placeholders_stay_unconfirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = onboarding.checklist(
                Path(directory), state_dir='待配置',
                environ={'PYTHONPATH': '局部路径'},
                host_checks={'text': '<待配置>'},
                model_routes=[{'role': '<待配置>', 'models': ['<待配置>'],
                               'effort': '<待配置>', 'max_parallel': 1}],
                execution_topology={'mode': '待配置'})
        statuses = {item['id']: item['status'] for item in result['items']}
        self.assertEqual(statuses['project_root'], 'ok')
        self.assertEqual(statuses['state_dir'], 'needs_user_input')
        self.assertEqual(statuses['dependency_paths'], 'needs_user_input')
        self.assertEqual(statuses['host_checks'], 'needs_user_input')
        self.assertEqual(statuses['model_routes'], 'needs_user_input')
        self.assertEqual(statuses['execution_topology'], 'needs_user_input')

    def test_project_tests_are_platform_reported(self):
        result = onboarding.checklist()
        status = {item['id']: item['status'] for item in result['items']}['project_tests']
        self.assertIn(status, ('ok', 'platform_limited'))

    def test_prompt_lists_required_items_first_and_blocks_planning(self):
        result = onboarding.checklist()
        self.assertIn('未确认前', result['prompt'])
        self.assertIn('（必填）', result['prompt'])


    def test_local_config_file_supplies_values_and_is_named(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / '.kyper' / 'setup.local.json'
            config.parent.mkdir()
            config.write_text(json.dumps({'state_dir': str(root / 'state'),
                                          'host_checks': {'text': 'session model'}}),
                              encoding='utf-8')
            result = onboarding.checklist(root)
            self.assertEqual(result['config_source'], str(config))
            self.assertIsNone(result['config_error'])
            statuses = {item['id']: item['status'] for item in result['items']}
            self.assertEqual(statuses['state_dir'], 'ok')
            self.assertEqual(statuses['host_checks'], 'ok')
            self.assertIn('dependency_paths', result['needs_input'])
            self.assertIn('git-ignored', result['config_note'])

    def test_unreadable_local_config_stays_a_question(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'broken.json'
            config.write_text('{not json', encoding='utf-8')
            result = onboarding.checklist(config_path=str(config))
            self.assertIn('unreadable', result['config_error'])
            self.assertFalse(result['ready'])

    def test_committed_example_uses_only_placeholders(self):
        text = (Path(__file__).resolve().parent.parent / 'docs'
                / 'setup.local.example.json').read_text(encoding='utf-8')
        data = json.loads(text)
        self.assertEqual(set(data) - {'_note'}, set(onboarding.CONFIG_KEYS))
        flat = json.dumps(data, ensure_ascii=False)
        self.assertNotRegex(flat.lower(), r'[a-z]:[\\/]')
        self.assertNotIn(str(Path.home()).lower(), flat.lower())
        self.assertNotIn('Users', flat)
        self.assertIn('<', flat)


if __name__ == '__main__':
    unittest.main()
