# Current validation

2026-10-19 UTC; independent plugin 0.1.0, approved design spec-v002.

## 2026-11-17 multi-host role projections

`python -m unittest discover -s tests`: 263 discovered, 257 passed, 6 skipped, 0 failures
and 0 errors on the development interpreter; 263 / 259 / 4 on the shared interpreter with the
optional `mcp` extra, which exercises the real stdio transport against the eight-tool surface.
The 13 JavaScript adapter tests pass. `map --check` passes on the refreshed map: 84 files and
97 internal edges.

Added exercises:

- six host projections (Claude Code, Cursor, Codex, Gemini CLI, GitHub Copilot and a generic
  prompt pack) render all five roles deterministically with `kyper-` namespaced names;
- Codex TOML is parsed with `tomllib`; Claude/Gemini/Copilot frontmatter has the documented
  field names and real tool names; Cursor `readonly` is `true` only for roles with no write
  scopes;
- model ids, `maxTurns`/`max_turns` and other invented host controls are absent; the capability
  matrix records `instruction_only` for Codex and `readonly_flag` for Cursor;
- Copilot's 30,000-character prompt limit is fail-closed; the export manifest is relative,
  hash-based, written with LF, accepts a CRLF checkout, and `--check` detects missing and
  changed files, including a partial export whose role subset comes from the manifest;
- export leaves unrelated files alone and never edits host configuration.
- configuration placeholders (`待配置`, `局部路径`, `<...>`) stay `needs_user_input` even when
  they occupy path fields or nested route records; the shipped example contains no machine path.
- `PROMPT_ALIAS` is `KalWf`; `capabilities()` exposes it with `alias_scope: prompt_shortcut_only`;
  the Skill copy test requires the alias in both distributable and project copies.

Not exercised: no exported file was loaded by all six real hosts. Frontmatter was checked
against official field shapes, not a vendor schema validator. Codex parsing is a real TOML
parse; this does not prove that a particular Codex release accepts every feature flag.

## 2026-11-17 KyperWorkflow 0.2.0 (rename + project map + first-run setup)

### 2026-11-17 roles, components and execution plan (same batch)

`python -m unittest discover -s tests`: 247 discovered, 241 passed, 6 skipped, 0 failures
and 0 errors on the development interpreter; 247 / 243 / 4 on the shared interpreter with the
optional `mcp` extra, which also exercises the real stdio transport against the seven-tool
surface. The 13 JavaScript adapter tests still pass.

Added exercises:

- role cards validate their own fields, and binding rejects out-of-scope writes, disallowed
  checks, a disallowed code mode and a disallowed complexity — read-only roles cannot take any
  write at all;
- every builtin component instantiates from explicit parameters, renders an acceptance sentence
  with no placeholder left, normalises backslash paths, and rejects unknown, missing or unsafe
  parameters including drive-letter and `..` paths;
- the planner produces dependency waves, packs start batches around write-scope conflicts and
  role-parallel limits, names the critical path, reports blockers, and refuses cycles or unknown
  dependencies; `next_runnable` never offers a task whose writes collide with a running one;
- the workflow stores `role`, `component` and `component_version` inside the approved proposal,
  enforces `max_parallel` on `start()`, requires the role's handoff keys before a `pass`, and
  still reloads a state file written by the previous schema;
- CLI `roles`, `component` and `plan` were run by hand against a generated state; `roles
  --export reviewer` emits a Markdown + frontmatter subagent card.

Not exercised: no role was given to a real subagent and no host was asked to run two batches in
parallel. The plan says what may overlap; it does not prove a host isolates concurrent writes.

### 2026-11-17 machine-local config isolation + MCP reinstall (same batch)

`python -m unittest discover -s tests`: 214 discovered, 208 passed, 6 skipped, 0 failures
and 0 errors on the development interpreter, and 214 / 210 / 4 on the shared interpreter that
has the optional `mcp` extra. The 13 JavaScript adapter tests still pass.

Committed and generated files no longer carry the operator's disk layout: `render_json` drops
the resolved absolute `root`, so the map document and all four graph exports contain repository
relative paths only. `tests/test_repo_hygiene.py` enforces this against the working tree
(drive-letter paths with a boundary so `http://` is not a false positive, the home directory,
the checkout path), asserts `.kyper/setup.local.json` stays ignored, and asserts the
placeholder-only `docs/setup.local.example.json` ships. The onboarding checklist now reads
answers from `KYPER_SETUP_CONFIG`, `~/.kyper/setup.local.json` or
`<root>/.kyper/setup.local.json`, reports the file it read, and treats a malformed file as
still-unconfirmed rather than as configuration. Onboarding tests patch `Path.home` and the
environment variable so they cannot read the developer's own config.

