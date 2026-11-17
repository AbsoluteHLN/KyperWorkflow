"""The pre-rename import path keeps working while pointing at the new package."""
import unittest
import warnings
from pathlib import Path

try:
    import mcp  # Optional [mcp] extra; a skip is not evidence the server runs.
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


class RenameShimTests(unittest.TestCase):
    def test_deprecated_package_forwards_to_kyper_workflow(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            import completion_plugin
        self.assertEqual(Path(completion_plugin.__path__[0]).name, 'kyper_workflow')

    def test_deprecated_submodule_import_still_works(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            from completion_plugin.workflow import Workflow
            from completion_plugin.structure import scan
        self.assertEqual(Workflow.__name__, 'Workflow')
        self.assertTrue(callable(scan))

    def test_package_metadata_is_visible_through_the_shim(self):
        """Deployed config launches `-m completion_plugin.server`, whose module
        body does `from . import __version__`; __path__ alone does not forward
        package attributes, so a missing re-export breaks the old entry point."""
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            import completion_plugin
            import kyper_workflow
        self.assertEqual(completion_plugin.__version__, kyper_workflow.__version__)
        self.assertEqual(completion_plugin.PROMPT_ALIAS, kyper_workflow.PROMPT_ALIAS)

    @unittest.skipUnless(MCP_AVAILABLE, 'optional mcp extra is not installed')
    def test_deprecated_server_module_imports(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            from completion_plugin import server
        self.assertTrue(hasattr(server, 'review_text'))


if __name__ == '__main__':
    unittest.main()
