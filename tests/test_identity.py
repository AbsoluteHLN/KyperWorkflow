"""The prompt shortcut is an alias, not a second MCP identity."""
import unittest

from kyper_workflow import PROMPT_ALIAS, __version__


class IdentityTests(unittest.TestCase):
    def test_prompt_alias_is_stable_and_short(self):
        self.assertEqual(PROMPT_ALIAS, 'KalWf')
        self.assertLessEqual(len(PROMPT_ALIAS), 8)

    def test_version_remains_separate_from_alias(self):
        self.assertEqual(__version__, '0.2.0')
        self.assertNotEqual(PROMPT_ALIAS, __version__)


if __name__ == '__main__':
    unittest.main()
