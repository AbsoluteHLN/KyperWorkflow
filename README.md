# KyperWorkflow 0.2.0

提示词快捷别名：`KalWf`。它只用于在对话中快速唤出，MCP server 注册名仍是 `kyper-workflow`。当前 MCP 契约、8 个只读工具和验收边界见 [docs/MCP-SPEC.md](docs/MCP-SPEC.md)。

中文快速入口：[Codex / Windows 安装与手动测试](docs/INSTALL-CODEX-WINDOWS.md)。旧 MCP 迁移：[说明](docs/MIGRATION-v0.4-to-plugin.md)。

Renamed from CompletionQAMCP / Completion Review Plugin, including the GitHub repository, which is now `https://github.com/AbsoluteHLN/KyperWorkflow.git`; see [rename notes](docs/RENAME-KYPERWORKFLOW.md). The old `completion_plugin` import path still works as a deprecated shim.

Independent private plugin under implementation against approved spec-v002. No cryptographic content identifiers are used. Explicit revisions and direct byte comparisons do not provide tamper protection.

Run without installation:

    python -m kyper_workflow.cli setup --root ./project
    python -m kyper_workflow.cli map --root ./project --write
    python -m kyper_workflow.cli check --root ./project --artifact main.py --revision 1
    python -m kyper_workflow.cli text ./draft.txt --profile academic
    python -m unittest discover -s tests -v

## First-run configuration

An MCP client should call `setup_checklist` at the start of a session and ask the user to confirm the items before planning work: project root, a state directory outside the project, dependency and library paths, whether project tests may run, who supplies text/model/browser/native checks, sub-agent roles with allowed models and effort, whether the host uses native subagents or sequential execution, the budget, the optional shared-memory target, and where the Skill is installed. Unconfirmed items keep their tasks blocked; nothing is defaulted on the user's behalf. See [docs/FIRST-RUN-SETUP.md](docs/FIRST-RUN-SETUP.md).

## Project map

`map` builds a deterministic relationship graph from local files: one node per file, one directed edge per observed Python import or relative document link, grouped into areas with entry points marked. It writes the map document `docs/PROJECT-MAP.md` and four graph views that all describe the same nodes and edges:

- `docs/PROJECT-MAP.md` — embedded file-level Mermaid graph plus the same graph collapsed per area, with per-file tables
- `.kyper/project-map.json` — full node, edge, area and symbol data
- `.kyper/project-graph.dot` — Graphviz, clustered by area
- `.kyper/project-graph.graphml` — GraphML 1.0 for Gephi, yEd or networkx
- `.kyper/project-graph.tsv` — tab-separated edge list

`--check` exits non-zero when any committed view is stale. `--graph --graph-format json|mermaid|dot|graphml|tsv` prints one view, and `--max-nodes N` collapses a large graph to the N highest-degree files while keeping both endpoints of every shown edge. `--memory` additionally returns an entity/relation payload in the common MCP knowledge-graph shape, and `project_memory` exposes the same graph through MCP. Preparing the payload is not storing or uploading it: the host decides, and no file is written by an MCP call.

Static analysis only: the map records observed imports and document links. It is not a runtime call graph, not ownership metadata, and not proof that a dependency is used correctly.

This repository's own map: [docs/PROJECT-MAP.md](docs/PROJECT-MAP.md).

The Skill in skills/kyper-workflow guides the two-stage planning flow. The Python modules supply state, bounded local checks, configurable profile validation and accounting contracts. Host adapters report their own capability limits. A Skill alone cannot enforce host completion.

Trusted host confirmation is injected by application code; no command accepts a model-supplied approval boolean. Real providers, actual host Stop installation, browser and native-device checks are not connected by default. Configuration and synthetic tests do not establish real backend availability.

No secrets are stored in profiles. Local state and host callbacks are trusted. Review directories must be trusted and preferably exclusive/read-only while checked. Direct comparisons are observations, not adversarial security protection.

This private repository publishes the independent plugin source. Persistent host installation and native Windows acceptance have not been verified.

## Team roles and reusable components