Reinstalling the deployed MCP exposed a rename regression: `completion_plugin.server` does
`from . import __version__`, which `__path__` forwarding does not provide, so the pre-rename
launch command failed with `ImportError`. `completion_plugin/__init__.py` now re-exports
`__version__`; `tests/test_rename_shim.py` covers both the attribute and importing the server
through the old path. After the fix, `-m completion_plugin.server` and
`-m kyper_workflow.server` both report `serverInfo.name = kyper-workflow` over stdio, and both
interpreters run the suite green. A host gateway in front of the server kept serving a cached
two-tool `tools/list` until its client reconnected, so that path needs a reconnect after
upgrades; direct stdio listing shows all five tools.

### 2026-11-17 graph views (same batch)

`python -m unittest discover -s tests`: 204 discovered, 199 passed, 5 skipped, 0 failures
and 0 errors. The 13 JavaScript adapter tests still pass. `kyper-workflow map --root .
--name KyperWorkflow --check` exits 0 on the committed map and exports, and exits 1 after
a structural change or after tampering with `.kyper/project-graph.tsv`.

Exported files were checked outside the suite as well: `dot -Tsvg` renders
`.kyper/project-graph.dot` without warnings, and the GraphML parses with one `node` and one
`edge` element per graph element and no dangling edge endpoint. Mermaid ids are prefixed so a
directory named `end` or `graph` cannot emit a reserved keyword as a node id.

The map is now a node/edge relationship graph with four deterministic views over one scan:
embedded file-level Mermaid (grouped by area, entry points marked), `.kyper/project-map.json`,
`.kyper/project-graph.dot`, `.kyper/project-graph.graphml` and `.kyper/project-graph.tsv`.
This repository renders 71 files / 66 internal edges; the embedded Mermaid view shows the
40 highest-degree files and states how many nodes it omitted. Added exercises: node ids equal
file paths, collapsed graphs keep both endpoints of every shown edge, colours depend only on
sorted area order, repeated renders are byte-identical, GraphML parses as XML with one node
and one edge element per graph element, and `--check` covers every export.

The GitHub repository is now `AbsoluteHLN/KyperWorkflow`; `origin` was repointed and the
clone instructions updated. The old URL is redirected by GitHub. Renaming the repository does
not publish anything: no source commit, tag or release was pushed, and the installed MCP
still runs the 0.1.2 package until it is reinstalled from this tree.

Same host (Windows 11, Python 3.13.5). `python -m unittest discover -s tests`:
196 discovered, 191 passed, 5 skipped, 0 failures and 0 errors. The 13 JavaScript
adapter tests still pass. `kyper-workflow map --root . --check` passes on the
committed map and returns 1 after a structural change.

New exercises: import/doc-link edge extraction, area and entry-point detection,
determinism of the rendered map, exclusion of generated output, file-limit
fail-closed behaviour, memory-payload shape, and the first-run checklist
(required items present, no item reported ready without user input, platform
reporting for project tests). Rename coverage: the `completion_plugin` shim still
imports, and the DSH adapter exports `kyperworkflow`.

Not exercised: no real host model, browser or native-device checks were run; the
project map is static analysis and makes no runtime claim.

## 2026-11-17 native Windows run

Windows 11, Python 3.13.5, `python -m unittest discover -s tests`: 177 discovered,
172 passed, 5 skipped, 0 failures and 0 errors. Skips were the off-platform
contract check, two cases needing symbolic-link privilege, the optional `mcp`
extra, and one POSIX-only PTY case. Native Windows runner tests passed six
consecutive runs after the descendant-cleanup fix.

New exercises in this run: host-attested text checks (pass, missing attestation,
stale revision, post-attestation edit), restart `recheck` then `complete`,
multi-task `resume`, append-only ledger with legacy array migration, and
unaccounted-reserve budget arithmetic.

2026-10-19 aggregate (superseded by the native Windows run above): 147 Python unittest methods passed; 13 JavaScript tests passed. These counts cover this new code, not legacy v0.8 tests. Independent workflow audit contributes 38 methods within that aggregate, not an extra additive count.

Actual local processes tested: Python syntax checks, temporary trusted unittest subprocesses, real MCP stdio initialize/list/call, real PTY wizard acceptance and cancellation. PTY input is a synthetic operator fixture, not an actual user's approval record.

Simulated backends: host model generation/independent prose review, profile model discovery/smoke, DSH Config/native-team contracts. They do not prove actual provider access, billing, native agent availability, DSH loading or real Stop behavior.

Important regression fixes include stale successful task results after revision, write-scope aliases, malformed restored state, generator dependency/check omissions, mutable result leakage, undetected concurrent writer overwrite, deleted-state recreation, nonfinite usage, stale evidence resurrection, changed project dependencies after test execution, syntax overwriting failed real tests, omitted required text checks and completion after file changes.

Publication/install not performed. Source package excludes transfer helpers and earlier product archives. Source scan found no retained content-fingerprint algorithm or legacy receipt fields in runtime code.

Final user-workflow review additionally verified approval-mode matching, non-boolean opt-in rejection, explicit unverified-source acknowledgement, and cancel/resume over real local PTY fixtures. No remaining blocking issue was reported in that review.

DSH integration example syntax and local action-store restart/writer exclusion/return isolation passed. npm pack with a temporary cache succeeded after its default cache path was unavailable; six package files were included. No runtime dependency was installed.
