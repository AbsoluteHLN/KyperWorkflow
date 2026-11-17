# 角色、组件与执行计划（KyperWorkflow）

这一层解决三个问题：谁来做、用哪个可复用模板、哪些任务能同时跑。全部是**声明式数据 + 确定性校验**，不调用模型、不创建进程、不写文件。

## 为什么不是“自动组队”

业界常见做法是让编排器自己决定角色和分工（能力注册表 + DAG + 拓扑排序）。KyperWorkflow 只吸收其中的**结构性部分**，不吸收“模型自己决定授权”的部分：

- 角色是用户可见的卡片，写清楚允许写哪些路径、允许哪些检查、并发上限、必须交回什么。
- 任务是用户批准过的原子规格，角色绑定只是给任务加一层**收缩**约束，不能扩大权限。
- 计划只回答“能否并行”，不替用户启动任务，也不把“排好了”当成“做完了”。

所以这里的“团队”是一份可审计的契约，而不是一个会自己生长的编排器。

## 角色卡（roles）

内置五个角色，语义刻意收窄：

| 角色 | 可写 | 检查 | 并发 | 必须交接 |
|---|---|---|---|---|
| `explorer` | 无 | text | 3 | `findings` |
| `implementer` | 任意 | code | 2 | `changed` |
| `test-author` | `tests/**` | code (project_tests) | 2 | `tests` |
| `reviewer` | 无 | text, model | 3 | `findings`, `verdict` |
| `integrator` | `docs/**`, `README.md`, `*.md` | text | 1 | `summary` |

绑定时逐项校验，任一条不满足就拒绝，并指出是哪一条：

- 任务声明的检查必须是角色允许的子集；
- `code` 检查的 `code_mode` 必须在角色允许的模式内；
- 任务复杂度必须在角色允许的档位内；
- 每个写入路径必须落在角色的某个 scope 模式里（`**`、`tests/**`、`*.md` 或精确路径）。

`reviewer` 与 `explorer` 的 scope 为空，所以任何写入都会被拒——只读角色不可能“顺手改一下”。

角色随审批一起冻结：`role` 存在任务里，进入 `_proposal()`，改角色等同于改规格，需要重新批准。

## 组件（components）

组件是参数化的任务模板，只渲染 `add_task` 的字段，不会自己新增任务：

| 组件 | 角色 | 参数 | 产出 |
|---|---|---|---|
| `code-change` | implementer | `behaviour`, `paths` | 单文件/多文件的语法级改动 |
| `test-covered-change` | implementer | `behaviour`, `paths`, `tests` | 需要项目测试通过的改动 |
| `doc-sync` | integrator | `topic`, `docs` | 文档与现状对齐 |
| `test-only` | test-author | `tests`, `covers` | 只动测试 |
| `review-only` | reviewer | `target`, `aspects` | 独立只读复核 |
| `investigation` | explorer | `question` | 只读调查 |

规则：

- 参数要么显式给出，要么报错；`required` 缺失就拒绝，不套默认值。
- 路径参数统一规范化，拒绝绝对路径、`..`、盘符路径和反斜杠。
- 组件版本记录进任务（`component_version`），便于以后判断规格是用哪版模板生成的。
- 组件渲染出的角色与 scope 会立刻自检一次，所以预览不会出现“能生成但 `add_task` 会拒”的字段。

## 执行计划（plan）

`Workflow.plan()` / `kyper-workflow plan --state <file>` / MCP `workflow_plan` 输出：

- **waves**：按依赖深度分层，同层任务互不依赖；
- **batches**：真正可以同时启动的分组，额外考虑写入范围冲突与角色并发上限；
- **critical_path**：最长依赖链，用来判断缩短哪一段才有意义；
- **conflicts**：同层中写入范围重叠的任务对，必须串行；
- **blocked**：上游失败导致无法开始的任务，以及原因。

同层不等于能并行：两个任务都写 `src/` 时会被拆进不同 batch 并列入 conflicts；三个 `implementer` 任务会按 `max_parallel=2` 拆成两批。

## 多宿主投影

同一张角色卡可以投到 Claude Code、Cursor、Codex、Gemini CLI、GitHub Copilot 和通用提示包。`kyper_workflow.hosts` 只发出各宿主官方文档承认的字段，并明确记录省略项：

- 名称统一加 `kyper-` 前缀，避免覆盖宿主内置 `explorer` 等角色；
- 不注入模型 id，模型路由仍由首次接入配置决定；
- `max_parallel` 不映射为 `maxTurns`/`timeout`，并发是计划层概念；
- 只有 Cursor 的 `readonly` 接近只读开关；其余宿主的路径范围仍是契约，不是沙箱；
- 角色默认是叶子工人，不授予再生成子代理的工具；
- 导出只写调用方显式给出的目录，并附 `.kyper-export.json` 供 `--check` 检查漂移。

完整能力矩阵、各宿主字段与验证边界见 [HOST-ADAPTERS.md](HOST-ADAPTERS.md)。

## 与现有生态的对应关系

- **原生子智能体宿主**：把角色卡当作可复用工人定义；主代理负责委派任务、验收和汇总，子代理不接管审批。
- **无原生子智能体的宿主**：使用 `generic` 提示包，一次执行一个角色与一个任务；组件和计划仍然有效。
- **Agent Skills**：`SKILL.md` 是流程级能力包；角色卡是任务级契约；两者互补，Skill 不能替代宿主的权限系统。
- **能力注册表 / DAG 编排**：本模块取拓扑排序与能力约束，不取“编排器自行扩权”。

## 边界

- 计划是静态推演，不感知真实运行状态、机器负载或模型差异；`next_runnable` 只依据状态文件里的 `status`。
- 角色约束防的是**误扩大范围**，不是恶意绕过；信任边界仍是本地状态与调用方。
- 没有安装任何宿主 hook、没有创建子智能体、没有调用模型。宿主若真的并行执行，仍需自己落实写入隔离。
