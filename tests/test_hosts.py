"""Host adapters are deterministic projections, not installed configuration."""
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from kyper_workflow import catalog, hosts


def role(catalog_data, role_id):
    return catalog.role(catalog_data, role_id)


def frontmatter(text):
    if not text.startswith('---\n'):
        raise AssertionError('missing frontmatter')
    header, _body = text[4:].split('\n---\n', 1)
    return header.splitlines()


class HostAdapterTests(unittest.TestCase):
    def setUp(self):
        self.catalog = catalog.builtin()

    def test_every_host_projects_every_role_deterministically(self):
        for host_id in hosts.HOST_IDS:
            for entry in self.catalog['roles']:
                first = hosts.render(host_id, entry)
                second = hosts.render(host_id, entry)
                self.assertEqual(first, second)
                self.assertTrue(first['content'].endswith('\n'))
                self.assertNotIn('\r', first['content'])
                self.assertTrue(first['name'].startswith('kyper-'))
                self.assertEqual(first['path'].split('/')[-1].startswith('kyper-'), True)
                self.assertNotIn(str(Path.home()), first['content'])

    def test_names_are_namespaced_to_avoid_host_builtins(self):
        for host_id in hosts.HOST_IDS:
            card = hosts.render(host_id, role(self.catalog, 'explorer'))
            self.assertEqual(card['name'], 'kyper-explorer')
        already = dict(role(self.catalog, 'explorer'))
        already['id'] = 'kyper-explorer'
        self.assertEqual(hosts.render('cursor', already)['name'], 'kyper-explorer')
        self.assertIn('kyper-explorer.md', hosts.render('claude', self.catalog['roles'][0])['path'])
        self.assertIn('kyper-explorer.toml', hosts.render('codex', self.catalog['roles'][0])['path'])
        self.assertIn('kyper-explorer.agent.md',
                      hosts.render('copilot', self.catalog['roles'][0])['path'])

    def test_unsafe_role_ids_cannot_escape_the_output_directory(self):
        unsafe = dict(role(self.catalog, 'explorer'))
        unsafe['id'] = '../escape'
        with self.assertRaisesRegex(ValueError, 'safe lowercase slug'):
            hosts.render('claude', unsafe)

    def test_read_only_roles_are_projected_as_read_only_where_supported(self):
        cursor_reviewer = hosts.render('cursor', role(self.catalog, 'reviewer'))['content']
        cursor_implementer = hosts.render('cursor', role(self.catalog, 'implementer'))['content']
        self.assertIn('readonly: true', cursor_reviewer)
        self.assertIn('readonly: false', cursor_implementer)

        claude_reviewer = hosts.render('claude', role(self.catalog, 'reviewer'))['content']
        claude_implementer = hosts.render('claude', role(self.catalog, 'implementer'))['content']
        self.assertNotIn('  - "Edit"', frontmatter(claude_reviewer))
        self.assertNotIn('  - "Write"', frontmatter(claude_reviewer))
        self.assertIn('  - "Edit"', frontmatter(claude_implementer))

        codex_reviewer = hosts.render('codex', role(self.catalog, 'reviewer'))['content']
        self.assertIn('features.shell_tool = false', codex_reviewer)
        self.assertNotIn('sandbox_mode', codex_reviewer)

    def test_codex_output_is_valid_standalone_toml(self):
        card = hosts.render('codex', role(self.catalog, 'explorer'))
        data = tomllib.loads(card['content'])
        self.assertEqual(data['name'], 'kyper-explorer')
        self.assertTrue(data['description'])
        self.assertIn('leaf worker', data['developer_instructions'])
        self.assertFalse(data['features']['shell_tool'])
        self.assertNotIn('model', data)

    def test_claude_frontmatter_has_a_real_tool_allowlist(self):
        card = hosts.render('claude', role(self.catalog, 'test-author'))
        header = frontmatter(card['content'])
        self.assertIn('name: "kyper-test-author"', header)
        self.assertIn('  - "Read"', header)
        self.assertIn('  - "Edit"', header)
        self.assertIn('  - "Skill"', header)
        self.assertIn('  - "mcp__kyper-workflow__*"', header)

    def test_gemini_and_copilot_use_only_documented_tool_names(self):
        gemini = hosts.render('gemini', role(self.catalog, 'reviewer'))['content']
        self.assertIn('  - "read_file"', frontmatter(gemini))
        self.assertIn('  - "grep_search"', frontmatter(gemini))
        self.assertIn('kind: local', frontmatter(gemini))

        copilot = hosts.render('copilot', role(self.catalog, 'implementer'))['content']
        header = frontmatter(copilot)
        self.assertIn('  - "read"', header)
        self.assertIn('  - "edit"', header)
        self.assertIn('  - "execute"', header)

    def test_copilot_prompt_limit_is_fail_closed(self):
        huge = dict(role(self.catalog, 'reviewer'))
        huge['purpose'] = 'x' * 30001
        with self.assertRaisesRegex(ValueError, 'prompt limit'):
            hosts.render('copilot', huge)

    def test_export_manifest_is_relative_and_drift_checkable(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            result = hosts.write('claude', self.catalog, out)
            self.assertIn('kyper-reviewer.md', result['files'])
            manifest = json.loads((out / hosts.MANIFEST).read_text(encoding='utf-8'))
            self.assertEqual(manifest['host'], 'claude')
            self.assertNotIn(str(out), json.dumps(manifest))
            self.assertNotIn(str(Path.home()), json.dumps(manifest))
            self.assertTrue(manifest['contract_digest'].startswith('sha256:'))
            self.assertTrue(hosts.check('claude', self.catalog, out)['clean'])

            target = out / 'kyper-reviewer.md'
            target.write_bytes(target.read_bytes().replace(b'\n', b'\r\n'))
            self.assertTrue(hosts.check('claude', self.catalog, out)['clean'],
                            'a Git CRLF checkout must not look like semantic drift')

            target.write_text(target.read_text(encoding='utf-8') + 'drift\n',
                              encoding='utf-8')
            drift = hosts.check('claude', self.catalog, out)
            self.assertFalse(drift['clean'])
            self.assertEqual(drift['stale'], [{'path': 'kyper-reviewer.md',
                                              'reason': 'differs'}])

    def test_export_does_not_remove_unrelated_files_or_install_host_config(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            extra = out / 'keep.txt'
            extra.write_text('keep', encoding='utf-8')
            hosts.write('cursor', self.catalog, out, role_ids=['reviewer'])
            self.assertEqual(extra.read_text(encoding='utf-8'), 'keep')
            manifest = json.loads((out / hosts.MANIFEST).read_text(encoding='utf-8'))
            self.assertEqual([item['role'] for item in manifest['roles']], ['reviewer'])
            self.assertNotIn('kyper-explorer.md', manifest['roles'][0]['path'])

    def test_generic_pack_has_no_pretend_host_fields(self):
        card = hosts.render('generic', role(self.catalog, 'integrator'))
        self.assertFalse(card['content'].startswith('---'))
        self.assertIn('# KyperWorkflow role: Integrator', card['content'])
        self.assertEqual(card['fields'], ['body'])

    def test_models_and_turn_limits_are_not_invented(self):
        for host_id in hosts.HOST_IDS:
            if host_id == 'generic':
                continue
            content = hosts.render(host_id, role(self.catalog, 'reviewer'))['content']
            self.assertNotIn('model:', content)
            self.assertNotIn('model =', content)
            self.assertNotIn('maxTurns', content)
            self.assertNotIn('max_turns', content)

    def test_capability_matrix_names_the_limits(self):
        matrix = hosts.capabilities()
        self.assertEqual(set(hosts.HOST_IDS),
                         {entry['id'] for entry in matrix['hosts']})
        by_id = {entry['id']: entry for entry in matrix['hosts']}
        self.assertEqual(by_id['cursor']['read_only'], 'readonly_flag')
        self.assertEqual(by_id['codex']['read_only'], 'instruction_only')
        self.assertEqual(by_id['gemini']['nesting'], 'forbidden')
        self.assertEqual(by_id['copilot']['prompt_limit'], 30000)
        self.assertFalse(by_id['generic']['native_subagents'])


if __name__ == '__main__':
    unittest.main()
