# 多宿主角色适配（KyperWorkflow）

2026-11-17 核对。目标不是为每个 coding agent 维护一份会漂移的角色表，而是：

1. `kyper_workflow.catalog` 里的角色与组件是唯一事实源；
2. `kyper_workflow.hosts` 只做**保守投影**，把角色渲染成宿主官方文档承认的字段；
3. 投影结果带清单与哈希，可 `--check`；
4. 导出只写调用方显式给出的目录，不自动改任何宿主配置。

一句话：**角色契约是主语，宿主文件是投影；投影失败可以重做，契约不能悄悄变宽。**

## 能力矩阵

“只读”列描述宿主实际能执行的手段，不是我们的愿望。

| 宿主 | 原生子智能体 | 文件位置 | 格式 | 只读约束 | 工具过滤 | 模型选择 | 嵌套 | 正文上限 |
|---|---|---|---|---|---|---|---|---|
| Claude Code | 是 | `.claude/agents/` | Markdown + YAML | 工具白名单可去掉写工具 | 白名单/黑名单 | 支持，本适配器省略 | 宿主策略 | 无公开硬上限 |
| Cursor | 是 | `.cursor/agents/` | Markdown + YAML | `readonly: true` 禁止编辑和改状态 shell | 无 | 支持，本适配器省略 | 一层 | 无公开硬上限 |
| Codex | 是 | `.codex/agents/` | 独立 TOML | **仅指令**；继承父会话沙箱 | 仅少量 `features.*` | 支持，本适配器省略 | 宿主策略 | 无公开硬上限 |
| Gemini CLI | 是 | `.gemini/agents/` | Markdown + YAML | 只读角色可给部分工具白名单 | 白名单 | 支持，本适配器省略 | **禁止** | 无公开硬上限 |
| GitHub Copilot | 是 | `.github/agents/` | `.agent.md` + YAML | 只读角色可给部分工具别名 | 白名单 | 支持，本适配器省略 | 未断言 | 30,000 字符 |
| 通用提示包 | 否 | 调用方指定 | Markdown | 无 | 无 | 无 | 父代理策略 | 无 |

### 关键结论

- **只有 Cursor 的 `readonly` 接近“只读开关”**，但它仍不限制具体路径。
- Claude、Gemini、Copilot 能过滤工具，但“只能写 `tests/**`”仍是角色契约，不是文件系统沙箱。
- Codex 的自定义代理继承父会话权限，单独文件**不会**创建只读沙箱；把 `features.shell_tool = false` 当成完整只读是错误理解。
- `max_parallel` 是计划层的并发上限，不是宿主的 `maxTurns`、`timeout_mins` 或线程数。适配器故意不映射它。
- 角色卡默认是**叶子工人**：不授予 Claude 的 `Agent`、Copilot 的 `agent`，也不鼓励 Cursor 再嵌套。主代理负责拆任务和汇总。

## 各宿主投影

### Claude Code

- 官方字段：`name`、`description`、`tools`、`disallowedTools`、`model`、`permissionMode`、`maxTurns`、`skills`、`mcpServers`、`hooks`、`memory`、`background`、`omitClaudeMd`、`effort`、`isolation` 等。
- 本适配器发出：`name`、`description`、`tools`。
- 故意省略：`model`（避免编造模型）、`permissionMode`（避免把计划模式误当只读）、`maxTurns`（并发不等于轮数）。
- 只读角色使用 `Read, Grep, Glob, Skill, mcp__kyper-workflow__*`；写角色额外得到 `Edit, Write, Bash, PowerShell`。
- 路径范围仍由任务批准和写入前校验负责，Claude 的工具白名单不检查路径。

