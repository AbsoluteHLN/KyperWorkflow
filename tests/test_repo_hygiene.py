"""Generated maps and tracked files must not carry this machine's layout."""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from kyper_workflow import structure

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ('.kyper/project-map.json', '.kyper/project-graph.dot',
             '.kyper/project-graph.graphml', '.kyper/project-graph.tsv',
             'docs/PROJECT-MAP.md')


def git(args):
    return subprocess.run(['git'] + args, cwd=ROOT, capture_output=True, text=True)


DRIVE = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:[\\/]')


class RepoHygieneTests(unittest.TestCase):
    def setUp(self):
        if git(['rev-parse', '--git-dir']).returncode != 0:
            self.skipTest('not a git checkout')

    def test_generated_views_have_no_absolute_paths(self):
        for relative in GENERATED:
            path = ROOT / relative
            self.assertTrue(path.is_file(), '%s is missing; run map --write' % relative)
            text = path.read_text(encoding='utf-8')
            self.assertIsNone(DRIVE.search(text), relative)
            self.assertNotIn(str(Path.home()), text, relative)
            self.assertNotIn(str(ROOT), text, relative)

    def test_tracked_files_do_not_hold_the_checkout_path(self):
        listed = git(['ls-files'])
        self.assertEqual(listed.returncode, 0)
        needle = str(ROOT)
        for relative in listed.stdout.splitlines():
            path = ROOT / relative
            if not path.is_file() or path.suffix in ('.png', '.jpg', '.gif', '.ico'):
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            self.assertNotIn(needle, text, relative)

    def test_local_config_is_ignored_and_example_ships(self):
        self.assertEqual(git(['check-ignore', '-q', '.kyper/setup.local.json']).returncode, 0,
                         'setup.local.json must stay untracked')
        example = 'docs/setup.local.example.json'
        self.assertTrue((ROOT / example).is_file(), '%s must ship with the repo' % example)
        self.assertNotEqual(git(['check-ignore', '-q', example]).returncode, 0,
                            '%s must not be ignored' % example)
        self.assertEqual(git(['ls-files', '--error-unmatch', '.kyper/setup.local.json']).returncode,
                         1, 'no machine-local config may be tracked')

    def test_committed_map_omits_root_key(self):
        data = json.loads((ROOT / '.kyper' / 'project-map.json').read_text(encoding='utf-8'))
        self.assertNotIn('root', data)
        self.assertIn('name', data)


if __name__ == '__main__':
    unittest.main()
