# Current validation

2026-10-19 UTC; independent plugin 0.1.0, approved design spec-v002.

## 2026-11-17 KyperWorkflow 0.2.0 (rename + project map + first-run setup)

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