来源：[Create custom subagents](https://code.claude.com/docs/en/sub-agents)

### Cursor

- 官方字段：`name`、`description`、`model`、`readonly`、`is_background`。
- 本适配器发出：`name`、`description`、`readonly`。
- 故意省略：`model`（默认继承更安全）、`is_background`（是否后台属于调度决策，不是角色能力）。
- 写范围为空 ⇒ `readonly: true`；有写范围 ⇒ `readonly: false`。
- Cursor 也读取 `.claude/agents` 和 `.codex/agents` 的兼容位置，但本项目只导出到 `.cursor/agents`，避免“同名谁优先”的隐式行为。

来源：[Subagents](https://cursor.com/docs/subagents)

### Codex

- 官方字段：`name`、`description`、`developer_instructions` 必填；可选 `model`、`model_reasoning_effort`、`model_reasoning_summary`、`model_verbosity`，以及 `features.shell_tool`、`features.apps`、`features.plugins`、`features.memories`、`features.request_permissions_tool` 等降权键。
- 本适配器发出：`name`、`description`、`developer_instructions`；只读/文档角色再加 `features.shell_tool = false` 和 `features.request_permissions_tool = false`。
- 故意省略：所有模型字段、`sandbox_mode`、`approval_policy`、`mcp_servers`。Codex 文档明确这些由父会话决定，自定义代理文件不能覆盖。
- 输出用标准库 `tomllib` 解析验证；这是真实 TOML 校验，不是字符串看起来像。

来源：[Subagents](https://learn.chatgpt.com/codex/agent-configuration/subagents)

### Gemini CLI

- 官方字段：`name`、`description`、`kind`、`tools`、`mcpServers`、`model`、`temperature`、`max_turns`、`timeout_mins`。
- 本适配器发出：`name`、`description`、`kind: local`、`tools`。
- 故意省略：`model`、`temperature`、`max_turns`、`timeout_mins`；这些属于用户路由与运行预算，不是角色字段。
- 只读角色发出 `read_file`、`grep_search`；写角色发出 `*`，因为按路径限制不是 Gemini 的能力。
- Gemini 子智能体**不能**再调用子智能体，这一点被明确写进能力矩阵。
- 注意：Google 已公告 Gemini CLI 对部分个人用户由 Antigravity CLI 接替；适配文件仍按 Gemini CLI 的官方 schema 生成。

来源：[Subagents](https://geminicli.com/docs/core/subagents/)

### GitHub Copilot

- 官方字段：`name`、`description`（必填）、`target`、`tools`、`model`、`disable-model-invocation`、`user-invocable`、`mcp-servers`、`metadata`。
- 本适配器发出：`name`、`description`、`tools`。
- 故意省略：`target`（默认两地都可用）、`model`、`mcp-servers`（MCP 应配置在仓库/会话层，而不是复制密钥或机器路径进角色文件）。
- 使用官方工具别名：`read`、`search`、`edit`、`execute`、`todo`；并允许 `kyper-workflow/*` 读取本项目 MCP。
- 正文超过 30,000 字符时直接报错，不生成一个宿主会截断或拒绝的文件。

来源：[Custom agents configuration](https://docs.github.com/en/copilot/reference/custom-agents-configuration)

### 通用提示包

没有原生角色文件的主持，使用 `--host generic` 导出 `kyper-roles/kyper-<role>.md`。它没有 frontmatter，不会被误认为某个宿主的原生代理；主代理一次执行一个角色与一个已批准任务，计划仍然有效。

## 命名与防冲突

所有导出名都加 `kyper-` 前缀：

- `kyper-explorer` 而不是 `explorer`；
- `kyper-reviewer` 而不是 `reviewer`；
- 文件名分别为 `kyper-explorer.md`、`kyper-explorer.toml`、`kyper-explorer.agent.md`。

原因很具体：Codex 的自定义代理若与内置 `explorer` 同名，会覆盖内置代理；Cursor、Claude 和 Copilot 也可能出现同名优先级问题。加前缀比依赖宿主的冲突规则可靠。

## 导出与漂移检查

```powershell
kyper-workflow export --list-hosts
kyper-workflow export --host claude --out .claude/agents
kyper-workflow export --host codex --out .codex/agents --role explorer --role reviewer
kyper-workflow export --host cursor --out <局部路径> --check
```

- `--out` 必须显式给出；没有默认安装位置。
- 不加 `--role` 时导出全部角色；加多个 `--role` 时只导出指定角色。
- `--check` 只读取，不写入；任一文件缺失，或在 CRLF→LF 规范化后内容不同，就返回 1。
- 每个目录写 `.kyper-export.json`：记录宿主、契约摘要、每个角色的字段、故意省略的字段和文件 SHA-256。
- 清单不记录输出目录的绝对路径，也不记录时间戳，因此可提交、可比较。
- 写入使用固定 LF 和 UTF-8；`--check` 接受 Git 在 Windows 检出的 CRLF，但不会忽略其他差异。

`--check` 在未显式给 `--role` 时会读取清单中的角色子集，所以“只导出 reviewer”也能被正确检查，不会要求补齐其他四个角色。

## 运行模式

### 原生子智能体模式

主代理是协调者，负责：

1. 取得用户批准的任务规格；
2. 从 `role_catalog` 选角色；
3. 把任务、验收标准、相关路径和交接格式写进委派提示；
4. 接收子代理的结构化交接；
5. 按 `workflow_plan` 的批次和冲突结果决定是否真的并行。

角色卡不依赖父会话历史；宿主通常只把角色提示和委派提示交给子代理。缺少任务上下文时，正确行为是 `blocked`，不是自行补全。

### 顺序执行模式

不支持原生角色文件的宿主，把同一张卡交给主代理，一次只执行一个任务。角色契约、组件参数、检查种类和交接键都不变，只是没有上下文隔离与并行收益。

### 混合模式

只读探索、独立复核可以交给原生子代理；写源码仍由主代理串行完成。不要因为宿主“能并行”就把两个写同一目录的任务同时启动。

## 为什么不做自动安装

- 各宿主的用户级目录、项目级目录和优先级不同；
- 同名文件可能覆盖用户已有角色；
- MCP、模型和权限属于机器级配置，不能由角色导出器替用户决定；
- 自动写入后很难判断“这是 KyperWorkflow 生成的，还是用户改过的”。

所以导出是显式动作，清单是来源证明，`--check` 是升级后的差异检查。首次接入仍由 `setup_checklist` 询问宿主、执行方式、模型路由和导出目录。

## 验证边界

已验证：

- 六种宿主 × 五个内置角色重复渲染字节一致；
- Codex 输出用 `tomllib` 成功解析；
- Claude/Gemini/Copilot frontmatter 的字段名、工具名和只读差异有测试；
- Cursor `readonly` 对只读/写角色分别为 `true`/`false`；
- Copilot 超长正文 fail-closed；
- 清单不含输出绝对路径或用户主目录，`--check` 能发现缺失和规范化后的内容漂移；
- 导出不删除无关文件，也不修改宿主配置。

未验证：

- 没有把角色卡实际加载进六个真实宿主并观察委派行为；
- frontmatter 只按官方字段形状验证，没有调用各宿主的私有 schema 校验器；
- 宿主升级后字段可能变化，应以各自的官方文档和真机试跑为准。

因此，这里证明的是**生成器与契约的一致性**，不是每个宿主的运行时行为。