Tasks can be bound to a declarative role card that caps what they may touch: `explorer` and `reviewer` are read-only, `test-author` may only write `tests/**`, `implementer` may write source, `integrator` may write docs. Binding is checked before the task enters the specification, so a role can only narrow a task, never widen it. `role`, `component` and `component_version` are part of the approved proposal, so changing them requires re-approval.

Components are parameterised task templates (`code-change`, `test-covered-change`, `test-only`, `doc-sync`, `review-only`, `investigation`). They render `add_task` fields and never add, remove or approve a task themselves. Paths are normalised and rejected if absolute or escaping the workspace.

`kyper-workflow plan --state <file>` (MCP `workflow_plan`) turns the approved graph into dependency waves, start batches that respect write-scope and role-parallel limits, the critical path and the blocker list. `kyper-workflow roles` (MCP `role_catalog`) prints the cards.

`kyper-workflow export --host <claude|cursor|codex|gemini|copilot|generic> --out <局部路径>` projects the same cards for one host. `--list-hosts` shows the capability matrix; `--check` detects drift; `--role` limits the export. Names are prefixed `kyper-` so they cannot override built-in agents. Only Cursor's `readonly` is close to a read-only switch; every host's path scope is still a contract, not a sandbox. No model ids or turn limits are invented, and nothing is installed automatically. See [docs/HOST-ADAPTERS.md](docs/HOST-ADAPTERS.md) and [docs/AGENT-TEAMS.md](docs/AGENT-TEAMS.md).

## Interactive terminal path

    python -m kyper_workflow.cli wizard --root /project --state /private/task-state.json --artifact main.py

This asks for key goals, official research sources or an explicit research waiver, direction choice, and approval of the complete versioned task package. It only runs syntax validation. Piped approval is rejected; cancellation executes no project check. Terminal access is a trusted operator boundary, not a way to authenticate a human against malicious local software. The Skill uses host research and richer task planning; the wizard does not claim to browse supplied URLs.

## Model-assisted polishing

kyper_workflow.polishing exposes the authorized host-model workflow for all three writing profiles. Missing host means blocked. Generated candidates and exact edit comparisons are returned; optional independent semantic review is separately labeled. Adoption is bound to document revision and current content. No external provider was contacted in validation; mock results are explicitly identified.

## Operational limits

Local state/usage locks now use native POSIX or Windows byte-range locking. Windows project checks use suspended process creation and a Job Object for bounded process-tree cleanup; native Windows runs pass locally, but each host still needs its own trial. See docs/WINDOWS-RUNNER.md. Restored successful task results cannot authorize a new completion without reconnecting current verifiers. DSH has a packable adapter but its trusted completionQAHost integration and official Schemastery runtime are not present here, so actual DSH loading, native-team calls and Stop behavior are unverified. Do not interpret mock tests or package creation as real-host installation.

## Host checks and restart recovery

A task declaring text, model, browser or native checks cannot pass on local code inspection alone: trusted host code must call `Review.attest(check, status=..., detail=..., revision=...)`, and a missing attestation stays blocked rather than becoming a pass. Attestations die with the specification revision and are re-confirmed for content freshness at gate time.

`runtime.recheck(workflow, ...)` re-establishes current verifiers after a process restart by re-reading every passed task's recorded inputs and re-running its declared checks; `Workflow.complete()` still refuses to finish without them. The operator `resume` command runs any remaining approved tasks in dependency order and refuses to replay a task that was interrupted while running.

To resume a cancelled final proposal without deleting state:

    python -m kyper_workflow.cli resume --state /private/task-state.json

The exact saved package is shown again. Interrupted running tasks are not blindly replayed. The wizard identifies source links as user-supplied/unverified and asks for explicit acknowledgement of that research limitation.

Save or inspect validated profile configuration without writing application code:

    python -m kyper_workflow.cli profiles --store /private/profiles.json --import-file ./profiles.json
    python -m kyper_workflow.cli profiles --store /private/profiles.json

This establishes schema validity only. Actual host capability, model discovery, authorized smoke and current recheck still require a configured trusted host. No API secret is requested or stored. Use a state/usage location outside the reviewed repository for project-test checks so bookkeeping does not invalidate the reviewed content.
