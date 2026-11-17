"""The distributable Skill and the project copy must not drift apart."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'skills' / 'kyper-workflow' / 'SKILL.md'
PROJECT_COPY = ROOT / '.agents' / 'skills' / 'kyper-workflow' / 'SKILL.md'


class SkillCopyTests(unittest.TestCase):
    def test_project_copy_matches_distributable_skill(self):
        self.assertTrue(SOURCE.is_file(), 'distributable Skill is missing')
        self.assertTrue(PROJECT_COPY.is_file(), 'project Skill copy is missing')
        self.assertEqual(PROJECT_COPY.read_bytes(), SOURCE.read_bytes(),
                         'skills/kyper-workflow and .agents/skills/kyper-workflow differ')
        text = SOURCE.read_text(encoding='utf-8')
        self.assertIn('Prompt alias: KalWf', text)
        self.assertIn('server name remains `kyper-workflow`', text)


if __name__ == '__main__':
    unittest.main()
