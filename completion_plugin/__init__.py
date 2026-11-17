"""Deprecated import path.

The package is now ``kyper_workflow``. This shim forwards submodule imports to
the real package so an existing ``-m completion_plugin.server`` entry keeps
working; new code and configuration should use ``kyper_workflow``.
"""
import os
import warnings

warnings.warn('completion_plugin is deprecated; import kyper_workflow instead',
              DeprecationWarning, stacklevel=2)

__path__ = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'kyper_workflow')]

# Deployed configuration still launches `-m completion_plugin.server`, and that
# module does `from . import __version__`. __path__ alone forwards submodules but
# not package attributes, so re-export the metadata here as well.
from kyper_workflow import __version__  # noqa: E402,F401
