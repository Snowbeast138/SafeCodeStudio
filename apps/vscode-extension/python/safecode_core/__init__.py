"""Standalone CST API; graph components are loaded only on request."""
from .cst import CSTService, CSTError

__all__ = ['CSTService', 'CSTError', 'Engine', 'Analysis',
           'IncrementalDirectoryGraphEngine', 'WorkspaceEngine']


def __getattr__(name):
    if name in {'Engine', 'Analysis'}:
        from .engine import Engine, Analysis
        return {'Engine': Engine, 'Analysis': Analysis}[name]
    if name == 'IncrementalDirectoryGraphEngine':
        from .incremental_graph import IncrementalDirectoryGraphEngine
        return IncrementalDirectoryGraphEngine
    if name == 'WorkspaceEngine':
        from .workspace import WorkspaceEngine
        return WorkspaceEngine
    raise AttributeError(name)
