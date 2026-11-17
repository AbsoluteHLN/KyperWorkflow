"""Optional MCP surface. Approval and file writes stay with trusted host actions."""
from mcp.server.fastmcp import FastMCP
from . import __version__, catalog, hosts, onboarding, plan, structure
from .editorial import review
from .workflow import Workflow

app = FastMCP('kyper-workflow')


@app.tool()
def capabilities() -> dict:
    return {'product': 'KyperWorkflow', 'version': __version__,
            'text': 'deterministic diagnostics, project map and review-only candidate comparison',
            'semantic_verification': 'not_configured', 'native': 'not_configured',
            'user_confirmation': 'trusted_host_only', 'stop_installed': False,
            'first_run_setup': 'required_before_planning',
            'project_map': 'deterministic_static_analysis',
            'team_model': 'declarative_roles_and_components',
            'scheduling': 'deterministic_dag_plan_no_auto_start',
            'host_adapters': 'five_native_hosts_plus_generic_prompt_pack',
            'note': ('Call setup_checklist and ask the user to configure the items before '
                     'planning work. role_catalog, workflow_plan and host_adapters are '
                     'read-only.')}


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
def role_catalog(catalog_path: str | None = None) -> dict:
    """Reusable role cards and parameterised task components, fully validated."""
    loaded = catalog.load(catalog_path)
    return {'catalog': loaded, 'digest': catalog.digest(loaded),
            'markdown': catalog.render_markdown(loaded),
            'write_policy': 'Read only. Components render task fields; they never add tasks.'}


@app.tool()
def host_adapters(host: str | None = None, role: str | None = None,
                  catalog_path: str | None = None) -> dict:
    """Host capability matrix and a read-only preview of one projected role card."""
    matrix = hosts.capabilities()
    if host is None:
        return matrix
    entry = hosts.host(host)
    if role is None:
        return {'host': entry, 'matrix': matrix,
                'write_policy': 'Read only. Use the CLI to export files.'}
    loaded = catalog.load(catalog_path)
    card = hosts.render(host, catalog.role(loaded, role))
    return {'host': entry, 'card': card,
            'write_policy': ('Prepared only; no host configuration was modified. '
                             'The CLI export requires an explicit --out directory.')}


@app.tool()
def workflow_plan(state: str, catalog_path: str | None = None) -> dict:
    """Deterministic wave/batch plan for the approved task graph of one state file."""
    workflow = Workflow(state, catalog=catalog.load(catalog_path))
    model = workflow.plan()
    return {'state': workflow.data['state'], 'revision': workflow.data['revision'],
            'plan': model, 'digest': plan.digest(model),
            'markdown': plan.render_markdown(model),
            'runnable': plan.next_runnable(workflow.data['tasks']),
            'limit': 'Scheduling only; it does not start work or confirm completion.'}


@app.tool()
def review_text(text: str, profile: str = 'conversation_summary', candidate: str | None = None) -> dict:
    return review(text, profile, candidate=candidate)


if __name__ == '__main__':
    app.run(transport='stdio')
