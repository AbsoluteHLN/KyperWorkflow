"""Optional MCP surface. Approval and file writes stay with trusted host actions."""
from mcp.server.fastmcp import FastMCP
from . import __version__, onboarding, structure
from .editorial import review

app = FastMCP('kyper-workflow')


@app.tool()
def capabilities() -> dict:
    return {'product': 'KyperWorkflow', 'version': __version__,
            'text': 'deterministic diagnostics, project map and review-only candidate comparison',
            'semantic_verification': 'not_configured', 'native': 'not_configured',
            'user_confirmation': 'trusted_host_only', 'stop_installed': False,
            'first_run_setup': 'required_before_planning',
            'project_map': 'deterministic_static_analysis',
            'note': 'Call setup_checklist and ask the user to configure the items before planning work.'}


@app.tool()
def setup_checklist(root: str | None = None, state_dir: str | None = None) -> dict:
    """First-run configuration items to confirm with the user in this session."""
    return onboarding.checklist(root, state_dir=state_dir)


@app.tool()
def project_map(root: str, max_nodes: int | None = None) -> dict:
    """Bounded, deterministic file/import/area graph of a local project."""
    project = structure.scan(root)
    nodes = structure.graph(project, max_nodes=max_nodes)
    return {'name': project['name'], 'files': project['files'], 'edges': project['edges'],
            'graph': {'nodes': nodes['nodes'], 'edges': nodes['edges'],
                      'areas': nodes['areas'], 'stats': nodes['stats']},
            'areas': project['areas'], 'area_edges': project['area_edges'],
            'entry_points': project['entry_points'], 'scripts': project['scripts'],
            'external_imports': project['external_imports'], 'limits': project['limits'],
            'summary': structure.digest(project),
            'graph_document': {'dot': '.kyper/project-graph.dot',
                               'graphml': '.kyper/project-graph.graphml',
                               'edge_list': '.kyper/project-graph.tsv'},
            'limit': 'Static analysis of local files; no runtime or semantic proof.'}


@app.tool()
def project_memory(root: str, doc_path: str = 'docs/PROJECT-MAP.md') -> dict:
    """Digest plus entity/relation payload for a shared-memory MCP server."""
    project = structure.scan(root)
    return {'digest': structure.digest(project),
            'document': structure.render_markdown(project),
            'memory': structure.memory_payload(project, doc_path=doc_path),
            'write_policy': 'Prepared only; the host decides whether to store or upload it.'}


@app.tool()
def review_text(text: str, profile: str = 'conversation_summary', candidate: str | None = None) -> dict:
    return review(text, profile, candidate=candidate)


if __name__ == '__main__':
    app.run(transport='stdio')
