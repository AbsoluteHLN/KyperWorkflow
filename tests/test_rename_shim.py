"""The pre-rename import path keeps working while pointing at the new package."""
import unittest
import warnings
from pathlib import Path


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


if __name__ == '__main__':
    unittest.main()
