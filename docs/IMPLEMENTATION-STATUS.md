# Implementation status — 2026-11-17

Product renamed to KyperWorkflow 0.2.0: package `kyper_workflow`, CLI `kyper-workflow`, MCP server `kyper-workflow`, Skill `kyper-workflow`. `completion_plugin` remains only as a deprecated import shim. See docs/RENAME-KYPERWORKFLOW.md.

Approved design: spec-v002. This is an implementation increment, not certification of every host.

Implemented and locally exercised:
- Deterministic project relationship graph (`kyper_workflow.structure`): bounded file list, line counts, Python import edges with relative-import resolution, relative Markdown link edges, areas, entry points from `pyproject [project.scripts]`, external imports. One scan feeds four views of the same node/edge graph: map Markdown with an embedded file-level Mermaid graph plus the per-area collapse, JSON, Graphviz DOT, GraphML and a TSV edge list; `--graph --graph-format` prints one view, `--max-nodes` collapses to the highest-degree files, `--check` is the staleness gate for every view, plus a digest and an MCP knowledge-graph entity/relation payload. Generated outputs exclude themselves so regeneration is stable.
- First-run configuration checklist (`kyper_workflow.onboarding`) exposed as the MCP `setup_checklist` tool, covering project root, out-of-project state directory, dependency/library paths, project-test permission, host check providers, sub-agent model routes, budget, shared-memory target and Skill install location. Undetected items stay `needs_user_input`; nothing is defaulted.
- Declarative team model (`kyper_workflow.catalog` + `kyper_workflow.plan`): role cards cap write scopes, allowed checks, code mode, complexity, parallel count and required handoff; parameterised components render `add_task` fields with fail-closed parameters and path normalisation; the planner derives dependency waves, start batches honouring write-scope and role-parallel limits, the critical path and blockers. Role, component and version become part of the approved proposal, role concurrency is enforced on `start()`, and a role task cannot pass without its handoff. Exposed as CLI `roles`/`component`/`plan` and read-only MCP `role_catalog`/`workflow_plan`; host-neutral role cards can be previewed without pretending to be host configuration. No model calls, no spawning, no auto-start.
- Conservative host projections (`kyper_workflow.hosts`): one role catalog rendered for Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot and a generic prompt pack. Names are prefixed `kyper-` to avoid built-in collisions; adapters emit only documented fields, deliberately omit model ids and turn limits, record omissions in a deterministic `.kyper-export.json`, and support canonical-LF `--check`. Export requires a caller-supplied local path and never edits host configuration. Capability matrix and verification limits are in `docs/HOST-ADAPTERS.md`.
- Independent stdlib core, version events, structured phase records, complete approval package, task dependencies/write scopes, explicit checks and current completion recheck.
- Direct byte comparisons with bounded input and invalidated-review latch; syntax and explicit trusted unittest execution.
- Trusted host attestation for text/model/browser/native checks, bound to the current revision and re-confirmed for content freshness; an unattested check stays blocked. Non-source artifacts report `blocked`, not a syntax failure.
- Restart recovery through `runtime.recheck`: passed tasks are re-read and re-checked before `complete()`; the operator `resume` path runs remaining approved tasks in dependency order and refuses to replay an interrupted running task.
- Windows Job Object cleanup tracks member PIDs by synchronize handle before termination, because job accounting and membership clear before the process signals.
- Persistent unknown/actual/estimated usage ledger with conflict detection and attempt IDs; bounded supervision; profile validation/routing and integrated dispatcher leaving generated output pending QA.
- Usage ledger is append-only JSONL with one-time legacy array migration; hard budgets accept a caller-declared unaccounted reserve for attempts without measured cost, and stay fail-closed without one.
- Three-profile writing diagnostics and concrete host-generated candidate workflow, change comparison, independent review seam and revision-bound adoption.
- Operator CLI path with approval/rejection, Skill, optional real local MCP stdio diagnostics.
- DSH native-team/config contract and package entry, with separate mock validation.

Blocked or not exercised:
- The project map links only Python imports and relative Markdown links; other languages are listed with path/line facts but no cross-file edges. It is not a call graph, an ownership map or a correctness proof, and an edit that preserves file size and line count does not change the map.
- No real host-model generation or billing probe: no configured authorized host provider in this environment. Mock usage does not establish real model availability.
- No exported role file has been loaded by all six real hosts. Codex TOML is parsed with `tomllib`; other frontmatter is checked against the documented field shapes, not a vendor schema validator. Host upgrades can change accepted fields.
- DSH official runtime dependency and trusted host integration are absent. Actual plugin panel, native teams, Stop lifecycle and user-install version compatibility are not validated.
- Browser/native-device validation are not connected; requested checks remain not_run/blocked.
- No persistent hook, credential setup or external private upload.

The local interactive entry is intentionally syntax-only. Rich research and model execution use the Skill and explicit host integration. Imported research links are operator records, not a claim that the CLI fetched them. Direct comparison and local event history do not provide adversarial integrity guarantees.

Actual environment probe: correct official DSH schema/team/CLI modules are absent and no DSH runtime process was visible. Read-only registry queries succeeded; published versions differ from master. adapters/dsh/README.md documents compatible-version selection, startup, required trusted integration and remaining real-host tests.
